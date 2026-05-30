"""AI Command Center — the conversational + proactive Cortex console.

Three responsibilities:

1. **Briefing** (`GET /api/cortex/console/briefing`) — proactive
   morning briefing computed from REAL platform data: seller-OS funnel,
   running missions, churn risk, recent campaign performance. Returns
   the top 3 opportunities + the single highest-confidence recommendation.

2. **Conversation** (`POST /api/cortex/console/chat`) — LLM hybrid: an
   Emergent-LLM-Key-powered intent classifier extracts (intent_type,
   params) from free-form natural language. The deterministic
   recommendation engine then builds the plan + reasoning + confidence
   so the response is always grounded in real data, never hallucinated.

3. **Execution** (`POST /api/cortex/console/execute`) — routes the
   approved recommendation through the user's autonomy level (L0-L5).
   Each level has a specific behavior (Create Draft / Queue for
   Approval / Launch / Full Autonomous) and the response surfaces which
   path was taken so the user is never surprised.

NO chatbot. The LLM only classifies + paraphrases — actual plans,
metrics, costs, and outcomes are all derived from real DB state by
`cortex_recommendations.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db, EMERGENT_LLM_KEY
from deps import get_current_user
from routes.cortex_recommendations import (
    build_briefing,
    build_recommendation_from_intent,
    AUTONOMY_BEHAVIOR,
    INTENT_TYPES,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------
class ChatPayload(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


class ExecutePayload(BaseModel):
    recommendation: dict     # shape from cortex_recommendations
    override_autonomy: Optional[int] = None  # one-off level override


# ---------------------------------------------------------------------
# LLM intent classifier
# ---------------------------------------------------------------------
INTENT_PROMPT = """You are Cortex, an AI business strategist for CortexViral. Your only job here is to read the operator's natural-language message and classify the INTENT.

Reply with STRICT JSON only. No prose. Schema:
{
  "intent": one of [%(intents)s],
  "params": {
    "niche": string or null,
    "target": int or null,
    "deadline_days": int or null,
    "channel": string or null,
    "free_form": string or null
  },
  "ack": short (<=120 chars) confirmation in Cortex's voice, e.g. "I'll plan a 50-seller woodworking mission and surface the brief for your review."
}

Intent catalogue:
- launch_seller_mission: user wants to recruit sellers (any verb: recruit, find, acquire, get, source). Extract niche + target count.
- run_bulk_outreach: user wants to outreach existing leads (push outreach, contact qualified leads).
- launch_retention_workflow: user wants to win back at-risk sellers, run churn recovery.
- generate_content_plan: user wants a content/post/campaign plan or social calendar.
- launch_ads_campaign: user wants paid ads (Google, Meta, TikTok ads).
- analyze_competitors: user wants competitor or category research.
- find_opportunities: user wants Cortex to surface growth opportunities proactively (open-ended "find me something").
- improve_conversions: user wants to lift conversion / funnel performance.
- explain: user wants Cortex to explain something (last mission, a metric, etc.).
- unknown: anything that doesn't match.

