"""Endpoints for the Cortex Recommendation Bridge layer.

The bridge is the structured executive recommendation generated from
every completed analysis job. See
`/app/backend/cortex/recommendation_bridge.py` for synthesis logic.

Routes:
  GET    /api/cortex/recommendation-bridges/{job_id}
         Fetch the bridge for a job. Generates it lazily if the job
         is completed but the bridge doesn't exist yet (handles older
         jobs created before the bridge layer shipped).

  POST   /api/cortex/recommendation-bridges/{job_id}/regenerate
         Force re-synthesis (e.g., after the user pushes back via
         "Discuss Recommendation").

  POST   /api/cortex/recommendation-bridges/{job_id}/discuss
         Drop a follow-up Cortex turn into chat explaining the
         reasoning in more depth — wired to the "Discuss
         Recommendation" CTA on the card.

  GET    /api/cortex/recommendation-bridges
         List bridges for the current user (newest first). Future
         home of the Executive Insights / Mission Suggestions panel.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


@api.get("/cortex/recommendation-bridges/{job_id}")
async def get_bridge(job_id: str, request: Request):
    """Return the bridge for a job. If the job is completed but no
    bridge exists yet, generate one on-demand."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")

    from cortex.recommendation_bridge import build_bridge_from_job
    bridge = await build_bridge_from_job(job_id)
    if not bridge:
        raise HTTPException(409,
                            f"Bridge unavailable (job status={j.get('status')})")
    bridge.pop("_id", None)
    return bridge


class RegeneratePayload(BaseModel):
    pushback: Optional[str] = None


@api.post("/cortex/recommendation-bridges/{job_id}/regenerate")
async def regenerate_bridge(job_id: str, payload: RegeneratePayload,
                              request: Request):
    """Discard the existing bridge and synthesize a fresh one. Useful
    when the user has pushed back on Cortex's first recommendation —
    the pushback text is forwarded to the LLM so the new bridge
    addresses the user's concern explicitly.

    Side-effect: when pushback is supplied AND the job has a
    conversation_id, posts the regenerated bridge into chat as a new
    Cortex turn (kind='recommendation_bridge') so the user sees
    Cortex's revised thinking inline."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j.get("status") not in ("completed", "reviewed", "mission_created"):
        raise HTTPException(409,
                            f"Job must be completed first (status={j.get('status')})")

    pushback = (payload.pushback or "").strip() or None
    if not pushback:
        # No pushback → ordinary regenerate (clear existing + resynth).
        await db.cortex_recommendation_bridges.delete_many({"job_id": job_id})

    from cortex.recommendation_bridge import build_bridge_from_job, post_bridge_to_chat
    bridge = await build_bridge_from_job(job_id, pushback=pushback)
    if not bridge:
        raise HTTPException(500, "Bridge synthesis failed")

    # When pushback is supplied, surface the revised bridge in chat so
    # the user immediately sees Cortex's new take.
    if pushback:
        await post_bridge_to_chat(job_id)

    bridge.pop("_id", None)
    return bridge


@api.post("/cortex/recommendation-bridges/{job_id}/discuss")
async def discuss_bridge(job_id: str, request: Request):
    """Wired to the 'Discuss Recommendation' CTA on the card. Drops a
    deeper-reasoning Cortex turn into the conversation so the user can
    push back or interrogate the recommendation."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")

    bridge_doc = await db.cortex_recommendation_bridges.find_one(
        {"job_id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not bridge_doc:
        raise HTTPException(404, "Bridge not found")

    conv_id = j.get("conversation_id")
    if not conv_id:
        latest = await db.cortex_conversations.find_one(
            {"user_id": user.user_id,
              "conversation_id": {"$exists": True}},
            {"_id": 0, "conversation_id": 1},
            sort=[("created_at", -1)],
        )
        conv_id = (latest or {}).get("conversation_id")
    if not conv_id:
        raise HTTPException(409, "No active conversation thread")

    # Compose a deeper explanation. We re-render the four-part frame
    # so the user sees Cortex's reasoning in detail.
    explanation = (
        f"Happy to unpack this further.\n\n"
        f"**What I'm seeing:** {bridge_doc.get('finding') or '—'}\n\n"
        f"**Why it's happening:** {bridge_doc.get('root_cause') or '—'}\n\n"
        f"**What I'd do about it:** {bridge_doc.get('recommendation') or '—'}\n\n"
        f"**Why I'm confident ({bridge_doc.get('confidence', 0)}%):** "
        + (("Strong signal across the report findings."
            if bridge_doc.get("confidence", 0) >= 80
            else "Moderate signal — happy to test an alternative if you "
                  "have a different read.")
           if bridge_doc.get("confidence", 0) > 0
           else "Limited signal — open to alternative directions.")
        + f"\n\n**Expected impact:** {bridge_doc.get('expected_impact') or '—'}\n\n"
        "Want to refine the recommendation, or shall I draft the mission?"
    )

    msg = {
        "id":              uuid.uuid4().hex,
        "conversation_id": conv_id,
        "user_id":         user.user_id,
        "role":            "cortex",
        "message":         explanation,
        "stage":           "recommendation",
        "created_at":      datetime.now(timezone.utc),
        "kind":            "recommendation_discuss",
        "job_id":          job_id,
    }
    await db.cortex_conversations.insert_one(msg)
    return {"ok": True, "conversation_id": conv_id, "message_id": msg["id"]}


@api.get("/cortex/recommendation-bridges")
async def list_bridges(request: Request, limit: int = 20):
    """List the user's bridges newest first. Powers the future
    Executive Insights / Mission Suggestions panel."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 20), 100))
    cur = db.cortex_recommendation_bridges.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    rows = [r async for r in cur]
    return {"bridges": rows, "count": len(rows)}
