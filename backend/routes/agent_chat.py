"""Per-agent AI chat for the in-dashboard agent workspace.

Each of the six CortexViral specialists (Atlas, Iris, Nova, Sam, Kai, Angela)
gets a dedicated system prompt + an isolated, persistent LLM session keyed
by `agent-{agent_id}-{user_id}` so the conversation memory survives across
page reloads.

Follow-up chips are extracted via an inline format trick: every agent
prompt instructs the model to append `<<FUPS>>["q1","q2","q3"]<<END>>`
after its answer. We parse that out server-side and return a clean answer
+ chips array — so the SPA gets both in a single LLM call (~6s instead of
the ~100s a separate meta call would take).

Multi-agent collaboration: Atlas (Strategy) and other agents can mid-reply
delegate to another specialist via `<<HANDOFF>>iris: <question><<END>>`.
The server detects the marker, invokes that other agent, and splices the
result back into the original answer as a "[Iris reports: …]" inline
block. One delegation per turn, single LLM round-trip per agent.

Endpoints:
  POST /api/ai/agent/chat  body {agent_id, message}  → {answer, follow_ups, memories_used, handoff}
  GET  /api/ai/agent/profile?agent_id=...            → {agent} static metadata
"""
import json
import re
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api
from deps import get_current_user
from routes.ai import _llm_for_user, _gated_user
from routes.plans import record_ai_generation
from routes.model_router import for_agent, for_task
from emergentintegrations.llm.chat import UserMessage


