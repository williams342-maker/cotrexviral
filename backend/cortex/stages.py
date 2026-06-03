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

import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Five canonical stages.
STAGES = ("discovery", "analysis", "recommendation",
            "mission_proposal", "execution",
            # `action` is the Action-First bypass stage (see
            # cortex.action_first). The classifier never emits this —
            # it's only set by the Action-First router.
            "action")


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
                     surface preliminary findings if any. NEVER end an
                     analysis turn with a promise to do future work
                     (e.g. "Let me pull together a picture", "I'll come
                     back with…"). Either deliver findings NOW or ask
                     a clarifying question NOW — the backend does not
                     auto-resume; the user is staring at your message
                     waiting.
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
  3a) ANALYSIS DELIVERY RULE — when stage IS `analysis`, you MUST return
     EITHER `findings.length >= 2` (concrete observations the user can
     verify) OR `clarifying_questions.length >= 1` (a specific question
     that unblocks the next step). NEVER return an analysis turn with
     empty findings AND empty clarifying_questions — that strands the
     user with no visible next action. If you genuinely lack the data
     to surface findings, switch to a clarifying question naming the
     specific data gap (e.g. "I can't see your conversion rate — what
     was last month's signup-to-active rate?").
  4) Move from `recommendation` → `mission_proposal` ONLY when the user
     says yes / accept / "create the mission" / "let's do it" / etc.
  5) If the user uses an explicit-execute phrase (e.g. "just launch it",
     "create the mission now", "skip the planning"), set
     `explicit_execution_request: true` AND stage = `mission_proposal`,
     bypassing the funnel.

DISCOVERY TRIGGERS — fire discovery ONLY when at least one is true:

  A) Goal is genuinely ambiguous (e.g. "grow my business" with no
     target, niche, channel, or KPI).
  B) User is about to spend significant money or burn a one-shot
     resource (ad budget, outreach to limited high-value list).
  C) User's request conflicts with the available evidence (e.g.
     they're asking to find more leads when 100+ qualified leads
     already exist in their pipeline).

If NONE of A/B/C apply — produce value immediately. Go straight to
analysis, recommendation, or action. Senior consultants don't
interview before doing useful work.

DISCOVERY BUDGET — a runtime counter (discovery_count) is provided
below. If discovery_count >= 2, you MUST advance the stage. NEVER
return another `discovery` turn after the budget is exhausted —
move to `analysis` or `recommendation` even if context is imperfect.
Cortex must produce value after at most 2 clarification rounds.

ANSWER SHORTCUTS — when stage IS `discovery`, your clarifying
questions MUST be accompanied by 3-6 candidate ANSWERS the user can
click to advance. Each shortcut is a short label (3-6 words) that, if
clicked, reduces uncertainty. Examples:
  Question: "Why are you recruiting sellers?"
  Shortcuts: ["Marketplace growth", "Inventory expansion",
              "Founder cohort", "Revenue goal", "Community"]
NEVER repeat the same question as a shortcut. Shortcuts must move
the conversation forward.

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
  "answer_shortcuts": ["<short answer 1>", "<short answer 2>", ...],
  "findings": ["<finding1>", "<finding2>"],
  "recommendation_summary": "<1-2 sentence headline of what you'd recommend, ONLY when stage is recommendation or later>",
  "alternatives": ["<alt1>", "<alt2>"],
  "intent": "<one of the intents above, ONLY when stage is mission_proposal>",
  "params": {}
}

