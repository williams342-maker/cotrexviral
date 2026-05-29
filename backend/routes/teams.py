"""Agent Teams — façade over the 9 existing personas.

The user-facing IA now organises agents into 4 teams. Behind the scenes,
each call is still routed to the same persona handlers (no duplicated
logic).

Team → Persona mapping (canonical):
  scout        → Rae, Lyra, Atlas         (research + listening + strategy)
  creator      → Nova, Atlas              (copywriting + structured proposals)
  operator     → Echo, Jules              (distribution + ops/budget)
  intelligence → Ori, Pico                (analytics + optimization)

Vera (CMO) sits ABOVE the teams — owned by the Cortex orchestrator.

This module exposes:
  GET  /api/teams                       — list all 4 teams + member personas
  GET  /api/teams/{team_id}             — team detail (personas, last 24h activity)
  GET  /api/teams/{team_id}/activity    — recent activity feed for the team
  POST /api/teams/{team_id}/dispatch    — fire a task at the team (Cortex uses this)
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


TEAM_DEFS = {
    "scout": {
        "id":           "scout",
        "name":         "Scout",
        "tagline":      "Spots the opportunities before anyone else.",
        "personas":     ["rae", "lyra", "atlas"],
        "responsibilities": [
            "Market research",
            "Trend detection",
            "Competitor monitoring",
            "Social listening",
            "Opportunity discovery",
        ],
        "outputs":      ["opportunities", "market_briefs", "campaign_recommendations"],
        "color":        "#22d3ee",   # cyan
    },
    "creator": {
        "id":           "creator",
        "name":         "Creator",
        "tagline":      "Turns insight into ready-to-ship creative.",
        "personas":     ["nova", "atlas"],
        "responsibilities": [
            "Campaign generation",
            "Content generation",
            "Ad generation",
            "Email generation",
            "Landing page generation",
        ],
        "outputs":      ["campaign_assets", "content_drafts", "creative_variants"],
        "color":        "#a78bfa",   # violet
    },
    "operator": {
        "id":           "operator",
        "name":         "Operator",
        "tagline":      "Ships campaigns reliably, on time, on budget.",
        "personas":     ["echo", "jules"],
        "responsibilities": [
            "Publishing",
            "Scheduling",
            "Approval workflows",
            "Budget controls",
            "Automation execution",
        ],
        "outputs":      ["published_campaigns", "distribution_reports"],
        "color":        "#34d399",   # emerald
    },
    "intelligence": {
        "id":           "intelligence",
        "name":         "Intelligence",
        "tagline":      "Knows what's working — and pushes the dial.",
        "personas":     ["ori", "pico"],
        "responsibilities": [
            "Analytics",
            "Attribution",
            "Performance scoring",
            "Optimization",
            "Winner detection",
        ],
        "outputs":      ["performance_reports", "recommendations", "automated_optimizations"],
        "color":        "#f59e0b",   # amber
    },
}


# Activity sources per team — collections we'll query for the activity feed.
# Each entry: (collection_name, type_label).
TEAM_ACTIVITY_SOURCES = {
    "scout":        [("social_listening_signals", "signal"),
                     ("campaign_briefs",          "brief")],
    "creator":      [("content_variants",         "variant"),
                     ("campaign_briefs",          "brief")],
    "operator":     [("content_items",            "publish"),
                     ("posts",                    "post")],
    "intelligence": [("performance_metrics",      "metric"),
                     ("experiments",              "experiment")],
}


# -----------------------------------------------------------------
# Pydantic schemas
# -----------------------------------------------------------------
class TeamDispatch(BaseModel):
    mission_id: Optional[str] = None
    task:       str             # short task description ("research craft markets")
    context:    Optional[dict] = None


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------
async def _team_kpis(team_id: str, user_id: str) -> dict:
    """Lightweight per-team KPI rollup, last 7 days."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    kpis: dict = {}
    if team_id == "scout":
        kpis["signals_7d"]  = await db.social_listening_signals.count_documents({
            "user_id": user_id, "captured_at": {"$gte": since}})
        kpis["briefs_7d"]   = await db.campaign_briefs.count_documents({
            "user_id": user_id, "created_at":  {"$gte": since}})
    elif team_id == "creator":
        kpis["drafts_7d"]   = await db.content_variants.count_documents({
            "user_id": user_id, "status": "draft", "created_at": {"$gte": since}})
        kpis["variants_7d"] = await db.content_variants.count_documents({
            "user_id": user_id, "created_at": {"$gte": since}})
    elif team_id == "operator":
        kpis["published_7d"] = await db.content_variants.count_documents({
            "user_id": user_id, "status": "published",
            "published_at": {"$gte": since}})
        kpis["scheduled_7d"] = await db.content_variants.count_documents({
            "user_id": user_id, "status": "scheduled"})
    elif team_id == "intelligence":
        kpis["experiments_active"] = await db.experiments.count_documents({
            "user_id": user_id, "status": "running"})
        kpis["winners_7d"] = await db.experiments.count_documents({
            "user_id": user_id, "status": "concluded",
            "concluded_at": {"$gte": since}})
    return kpis


