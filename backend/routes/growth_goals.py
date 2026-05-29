"""Growth Goals — durable OKRs owned by Vera.

Each goal links a measurable metric to a target + deadline. The `current`
value is auto-computed from the normalized content + perf layers on every
read, so nobody has to manually update progress. The Monday standup
already gathers `goals` via `_gather_user_facts`, so Vera's contribution
will naturally reference them once any are created.

Status lifecycle: active → completed (hit target) | abandoned (manual).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# Supported metrics + how to compute `current` for each.
# Each entry maps a string to a callable(user_id, since) -> int.
# `since` is the goal's start_date — measures "progress since start".
SUPPORTED_METRICS = {
    "posts_published":     "Total posts published",
    "instagram.posts":     "Instagram posts published",
    "facebook.posts":      "Facebook posts published",
    "linkedin.posts":      "LinkedIn posts published",
    "tiktok.posts":        "TikTok posts published",
    "total_impressions":   "Sum of impressions (all platforms)",
    "total_engagements":   "Sum of engagements (all platforms)",
    "listening_signals":   "Listening signals captured",
}


async def _compute_current(user_id: str, metric: str, start_date: Optional[datetime]) -> int:
    """Look up the live value for a metric since the goal's start_date.
    Returns 0 on unknown metric — defensive so a typo doesn't crash.
    """
    since = start_date or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if metric == "posts_published":
        return await db.content_variants.count_documents({
            "user_id": user_id, "status": "published",
            "published_at": {"$gte": since},
        })
    if "." in metric:
        platform, kind = metric.split(".", 1)
        if kind == "posts":
            return await db.content_variants.count_documents({
                "user_id": user_id, "platform": platform, "status": "published",
                "published_at": {"$gte": since},
            })
    if metric in {"total_impressions", "total_engagements"}:
        # Pull the last_7d / all_time windows from rollups — closest proxy we
        # have for cumulative since the start_date. Future: query the daily
        # time-series rows directly for exact since-window math.
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None,
                        "v": {"$sum": f"$windows.all_time.{metric.split('_')[1]}"}}},
        ]
        async for r in db.performance_rollups.aggregate(pipeline):
            return int(r.get("v") or 0)
        return 0
    if metric == "listening_signals":
        return await db.social_listening_signals.count_documents({
            "user_id": user_id, "detected_at": {"$gte": since},
        })
    return 0


# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
class GoalIn(BaseModel):
    title:       str = Field(..., min_length=3, max_length=140)
    description: Optional[str] = Field(None, max_length=600)
    metric:      str
    target:      int = Field(..., gt=0)
    deadline:    Optional[str] = None  # ISO date string; optional
    start_date:  Optional[str] = None  # defaults to now if absent


class GoalPatch(BaseModel):
    title:       Optional[str] = None
    description: Optional[str] = None
    target:      Optional[int] = None
    deadline:    Optional[str] = None
    status:      Optional[str] = None  # active | completed | abandoned


def _hydrate_one(doc: dict, current: int) -> dict:
    """Decorate a stored row with `current`, `progress_pct`, and a `is_overdue` flag.
    The DB never stores `current` — always computed live."""
    doc = dict(doc)
    target = max(1, int(doc.get("target") or 1))
    pct = round(min(100.0, current / target * 100), 1)
    deadline = doc.get("deadline")
    overdue = False
    if deadline:
        try:
            d = deadline if isinstance(deadline, datetime) else datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
            overdue = (d < datetime.now(timezone.utc)) and (doc.get("status") == "active") and (current < target)
        except Exception:
            overdue = False
    doc["current"] = current
    doc["progress_pct"] = pct
    doc["is_overdue"] = overdue
    return doc


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.get("/goals/metrics")
async def list_supported_metrics(request: Request):
    """Surface the metric enum to the frontend so the create form has a
    dropdown that always matches the resolver."""
    user = await get_current_user(request)
    return {"metrics": [{"id": k, "label": v} for k, v in SUPPORTED_METRICS.items()]}


@api.post("/goals")
async def create_goal(payload: GoalIn, request: Request):
    user = await get_current_user(request)
    if payload.metric not in SUPPORTED_METRICS:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {payload.metric}")
    now = datetime.now(timezone.utc)
    start_dt = (
        datetime.fromisoformat(payload.start_date.replace("Z", "+00:00"))
        if payload.start_date else now
    )
    deadline_dt = (
        datetime.fromisoformat(payload.deadline.replace("Z", "+00:00"))
        if payload.deadline else None
    )
    doc = {
        "id":          uuid.uuid4().hex,
        "user_id":     user.user_id,
        "title":       payload.title.strip(),
        "description": (payload.description or "").strip() or None,
        "metric":      payload.metric,
        "target":      int(payload.target),
        "start_date":  start_dt,
        "deadline":    deadline_dt,
        "status":      "active",
        "owner_agent": "vera",
        "created_at":  now,
        "updated_at":  now,
    }
    await db.growth_goals.insert_one(doc)
    doc.pop("_id", None)
    current = await _compute_current(user.user_id, doc["metric"], doc["start_date"])
    return _hydrate_one(doc, current)


@api.get("/goals")
async def list_goals(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query: dict = {"user_id": user.user_id}
    if status:
        query["status"] = status
    docs = await db.growth_goals.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    hydrated = []
    for d in docs:
        current = await _compute_current(user.user_id, d["metric"], d.get("start_date"))
        hydrated.append(_hydrate_one(d, current))
    # Summary stats for the dashboard hero row
    active = [g for g in hydrated if g["status"] == "active"]
    completed = [g for g in hydrated if g["status"] == "completed"]
    avg_pct = round(sum(g["progress_pct"] for g in active) / len(active), 1) if active else 0
    return {
        "items":            hydrated,
        "count":            len(hydrated),
        "active_count":     len(active),
        "completed_count":  len(completed),
        "avg_progress_pct": avg_pct,
        "overdue_count":    sum(1 for g in active if g.get("is_overdue")),
    }


@api.patch("/goals/{goal_id}")
async def update_goal(goal_id: str, payload: GoalPatch, request: Request):
    user = await get_current_user(request)
    fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.title is not None:    fields["title"] = payload.title.strip()
    if payload.description is not None: fields["description"] = payload.description.strip() or None
    if payload.target is not None:   fields["target"] = int(payload.target)
    if payload.deadline is not None:
        fields["deadline"] = datetime.fromisoformat(payload.deadline.replace("Z", "+00:00")) if payload.deadline else None
    if payload.status is not None:
        if payload.status not in {"active", "completed", "abandoned"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        fields["status"] = payload.status
    res = await db.growth_goals.update_one(
        {"id": goal_id, "user_id": user.user_id}, {"$set": fields},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    doc = await db.growth_goals.find_one({"id": goal_id}, {"_id": 0})
    current = await _compute_current(user.user_id, doc["metric"], doc.get("start_date"))
    return _hydrate_one(doc, current)


@api.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.growth_goals.delete_one({"id": goal_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


@api.post("/goals/{goal_id}/auto-complete")
async def auto_complete_check(goal_id: str, request: Request):
    """Flip status to `completed` if current >= target. Idempotent.
    Called from the standup generator + the Goals dashboard polling."""
    user = await get_current_user(request)
    doc = await db.growth_goals.find_one(
        {"id": goal_id, "user_id": user.user_id, "status": "active"},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Active goal not found")
    current = await _compute_current(user.user_id, doc["metric"], doc.get("start_date"))
    if current >= int(doc.get("target") or 0):
        await db.growth_goals.update_one(
            {"id": goal_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
        )
        return {"completed": True, "current": current}
    return {"completed": False, "current": current}
