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


# ---------------------------------------------------------------------
# Team Performance — bird's-eye view of every agent's week
# ---------------------------------------------------------------------
async def _week_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Returns (monday_00:00_utc, sunday_23:59_utc) for the ISO week of `now`."""
    dt = now or datetime.now(timezone.utc)
    from datetime import timedelta
    monday = dt - timedelta(days=dt.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = monday + timedelta(days=7) - timedelta(microseconds=1)
    return monday, sunday


@api.get("/agents/team-performance")
async def team_performance(request: Request):
    """One bird's-eye row per agent: budget usage + this-week contributions.

    Vera:  goals on/off track (count of active goals + % avg progress)
    Atlas: briefs proposed / approved / auto-approved + average decision time
    Nova:  posts published this week
    Rae:   personas defined + listening signals tagged with their voice
    Lyra:  listening signals captured this week + agent-bus replies given
    Echo:  scheduled posts (lifetime) — Echo doesn't have a per-week op yet
    Ori:   experiments running / completed / inconclusive + memory writes
    Jules: budgets exhausted today + briefs gated this week

    Each row uses `verb + count` so the operator can scan at a glance:
    'Atlas proposed 5, approved 3, auto-approved 1'."""
    user = await get_current_user(request)
    week_start, _week_end = await _week_bounds()

    # Concurrent reads — these are independent.
    import asyncio as _aio
    (briefs_all, briefs_week, exps_all, posts_week,
     signals_week, msgs_week, mem_winners_week,
     standups_week, goals_active) = await _aio.gather(
        db.proposed_briefs.find({"user_id": user.user_id}, {"_id": 0, "status": 1, "auto_approved": 1, "created_at": 1, "decided_at": 1}).to_list(length=2000),
        db.proposed_briefs.count_documents({"user_id": user.user_id, "created_at": {"$gte": week_start}}),
        db.experiments.find({"user_id": user.user_id}, {"_id": 0, "status": 1, "ended_at": 1, "created_at": 1}).to_list(length=2000),
        db.posts.count_documents({"user_id": user.user_id, "status": "published", "published_at": {"$gte": week_start}}),
        db.social_listening_signals.count_documents({"user_id": user.user_id, "detected_at": {"$gte": week_start}}),
        db.agent_messages.count_documents({"user_id": user.user_id, "created_at": {"$gte": week_start}}),
        db.cortex_memory.count_documents({"user_id": user.user_id, "kind": "experiment_winner", "created_at": {"$gte": week_start}}),
        db.weekly_standups.count_documents({"user_id": user.user_id, "generated_at": {"$gte": week_start}}),
        db.growth_goals.find({"user_id": user.user_id, "status": "active"}, {"_id": 0, "current": 1, "target": 1}).to_list(length=200),
    )

    # Derived stats.
    briefs_week_rows = [b for b in briefs_all if isinstance(b.get("created_at"), datetime) and
                        (b["created_at"].replace(tzinfo=timezone.utc) if b["created_at"].tzinfo is None else b["created_at"]) >= week_start]
    briefs_approved_week = sum(1 for b in briefs_week_rows if b["status"] == "approved")
    briefs_auto_week = sum(1 for b in briefs_week_rows if b.get("auto_approved"))
    decided = [b for b in briefs_week_rows if b.get("decided_at")]
    avg_decision_min = 0
    if decided:
        diffs = []
        for b in decided:
            ca, da = b.get("created_at"), b.get("decided_at")
            if isinstance(ca, datetime) and isinstance(da, datetime):
                if ca.tzinfo is None: ca = ca.replace(tzinfo=timezone.utc)
                if da.tzinfo is None: da = da.replace(tzinfo=timezone.utc)
                diffs.append((da - ca).total_seconds() / 60)
        avg_decision_min = round(sum(diffs) / len(diffs), 1) if diffs else 0

    exps_week = [e for e in exps_all if isinstance(e.get("created_at"), datetime) and
                 (e["created_at"].replace(tzinfo=timezone.utc) if e["created_at"].tzinfo is None else e["created_at"]) >= week_start]
    exps_running = sum(1 for e in exps_all if e["status"] == "running")
    exps_completed_week = sum(1 for e in exps_week if e["status"] == "completed")
    exps_inconclusive_week = sum(1 for e in exps_week if e["status"] == "inconclusive")

    # Goal progress: avg (current/target) across active goals.
    goal_pct = 0.0
    if goals_active:
        valid = [(g.get("current") or 0) / g["target"] for g in goals_active
                 if isinstance(g.get("target"), (int, float)) and g["target"] > 0]
        goal_pct = round((sum(valid) / len(valid)) * 100, 1) if valid else 0.0

    contributions: dict[str, dict] = {
        "vera":  {"headline": f"{len(goals_active)} active goal(s), avg {goal_pct:.0f}% to target",
                  "verbs": [{"label": "Active goals", "value": len(goals_active)},
                            {"label": "Avg progress", "value": f"{goal_pct:.0f}%"}]},
        "atlas": {"headline": f"{briefs_week} brief(s) proposed, {briefs_approved_week} approved, {briefs_auto_week} auto-approved",
                  "verbs": [{"label": "Proposed",      "value": briefs_week},
                            {"label": "Approved",      "value": briefs_approved_week},
                            {"label": "Auto-approved", "value": briefs_auto_week},
                            {"label": "Avg decision",  "value": f"{avg_decision_min:.0f}m"}]},
        "nova":  {"headline": f"{posts_week} post(s) published this week",
                  "verbs": [{"label": "Published", "value": posts_week}]},
        "rae":   {"headline": f"{standups_week} standup(s) this week",
                  "verbs": [{"label": "Standups", "value": standups_week}]},
        "lyra":  {"headline": f"{signals_week} listening signal(s) captured",
                  "verbs": [{"label": "Signals", "value": signals_week},
                            {"label": "Replies in chatter", "value": msgs_week}]},
        "echo":  {"headline": f"{posts_week} post(s) scheduled/published this week",
                  "verbs": [{"label": "Posts", "value": posts_week}]},
        "ori":   {"headline": f"{exps_running} running · {exps_completed_week} winner(s) · {mem_winners_week} memory write(s)",
                  "verbs": [{"label": "Running",        "value": exps_running},
                            {"label": "Winners (wk)",   "value": exps_completed_week},
                            {"label": "Inconclusive",   "value": exps_inconclusive_week},
                            {"label": "Memory writes",  "value": mem_winners_week}]},
        "jules": {"headline": "Budget guardian — see Autonomy page",
                  "verbs": [{"label": "Bus messages (wk)", "value": msgs_week}]},
    }

    rows = []
    for p in PERSONAS:
        budget = await check_budget(p["id"], user.user_id)
        c = contributions.get(p["id"], {"headline": "—", "verbs": []})
        rows.append({
            "agent_id":     p["id"],
            "name":         p["name"],
            "role":         p["role"],
            "headline":     c["headline"],
            "verbs":        c["verbs"],
            "headroom_pct": budget.get("headroom_pct", 0),
            "can_act":      budget.get("can_act", True),
        })
    return {
        "rows":            rows,
        "iso_week":        _iso_week_key(),
        "week_started_at": week_start,
        "briefs_week":     briefs_week,
        "experiments_active": exps_running,
        "signals_week":    signals_week,
    }
