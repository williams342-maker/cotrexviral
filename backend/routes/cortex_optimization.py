"""Cortex Autonomous Optimization endpoints.

UI surfaces the OODA loop's findings as 'Cortex detected …' panels in
the Command Center. These endpoints read from cortex_optimization_log
and optionally trigger a fresh iteration on demand."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import Request

from core import api, db
from deps import get_current_user
from cortex.optimization_loop import run_for_user, _serialize

logger = logging.getLogger(__name__)


@api.get("/cortex/optimization/log")
async def optimization_log(request: Request, limit: int = 8):
    """Recent OODA-loop findings for this user, newest first."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 30))
    cur = db.cortex_optimization_log.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("created_at", -1).limit(limit)
    items = [_serialize(d) async for d in cur]
    return {"items": items, "count": len(items)}


@api.get("/cortex/optimization/status")
async def optimization_status(request: Request):
    """Headline status for the right-rail 'Cortex is monitoring' card."""
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d  = now - timedelta(days=7)

    # Newest finding still considered 'active' (<24h old).
    latest = await db.cortex_optimization_log.find_one(
        {"user_id": user.user_id, "created_at": {"$gte": since_24h}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    detections_24h = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "created_at": {"$gte": since_24h}})
    detections_7d  = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "created_at": {"$gte": since_7d}})

    improved = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "learning": "improved",
         "created_at": {"$gte": since_7d}})

    return {
        "active":              latest is not None,
        "latest":              _serialize(latest) if latest else None,
        "detections_24h":      detections_24h,
        "detections_7d":       detections_7d,
        "improved_7d":         improved,
        "monitoring_since":    None,  # placeholder for future onboarding ts
    }


@api.post("/cortex/optimization/run-now")
async def optimization_run_now(request: Request):
    """Trigger a fresh OODA iteration immediately for this user.
    Useful for the 'Scan now' button in the UI."""
    user = await get_current_user(request)
    try:
        doc = await run_for_user(user.user_id)
    except Exception:
        logger.exception("optimization_run_now failed")
        doc = None
    return {"ran": True, "fired": doc is not None, "finding": doc}
