"""Autonomy Budgets — per-agent caps owned by Jules (Ops Manager).

Each persona ships with an `autonomy_budget` dict:
  {max_tokens_per_week, max_usd_per_week, max_irreversible_per_week}

This module:
  • Persists per-week usage in `agent_usage_ledger` (ISO week granularity).
  • Exposes `record_usage()` + `check_budget()` helpers for other modules.
  • Powers the auto-approve gate in routes/briefs.py — when an agent is
    well under cap AND the operator opted in, autopilot briefs spawn
    campaigns directly (skip HITL).

Irreversible actions = anything that creates user-visible side effects
that can't be undone for free (auto-approving a brief, publishing a post,
sending an email). Tokens + USD are recorded for visibility but don't
gate side effects on their own.

Resetting a week is automatic — the ledger key is `(agent_id, user_id,
iso_week)`, so each Monday starts from zero by virtue of the new key.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from routes.agent_personas import PERSONAS

logger = logging.getLogger(__name__)


def _iso_week_key(when: Optional[datetime] = None) -> str:
    """Returns 'YYYY-Www' (e.g. '2026-W22') — the ledger partition key."""
    dt = when or datetime.now(timezone.utc)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _personas_by_id() -> dict[str, dict]:
    return {p["id"]: p for p in PERSONAS}


# ---------------------------------------------------------------------
# Public helpers — called from briefs / standups / marketing_os
# ---------------------------------------------------------------------
async def record_usage(
    agent_id: str,
    user_id: str,
    *,
    tokens: int = 0,
    usd: float = 0.0,
    irreversible: int = 0,
) -> dict:
    """Atomic upsert of the ledger row for this week. Safe to call from
    any path — errors are logged but never raised so a ledger hiccup
    doesn't break the calling agent."""
    if agent_id not in _personas_by_id():
        logger.warning("record_usage: unknown agent_id=%s — skipping", agent_id)
        return {}
    try:
        now = datetime.now(timezone.utc)
        key = {"agent_id": agent_id, "user_id": user_id, "iso_week": _iso_week_key(now)}
        await db.agent_usage_ledger.update_one(
            key,
            {
                "$inc": {
                    "tokens":             max(0, int(tokens)),
                    "usd":                max(0.0, float(usd)),
                    "irreversible_count": max(0, int(irreversible)),
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "id":         uuid.uuid4().hex,
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except Exception:
        logger.exception("record_usage failed for agent=%s user=%s", agent_id, user_id)
    return {}


async def check_budget(agent_id: str, user_id: str) -> dict:
    """Returns the current week's snapshot for `agent_id`. Missing ledger
    row → zero usage. Missing persona → 404-shaped dict (caller decides)."""
    p = _personas_by_id().get(agent_id)
    if not p:
        return {"agent_id": agent_id, "missing": True}
    cap = p.get("autonomy_budget") or {}
    tok_cap = int(cap.get("max_tokens_per_week") or 0)
    usd_cap = float(cap.get("max_usd_per_week") or 0.0)
    irr_cap = int(cap.get("max_irreversible_per_week") or 0)

    row = await db.agent_usage_ledger.find_one(
        {"agent_id": agent_id, "user_id": user_id, "iso_week": _iso_week_key()},
        {"_id": 0, "tokens": 1, "usd": 1, "irreversible_count": 1},
    ) or {}
    tok_used = int(row.get("tokens") or 0)
    usd_used = float(row.get("usd") or 0.0)
    irr_used = int(row.get("irreversible_count") or 0)

    def _pct(used, cap_):
        return round((used / cap_) * 100, 1) if cap_ > 0 else 0.0

    snapshot = {
        "agent_id":          agent_id,
        "agent_name":        p["name"],
        "agent_role":        p["role"],
        "iso_week":          _iso_week_key(),
        "tokens_used":       tok_used,
        "tokens_cap":        tok_cap,
        "tokens_pct":        _pct(tok_used, tok_cap),
        "usd_used":          round(usd_used, 3),
        "usd_cap":           usd_cap,
        "usd_pct":           _pct(usd_used, usd_cap),
        "irreversible_used": irr_used,
        "irreversible_cap":  irr_cap,
        "irreversible_pct":  _pct(irr_used, irr_cap),
    }
    # All three checks must pass to allow an irreversible action.
    snapshot["can_act"] = (
        tok_used < tok_cap if tok_cap else True
    ) and (
        usd_used < usd_cap if usd_cap else True
    ) and (
        irr_used < irr_cap if irr_cap else True
    )
    # Highest pct across the three — used for the UI warning banner.
    snapshot["headroom_pct"] = max(snapshot["tokens_pct"], snapshot["usd_pct"], snapshot["irreversible_pct"])
    return snapshot


async def can_auto_approve(agent_id: str, user_id: str) -> tuple[bool, str]:
    """Returns (allowed, reason). Reason is human-readable so the briefs
    code can stamp it on the brief row for transparency."""
    snap = await check_budget(agent_id, user_id)
    if snap.get("missing"):
        return False, "unknown agent"
    if not snap["can_act"]:
        if snap["irreversible_used"] >= snap["irreversible_cap"] and snap["irreversible_cap"] > 0:
            return False, f"irreversible cap reached ({snap['irreversible_used']}/{snap['irreversible_cap']}/wk)"
        if snap["tokens_cap"] and snap["tokens_used"] >= snap["tokens_cap"]:
            return False, f"token cap reached ({snap['tokens_used']}/{snap['tokens_cap']}/wk)"
        if snap["usd_cap"] and snap["usd_used"] >= snap["usd_cap"]:
            return False, f"USD cap reached (${snap['usd_used']}/${snap['usd_cap']}/wk)"
        return False, "budget exhausted"
    return True, f"OK ({snap['irreversible_used']}/{snap['irreversible_cap']} irrev used this week)"


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.get("/agents/budgets")
async def list_budgets(request: Request):
    """Returns the current-week budget snapshot for every persona. Used
    by the /dashboard/autonomy page and the briefs hero card."""
    user = await get_current_user(request)
    snapshots = []
    for p in PERSONAS:
        snapshots.append(await check_budget(p["id"], user.user_id))
    return {
        "items":    snapshots,
        "iso_week": _iso_week_key(),
        "at_risk":  sum(1 for s in snapshots if s["headroom_pct"] >= 80),
        "exhausted": sum(1 for s in snapshots if not s["can_act"]),
    }


@api.get("/agents/budgets/{agent_id}")
async def get_budget(agent_id: str, request: Request):
    user = await get_current_user(request)
    snap = await check_budget(agent_id, user.user_id)
    if snap.get("missing"):
        raise HTTPException(status_code=404, detail="Agent not found")
    return snap


class _ResetBody(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=40)


@api.post("/agents/budgets/reset")
async def reset_budget(payload: _ResetBody, request: Request):
    """Admin-only test helper — wipes the current ISO week's ledger row
    for one agent. Lets ops folks rehearse "what happens at 0% / 100%"
    without waiting until Monday."""
    from deps import require_admin
    user = await require_admin(request)
    if payload.agent_id not in _personas_by_id():
        raise HTTPException(status_code=404, detail="Agent not found")
    res = await db.agent_usage_ledger.delete_one({
        "agent_id": payload.agent_id,
        "user_id":  user.user_id,
        "iso_week": _iso_week_key(),
    })
    return {"ok": True, "deleted": res.deleted_count, "iso_week": _iso_week_key()}