Tone:
  - discovery     → curious, executive consultant. CHALLENGE assumptions
                    when the user proposes a solution without first
                    naming the problem (e.g. "I want more traffic" →
                    push back: "Why traffic? What's your current
                    conversion rate? Will more traffic actually move
                    revenue, or just cost?"). Ask 1-2 short questions
                    that interrogate the underlying GOAL, not just
                    surface preferences. ALWAYS end the `ack` with a
                    question mark.
  - analysis      → diagnostic, share what you're scanning AND DELIVER —
                    either name specific findings or ask one specific
                    question. No "I'll work on it" hedges; do the work
                    in this turn.
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
    discovery_count: int = 0,
) -> dict:
    """Run the stage classifier. Returns a dict with `stage`, `ack`,
    `clarifying_questions`, `answer_shortcuts`, `findings`, plus
    optional `intent` / `params` when the stage advances to
    `mission_proposal`. Plan-card synthesis is handled by the caller
    (only when stage ∈ {mission_proposal, execution}).

    `discovery_count` is the number of prior discovery turns in the
    current conversation. Used to enforce the Discovery Budget —
    after 2 rounds, the classifier output is post-processed to force
    progression to analysis/recommendation."""
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
        from cortex.llm_provider import cortex_tool_call
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
                f"discovery_count (turns already spent on discovery): {discovery_count}\n"
                + ("⚠️ DISCOVERY BUDGET EXHAUSTED — you MUST advance past discovery this turn.\n"
                    if discovery_count >= 2 else "")
                + f"\nLatest user message:\n{user_message}"
            )
        else:
            user_payload = (
                f"discovery_count (turns already spent on discovery): {discovery_count}\n"
                + ("⚠️ DISCOVERY BUDGET EXHAUSTED — you MUST advance past discovery this turn.\n"
                    if discovery_count >= 2 else "")
                + f"\nLatest user message:\n{user_message}"
            )

        tool = {
            "name":        "classify_stage_response",
            "description": "Classify the conversation stage and produce Cortex's response with clarifying questions / findings / recommendation as appropriate for that stage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string", "enum": list(STAGES)},
                    "discovery_complete":         {"type": "boolean"},
                    "analysis_complete":          {"type": "boolean"},
                    "recommendation_accepted":    {"type": "boolean"},
                    "explicit_execution_request": {"type": "boolean"},
                    "ack":                        {"type": "string"},
                    "clarifying_questions":       {"type": "array",
                                                   "items": {"type": "string"}},
                    "answer_shortcuts":           {"type": "array",
                                                   "items": {"type": "string"},
                                                   "description": "Short clickable answers when stage=discovery. NEVER mirror the question."},
                    "findings":                   {"type": "array",
                                                   "items": {"type": "string"}},
                    "recommendation_summary":     {"type": "string"},
                    "alternatives":               {"type": "array",
                                                   "items": {"type": "string"}},
                    "intent":                     {"type": ["string", "null"],
                                                   "enum": list(intent_types) + [None]},
                    "params":                     {"type": "object"},
                },
                "required": ["stage", "ack"],
            },
        }
        args, _label, _mode = await cortex_tool_call(
            system=system,
            user_text=user_payload,
            tool=tool,
            session_id=f"cortex-stage-{user_id}-{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            # Stage classification is structured, narrow output — Haiku 4.5
            # nails it in ~2-4s vs Sonnet's ~6-15s, and the difference is
            # invisible at the UI layer because the answer is constrained
            # by the tool schema. Failover chain (haiku → claude → gpt)
            # still keeps reliability.
            prefer="haiku",
            required=["stage", "ack"],
        )
        if not args:
            return _heuristic_response(user_message, intent_types)
        result = _normalize(args, intent_types)

        # ----- Discovery Budget enforcement -------------------------
        # If we've already burned 2 discovery rounds and the model
        # STILL returned discovery, force progression to analysis so
        # the user always sees forward motion after 2 rounds.
        if discovery_count >= 2 and result["stage"] == "discovery":
            logger.info("classify_and_respond: budget exhausted, forcing advance")
            result["stage"] = "analysis"
            result["discovery_complete"] = True
            # Replace the pure-question ack with a "moving forward" message.
            if not result["findings"]:
                result["findings"] = [
                    "Working with what we have so far — happy to refine as we go.",
                ]
            if "?" in (result.get("ack") or "") and not result.get("recommendation_summary"):
                result["ack"] = (
                    "I have enough to work with. Let me share what I'm seeing "
                    "and a recommendation — we can refine from there."
                )
        return result
    except Exception:
        logger.exception("classify_and_respond: LLM failed, using heuristic fallback")
        return _heuristic_response(user_message, intent_types)


# ---------------------------------------------------------------- helpers
def _normalize(data: dict, intent_types: list[str]) -> dict:
    stage = data.get("stage") or "discovery"
    if stage not in STAGES:
        stage = "discovery"
    intent = data.get("intent") if data.get("intent") in intent_types else None
    ack = str(data.get("ack") or "")[:600]
    clarifying = [str(q)[:160] for q in (data.get("clarifying_questions") or [])][:3]
    # Answer shortcuts (3-6 short clickable answers). Stripped down to
    # avoid noise — drop any that are obvious mirrors of the question.
    raw_short = [str(s).strip() for s in (data.get("answer_shortcuts") or [])]
    answer_shortcuts: list[str] = []
    seen = set()
    for s in raw_short:
        if not s or len(s) > 60:
            continue
        # Reject shortcuts that look like restatements of any clarifying
        # question (the spec forbids this).
        if "?" in s:
            continue
        low = s.lower()
        if low in seen:
            continue
        seen.add(low)
        answer_shortcuts.append(s)
        if len(answer_shortcuts) >= 6:
            break

    # Discovery-stage UX: the spec requires the assistant to actually
    # ask a question, not just preamble. If Claude's ack ends without
    # a '?', append the first clarifying question so the user always
    # sees a concrete prompt to answer.
    if stage == "discovery" and ack and "?" not in ack and clarifying:
        ack = f"{ack.rstrip(' .:;,')} — {clarifying[0]}"
    return {
        "stage":                       stage,
        "discovery_complete":          bool(data.get("discovery_complete")),
        "analysis_complete":           bool(data.get("analysis_complete")),
        "recommendation_accepted":     bool(data.get("recommendation_accepted")),
        "explicit_execution_request":  bool(data.get("explicit_execution_request")),
        "ack":                         ack,
        "clarifying_questions":        clarifying,
        "answer_shortcuts":            answer_shortcuts,
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
