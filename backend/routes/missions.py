"""Missions — the mission-driven layer of the autonomous marketing OS.

A Mission is a user-stated business outcome ("Generate 50 new maker
signups for CraftersMarket") that Cortex coordinates across the 4 agent
teams (Scout / Creator / Operator / Intelligence) until the outcome is
achieved or the user pauses it.

Mission != Growth Goal:
  - Growth Goal = a KPI target ("ig_followers reaches 5000") — passive.
  - Mission    = an active project that consumes Growth Goals, spawns
                 campaigns, and self-iterates. Each Mission can be backed
                 by one or more Growth Goals when the user wants the
                 metric machinery to compute progress automatically.

The compute_progress() helper aggregates progress from the linked Growth
Goal (if any) AND from the missions's own campaign output (campaigns
shipped, content variants published, etc.) — whichever yields the higher
fidelity number wins.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)

# Mission lifecycle:
#   draft → running → (paused | succeeded | abandoned)
STATUSES = {"draft", "running", "paused", "succeeded", "abandoned"}

# Autonomy levels (also stored per-team override in mission.team_autonomy).
#   0  Manual approval for everything.
#   1  Auto-create content (Creator team auto-drafts; Operator stays manual).
#   2  Auto-publish on pre-approved channels (Operator level 1).
#   3  Auto-optimize campaigns (Intelligence may swap creative/budget).
#   4  Goal-seeking — Cortex may extend timeline / shift budget within caps.
#   5  Full autonomous — all teams unlocked within mission budget caps.
AUTONOMY_LEVELS = {0, 1, 2, 3, 4, 5}

# The 4 agent teams. Mirrored in routes/teams.py and the frontend.
TEAMS = ("scout", "creator", "operator", "intelligence")


# -----------------------------------------------------------------
# Pydantic schemas
# -----------------------------------------------------------------
class MissionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    metric: Optional[str] = None       # e.g. "instagram.posts" or "leads"
    target: Optional[int] = None       # numeric target (50 for "50 signups")
    deadline: Optional[datetime] = None
    autonomy_level: int = 1            # default: auto-create content, manual publish
    team_autonomy: Optional[dict] = None  # {"creator": 2, "operator": 0, ...}
    teams_assigned: List[str] = Field(default_factory=lambda: list(TEAMS))
    budget_usd_cap: Optional[float] = None
    growth_goal_id: Optional[str] = None  # link to an existing Growth Goal
    # --- Seller Acquisition mission type (Phase 1 of Seller OS) ---
    mission_type: Optional[str] = None   # "seller_acquisition" | None (= generic)
    seller_target_niche: Optional[str] = None  # "woodworking", "laser engraving"
    seller_target_location: Optional[str] = None
    qualification_threshold: Optional[float] = None  # default 60.0


class MissionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    autonomy_level: Optional[int] = None
    team_autonomy: Optional[dict] = None
    deadline: Optional[datetime] = None
    budget_usd_cap: Optional[float] = None
    seller_target_niche: Optional[str] = None
    seller_target_location: Optional[str] = None
    qualification_threshold: Optional[float] = None


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------
async def compute_progress(mission: dict) -> dict:
    """Returns dict with `current`, `target`, `confidence`, `eta_days`,
    `top_channel`, `best_asset`, `campaigns_active`.

    Strategy:
      • current   = max(linked growth_goal.current,
                        len(campaigns spawned by this mission that are 'active'))
      • confidence = simple velocity-vs-deadline calculation, capped [0, 100].
      • eta_days   = (target - current) / daily_velocity, rounded up.
      • top_channel = platform with the most published content this mission.
      • best_asset = highest-engagement content_variant attributed.
    """
    # Mongo strips tzinfo on round-trip — coerce both datetime fields to
    # UTC-aware so we can compare against datetime.now(timezone.utc) safely.
    def _utc(d):
        if isinstance(d, datetime) and d.tzinfo is None:
            return d.replace(tzinfo=timezone.utc)
        return d
    mission = dict(mission)  # don't mutate the caller's dict
    for k in ("started_at", "deadline", "created_at", "completed_at"):
        mission[k] = _utc(mission.get(k))
    user_id = mission["user_id"]
    target = int(mission.get("target") or 0)
    target = max(target, 1)  # avoid div-by-zero

    # 1. Current — via Growth Goal link if present, else via the mission's own
    #    campaign output count.
    current = 0
    if mission.get("growth_goal_id"):
        goal = await db.growth_goals.find_one({"id": mission["growth_goal_id"]})
        if goal:
            current = int(goal.get("current") or 0)

    # Campaigns + variants this mission spawned.
    campaigns_active = await db.campaigns.count_documents({
        "user_id":    user_id,
        "mission_id": mission["id"],
        "status":     "active",
    })
    variants_published = await db.content_variants.count_documents({
        "user_id":    user_id,
        "mission_id": mission["id"],
        "status":     "published",
    })
    current = max(current, variants_published)

    # 2. Top channel — platform with most published variants for this mission.
    top_channel = None
    try:
        pipeline = [
            {"$match": {"user_id": user_id,
                        "mission_id": mission["id"],
                        "status": "published"}},
            {"$group": {"_id": "$platform", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 1},
        ]
        async for r in db.content_variants.aggregate(pipeline):
            top_channel = r["_id"]
            break
    except Exception:
        logger.debug("top_channel lookup failed", exc_info=True)

    # 3. Best asset — highest-engagement content_variant for this mission.
    best_asset = None
    try:
        pipeline = [
            {"$match": {"user_id": user_id,
                        "mission_id": mission["id"],
                        "status": "published",
                        "performance.engagements": {"$exists": True}}},
            {"$sort": {"performance.engagements": -1}},
            {"$limit": 1},
            {"$project": {"_id": 0, "id": 1, "platform": 1, "title": 1,
                          "engagements": "$performance.engagements"}},
        ]
        async for r in db.content_variants.aggregate(pipeline):
            best_asset = r
            break
    except Exception:
        logger.debug("best_asset lookup failed", exc_info=True)

    # 4. Confidence — velocity-vs-deadline. With no deadline, fall back to
    #    raw progress %.
    pct = min(100, int(round(100 * current / target)))
    confidence = pct
    deadline = mission.get("deadline")
    started_at = mission.get("started_at") or mission.get("created_at")
    if deadline and started_at and current > 0:
        total_days = max(1, (deadline - started_at).total_seconds() / 86400)
        elapsed_days = max(1, (datetime.now(timezone.utc) - started_at).total_seconds() / 86400)
        # Are we on pace? If yes → confidence high. If behind, drop it.
        expected = (elapsed_days / total_days) * target
        if expected > 0:
            pace_ratio = current / expected
            # >= 1.0 → at or ahead of pace, confidence pegged to pct.
            # < 1.0 → behind, scale confidence down.
            confidence = int(round(pct * min(1.0, pace_ratio)))
            confidence = max(0, min(100, confidence))

    # 5. ETA — naive linear projection.
    eta_days = None
    if current > 0 and started_at:
        elapsed_days = max(1, (datetime.now(timezone.utc) - started_at).total_seconds() / 86400)
        velocity = current / elapsed_days
        if velocity > 0:
            remaining = max(0, target - current)
            eta_days = int(round(remaining / velocity)) if remaining > 0 else 0

    return {
        "current":          current,
        "target":           target,
        "progress_pct":     pct,
        "confidence":       confidence,
        "eta_days":         eta_days,
        "top_channel":      top_channel,
        "best_asset":       best_asset,
        "campaigns_active": campaigns_active,
        "variants_published": variants_published,
    }


def _serialize(mission: dict) -> dict:
    """Return a Mongo doc with `_id` stripped and dates ISO-formatted."""
    out = {k: v for k, v in mission.items() if k != "_id"}
    for k in ("created_at", "updated_at", "started_at", "completed_at", "deadline"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# -----------------------------------------------------------------
# Routes
# -----------------------------------------------------------------
@api.post("/missions")
async def create_mission(payload: MissionCreate, request: Request):
    user = await get_current_user(request)
    if payload.autonomy_level not in AUTONOMY_LEVELS:
        raise HTTPException(400, "autonomy_level must be 0-5")
    for team in payload.teams_assigned:
        if team not in TEAMS:
            raise HTTPException(400, f"Unknown team: {team}")

    now = datetime.now(timezone.utc)
    doc = {
        "id":              uuid.uuid4().hex,
        "user_id":         user.user_id,
        "title":           payload.title.strip(),
        "description":     (payload.description or "").strip() or None,
        "metric":          payload.metric,
        "target":          payload.target,
        "deadline":        payload.deadline,
        "autonomy_level":  payload.autonomy_level,
        "team_autonomy":   payload.team_autonomy or {},
        "teams_assigned":  payload.teams_assigned,
        "budget_usd_cap":  payload.budget_usd_cap,
        "growth_goal_id":  payload.growth_goal_id,
        "mission_type":    payload.mission_type or "generic",
        "seller_target_niche":    payload.seller_target_niche,
        "seller_target_location": payload.seller_target_location,
        "qualification_threshold": payload.qualification_threshold,
        "status":          "draft",
        "created_at":      now,
        "updated_at":      now,
        "started_at":      None,
        "completed_at":    None,
    }
    await db.missions.insert_one(doc)
    return _serialize(doc)


@api.get("/missions")
async def list_missions(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    q = {"user_id": user.user_id}
    if status:
        if status not in STATUSES:
            raise HTTPException(400, f"Unknown status: {status}")
        q["status"] = status
    rows = await db.missions.find(q).sort("created_at", -1).to_list(length=500)

    # Annotate each with computed progress for the dashboard cards.
    out = []
    for r in rows:
        progress = await compute_progress(r)
        out.append({**_serialize(r), "progress": progress})
    return {"missions": out, "count": len(out)}


@api.get("/missions/{mission_id}")
async def get_mission(mission_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Mission not found")
    progress = await compute_progress(doc)
    return {**_serialize(doc), "progress": progress}


@api.patch("/missions/{mission_id}")
async def update_mission(mission_id: str, payload: MissionUpdate, request: Request):
    user = await get_current_user(request)
    doc = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Mission not found")

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.title is not None:
        updates["title"] = payload.title.strip()
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.status is not None:
        if payload.status not in STATUSES:
            raise HTTPException(400, f"Unknown status: {payload.status}")
        updates["status"] = payload.status
        # Lifecycle hooks
        if payload.status == "running" and not doc.get("started_at"):
            updates["started_at"] = datetime.now(timezone.utc)
        if payload.status in ("succeeded", "abandoned") and not doc.get("completed_at"):
            updates["completed_at"] = datetime.now(timezone.utc)
    if payload.autonomy_level is not None:
        if payload.autonomy_level not in AUTONOMY_LEVELS:
            raise HTTPException(400, "autonomy_level must be 0-5")
        updates["autonomy_level"] = payload.autonomy_level
    if payload.team_autonomy is not None:
        updates["team_autonomy"] = payload.team_autonomy
    if payload.deadline is not None:
        updates["deadline"] = payload.deadline
    if payload.budget_usd_cap is not None:
        updates["budget_usd_cap"] = payload.budget_usd_cap
    if payload.seller_target_niche is not None:
        updates["seller_target_niche"] = payload.seller_target_niche
    if payload.seller_target_location is not None:
        updates["seller_target_location"] = payload.seller_target_location
    if payload.qualification_threshold is not None:
        updates["qualification_threshold"] = float(payload.qualification_threshold)

    await db.missions.update_one({"id": mission_id}, {"$set": updates})
    fresh = await db.missions.find_one({"id": mission_id})
    progress = await compute_progress(fresh)
    return {**_serialize(fresh), "progress": progress}


@api.get("/missions/{mission_id}/seller-funnel")
async def get_seller_funnel(mission_id: str, request: Request):
    """Mission Dashboard's 8 KPI cards for a Seller-Acquisition mission.

    Returns:
      discovered, qualified, outreached, interested, onboarding, active,
      projected_completion (current/target/eta_days/confidence),
      score_summary
    """
    user = await get_current_user(request)
    mission = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not mission:
        raise HTTPException(404, "Mission not found")

    # Per-stage counts
    from routes.seller_leads import funnel_for_mission
    funnel = await funnel_for_mission(user.user_id, mission_id)

    # Average seller score across qualified+ leads
    avg_score = None
    pipeline = [
        {"$match": {"user_id": user.user_id, "mission_id": mission_id,
                    "seller_score": {"$ne": None}}},
        {"$group": {"_id": None, "avg": {"$avg": "$seller_score"},
                    "min": {"$min": "$seller_score"},
                    "max": {"$max": "$seller_score"},
                    "n": {"$sum": 1}}},
    ]
    async for r in db.seller_leads.aggregate(pipeline):
        avg_score = {
            "average": round(r["avg"] or 0, 1),
            "min":     round(r["min"] or 0, 1),
            "max":     round(r["max"] or 0, 1),
            "n":       r["n"],
        }
        break

    # Projected completion
    target = int(mission.get("target") or 0)
    onboarded = funnel.get("active", 0) + funnel.get("onboarding", 0)
    progress_pct = 0 if target <= 0 else min(100, int(round(100 * onboarded / target)))

    return {
        "mission_id":      mission_id,
        "mission_type":    mission.get("mission_type"),
        "target":          target,
        "funnel":          funnel,
        "score_summary":   avg_score,
        "projected_completion": {
            "current":      onboarded,
            "target":       target,
            "progress_pct": progress_pct,
        },
    }


@api.delete("/missions/{mission_id}")
async def delete_mission(mission_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.missions.delete_one({"id": mission_id, "user_id": user.user_id})
    if not res.deleted_count:
        raise HTTPException(404, "Mission not found")
    return {"ok": True, "deleted": mission_id}


@api.post("/missions/{mission_id}/start")
async def start_mission(mission_id: str, request: Request):
    """Convenience: transitions draft → running and records started_at."""
    user = await get_current_user(request)
    doc = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Mission not found")
    if doc["status"] not in ("draft", "paused"):
        raise HTTPException(400, f"Cannot start mission in status {doc['status']}")
    now = datetime.now(timezone.utc)
    await db.missions.update_one(
        {"id": mission_id},
        {"$set": {
            "status":     "running",
            "started_at": doc.get("started_at") or now,
            "updated_at": now,
        }},
    )
    fresh = await db.missions.find_one({"id": mission_id})
    progress = await compute_progress(fresh)
    return {**_serialize(fresh), "progress": progress}


@api.post("/missions/{mission_id}/pause")
async def pause_mission(mission_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Mission not found")
    if doc["status"] != "running":
        raise HTTPException(400, f"Cannot pause mission in status {doc['status']}")
    await db.missions.update_one(
        {"id": mission_id},
        {"$set": {"status": "paused", "updated_at": datetime.now(timezone.utc)}},
    )
    fresh = await db.missions.find_one({"id": mission_id})
    return {**_serialize(fresh), "progress": await compute_progress(fresh)}
