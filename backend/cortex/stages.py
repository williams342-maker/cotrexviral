"""Cortex 5-stage Discovery-First conversation machine.

Replaces the old "intent → plan card immediately" pattern with a
consultant-style flow:

    discovery → analysis → recommendation → mission_proposal → execution

The LLM classifier returns the CURRENT stage + a stage-appropriate
response. Plan cards are gated: they NEVER render unless the user has
already accepted a recommendation OR explicitly asked for execution.

Public API:
    classify_and_respond(message, user_id, history, memory_block) -> {
        stage, ack, clarifying_questions, findings,
        intent, params, recommendation, recommendation_offered,
        explicit_execution_request,
    }
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Five canonical stages.
STAGES = ("discovery", "analysis", "recommendation",
            "mission_proposal", "execution")


# Regex shortcuts users can use to bypass discovery and jump straight
# to execution. Phrases like "just launch it" / "create the mission now"
# trigger the explicit_execution_request path → Plan Card immediately.
_EXEC_OVERRIDE = re.compile(
    r"\b(just (do|launch|run) it|skip (discovery|analysis|planning|the questions)"
    r"|create (the )?mission( now)?|launch( it| this| the mission)?( now)?"
    r"|do it|go ahead|run it|execute( it)?( now)?|start (it|the mission)( now)?)\b",
    re.IGNORECASE,
)

# Phrases that signal recommendation acceptance ("yes please create a mission").
_ACCEPT = re.compile(
    r"\b(yes|yeah|yep|sure|okay|ok|sounds good|please do|go ahead|"
    r"create (a |the )?mission|create it|let's do it|do it|launch( it)?)\b",
    re.IGNORECASE,
)


STAGE_CLASSIFIER_PROMPT = """\
You are Cortex's stage controller — a consultant-style orchestrator for an
AI growth operating system. Read the user's latest message + recent
conversation + accumulated context, and decide which of these stages this
turn belongs to:

  discovery        — Cortex is still gathering goal/context. Ask
                     clarifying questions. NO recommendations, NO plans.
  analysis         — Cortex is researching (website/campaign/competitor/
                     marketplace scan). Acknowledge what you're scanning;
                     surface preliminary findings if any.
  recommendation   — Discovery + Analysis have produced enough context.
                     Present FINDINGS + REASONING + an alternative or two,
                     and ASK whether the user wants to create a mission.
                     Do NOT produce a plan card yet.
  mission_proposal — User accepted the recommendation (or explicitly asked
                     for execution). NOW propose a concrete mission and a
                     plan card can render. Provide `intent` from the list
                     below.
  execution        — User clicked Launch/Automate already; reserved for
                     post-execute follow-up turns. (You almost never set
                     this — it's set by the execute endpoint.)

Rules for stage progression — be conservative:

  1) New topics start in `discovery` unless the user clearly provided
     full context (goal, scope, and at least one constraint).
  2) Move from `discovery` → `analysis` only when at least ONE of:
        - the user has answered 2+ clarifying questions
        - the user explicitly named a target (e.g. "for woodworking" or
          "from etsy") AND a desired outcome (e.g. "recruit 50 sellers")
  3) Move from `analysis` → `recommendation` after you've named at least
     2 concrete findings.
  4) Move from `recommendation` → `mission_proposal` ONLY when the user
     says yes / accept / "create the mission" / "let's do it" / etc.
  5) If the user uses an explicit-execute phrase (e.g. "just launch it",
     "create the mission now", "skip the planning"), set
     `explicit_execution_request: true` AND stage = `mission_proposal`,
     bypassing the funnel.

Available mission intents (only set when stage is `mission_proposal`):
  %(intents)s

Return STRICT JSON only — no prose, no fences. Schema:

{
  "stage": "discovery|analysis|recommendation|mission_proposal|execution",
  "discovery_complete": true|false,
  "analysis_complete": true|false,
  "recommendation_accepted": true|false,
  "explicit_execution_request": true|false,
  "ack": "<your reply to the user — matches the stage's tone>",
  "clarifying_questions": ["<question1>", "<question2>"],
  "findings": ["<finding1>", "<finding2>"],
  "recommendation_summary": "<1-2 sentence headline of what you'd recommend, ONLY when stage is recommendation or later>",
  "alternatives": ["<alt1>", "<alt2>"],
  "intent": "<one of the intents above, ONLY when stage is mission_proposal>",
  "params": {}
}

Tone:
  - discovery     → curious, 1-2 short questions max
  - analysis      → diagnostic, share what you're scanning
  - recommendation→ executive briefing, findings + reasoning + ask
  - mission_proposal → action-oriented, confirms the plan
