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
from typing import List, Optional

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


# ---------------------------------------------------- user-facing memory
#  Powers the "Cortex Memory" section in Account Settings. Lets a user
#  see exactly what Cortex remembers about them, pin important turns so
#  they survive the per-user cap pruner, delete individual turns, and
#  wipe the whole thing. The strategic-memory doc is returned by the
#  existing `/cortex/memory/strategy` endpoint above.

class MemoryListResp(BaseModel):
    items:        list[dict]
    total_stored: int
    pinned_count: int


@api.get("/cortex/memory/me")
async def my_memory(request: Request, limit: int = 50, q: str = ""):
    """Return the current user's stored conversation turns, newest
    first. Pinned turns always appear at the top regardless of recency.
    Optional `q` filter does a case-insensitive substring search.
    Excludes the `vector` field (large + meaningless to humans)."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 200))

    base_filter = {"user_id": user.user_id}
    if q.strip():
        # Plain regex; we don't need fuzzy search here since semantic
        # recall already exists. This is for "did Cortex actually
        # record that I said X?" inspection.
        base_filter["text"] = {"$regex": q.strip()[:80], "$options": "i"}

    cur = db[cmem.COLLECTION_V2].find(
        base_filter,
        {"_id": 0, "id": 1, "role": 1, "text": 1,
         "created_at": 1, "meta": 1, "pinned": 1},
    ).sort([("pinned", -1), ("created_at", -1)]).limit(limit)
    rows = await cur.to_list(length=limit)
    for r in rows:
        ts = r.get("created_at")
        if isinstance(ts, datetime):
            r["created_at"] = ts.isoformat()
        # Trim long bodies for the UI list — full text is shown on hover.
        r["preview"] = (r.get("text") or "")[:240]
    total = await db[cmem.COLLECTION_V2].count_documents({"user_id": user.user_id})
    pinned = await db[cmem.COLLECTION_V2].count_documents(
        {"user_id": user.user_id, "pinned": True}
    )
    return {"items": rows, "total_stored": total, "pinned_count": pinned}


class PinPayload(BaseModel):
    pinned: bool = True


@api.post("/cortex/memory/pin/{turn_id}")
async def pin_memory(turn_id: str, payload: PinPayload, request: Request):
    """Pin (default) or unpin a stored conversation turn. Pinned turns
    bypass the per-user-cap pruner inside `record_turn`."""
    user = await get_current_user(request)
    res = await db[cmem.COLLECTION_V2].update_one(
        {"id": turn_id, "user_id": user.user_id},
        {"$set": {"pinned": bool(payload.pinned)}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Memory turn not found")
    return {"id": turn_id, "pinned": bool(payload.pinned)}


@api.delete("/cortex/memory/turn/{turn_id}")
async def delete_memory(turn_id: str, request: Request):
    user = await get_current_user(request)
    res = await db[cmem.COLLECTION_V2].delete_one(
        {"id": turn_id, "user_id": user.user_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Memory turn not found")
    return {"deleted": True, "id": turn_id}


class BulkDeleteMemoryPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)


@api.post("/cortex/memory/bulk-delete")
async def bulk_delete_memory(payload: BulkDeleteMemoryPayload, request: Request):
    """Bulk-delete memory turns owned by the current user. User-scoped:
    a spoofed id list can never touch another user's vectors. Capped at
    500 ids per batch to match the per-user vector cap."""
    user = await get_current_user(request)
    ids = [i for i in (payload.ids or []) if isinstance(i, str) and i.strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    ids = ids[:500]
    res = await db[cmem.COLLECTION_V2].delete_many(
        {"id": {"$in": ids}, "user_id": user.user_id})
    return {"ok": True, "deleted": int(res.deleted_count), "requested": len(ids)}


@api.delete("/cortex/memory/all")
async def wipe_memory(request: Request):
    """Nuclear option — wipe ALL of this user's stored vectors AND
    their strategy doc. Cortex starts fresh on the next message."""
    user = await get_current_user(request)
    n_vec = (await db[cmem.COLLECTION_V2].delete_many(
        {"user_id": user.user_id}
    )).deleted_count
    n_strat = (await db.cortex_strategy.delete_many(
        {"user_id": user.user_id}
    )).deleted_count
    logger.info("memory wipe by user=%s vectors=%d strategy=%d",
                user.user_id, n_vec, n_strat)
    return {"deleted_vectors": n_vec, "deleted_strategy": n_strat}


@api.get("/cortex/memory/health")
async def memory_health(request: Request):
    await get_current_user(request)
    info = await cmem.health()
    info["provider_chain"] = active_chain(prefer="claude")
    # Surface native-tool-call wrapper stability so we can compare
    # tool-call success rate vs JSON fallback rate over time.
    try:
        from cortex.llm_provider import _tool_call_stats
        info["tool_call_stats"] = _tool_call_stats()
    except Exception:
        pass
    return info


@api.get("/cortex/memory/tool-call-trend")
async def tool_call_trend(request: Request):
    """Durable rolling-window stats from `cortex_tool_call_log`.

    Returns rates for the last 1h / 24h / 7d so the promotion gate
    (rate >0.95 over multiple days) is observable without resetting on
    backend restart. Used by the iter21 monitoring rule before
    promoting the wrapper to more LLM call sites."""
    await get_current_user(request)
    now = datetime.now(timezone.utc)
    windows = {
        "1h":  now - timedelta(hours=1),
        "24h": now - timedelta(hours=24),
        "7d":  now - timedelta(days=7),
    }
    out: dict = {}
    for name, since in windows.items():
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id":          "$mode",
                "n":            {"$sum": 1},
                "avg_latency":  {"$avg": "$latency_ms"},
            }},
        ]
        rows = []
        try:
            async for r in db.cortex_tool_call_log.aggregate(pipeline):
                rows.append(r)
        except Exception:
            logger.exception("tool_call_trend: aggregate failed")
        total = sum(int(r["n"] or 0) for r in rows) or 0
        by_mode = {r["_id"]: int(r["n"] or 0) for r in rows}
        latency_by_mode = {r["_id"]: round(float(r.get("avg_latency") or 0)) for r in rows}
        out[name] = {
            "total":            total,
            "by_mode":          by_mode,
            "tool_call_rate":   (by_mode.get("tool_call", 0) / total) if total else 0.0,
            "fallback_rate":    (by_mode.get("json_fallback", 0) / total) if total else 0.0,
            "hard_fail_rate":   (by_mode.get("hard_fail", 0) / total) if total else 0.0,
            "avg_latency_ms":   latency_by_mode,
        }
    out["promotion_ready"] = (
        out["24h"]["total"] >= 50          # enough volume to be meaningful
        and out["24h"]["tool_call_rate"] >= 0.95
        and out["24h"]["hard_fail_rate"] <= 0.02
    )
    return out


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