async def _team_activity(team_id: str, user_id: str, limit: int = 20) -> List[dict]:
    """Pull recent rows from each source collection, normalize."""
    sources = TEAM_ACTIVITY_SOURCES.get(team_id, [])
    rows: List[dict] = []
    for coll, type_label in sources:
        col = db[coll]
        try:
            cursor = col.find(
                {"user_id": user_id}, {"_id": 0},
            ).sort("created_at", -1).limit(limit)
            async for r in cursor:
                r["__type"] = type_label
                # Normalize a `when` timestamp the UI can sort by.
                when = (r.get("created_at") or r.get("captured_at")
                        or r.get("published_at") or r.get("updated_at"))
                if isinstance(when, datetime):
                    r["__when"] = when.isoformat()
                rows.append(r)
        except Exception:
            logger.debug("activity source %s failed", coll, exc_info=True)
    # Sort by __when desc and trim
    rows.sort(key=lambda r: r.get("__when") or "", reverse=True)
    return rows[:limit]


# -----------------------------------------------------------------
# Routes
# -----------------------------------------------------------------
@api.get("/teams")
async def list_teams(request: Request):
    user = await get_current_user(request)
    out = []
    for tid in ("scout", "creator", "operator", "intelligence"):
        defn = TEAM_DEFS[tid]
        kpis = await _team_kpis(tid, user.user_id)
        out.append({**defn, "kpis": kpis})
    return {"teams": out}


@api.get("/teams/{team_id}")
async def get_team(team_id: str, request: Request):
    if team_id not in TEAM_DEFS:
        raise HTTPException(404, f"Unknown team: {team_id}")
    user = await get_current_user(request)
    defn = TEAM_DEFS[team_id]

    # Hydrate persona docs (display name, role, status).
    personas = []
    for pid in defn["personas"]:
        p = await db.agent_personas.find_one({"id": pid}, {"_id": 0})
        if p:
            personas.append(p)

    kpis = await _team_kpis(team_id, user.user_id)
    activity = await _team_activity(team_id, user.user_id, limit=20)

    return {
        **defn,
        "personas":        personas,
        "kpis":            kpis,
        "recent_activity": activity,
    }


@api.get("/teams/{team_id}/activity")
async def get_team_activity(team_id: str, request: Request, limit: int = 50):
    if team_id not in TEAM_DEFS:
        raise HTTPException(404, f"Unknown team: {team_id}")
    user = await get_current_user(request)
    rows = await _team_activity(team_id, user.user_id, limit=min(200, max(1, limit)))
    return {"activity": rows, "count": len(rows)}


@api.post("/teams/{team_id}/dispatch")
async def dispatch_to_team(team_id: str, payload: TeamDispatch, request: Request):
    """Fire a task at a team. Records the dispatch as an agent_message so
    the existing inbox/chatter UI picks it up.

    Cortex uses this to coordinate work without each team needing its own
    bespoke handler. The first persona in the team becomes the addressee.
    """
    if team_id not in TEAM_DEFS:
        raise HTTPException(404, f"Unknown team: {team_id}")
    user = await get_current_user(request)
    defn = TEAM_DEFS[team_id]
    addressee = defn["personas"][0]  # lead persona — Rae for scout, Nova for creator etc.

    now = datetime.now(timezone.utc)
    msg = {
        "id":          uuid.uuid4().hex,
        "user_id":     user.user_id,
        "from_agent":  "cortex",
        "to_agent":    addressee,
        "team":        team_id,
        "mission_id":  payload.mission_id,
        "task":        payload.task,
        "context":     payload.context or {},
        "status":      "queued",
        "created_at":  now,
        "updated_at":  now,
    }
    await db.agent_messages.insert_one(msg)
    # Mirror into a per-team dispatch log so future Team-detail pages can render
    # the team's own task queue cleanly without filtering chatter.
    await db.team_dispatches.insert_one({**msg})
    return {"ok": True, "dispatch_id": msg["id"], "team": team_id, "lead_persona": addressee}