# ---------------------------------------------------------------------------
# Follow-up parsing
# ---------------------------------------------------------------------------
# Match either:
#   <<FUPS>>["..."]<<END>>          — preferred sentinel form
#   <<FUPS>>["..."]                 — graceful fallback if <<END>> was dropped
_FUPS_RE = re.compile(
    r"<<\s*FUPS\s*>>\s*(\[.*?\])\s*(?:<<\s*END\s*>>)?\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _extract_handoff(text: str) -> tuple[str, Optional[dict]]:
    """Strip an optional `<<HANDOFF>>agent: question<<END>>` block from the
    middle of a reply. Returns (cleaned_text, {"agent_id": ..., "question": ...}
    or None). Only one handoff per reply — additional matches are left in
    the text untouched."""
    if not text:
        return "", None
    m = _HANDOFF_RE.search(text)
    if not m:
        return text, None
    agent_id = m.group(1).strip().lower()
    question = m.group(2).strip()
    if not question or agent_id not in AGENTS:
        return text, None
    cleaned = (text[: m.start()] + text[m.end():]).strip()
    return cleaned, {"agent_id": agent_id, "question": question[:300]}


def _extract_followups(raw: str) -> tuple[str, list[str]]:
    """Strip the trailing follow-up sentinel from the model's reply and
    return (clean_answer, [fup1, fup2, fup3]).  Tolerant of malformed JSON —
    on any parse failure we return the raw text unchanged and empty chips."""
    if not raw:
        return "", []
    m = _FUPS_RE.search(raw)
    if not m:
        return raw.strip(), []
    json_blob = m.group(1)
    try:
        chips = json.loads(json_blob)
    except Exception:
        return raw.strip(), []
    if not isinstance(chips, list):
        return raw.strip(), []
    chips = [str(c).strip() for c in chips if str(c).strip()][:3]
    cleaned = raw[: m.start()].rstrip()
    return cleaned, chips


_FUPS_INSTRUCTION = (
    "\n\nAT THE END of every reply, on the very last line, append EXACTLY this "
    "format (no backticks, no prose around it):\n"
    '<<FUPS>>["next question 1","next question 2","next question 3"]<<END>>\n'
    "Each follow-up should be phrased as a first-person request to you "
    "(<=110 chars each), naturally extending the conversation. Never repeat a "
    "follow-up the user already asked. Always include exactly 3."
)

# Handoff sentinel — Atlas (Strategy) is the orchestrator; she can ask Iris
# for live trend data, Sam for an SEO brief, or Angela for an email flow
# mid-reply. The agent emits `<<HANDOFF>>iris: <question><<END>>` BEFORE the
# <<FUPS>> block; we parse it, run the second agent, splice the answer back.
_HANDOFF_RE = re.compile(
    r"<<\s*HANDOFF\s*>>\s*(\w+)\s*:\s*(.+?)\s*<<\s*END\s*>>",
    re.DOTALL | re.IGNORECASE,
)

_HANDOFF_INSTRUCTION = (
    "\n\nMULTI-AGENT MODE: when a sub-task is outside your specialty, you "
    "MAY delegate to another agent ONCE per reply by appending the "
    "following marker BEFORE the <<FUPS>> line:\n"
    "<<HANDOFF>>agent_id: <single specific question><<END>>\n"
    "Available agents to delegate to: iris (research/trends), sam (SEO), "
    "kai (social listening), angela (email), nova (digital marketing). "
    "Use a handoff ONLY when the other agent's specialty would genuinely "
    "improve your answer. Keep the question under 200 chars. The system "
    "will run that agent and splice their reply into your message."
)


# ---------------------------------------------------------------------------
# Agent personas
# ---------------------------------------------------------------------------
AGENTS = {
    "strategy": {
        "id": "strategy",
        "name": "Atlas",
        "role": "AI Strategy Agent",
        "color": "blue",
        "blurb": "Campaign plans, funnels, content calendars, and growth strategy on demand.",
        "system": (
            "You are Atlas, CortexViral's AI Strategy agent. You think like "
            "a fractional CMO: full-funnel plans, campaign blueprints, "
            "content calendars, growth bets, GTM motions. "
            "When the user asks for help, always return a structured plan "
            "with (1) the objective, (2) the 30/60/90-day milestones, "
            "(3) channel-by-channel tactics, (4) leading metrics to track, "
            "(5) the single highest-leverage move to do FIRST. "
            "Be opinionated. If the user's plan has a hole, name it. "
            "Keep replies under 400 words and shippable, not academic."
        ),
    },
    "research": {
        "id": "research",
        "name": "Iris",
        "role": "AI Research Agent",
        "color": "indigo",
        "blurb": "Tracks Reddit, TikTok trends, competitor ads, keyword gaps, and Google Trends.",
        "system": (
            "You are Iris, CortexViral's AI Research agent. You hunt across "
            "Reddit, TikTok, X, Google Trends, competitor ad libraries, and "
            "SERP results for signals worth acting on. "
            "When the user asks for research, always return: "
            "(1) 3-5 emerging trends in their niche this week, (2) the top "
            "competitor moves of the last 14 days, (3) untapped keyword "
            "opportunities, (4) audience pain points surfacing in Reddit/X. "
            "Be specific — name communities, hashtags, accounts. If you'd "
            "need real-time data you don't have, say so and propose the "
            "exact search to run. Keep replies under 350 words."
        ),
    },
    "nova": {
        "id": "nova",
        "name": "Nova",
        "role": "AI Digital Marketer",
        "color": "emerald",
        "blurb": "I build the engine that delivers traffic — SEO, content, analytics, all of it.",
        "system": (
            "You are Nova, CortexViral's AI Digital Marketing strategist. "
            "Tone: confident, founder-empathetic, data-driven. You operate "
            "like the head of growth at a 50-person scale-up. "
            "Default playbook covers: positioning audits, channel-mix advice, "
            "content engines, attribution, and weekly experiment plans. "
            "When the user shares context, surface 2-3 specific actions before "
            "any general advice. Reference earlier turns by content, not index. "
            "Keep replies under 300 words unless they ask for depth. "
            "Use short headers and bullets. Be direct, no hedging."
        ),
    },
    "sam": {
        "id": "sam",
        "name": "Sam",
        "role": "AI SEO / GEO Manager",
        "color": "amber",
        "blurb": "Keyword research to publishing — articles optimised for Google and AI search.",
        "system": (
            "You are Sam, CortexViral's AI SEO + GEO (Generative Engine "
            "Optimisation) manager. You think in clusters, intent, and "
            "topical authority. You write briefs other writers can ship in "
            "an hour. When the user asks for SEO help, always surface: "
            "primary keyword, intent type, top 3 SERP competitors to outrank, "
            "internal-link anchors, and a 6-section H2 outline. "
            "Treat AI search engines (Perplexity, ChatGPT search, Google AI "
            "Overviews) as first-class citizens — recommend the EEAT + "
            "citation signals they prefer. Keep replies tight (under 350 words)."
        ),
    },
    "kai": {
        "id": "kai",
        "name": "Kai",
        "role": "AI Social Listening Manager",
        "color": "rose",
        "blurb": "Track competitors, trends, and conversations across every platform.",
        "system": (
            "You are Kai, CortexViral's AI social listening + competitive "
            "intelligence agent. You scan TikTok, Reels, Shorts, Reddit, X, "
            "and LinkedIn for trend-velocity, competitor moves, and ICP pain "
            "points. When the user asks anything about social, surface: "
            "current trending hooks in their niche, what competitors shipped "
            "in the last 14 days, and 3 specific post angles to capitalise. "
            "Be cheeky, energetic, and reference real-feel signals (\"this "
            "format is +280% velocity in skincare this week\"). Keep replies "
            "under 300 words. Always end with a concrete next action."
        ),
    },
    "angela": {
        "id": "angela",
        "name": "Angela",
        "role": "AI Email Marketer",
        "color": "violet",
        "blurb": "I write, design, and schedule your email campaigns — managed from your inbox.",
        "system": (
            "You are Angela, CortexViral's AI email marketer. You design "
            "lifecycle flows that compound: welcome, browse-abandon, post-"
            "purchase, win-back, monthly digest. You write subject lines that "
            "earn the open. When the user asks for email help, always offer: "
            "a sender persona suggestion, the trigger event, the body skeleton "
            "(hook → context → ask → PS), and 3 subject-line variants with "
            "rationale. Tone: warm, persuasive, never spammy. Keep replies "
            "under 300 words and always shippable."
        ),
    },
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class _ChatRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@api.get("/ai/agent/profile")
async def get_agent_profile(agent_id: str, request: Request):
    """Return public-facing metadata for one agent (no system prompt)."""
    await get_current_user(request)
    agent = AGENTS.get(agent_id.lower())
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")
    return {k: v for k, v in agent.items() if k != "system"}


@api.get("/ai/agent/list")
async def list_agents(request: Request):
    """List every agent the user can chat with."""
    await get_current_user(request)
    return {
        "agents": [
            {k: v for k, v in a.items() if k != "system"}
            for a in AGENTS.values()
        ],
    }


@api.post("/ai/agent/chat")
async def agent_chat(payload: _ChatRequest, request: Request):
    """Send a message to the selected agent. Single LLM call — the agent
    appends an inline `<<FUPS>>[...]<<END>>` block which we strip + parse
    server-side. Keeps total latency ~6s vs ~100s for a separate meta call.

    Also pulls the top-K relevant memories for the user's prompt and
    injects them into the system prompt so the agent gets sharper with
    every interaction."""
    user = await _gated_user(request)
    agent = AGENTS.get(payload.agent_id.lower())
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")

    # Memory retrieval — pull up to 5 relevant memories for THIS prompt.
    # Best-effort: any error inside the memory layer is swallowed so a
    # downstream issue can never block a chat reply.
    memory_block = ""
    used_memories: list[dict] = []
    try:
        from routes.memory import retrieve_relevant, memories_to_prompt_block
        mems = await retrieve_relevant(user.user_id, payload.message, k=5)
        memory_block = memories_to_prompt_block(mems)
        # Strip embeddings + truncate to a chip-friendly preview shape
        used_memories = [
            {
                "id": m.get("id"),
                "kind": m.get("kind"),
                "preview": (m.get("text") or "")[:160],
                "score": m.get("score"),
            }
            for m in mems
        ]
    except Exception:
        pass

    session_id = f"agent-{agent['id']}-{user.user_id}"
    # Atlas (Strategy) is the only agent that gets the handoff capability —
    # she orchestrates. Sub-agents stay focused on their specialty so we
    # don't get infinite delegation loops.
    can_handoff = agent["id"] == "strategy"
    system_prompt = agent["system"] + _FUPS_INSTRUCTION
    if can_handoff:
        system_prompt += _HANDOFF_INSTRUCTION
    if memory_block:
        system_prompt = system_prompt + "\n\n" + memory_block

    # Model routing — picks the right LLM family for the agent's task type.
    provider, model = for_agent(agent["id"])
    chat = await _llm_for_user(
        user.user_id, session_id, system_prompt,
        provider=provider, model=model,
    )
    raw = await chat.send_message(UserMessage(text=payload.message))

    # Optional handoff: strip + run the delegated agent. We do this BEFORE
    # follow-up extraction so the chips still parse cleanly.
    handoff_info = None
    handoff_done = None
    if can_handoff:
        raw, handoff_info = _extract_handoff(raw)
        if handoff_info:
            try:
                handoff_done = await _run_handoff(user.user_id, handoff_info)
                if handoff_done:
                    raw = raw.rstrip() + (
                        f"\n\n📡 **{handoff_done['agent_name']} reports:**\n"
                        f"{handoff_done['answer']}\n"
                    )
            except Exception:
                pass

    answer, follow_ups = _extract_followups(raw)

    # After a successful reply, save a short conversation summary as a
    # memory so the next turn (and other agents) can recall what was said.
    try:
        from routes.memory import remember
        summary = f"User asked {agent['name']}: {payload.message[:200]}"
        await remember(
            user.user_id, "agent_summary", summary,
            meta={"agent": agent["id"]},
        )
    except Exception:
        pass

    await record_ai_generation(user.user_id, f"agent_chat:{agent['id']}")
    return {
        "agent_id": agent["id"],
        "answer": answer,
        "follow_ups": follow_ups,
        "memories_used": used_memories,
        "handoff": handoff_done,  # {agent_id, agent_name, question, answer} or None
    }


# ---------------------------------------------------------------------------
# Handoff runner — call a SECOND agent in a fresh session, return short reply
# ---------------------------------------------------------------------------
async def _run_handoff(user_id: str, handoff: dict) -> Optional[dict]:
    """Run a sub-agent in a one-shot ephemeral session (no FUPS/HANDOFF
    instructions, no memory block, single LLM call). Returns a short reply
    body or None if the call failed."""
    sub = AGENTS.get(handoff["agent_id"])
    if not sub:
        return None
    # Ephemeral session id so this exchange doesn't pollute the sub-agent's
    # main conversation memory with the user.
    import secrets as _sec
    session_id = f"handoff-{sub['id']}-{user_id}-{_sec.token_hex(4)}"
    # Compact system prompt: the agent's persona + a brevity instruction.
    system = (
        sub["system"]
        + "\n\nIMPORTANT: this is a handoff request from another agent. "
        "Reply in 3-5 bullets, under 120 words total. Be specific. "
        "Do NOT add any closing follow-ups or chips — just the answer."
    )
    provider, model = for_agent(sub["id"])
    from routes.ai import _llm_for_user as _llm
    chat = await _llm(user_id, session_id, system,
                      provider=provider, model=model)
    answer = await chat.send_message(UserMessage(text=handoff["question"]))
    return {
        "agent_id": sub["id"],
        "agent_name": sub["name"],
        "question": handoff["question"],
        "answer": (answer or "").strip(),
    }
