"""Cortex active-mission rail backend.

Powers the new "Active Mission Rail" in the Conversational Command
Center. Returns rich, real-time status per running mission:

  - current_phase     (inferred from data — seller-stage distribution)
  - progress_pct      (via routes.missions.compute_progress)
  - last_action       (most-recent mission/seller event)
  - next_action       (engine's next planned step)
  - eta_days

Also exposes the post-execute "follow-up" turn — Cortex auto-appends
a contextual refinement question after launching a mission so the
conversation never ends.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import api, db
from deps import get_current_user
from routes.missions import compute_progress

logger = logging.getLogger(__name__)


# Seller-acquisition phase inference: maps the dominant lead stage to
# the human-readable phase name + the next phase Cortex will move into.
SELLER_PHASE_MAP = [
    # (phase_key,          dominant_stages,                 label,           next_label)
    ("discovery",          {"discovered"},                  "Discovery",     "Qualification"),
    ("qualification",      {"qualified"},                   "Qualification", "Outreach"),
    ("outreach",           {"outreached"},                  "Outreach",      "Conversations"),
    ("conversations",      {"interested", "replied"},       "Conversations", "Onboarding"),
    ("onboarding",         {"onboarded"},                   "Onboarding",    "Retention"),
    ("retention",          {"active", "at_risk", "churned"}, "Retention",    "Complete"),
]


async def _infer_seller_phase(user_id: str, mission_id: str) -> dict:
    """Look at the user's seller_leads for this mission and infer the
    current pipeline phase from the highest-stage majority cluster."""
    pipeline = [
        {"$match": {"user_id": user_id, "mission_id": mission_id}},
        {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
    ]
    stages: dict[str, int] = {}
    async for r in db.seller_leads.aggregate(pipeline):
        stages[r["_id"] or "unknown"] = int(r["n"] or 0)

    # Falls through phases in reverse (most-advanced first). The first phase
    # that has any leads becomes the "current" phase — because once leads
    # have moved past discovery, that's where Cortex's attention is.
    current = None
    for phase_key, stage_set, label, next_label in reversed(SELLER_PHASE_MAP):
        if any(stages.get(s, 0) > 0 for s in stage_set):
            current = (phase_key, label, next_label)
            break
    if current is None:
        current = ("discovery", "Discovery", "Qualification")

    phase_key, label, next_label = current
    return {
        "key":         phase_key,
        "label":       label,
        "next_label":  next_label,
        "stages":      stages,
        "leads_total": sum(stages.values()),
    }


async def _last_action(user_id: str, mission_id: str) -> Optional[dict]:
    """Most recent event across BOTH mission_events and
    seller_outreach_events. Merges by created_at and returns the
    single newest row so the rail reflects the freshest activity."""
    candidates: list[dict] = []
    for coll in ("mission_events", "seller_outreach_events"):
        try:
            base = {"user_id": user_id, "mission_id": mission_id}
            cur = db[coll].find(base, {"_id": 0}).sort("created_at", -1).limit(1)
            async for r in cur:
                candidates.append({
                    "label":      (r.get("event") or r.get("type") or "tick").replace("_", " "),
                    "summary":    r.get("body") or r.get("payload", {}).get("title") or "",
                    "created_at": r.get("created_at"),
                    "source":     coll,
                })
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
                     reverse=True)
    top = candidates[0]
    ts = top.get("created_at")
    top["created_at"] = ts.isoformat() if isinstance(ts, datetime) else ts
    return top


@api.get("/cortex/missions/active")
async def cortex_active_missions(request: Request, limit: int = 6):
    """Active missions for the right-rail. Returns rich status per
    mission: phase, progress, last_action, next_action, eta."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 20))

    cur = db.missions.find(
        {"user_id": user.user_id,
         "status":  {"$in": ["running", "active", "queued", "paused"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit)

    out: list[dict] = []
    async for m in cur:
        try:
            progress = await compute_progress(m)
        except Exception:
            progress = {"current": 0, "target": int(m.get("target") or 1),
                          "progress_pct": 0, "eta_days": None}

        phase = None
        if m.get("mission_type") == "seller_acquisition":
            phase = await _infer_seller_phase(user.user_id, m["id"])

        last = await _last_action(user.user_id, m["id"])

        out.append({
            "id":             m["id"],
            "title":          m.get("title") or "Mission",
            "mission_type":   m.get("mission_type") or "campaign",
            "status":         m.get("status") or "running",
            "autonomy_level": m.get("autonomy_level"),
            "created_at":     _iso(m.get("created_at")),
            "progress": {
                "current":      progress.get("current"),
                "target":       progress.get("target"),
                "pct":          progress.get("progress_pct"),
                "eta_days":     progress.get("eta_days"),
                "confidence":   progress.get("confidence"),
            },
            "phase":       phase,
            "last_action": last,
            "next_action": {
                "label":       (phase or {}).get("next_label") or "Continue",
                "description": _next_action_copy(m, phase, progress),
            },
        })

    return {"missions": out, "count": len(out)}


def _next_action_copy(m: dict, phase: Optional[dict],
                       progress: dict) -> str:
    """Human readable 'next action' line for the rail."""
    if not phase:
        return "Continue execution"
    pkey = phase.get("key")
    leads = phase.get("leads_total", 0) or 0
    if pkey == "discovery":
        return f"Scouting candidate sellers · {leads} discovered so far"
    if pkey == "qualification":
        return f"Scoring {leads} discovered leads"
    if pkey == "outreach":
        return "Personalizing audit + sending first-touch messages"
    if pkey == "conversations":
        return "Replying to interested sellers + booking calls"
    if pkey == "onboarding":
        return "Walking signed sellers through setup"
    if pkey == "retention":
        return "Monitoring activity + nudging at-risk sellers"
    return "Continue execution"


@api.get("/cortex/missions/{mission_id}/events")
async def cortex_mission_events(mission_id: str, request: Request,
                                 since: Optional[str] = None,
                                 limit: int = 20):
    """Mission event timeline — feeds the in-chat live updates feature.
    `since` is an ISO timestamp; only events newer than this are returned
    (used by the polling loop on the frontend)."""
    user = await get_current_user(request)
    mission = await db.missions.find_one(
        {"id": mission_id, "user_id": user.user_id}, {"_id": 0})
    if not mission:
        raise HTTPException(404, "Mission not found")

    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            since_dt = None

    base = {"user_id": user.user_id, "mission_id": mission_id}
    if since_dt:
        base["created_at"] = {"$gt": since_dt}

    out: list[dict] = []
    for coll, ev_field in (("mission_events", "event"),
                            ("seller_outreach_events", "event")):
        try:
            cur = db[coll].find(base if coll == "mission_events"
                                 else {**base, "mission_id": mission_id},
                                 {"_id": 0}).sort("created_at", -1).limit(limit)
            async for r in cur:
                ts = r.get("created_at")
                out.append({
                    "id":         r.get("id"),
                    "label":      (r.get(ev_field) or "tick").replace("_", " "),
                    "body":       r.get("body") or r.get("payload", {}).get("title"),
                    "channel":    r.get("channel"),
                    "source":     coll,
                    "created_at": ts.isoformat() if isinstance(ts, datetime) else ts,
                })
        except Exception:
            continue
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"mission_id": mission_id, "events": out[:limit], "count": min(len(out), limit)}


@api.get("/cortex/missions/{mission_id}")
async def cortex_mission_detail(mission_id: str, request: Request):
    """Single-mission detail — same shape as the list item."""
    user = await get_current_user(request)
    m = await db.missions.find_one(
        {"id": mission_id, "user_id": user.user_id}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Mission not found")
    try:
        progress = await compute_progress(m)
    except Exception:
        progress = {"current": 0, "target": int(m.get("target") or 1),
                      "progress_pct": 0, "eta_days": None}
    phase = None
    if m.get("mission_type") == "seller_acquisition":
        phase = await _infer_seller_phase(user.user_id, m["id"])
    last = await _last_action(user.user_id, m["id"])
    return {
        "id":             m["id"],
        "title":          m.get("title") or "Mission",
        "mission_type":   m.get("mission_type"),
        "status":         m.get("status"),
        "autonomy_level": m.get("autonomy_level"),
        "created_at":     _iso(m.get("created_at")),
        "progress": {
            "current":  progress.get("current"),
            "target":   progress.get("target"),
            "pct":      progress.get("progress_pct"),
            "eta_days": progress.get("eta_days"),
            "confidence": progress.get("confidence"),
        },
        "phase":       phase,
        "last_action": last,
        "next_action": {
            "label":       (phase or {}).get("next_label") or "Continue",
            "description": _next_action_copy(m, phase, progress),
        },
    }


def _iso(v) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return v if isinstance(v, str) else None
