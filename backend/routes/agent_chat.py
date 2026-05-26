"""Per-agent AI chat for the in-dashboard agent workspace.

Each of the four CortexViral specialists (Nova, Sam, Kai, Angela) gets a
dedicated system prompt + an isolated, persistent LLM session keyed by
`agent-{agent_id}-{user_id}` so the conversation memory survives across
page reloads.

Follow-up chips are extracted via an inline format trick: every agent
prompt instructs the model to append `<<FUPS>>["q1","q2","q3"]<<END>>`
after its answer. We parse that out server-side and return a clean answer
+ chips array — so the SPA gets both in a single LLM call (~6s instead of
the ~100s a separate meta call would take).

Endpoints:
  POST /api/ai/agent/chat  body {agent_id, message}  → {answer, follow_ups}
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


# ---------------------------------------------------------------------------
# Agent personas
# ---------------------------------------------------------------------------
AGENTS = {
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
    server-side. Keeps total latency ~6s vs ~100s for a separate meta call."""
    user = await _gated_user(request)
    agent = AGENTS.get(payload.agent_id.lower())
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")

    session_id = f"agent-{agent['id']}-{user.user_id}"
    chat = await _llm_for_user(
        user.user_id, session_id, agent["system"] + _FUPS_INSTRUCTION,
    )
    raw = await chat.send_message(UserMessage(text=payload.message))
    answer, follow_ups = _extract_followups(raw)

    await record_ai_generation(user.user_id, f"agent_chat:{agent['id']}")
    return {
        "agent_id": agent["id"],
        "answer": answer,
        "follow_ups": follow_ups,
    }