If the user mentions a number, set `target`. If they mention a niche/category/vertical (woodworking, candle-makers, jewelry, etc.), set `niche`. If they mention a deadline ("by Father's Day", "this month", "in 14 days"), convert to `deadline_days` (integer days from today, best estimate)."""


async def _classify_intent(message: str, user_id: str) -> dict:
    """Run the message through the LLM intent classifier. Falls back
    to a deterministic regex when EMERGENT_LLM_KEY is missing or LLM
    errors — keeps the chat endpoint working offline / on key outage."""
    fallback = _regex_intent(message)
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage
        import json, re
        system = INTENT_PROMPT % {"intents": ", ".join(INTENT_TYPES)}
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY,
                    session_id=f"cortex-intent-{user_id}-{uuid.uuid4().hex[:8]}",
                    system_message=system)
            .with_model("openai", "gpt-5")
        )
        raw, _ = await send_with_usage(
            chat, UserMessage(text=message),
            agent_id="cortex", user_id=user_id, model="gpt-5",
        )
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
        data = json.loads(text)
        intent = data.get("intent")
        if intent not in INTENT_TYPES:
            return fallback
        return {
            "intent": intent,
            "params": data.get("params") or {},
            "ack":    str(data.get("ack") or "")[:160],
        }
    except Exception:
        logger.exception("cortex chat: LLM classification failed, using regex fallback")
        return fallback


def _regex_intent(message: str) -> dict:
    """Offline-safe intent fallback. Catches the most common verbs."""
    import re
    m = (message or "").lower().strip()
    params: dict = {}

    # Target count
    num = re.search(r"\b(\d{1,5})\b", m)
    if num:
        params["target"] = int(num.group(1))

    # Niche (rough)
    NICHES = ["woodworking", "candle", "jewelry", "ceramics", "leather",
              "knitting", "soap", "pottery", "art print", "stationery"]
    for n in NICHES:
        if n in m:
            params["niche"] = n
            break

    if any(v in m for v in ("recruit", "acquire seller", "find seller", "find maker",
                              "source seller", "onboard seller", "seller acquisition")):
        return {"intent": "launch_seller_mission", "params": params,
                "ack": "I'll draft a seller acquisition mission and surface the plan."}
    if any(v in m for v in ("outreach", "contact qualified", "push outreach")):
        return {"intent": "run_bulk_outreach", "params": params,
                "ack": "Pulling qualified leads ready for outreach."}
    if any(v in m for v in ("retention", "win back", "churn", "save at-risk")):
        return {"intent": "launch_retention_workflow", "params": params,
                "ack": "Identifying at-risk sellers for a retention workflow."}
    if any(v in m for v in ("content plan", "content calendar", "post plan", "campaign")):
        return {"intent": "generate_content_plan", "params": params,
                "ack": "Sketching a content plan based on your category."}
    if any(v in m for v in ("ads campaign", "google ads", "meta ads", "facebook ads", "tiktok ads")):
        return {"intent": "launch_ads_campaign", "params": params,
                "ack": "Drafting an ads brief for your approval."}
    if any(v in m for v in ("competitor", "competition", "rivals")):
        return {"intent": "analyze_competitors", "params": params,
                "ack": "Running a competitor scan."}
    if any(v in m for v in ("opportunit", "growth", "what should i")):
        return {"intent": "find_opportunities", "params": params,
                "ack": "Surfacing your top growth opportunities."}
    if any(v in m for v in ("conversion", "improve conversion", "optimize funnel")):
        return {"intent": "improve_conversions", "params": params,
                "ack": "Auditing your funnel for conversion lifts."}
    if any(v in m for v in ("explain", "what is", "why")):
        return {"intent": "explain", "params": params,
                "ack": "Let me break that down."}
    return {"intent": "unknown", "params": params,
            "ack": "I'm not sure I understood — try 'recruit 50 woodworking makers' or 'find growth opportunities'."}


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
@api.get("/cortex/console/briefing")
async def console_briefing(request: Request):
    """The proactive morning briefing — pulled from real DB state."""
    user = await get_current_user(request)
    return await build_briefing(user.user_id)


@api.get("/cortex/console/opportunities")
async def console_opportunities(request: Request, limit: int = 20):
    """A larger feed of opportunities (used by the bottom-of-page
    continuous stream). Same engine as the briefing, just paginated."""
    user = await get_current_user(request)
    briefing = await build_briefing(user.user_id, max_opportunities=max(1, min(limit, 50)))
    return {"opportunities": briefing.get("opportunities", []),
            "count": len(briefing.get("opportunities", []))}


@api.post("/cortex/console/chat")
async def console_chat(payload: ChatPayload, request: Request):
    """Natural-language conversation. Returns a recommendation card —
    NOT executed. The user must hit Execute (which honors autonomy)."""
    user = await get_current_user(request)
    intent_data = await _classify_intent(payload.message, user.user_id)
    rec = await build_recommendation_from_intent(
        user_id=user.user_id,
        intent=intent_data["intent"],
        params=intent_data.get("params") or {},
        user_message=payload.message,
    )
    # Persist the chat turn so the Conversations history works.
    await db.cortex_conversations.insert_one({
        "id":         uuid.uuid4().hex,
        "user_id":    user.user_id,
        "role":       "user",
        "message":    payload.message[:1000],
        "created_at": datetime.now(timezone.utc),
    })
    await db.cortex_conversations.insert_one({
        "id":             uuid.uuid4().hex,
        "user_id":        user.user_id,
        "role":           "cortex",
        "message":        intent_data["ack"],
        "intent":         intent_data["intent"],
        "params":         intent_data.get("params"),
        "recommendation": rec,
        "created_at":     datetime.now(timezone.utc),
    })
    return {
        "intent":         intent_data["intent"],
        "params":         intent_data.get("params") or {},
        "ack":            intent_data["ack"],
        "recommendation": rec,
    }


@api.get("/cortex/console/history")
async def console_history(request: Request, limit: int = 40):
    """Recent chat turns for replay on first load."""
    user = await get_current_user(request)
    cur = db.cortex_conversations.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("created_at", -1).limit(min(200, max(1, limit)))
    rows = await cur.to_list(length=limit)
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    rows.reverse()  # oldest-first for chat replay
    return {"turns": rows, "count": len(rows)}


@api.post("/cortex/console/execute")
async def console_execute(payload: ExecutePayload, request: Request):
    """Route an approved recommendation through the user's autonomy
    level. Returns the action taken + a human-readable explanation."""
    user = await get_current_user(request)
    rec = payload.recommendation
    if not isinstance(rec, dict) or not rec.get("type"):
        raise HTTPException(400, "Invalid recommendation payload")

    # Resolve effective autonomy level.
    user_doc = await db.users.find_one({"user_id": user.user_id}) or {}
    level = payload.override_autonomy
    if level is None:
        level = user_doc.get("autonomy_level", 2)
    level = max(0, min(5, int(level)))

    behavior = AUTONOMY_BEHAVIOR.get(rec["type"], {}).get(level)
    if behavior is None:
        # Fall back to a generic table when the rec type doesn't have
        # an explicit autonomy matrix yet (shouldn't happen — engine
        # always emits one).
        behavior = ("draft" if level <= 1 else
                    "queue" if level <= 2 else
                    "launch")

    # Execute per behavior.
    if behavior == "draft":
        return await _execute_draft(user.user_id, rec, level)
    if behavior == "queue":
        return await _execute_queue(user.user_id, rec, level)
    if behavior == "launch":
        return await _execute_launch(user.user_id, rec, level)
    if behavior == "auto":
        # Full-autonomous — still launch, but flag the row so the
        # mission-loop knows it can self-iterate without human gates.
        return await _execute_launch(user.user_id, rec, level, autopilot=True)

    raise HTTPException(500, f"Unknown autonomy behavior: {behavior}")


async def _execute_draft(user_id: str, rec: dict, level: int) -> dict:
    """L0 — persist a draft row, no side effect."""
    rid = uuid.uuid4().hex
    await db.cortex_drafts.insert_one({
        "id":         rid,
        "user_id":    user_id,
        "recommendation": rec,
        "autonomy_level": level,
        "status":     "draft",
        "created_at": datetime.now(timezone.utc),
    })
    return {
        "action_taken": "draft",
        "draft_id":     rid,
        "autonomy_level": level,
        "message":      "Saved as a draft. Open the Missions page to review and approve.",
    }


async def _execute_queue(user_id: str, rec: dict, level: int) -> dict:
    """L1/L2 — generate the plan + put it in the approval queue."""
    qid = uuid.uuid4().hex
    await db.cortex_approval_queue.insert_one({
        "id":         qid,
        "user_id":    user_id,
        "recommendation": rec,
        "autonomy_level": level,
        "status":     "pending_approval",
        "created_at": datetime.now(timezone.utc),
    })
    return {
        "action_taken": "queued",
        "queue_id":     qid,
        "autonomy_level": level,
        "message":      "Plan generated and queued for your approval. Review it in the Missions page.",
    }


async def _execute_launch(user_id: str, rec: dict, level: int,
                           autopilot: bool = False) -> dict:
    """L3-L5 — actually launch the action. Each rec type has its own
    side effect (launch mission, fire outreach, etc.)."""
    t = rec["type"]
    payload = rec.get("action_payload") or {}
    msg_prefix = "Cortex is now executing autonomously: " if autopilot else ""

    if t == "launch_seller_mission":
        # Reuse the existing mission creation pipeline.
        from routes.missions import _create_mission_core
        try:
            mission_id = await _create_mission_core(
                user_id=user_id,
                title=rec.get("title") or "Seller Acquisition Mission",
                description=rec.get("expected_outcome") or "",
                metric="sellers_recruited",
                target=int(payload.get("target", 50)),
                mission_type="seller_acquisition",
                seller_target_niche=payload.get("niche"),
                autonomy_level=level,
                budget_usd_cap=payload.get("budget_usd_cap") or rec.get("estimated_cost_usd"),
            )
            return {
                "action_taken": "launched",
                "mission_id":   mission_id,
                "autonomy_level": level,
                "message":      f"{msg_prefix}Mission launched. Scout team is sourcing leads now.",
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("console execute: launch_seller_mission failed")
            raise HTTPException(500, "Failed to launch mission. Check backend logs.")

    if t == "run_bulk_outreach":
        # Bulk-queue outreach for all qualified leads of the user.
        cursor = db.seller_leads.find(
            {"user_id": user_id, "stage": "qualified"}).limit(50)
        leads = await cursor.to_list(length=50)
        fired = 0
        for lead in leads:
            try:
                from routes.seller_outreach import _record_event, _advance_stage_for_event
                evt = await _record_event(user_id, lead["id"], "sent",
                                           channel="email",
                                           offer_type=lead.get("source") and "free_seo_audit",
                                           extra={"by": "cortex_console_bulk"})
                new_stage = _advance_stage_for_event("sent")
                if new_stage:
                    await db.seller_leads.update_one(
                        {"id": lead["id"]},
                        {"$set": {"stage": new_stage,
                                  "updated_at": datetime.now(timezone.utc)}},
                    )
                fired += 1
            except Exception:
                logger.exception("bulk outreach failed for lead=%s", lead.get("id"))
        return {
            "action_taken": "launched",
            "leads_fired":  fired,
            "autonomy_level": level,
            "message":      f"{msg_prefix}Outreach fired to {fired} qualified seller(s).",
        }

    if t == "launch_retention_workflow":
        from routes.seller_retention_intel import scan_all_active
        res = await scan_all_active(user_id=user_id)
        return {
            "action_taken": "launched",
            **res,
            "autonomy_level": level,
            "message":      f"{msg_prefix}Retention scan complete. "
                            f"Scanned {res['scanned']} · "
                            f"workflows launched {res['workflows_launched']}.",
        }

    # Generic — persist as launched record without external side effect.
    # (analyse_competitors, generate_content_plan, etc. — those plans
    # surface as opportunities for now; deeper integrations come later.)
    rid = uuid.uuid4().hex
    await db.cortex_recommendations_log.insert_one({
        "id":         rid,
        "user_id":    user_id,
        "type":       t,
        "recommendation": rec,
        "autonomy_level": level,
        "status":     "logged",
        "created_at": datetime.now(timezone.utc),
    })
    return {
        "action_taken": "logged",
        "log_id":       rid,
        "autonomy_level": level,
        "message":      f"{msg_prefix}Cortex recorded the recommendation. Deep execution for `{t}` ships in the next iteration.",
    }