"""


async def classify_and_respond(
    *,
    user_message: str,
    user_id: str,
    history: list[dict],
    memory_block: str = "",
    intent_types: list[str],
) -> dict:
    """Run the stage classifier. Returns a dict with `stage`, `ack`,
    `clarifying_questions`, `findings`, plus optional `intent` / `params`
    when the stage advances to `mission_proposal`. Plan-card synthesis is
    handled by the caller (only when stage ∈ {mission_proposal, execution})."""
    from core import EMERGENT_LLM_KEY

    # ----- Fast-path: explicit execution override --------------------
    if _EXEC_OVERRIDE.search(user_message):
        fallback_intent = _regex_intent(user_message, intent_types)
        return {
            "stage":                       "mission_proposal",
            "discovery_complete":          True,
            "analysis_complete":           True,
            "recommendation_accepted":     True,
            "explicit_execution_request":  True,
            "ack":                         "Okay — skipping discovery. Here's the plan.",
            "clarifying_questions":        [],
            "findings":                    [],
            "recommendation_summary":      "",
            "alternatives":                [],
            "intent":                      fallback_intent.get("intent") or "find_opportunities",
            "params":                      fallback_intent.get("params") or {},
        }

    # ----- LLM-driven stage classification ---------------------------
    if not EMERGENT_LLM_KEY:
        return _heuristic_response(user_message, intent_types)

    try:
        from cortex.llm_provider import cortex_chat
        system = STAGE_CLASSIFIER_PROMPT % {"intents": ", ".join(intent_types)}
        if memory_block:
            system = f"{system}\n\n---\n{memory_block}"

        # Compose a short transcript for context (last 10 turns).
        if history:
            transcript = "\n".join(
                f"[{h.get('role','user')}] {(h.get('message') or '')[:240]}"
                for h in history[-10:]
            )
            user_payload = (
                f"Recent conversation:\n{transcript}\n\n"
                f"Latest user message:\n{user_message}"
            )
        else:
            user_payload = f"Latest user message:\n{user_message}"

        raw, _label = await cortex_chat(
            system=system,
            user_text=user_payload,
            session_id=f"cortex-stage-{user_id}-{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            prefer="claude",
            json_mode=True,
        )
        data = json.loads(raw)
        return _normalize(data, intent_types)
    except Exception:
        logger.exception("classify_and_respond: LLM failed, using heuristic fallback")
        return _heuristic_response(user_message, intent_types)


# ---------------------------------------------------------------- helpers
def _normalize(data: dict, intent_types: list[str]) -> dict:
    stage = data.get("stage") or "discovery"
    if stage not in STAGES:
        stage = "discovery"
    intent = data.get("intent") if data.get("intent") in intent_types else None
    return {
        "stage":                       stage,
        "discovery_complete":          bool(data.get("discovery_complete")),
        "analysis_complete":           bool(data.get("analysis_complete")),
        "recommendation_accepted":     bool(data.get("recommendation_accepted")),
        "explicit_execution_request":  bool(data.get("explicit_execution_request")),
        "ack":                         str(data.get("ack") or "")[:600],
        "clarifying_questions": [
            str(q)[:160] for q in (data.get("clarifying_questions") or [])
        ][:3],
        "findings": [
            str(f)[:200] for f in (data.get("findings") or [])
        ][:5],
        "recommendation_summary":      str(data.get("recommendation_summary") or "")[:300],
        "alternatives": [
            str(a)[:160] for a in (data.get("alternatives") or [])
        ][:3],
        "intent":                      intent,
        "params":                      data.get("params") or {},
    }


def _heuristic_response(message: str, intent_types: list[str]) -> dict:
    """Offline fallback when LLM is unavailable. Defaults to discovery
    unless an _EXEC_OVERRIDE phrase appeared (already handled) or the
    message reads like a clear "yes accept"."""
    accepted = bool(_ACCEPT.search(message))
    if accepted:
        fb = _regex_intent(message, intent_types)
        return _normalize({
            "stage":                   "mission_proposal",
            "discovery_complete":      True,
            "analysis_complete":       True,
            "recommendation_accepted": True,
            "ack":                     "Got it. Here's the plan.",
            "intent":                  fb.get("intent") or "find_opportunities",
            "params":                  fb.get("params") or {},
        }, intent_types)
    # Default discovery prompt.
    return _normalize({
        "stage":                "discovery",
        "ack":                  "Tell me a bit more so I can help. What outcome are you trying to achieve, and what's the biggest blocker right now?",
        "clarifying_questions": ["What outcome are you trying to achieve?",
                                  "What's your biggest blocker right now?"],
    }, intent_types)


def _regex_intent(message: str, intent_types: list[str]) -> dict:
    """Lightweight intent guess for the override / accept paths."""
    m = message.lower()
    if any(k in m for k in ("seller", "maker", "recruit", "etsy", "shopify", "woodwork", "ceramic")):
        target = 50
        match = re.search(r"\b(\d{1,4})\b", m)
        if match:
            try: target = int(match.group(1))
            except Exception: pass
        niche = None
        for n in ("woodworking", "ceramic", "candle", "leather", "jewelry", "pottery"):
            if n in m:
                niche = n; break
        return {"intent": "launch_seller_mission",
                "params": {"target": target, **({"niche": niche} if niche else {})}}
    if "content" in m or "post" in m:
        return {"intent": "generate_content_plan", "params": {}}
    if "outreach" in m or "email" in m:
        return {"intent": "run_bulk_outreach", "params": {}}
    if "competitor" in m or "competit" in m:
        return {"intent": "analyze_competitors", "params": {}}
    if "retent" in m or "churn" in m:
        return {"intent": "launch_retention_workflow", "params": {}}
    return {"intent": "find_opportunities", "params": {}}


def should_render_plan_card(stage_data: dict) -> bool:
    """Recommendation Confidence Gate.
    Plan card renders iff:
      - explicit_execution_request, OR
      - stage in (mission_proposal, execution) with recommendation_accepted
    """
    if stage_data.get("explicit_execution_request"):
        return True
    if stage_data.get("stage") in ("mission_proposal", "execution"):
        return True
    return False
