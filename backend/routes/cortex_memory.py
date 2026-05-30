"""Cortex memory + execution-log REST endpoints.

Powers the new Conversational Command Center:
  - GET  /api/cortex/memory/strategy     → current strategy doc
  - POST /api/cortex/memory/recall       → semantic recall (debug)
  - POST /api/cortex/memory/refresh      → re-distill strategy now
  - GET  /api/cortex/memory/health       → qdrant + provider chain
  - GET  /api/cortex/execution-log       → recent agent activity for
                                            the bottom drawer in the UI
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from cortex import memory as cmem
from cortex.llm_provider import active_chain

logger = logging.getLogger(__name__)


class RecallPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    k:     int = Field(5, ge=1, le=20)


@api.get("/cortex/memory/strategy")
async def memory_strategy(request: Request, refresh: bool = False):
    """Return the user's strategic-memory doc. ?refresh=true triggers
    a re-distillation before returning."""
    user = await get_current_user(request)
    if refresh:
        doc = await cmem.update_strategy_summary(user.user_id, force=True)
    else:
        doc = await cmem.get_strategy(user.user_id)
        if not doc:
            # Soft-initialize on first read so the UI has something to render.
            doc = await cmem.update_strategy_summary(user.user_id, force=True)
    return doc or {}


@api.post("/cortex/memory/refresh")
async def memory_refresh(request: Request):
    user = await get_current_user(request)
    doc = await cmem.update_strategy_summary(user.user_id, force=True)
    return doc or {}


@api.post("/cortex/memory/recall")
async def memory_recall(payload: RecallPayload, request: Request):
    user = await get_current_user(request)
    hits = await cmem.recall_semantic(user.user_id, payload.query, k=payload.k)
    return {"query": payload.query, "hits": hits, "count": len(hits)}


@api.get("/cortex/memory/health")
async def memory_health(request: Request):
    await get_current_user(request)
    info = await cmem.health()
    info["provider_chain"] = active_chain(prefer="claude")
    return info


# ---------------------------------------------------------- exec log
@api.get("/cortex/execution-log")
async def cortex_execution_log(request: Request, limit: int = 30):
    """Aggregate recent execution activity for the bottom drawer:
      - cortex_recommendations_log (auto-launched / queued)
      - cortex_approval_queue      (pending approvals)
      - mission events             (scout/creator/operator/intelligence ticks)
      - agent_usage_ledger         (LLM/agent calls)
    Returns a unified time-sorted feed of recent actions.
    """
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 100))
    since = datetime.now(timezone.utc) - timedelta(days=7)

    feed: list[dict] = []

    async def _scan(coll, query, transform):
        try:
            cur = db[coll].find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
            async for row in cur:
                item = transform(row)
                if item:
                    feed.append(item)
        except Exception:
            logger.exception("execution-log: scan %s failed", coll)

    base = {"user_id": user.user_id, "created_at": {"$gte": since}}

    await _scan("cortex_recommendations_log", base, lambda r: {
        "kind":  "auto_launched",
        "title": (r.get("recommendation") or {}).get("title") or r.get("type"),
        "type":  r.get("type"),
        "level": r.get("autonomy_level"),
        "status": r.get("status"),
        "created_at": _iso(r.get("created_at")),
    })
    await _scan("cortex_approval_queue", base, lambda r: {
        "kind":  "queued_for_approval",
        "title": (r.get("recommendation") or {}).get("title") or "Plan awaiting approval",
        "type":  (r.get("recommendation") or {}).get("type"),
        "level": r.get("autonomy_level"),
        "status": r.get("status"),
        "queue_id": r.get("id"),
        "created_at": _iso(r.get("created_at")),
    })
    await _scan("cortex_drafts", base, lambda r: {
        "kind":  "draft_saved",
        "title": (r.get("recommendation") or {}).get("title") or "Plan saved as draft",
        "type":  (r.get("recommendation") or {}).get("type"),
        "level": r.get("autonomy_level"),
        "created_at": _iso(r.get("created_at")),
    })
    # Missions launched
    await _scan("missions", {"user_id": user.user_id,
                              "created_at": {"$gte": since}}, lambda r: {
        "kind":  "mission_launched",
        "title": r.get("title") or "Mission",
        "type":  r.get("mission_type") or "mission",
        "level": r.get("autonomy_level"),
        "status": r.get("status"),
        "mission_id": r.get("id"),
        "created_at": _iso(r.get("created_at")),
    })
    # Agent run log (cheap surface — last few ticks)
    await _scan("agent_run_log", {"user_id": user.user_id,
                                    "created_at": {"$gte": since}}, lambda r: {
        "kind":  "agent_tick",
        "title": f"{r.get('agent_id') or 'agent'} · {r.get('event') or 'tick'}",
        "agent": r.get("agent_id"),
        "event": r.get("event"),
        "created_at": _iso(r.get("created_at")),
    })

    # Sort & cap.
    feed.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"items": feed[:limit], "count": min(len(feed), limit)}


def _iso(v) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return v if isinstance(v, str) else None
