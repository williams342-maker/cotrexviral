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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# How long a bridge stays "fresh" for the Mission Dashboard hero. Older
# bridges are still readable via /by-id/{bridge_id}; they just stop being
# surfaced as the proactive recommendation.
_BRIDGE_FRESHNESS_DAYS = 14
# Minimum confidence for a bridge to be considered for the hero card —
# below this we fall back to the briefing's deterministic top_recommendation.
_BRIDGE_MIN_CONFIDENCE = 60


async def _bridge_consumed(user_id: str, bridge_id: str) -> bool:
    """A bridge is 'consumed' once it has been launched/dismissed via
    the hero card. The hero card writes to `cortex_dismissed_plans` on
    dismiss and to `missions` (with `auto_optimize_meta.bridge_id`) on
    launch — either signal removes the bridge from the rotation."""
    if await db.missions.count_documents(
        {"user_id": user_id, "auto_optimize_meta.bridge_id": bridge_id}
    ):
        return True
    if await db.cortex_dismissed_plans.count_documents(
        {"user_id": user_id, "rec_id": bridge_id}
    ):
        return True
    return False


def _bridge_to_rec_card(bridge: dict, rec_payload: dict) -> dict:
    """Wrap a bridge row + the deterministic plan card it maps to into
    the unified shape the Mission Dashboard hero renders."""
    return {
        "source":          "bridge",
        "bridge_id":       bridge.get("id"),
        "title":           bridge.get("finding") or rec_payload.get("title"),
        "summary":         (bridge.get("recommendation")
                            or rec_payload.get("summary")
                            or ""),
        "reasoning":       bridge.get("reasoning") or "",
        "confidence":      int(bridge.get("confidence") or 0),
        "expected_outcome": (bridge.get("expected_impact")
                             or rec_payload.get("expected_outcome") or ""),
        "estimated_timeline_days": rec_payload.get("estimated_timeline_days") or 0,
        "estimated_cost_usd":      rec_payload.get("estimated_cost_usd") or 0,
        "mission_intent":  bridge.get("mission_intent"),
        "recommendation":  rec_payload,   # full plan card for /console/execute
    }


def _briefing_to_rec_card(top_rec: dict) -> dict:
    """Re-shape a briefing's top_recommendation into the unified hero
    payload. `confidence` is stored as 0..1 in plan cards, so we scale
    to 0..100 for display."""
    conf_raw = top_rec.get("confidence") or 0
    try:
        conf_pct = int(round(float(conf_raw) * 100))
    except Exception:
        conf_pct = 0
    return {
        "source":          "briefing",
        "bridge_id":       None,
        "title":           top_rec.get("title") or "Recommended next action",
        "summary":         top_rec.get("summary") or "",
        "reasoning":       "",
        "confidence":      conf_pct,
        "expected_outcome": top_rec.get("expected_outcome") or "",
        "estimated_timeline_days": top_rec.get("estimated_timeline_days") or 0,
        "estimated_cost_usd":      top_rec.get("estimated_cost_usd") or 0,
        "mission_intent":  top_rec.get("type"),
        "recommendation":  top_rec,
    }


@api.get("/cortex/mission-dashboard/recommended-action")
async def get_recommended_action(request: Request):
    """The single 'what should I do next?' card surfaced at the top of
    the Mission Dashboard. Picks (in order):

      1. The newest un-consumed bridge with confidence ≥
         `_BRIDGE_MIN_CONFIDENCE` within the freshness window. Bridges
         carry deep provenance (a finished analysis job), so they're
         strictly higher signal than briefing heuristics.
      2. The deterministic briefing's `top_recommendation` if no bridge
         qualifies. Always non-empty for users with any pipeline state.

    Response shape (or `{has_recommendation: false}` when neither path
    yields a card):
        {
          has_recommendation, source, bridge_id?, title, summary,
          reasoning, confidence (0–100), expected_outcome,
          estimated_timeline_days, estimated_cost_usd, mission_intent,
          recommendation { ... plan card consumed by /cortex/console/execute }
        }
    """
    user = await get_current_user(request)

    # --- Path 1: bridge candidate -----------------------------------
    cutoff = datetime.now(timezone.utc) - timedelta(days=_BRIDGE_FRESHNESS_DAYS)
    cur = db.cortex_recommendation_bridges.find(
        {
            "user_id":     user.user_id,
            "confidence":  {"$gte": _BRIDGE_MIN_CONFIDENCE},
            "created_at":  {"$gte": cutoff},
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(10)

    bridges = [b async for b in cur]
    for bridge in bridges:
        if await _bridge_consumed(user.user_id, bridge.get("id")):
            continue
        # Hydrate the deterministic plan card the bridge's intent maps
        # to — that's what /cortex/console/execute consumes.
        try:
            from routes.cortex_recommendations import build_recommendation_from_intent
            rec_payload = await build_recommendation_from_intent(
                user_id=user.user_id,
                intent=bridge.get("mission_intent") or "find_opportunities",
                params=bridge.get("mission_params") or {},
                user_message=bridge.get("recommendation") or "",
            )
        except Exception:
            logger.exception("recommended-action: bridge → rec card failed")
            continue
        card = _bridge_to_rec_card(bridge, rec_payload)
        card["has_recommendation"] = True
        return card

    # --- Path 2: deterministic briefing fallback --------------------
    try:
        from routes.cortex_recommendations import build_briefing
        briefing = await build_briefing(user.user_id, max_opportunities=4)
    except Exception:
        logger.exception("recommended-action: briefing fallback failed")
        return {"has_recommendation": False}

    top_rec = briefing.get("top_recommendation")
    if not top_rec:
        return {"has_recommendation": False}

    card = _briefing_to_rec_card(top_rec)
    card["has_recommendation"] = True
    return card


@api.get("/cortex/recommendation-bridges/by-id/{bridge_id}")
async def get_bridge_by_id(bridge_id: str, request: Request):
    """Fetch a single bridge by its row id (not by job_id). Used by the
    Mission Detail page to render provenance — every Optimize-via-Bridge
    mission stamps `auto_optimize_meta.bridge_id`, and this endpoint
    hydrates the structured recommendation behind that link."""
    user = await get_current_user(request)
    bridge = await db.cortex_recommendation_bridges.find_one(
        {"id": bridge_id, "user_id": user.user_id}, {"_id": 0})
    if not bridge:
        raise HTTPException(404, "Bridge not found")
    return bridge


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
