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
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from cortex import memory as cmem
from cortex.stages import classify_and_respond, should_render_plan_card
from routes.cortex_console import INTENT_TYPES
from routes.cortex_recommendations import build_recommendation_from_intent

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format one SSE message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@api.get("/cortex/console/chat/stream")
async def cortex_chat_stream(request: Request, message: str = "",
                               session_id: str = "",
                               conversation_id: str = ""):
    """SSE-streamed Cortex chat. Browsers can only send GET via
    EventSource so the message is passed as a query param (capped
    server-side at 1000 chars to match the POST endpoint).

    Implementation note — proxy survival:
      Production traffic flows through Cloudflare + K8s ingress before
      reaching uvicorn. Both layers can buffer responses or drop
      idle connections during long-running awaits (the `planning`
      Claude call takes 5-15s with zero bytes on the wire). To keep
      the stream alive:
        1. We emit an SSE comment immediately to force header flush.
        2. A background heartbeat task pushes `: heartbeat` comments
           every 5s onto the same queue the pipeline pushes events.
        3. The generator drains the queue until the pipeline signals
           completion (or error), then closes cleanly.
      EventSource silently ignores comment lines, so this is invisible
      to the client but prevents the "Connection closed before
      completion" failure mode on production.
    """
    user = await get_current_user(request)
    msg = (message or "").strip()[:1000]
    if not msg:
        raise HTTPException(400, "message is required")
    conv_id = (conversation_id or "").strip() or "legacy"

    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    DONE = None  # sentinel

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(5)
                await queue.put(": heartbeat\n\n")
        except asyncio.CancelledError:
            return

    async def _pipeline():
        try:
            # ----- Phase 1: classifying ------------------------
            await queue.put(_sse("phase", {
                "phase": "classifying",
                "label": "Understanding your goal…",
            }))

            # ----- Phase 2: recalling memory + loading history -------
            # All three reads are independent (Mongo strategy lookup,
            # embedding-backed semantic recall, Mongo history) — run them
            # concurrently. Saves ~1-2s vs the previous sequential chain.
            await queue.put(_sse("phase", {
                "phase": "recalling",
                "label": "Recalling our prior conversations…",
            }))
            hist_cur = db.cortex_conversations.find(
                {"user_id": user.user_id, "conversation_id": conv_id},
                {"_id": 0, "role": 1, "message": 1, "stage": 1},
            ).sort("created_at", -1).limit(10)
            strategy, recalled, history = await asyncio.gather(
                cmem.get_strategy(user.user_id),
                cmem.recall_semantic(user.user_id, msg, k=5),
                hist_cur.to_list(10),
            )
            history.reverse()
            discovery_count = sum(
                1 for turn in history
                if turn.get("role") == "cortex"
                and turn.get("stage") == "discovery"
            )
            memory_block = cmem.render_memory_block(strategy, recalled)
            await queue.put(_sse("memory", {
                "strategy_summary": (strategy or {}).get("summary", ""),
                "recalled_count":   len(recalled),
                "recalled_preview": [
                    {"text": r.get("text", "")[:140],
                     "when": (r.get("created_at") or "")[:10]}
                    for r in recalled[:3]
                ],
            }))

            # ----- Phase 3: planning (LLM stage classifier) ----
            await queue.put(_sse("phase", {
                "phase": "planning",
                "label": "Cortex is thinking through your goal…",
            }))

            stage_data = await classify_and_respond(
                user_message=msg,
                user_id=user.user_id,
                history=history,
                memory_block=memory_block,
                intent_types=INTENT_TYPES,
                discovery_count=discovery_count,
            )

            rec = None
            if should_render_plan_card(stage_data) and stage_data.get("intent"):
                rec = await build_recommendation_from_intent(
                    user_id=user.user_id,
                    intent=stage_data["intent"],
                    params=stage_data.get("params") or {},
                    user_message=msg,
                )

            now = datetime.now(timezone.utc)
            # Persist both turns in parallel — independent inserts.
            await asyncio.gather(
                db.cortex_conversations.insert_one({
                    "id": uuid.uuid4().hex, "user_id": user.user_id,
                    "conversation_id": conv_id,
                    "role": "user", "message": msg,
                    "stage": stage_data["stage"], "created_at": now,
                }),
                db.cortex_conversations.insert_one({
                    "id": uuid.uuid4().hex, "user_id": user.user_id,
                    "conversation_id": conv_id,
                    "role": "cortex", "message": stage_data["ack"],
                    "stage": stage_data["stage"],
                    "intent": stage_data.get("intent"),
                    "params": stage_data.get("params"),
                    "clarifying_questions": stage_data.get("clarifying_questions"),
                    "answer_shortcuts": stage_data.get("answer_shortcuts") or [],
                    "findings": stage_data.get("findings"),
                    "recommendation_summary": stage_data.get("recommendation_summary"),
                    "alternatives": stage_data.get("alternatives"),
                    "recommendation": rec, "created_at": now,
                }),
            )
            # Memory-write embedding calls are ~1-2s each. They're not on
            # the user's critical path — fire and forget so we can flush
            # `ready` immediately. Errors are logged but never block.
            async def _memo_record():
                try:
                    await cmem.record_turn(user.user_id, "user", msg,
                                            meta={"stage": stage_data["stage"]})
                    await cmem.record_turn(user.user_id, "cortex", stage_data["ack"],
                                            meta={"stage": stage_data["stage"],
                                                   "intent": stage_data.get("intent"),
                                                   "rec_id": (rec or {}).get("id")})
                except Exception:
                    logger.exception("stream: record_turn failed (non-fatal)")
            asyncio.create_task(_memo_record())

            # ----- Phase 4: ready ------------------------------
            await queue.put(_sse("ready", {
                "conversation_id":         conv_id,
                "stage":                   stage_data["stage"],
                "discovery_complete":      stage_data["discovery_complete"],
                "analysis_complete":       stage_data["analysis_complete"],
                "recommendation_accepted": stage_data["recommendation_accepted"],
                "explicit_execution_request": stage_data["explicit_execution_request"],
                "intent":                  stage_data.get("intent"),
                "params":                  stage_data.get("params") or {},
                "ack":                     stage_data["ack"],
                "clarifying_questions":    stage_data.get("clarifying_questions") or [],
                "answer_shortcuts":        stage_data.get("answer_shortcuts") or [],
                "findings":                stage_data.get("findings") or [],
                "recommendation_summary":  stage_data.get("recommendation_summary") or "",
                "alternatives":            stage_data.get("alternatives") or [],
                "recommendation":          rec,
                "memory": {
                    "recalled_count":   len(recalled),
                    "strategy_summary": (strategy or {}).get("summary", ""),
                },
            }))
        except Exception as e:
            logger.exception("cortex_chat_stream: pipeline failed")
            err_msg = str(e)
            if ("Budget has been exceeded" in err_msg
                    or ("BadRequestError" in err_msg and "Budget" in err_msg)):
                friendly = ("Emergent LLM key budget exhausted. "
                            "Go to Profile → Universal Key → Add Balance "
                            "(or enable auto top-up) to keep Cortex running.")
            elif "EMERGENT_LLM_KEY" in err_msg:
                friendly = ("Emergent LLM key is missing on the server. "
                            "Contact Emergent Support to restore it.")
            elif "rate limit" in err_msg.lower():
                friendly = "Hit an upstream rate limit. Wait a moment and try again."
            else:
                friendly = err_msg[:300]
            await queue.put(_sse("error", {"message": friendly}))
        finally:
            await queue.put(DONE)

    async def gen():
        # Force the proxy to flush response headers immediately. This
        # alone fixes most "Connection closed before completion"
        # failures caused by buffering proxies (Cloudflare etc.).
        yield ": cortex-stream open\n\n"

        pipeline_task = asyncio.create_task(_pipeline())
        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            while True:
                item = await queue.get()
                if item is DONE:
                    break
                yield item
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            # Pipeline should already be done by the time DONE was
            # enqueued, but await defensively to surface any late
            # cancellation cleanly.
            try:
                await pipeline_task
            except Exception:
                logger.exception("cortex_chat_stream: pipeline_task tail")

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache, no-transform",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection":        "keep-alive",
        },
    )
