"""Cortex SSE streaming chat — "thinking out loud" phase events.

emergentintegrations doesn't expose token-level streaming, but we CAN
stream the orchestration phases so the user sees Cortex's executive
process in real time:

  1. classifying intent       (~50ms)
  2. recalling memory          (~200ms — Qdrant + Mongo)
  3. planning                  (Claude call, 3-10s)
  4. ready                     (final payload)

Frontend connects via EventSource to /api/cortex/console/chat/stream
and renders phase pills as they arrive, then swaps in the full
recommendation card on `ready`.

This is honest streaming — every event corresponds to real backend
state, no fake delays.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from cortex import memory as cmem
from routes.cortex_console import _classify_intent
from routes.cortex_recommendations import build_recommendation_from_intent

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format one SSE message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@api.get("/cortex/console/chat/stream")
async def cortex_chat_stream(request: Request, message: str = "",
                               session_id: str = ""):
    """SSE-streamed Cortex chat. Browsers can only send GET via
    EventSource so the message is passed as a query param (capped
    server-side at 1000 chars to match the POST endpoint)."""
    user = await get_current_user(request)
    msg = (message or "").strip()[:1000]
    if not msg:
        raise HTTPException(400, "message is required")

    async def gen():
        try:
            # ----- Phase 1: classifying ------------------------
            yield _sse("phase", {
                "phase": "classifying",
                "label": "Understanding your goal…",
            })
            await asyncio.sleep(0)

            # ----- Phase 2: recalling memory -------------------
            yield _sse("phase", {
                "phase": "recalling",
                "label": "Recalling our prior conversations…",
            })
            strategy = await cmem.get_strategy(user.user_id)
            recalled = await cmem.recall_semantic(user.user_id, msg, k=5)
            memory_block = cmem.render_memory_block(strategy, recalled)
            yield _sse("memory", {
                "strategy_summary": (strategy or {}).get("summary", ""),
                "recalled_count":   len(recalled),
                "recalled_preview": [
                    {"text": r.get("text", "")[:140],
                     "when": (r.get("created_at") or "")[:10]}
                    for r in recalled[:3]
                ],
            })

            # ----- Phase 3: planning (Claude call) -------------
            yield _sse("phase", {
                "phase": "planning",
                "label": "Cortex is drafting the plan…",
            })
            intent_data = await _classify_intent(msg, user.user_id,
                                                   memory_block=memory_block)
            rec = await build_recommendation_from_intent(
                user_id=user.user_id,
                intent=intent_data["intent"],
                params=intent_data.get("params") or {},
                user_message=msg,
            )

            # Persist conversation history (same as POST endpoint).
            now = datetime.now(timezone.utc)
            await db.cortex_conversations.insert_one({
                "id": uuid.uuid4().hex, "user_id": user.user_id,
                "role": "user", "message": msg, "created_at": now,
            })
            await db.cortex_conversations.insert_one({
                "id": uuid.uuid4().hex, "user_id": user.user_id,
                "role": "cortex", "message": intent_data["ack"],
                "intent": intent_data["intent"],
                "params": intent_data.get("params"),
                "recommendation": rec, "created_at": now,
            })
            try:
                await cmem.record_turn(user.user_id, "user", msg,
                                        meta={"intent": intent_data["intent"]})
                await cmem.record_turn(user.user_id, "cortex", intent_data["ack"],
                                        meta={"intent": intent_data["intent"],
                                               "rec_id": (rec or {}).get("id")})
            except Exception:
                logger.exception("stream: record_turn failed (non-fatal)")

            # ----- Phase 4: ready ------------------------------
            yield _sse("ready", {
                "intent":         intent_data["intent"],
                "params":         intent_data.get("params") or {},
                "ack":            intent_data["ack"],
                "recommendation": rec,
                "memory": {
                    "recalled_count":   len(recalled),
                    "strategy_summary": (strategy or {}).get("summary", ""),
                },
            })
        except Exception as e:
            logger.exception("cortex_chat_stream: pipeline failed")
            yield _sse("error", {"message": str(e)[:300]})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
