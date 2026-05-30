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
    conversation_id: Optional[str] = None     # multi-thread support


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


async def _classify_intent(message: str, user_id: str,
                            memory_block: str = "") -> dict:
    """Run the message through the LLM intent classifier via the
    provider-abstracted cortex_tool_call (native tool-calling under
    LiteLLM, with JSON-mode fallback). Falls back to a deterministic
    regex when EMERGENT_LLM_KEY is missing or every provider errors —
    keeps the chat endpoint working offline / on key outage.

    `memory_block` is the optional strategic+semantic memory snapshot
    rendered by `cortex.memory.render_memory_block()`; injected into the
    system prompt so Cortex's classification & ack reference the user's
    long-term goals rather than starting from scratch every turn."""
    fallback = _regex_intent(message)
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        from cortex.llm_provider import cortex_tool_call
        system = INTENT_PROMPT % {"intents": ", ".join(INTENT_TYPES)}
        if memory_block:
            system = f"{system}\n\n---\n{memory_block}"
        tool = {
            "name":        "classify_intent",
            "description": "Classify the operator's message into an intent + extract mission parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": list(INTENT_TYPES)},
                    "params": {
                        "type": "object",
                        "properties": {
                            "niche":         {"type": ["string", "null"]},
                            "target":        {"type": ["integer", "null"]},
                            "deadline_days": {"type": ["integer", "null"]},
                            "channel":       {"type": ["string", "null"]},
                            "free_form":     {"type": ["string", "null"]},
                        },
                    },
                    "ack": {"type": "string",
                              "description": "Short (<=120 chars) confirmation in Cortex's voice."},
                },
                "required": ["intent", "ack"],
            },
        }
        args, _label, mode = await cortex_tool_call(
            system=system,
            user_text=message,
            tool=tool,
            session_id=f"cortex-intent-{user_id}-{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            prefer="claude",
            required=["intent"],
        )
        if not args:
            return fallback
        intent = args.get("intent")
        if intent not in INTENT_TYPES:
            return fallback
        logger.debug("cortex intent: %s via %s", intent, mode)
        return {
            "intent": intent,
            "params": args.get("params") or {},
            "ack":    str(args.get("ack") or "")[:160],
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
    """Discovery-First conversation. Cortex behaves like a consultant:
    discovery → analysis → recommendation → mission_proposal → execution.

    Plan cards are GATED — they only render when the user has accepted
    a recommendation OR explicitly asked for execution. Otherwise the
    turn is text-only (clarifying questions, findings, or a soft
    "Would you like me to create a mission?" CTA)."""
    user = await get_current_user(request)

    # ---- Conversation scope ----
    # Use the caller-supplied conversation_id when provided so we can
    # support ChatGPT-style multi-thread history; default to "legacy"
    # for backwards-compat with pre-multi-thread rows.
    conv_id = (payload.conversation_id or "").strip() or "legacy"

    # ---- Memory snapshot before classification ----
    from cortex import memory as cmem
    from cortex.stages import classify_and_respond, should_render_plan_card
    strategy = await cmem.get_strategy(user.user_id)
    recalled = await cmem.recall_semantic(user.user_id, payload.message, k=5)
    memory_block = cmem.render_memory_block(strategy, recalled)

    # Pull last ~10 turns for stage continuity.
    hist_cur = db.cortex_conversations.find(
        {"user_id": user.user_id}, {"_id": 0, "role": 1, "message": 1, "stage": 1},
    ).sort("created_at", -1).limit(10)
    history = [h async for h in hist_cur]
    history.reverse()

    stage_data = await classify_and_respond(
        user_message=payload.message,
        user_id=user.user_id,
        history=history,
        memory_block=memory_block,
        intent_types=INTENT_TYPES,
    )

    # Plan card is GATED — only synthesized when the consultant funnel
    # advances to mission_proposal+ OR the user explicitly requests execution.
    rec = None
    if should_render_plan_card(stage_data) and stage_data.get("intent"):
        rec = await build_recommendation_from_intent(
            user_id=user.user_id,
            intent=stage_data["intent"],
            params=stage_data.get("params") or {},
            user_message=payload.message,
        )

    now = datetime.now(timezone.utc)
    # Persist the chat turn so the Conversations history works.
    await db.cortex_conversations.insert_one({
        "id":              uuid.uuid4().hex,
        "user_id":         user.user_id,
        "conversation_id": conv_id,
        "role":            "user",
        "message":         payload.message[:1000],
        "stage":           stage_data["stage"],
        "created_at":      now,
    })
    await db.cortex_conversations.insert_one({
        "id":              uuid.uuid4().hex,
        "user_id":         user.user_id,
        "conversation_id": conv_id,
        "role":            "cortex",
        "message":         stage_data["ack"],
        "stage":           stage_data["stage"],
        "intent":          stage_data.get("intent"),
        "params":          stage_data.get("params"),
        "clarifying_questions": stage_data.get("clarifying_questions"),
        "findings":        stage_data.get("findings"),
        "recommendation_summary": stage_data.get("recommendation_summary"),
        "alternatives":    stage_data.get("alternatives"),
        "recommendation":  rec,
        "created_at":      now,
    })

    # ---- Embed into Qdrant (best-effort) ----
    try:
        await cmem.record_turn(user.user_id, "user", payload.message,
                                meta={"stage": stage_data["stage"]})
        await cmem.record_turn(user.user_id, "cortex", stage_data["ack"],
                                meta={"stage": stage_data["stage"],
                                       "intent": stage_data.get("intent"),
                                       "rec_id": (rec or {}).get("id")})
    except Exception:
        logger.exception("cortex chat: memory record_turn failed (non-fatal)")

    # ---- Periodic strategy refresh (every 8 turns) ----
    try:
        if await db.cortex_conversations.count_documents(
            {"user_id": user.user_id}) % 8 == 0:
            await cmem.update_strategy_summary(user.user_id)
    except Exception:
        logger.exception("cortex chat: strategy refresh failed (non-fatal)")

    # ---- Auto-rename conversation after 4+ turns ----
    # On the 4th total turn (2nd round-trip), let Claude generate a
    # concise 3-7 word title that replaces the verbose first-message
    # default. Stored on cortex_conversation_meta so the history
    # sidebar picks it up immediately.
    try:
        if conv_id and conv_id != "legacy":
            cnt = await db.cortex_conversations.count_documents(
                {"user_id": user.user_id, "conversation_id": conv_id})
            existing_meta = await db.cortex_conversation_meta.find_one(
                {"user_id": user.user_id, "conversation_id": conv_id},
                {"_id": 0, "auto_renamed": 1})
            if cnt >= 4 and not (existing_meta or {}).get("auto_renamed"):
                await _maybe_auto_rename(user.user_id, conv_id)
    except Exception:
        logger.exception("cortex chat: auto-rename failed (non-fatal)")

    return {
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
        "findings":                stage_data.get("findings") or [],
        "recommendation_summary":  stage_data.get("recommendation_summary") or "",
        "alternatives":            stage_data.get("alternatives") or [],
        "recommendation":          rec,
        "memory": {
            "strategy_summary": (strategy or {}).get("summary", "") if strategy else "",
            "recalled_count":   len(recalled),
        },
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
        result = await _execute_draft(user.user_id, rec, level)
    elif behavior == "queue":
        result = await _execute_queue(user.user_id, rec, level)
    elif behavior == "launch":
        result = await _execute_launch(user.user_id, rec, level)
    elif behavior == "auto":
        # Full-autonomous — still launch, but flag the row so the
        # mission-loop knows it can self-iterate without human gates.
        result = await _execute_launch(user.user_id, rec, level, autopilot=True)
    else:
        raise HTTPException(500, f"Unknown autonomy behavior: {behavior}")

    # ----- Auto follow-up turn ---------------------------------------
    # After execution, Cortex appends a contextual refinement question
    # so the conversation never feels "over" — the user just hired an
    # autonomous teammate and can keep collaborating with them.
    try:
        followup_text = _build_followup_text(rec, result)
        if followup_text:
            followup_doc = {
                "id":             uuid.uuid4().hex,
                "user_id":        user.user_id,
                "role":           "cortex",
                "message":        followup_text,
                "intent":         "followup",
                "followup_for":   result.get("mission_id") or result.get("queue_id") or result.get("draft_id"),
                "rec_type":       rec.get("type"),
                "created_at":     datetime.now(timezone.utc),
            }
            await db.cortex_conversations.insert_one(followup_doc)
            # Strip _id for response.
            followup_doc.pop("_id", None)
            followup_doc["created_at"] = followup_doc["created_at"].isoformat()
            result["followup"] = {
                "id":      followup_doc["id"],
                "message": followup_doc["message"],
                "for":     followup_doc["followup_for"],
            }
    except Exception:
        logger.exception("console_execute: follow-up generation failed (non-fatal)")

    return result


def _build_followup_text(rec: dict, result: dict) -> str:
    """Generate Cortex's contextual follow-up message based on the
    type of plan executed + the action taken. Deterministic (not LLM)
    so it's instant + cheap. Mirrors the chat tone."""
    t = rec.get("type")
    action = result.get("action_taken")
    mid = result.get("mission_id")
    qid = result.get("queue_id")
    payload = rec.get("action_payload") or {}
    niche = payload.get("niche")
    target = payload.get("target")

    head = ""
    if action == "launched" and mid:
        head = f"Mission launched (`{mid[:8]}`). Current phase: **Discovery**. "
    elif action == "queued":
        head = f"Plan queued for approval (`{(qid or '')[:8]}`). "
    elif action == "draft":
        head = "Saved as draft. "

    if t == "launch_seller_mission":
        niche_str = niche or "your target category"
        target_str = target or "your goal"
        body = (
            f"I'm now scanning Etsy, Shopify, and {niche_str} communities for {target_str} candidate sellers. "
            "While I work, would you like me to:\n"
            "  • focus on premium / high-AOV sellers\n"
            "  • focus on high-volume / many-listings sellers\n"
            "  • prioritize a specific region (e.g. Pacific Northwest, EU, UK)\n"
            "  • surface anything else I should weight in qualification?"
        )
        return head + body

    if t == "run_bulk_outreach":
        body = (
            "Outreach is firing now. Want me to:\n"
            "  • A/B test two subject lines\n"
            "  • throttle to N sends per hour\n"
            "  • auto-attach a personalized audit PDF to every message?"
        )
        return head + body

    if t == "launch_retention_workflow":
        body = (
            "Retention scan started — I'll surface at-risk sellers as I find them. "
            "Want me to auto-trigger the churn-recovery email sequence, or hold and let you review each one?"
        )
        return head + body

    if t in ("launch_ads_campaign", "generate_content_plan"):
        body = (
            "Working on it now. Any constraints I should respect — budget cap, brand voice, channels to exclude?"
        )
        return head + body

    # Generic fallback so the conversation always continues.
    if head:
        return head + "I'll keep you posted as updates land. Anything else you want me to weight while I work?"
    return ""


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



async def _maybe_auto_rename(user_id: str, conv_id: str) -> None:
    """Generate a concise 3-7 word title from the conversation so far
    and store it on cortex_conversation_meta. Best-effort; failures
    are logged and silently ignored."""
    rows = []
    cur = db.cortex_conversations.find(
        {"user_id": user_id, "conversation_id": conv_id},
        {"_id": 0, "role": 1, "message": 1},
    ).sort("created_at", 1).limit(10)
    async for r in cur:
        rows.append(r)
    if len(rows) < 2:
        return
    transcript = "\n".join(
        f"[{r.get('role','user')}] {(r.get('message') or '')[:200]}"
        for r in rows
    )[:3000]
    try:
        from cortex.llm_provider import cortex_chat
        raw, _label = await cortex_chat(
            system=(
                "You write short, descriptive titles for business conversations. "
                "Return JSON: {\"title\": \"<3-7 words, no punctuation, no quotes>\"}. "
                "Capture the subject of the conversation, not the act of talking. "
                "Examples: 'Recruit Etsy woodworking sellers', "
                "'Q3 outreach throttling', 'Father's Day campaign plan'."
            ),
            user_text=f"Conversation:\n{transcript}",
            session_id=f"cortex-title-{user_id}-{conv_id[:8]}",
            user_id=user_id, prefer="claude", json_mode=True,
        )
        import json as _json
        data = _json.loads(raw)
        title = str(data.get("title") or "").strip()[:80]
    except Exception:
        logger.exception("auto_rename: LLM call failed (non-fatal)")
        return
    if not title:
        return
    await db.cortex_conversation_meta.update_one(
        {"user_id": user_id, "conversation_id": conv_id},
        {"$set": {"title": title, "auto_renamed": True,
                   "updated_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
