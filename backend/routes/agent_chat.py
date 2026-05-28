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
import asyncio
import json
import re
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import api
from deps import get_current_user
from routes.ai import _llm_for_user, _gated_user
from routes.plans import record_ai_generation
from routes.model_router import for_agent, resolve_user_mode, USER_MODES
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
    the text untouched.

    Resolves the captured token through `_AGENT_LOOKUP` so the LLM can
    emit either the agent's display name (`iris`) or its internal id
    (`research`) — both work."""
    if not text:
        return "", None
    m = _HANDOFF_RE.search(text)
    if not m:
        return text, None
    raw_token = m.group(1).strip().lower()
    agent_id = _AGENT_LOOKUP.get(raw_token)
    question = m.group(2).strip()
    if not question or not agent_id:
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


# Lookup: lowercased display name OR internal id → canonical AGENTS key.
# The system prompt instructs the LLM to delegate by NAME ("iris", "sam") —
# we accept either so the parser is forgiving.
_AGENT_LOOKUP: dict[str, str] = {}
for _id, _agent in AGENTS.items():
    _AGENT_LOOKUP[_id] = _id
    _AGENT_LOOKUP[_agent["name"].lower()] = _id


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class _ChatRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=4000)
    # Optional model-routing override. Accepted values are exposed via
    # `GET /api/ai/agent/modes` (`auto` | `fast` | `deep` | `creative`).
    # Anything unknown is silently treated as `auto`.
    mode: Optional[str] = Field(default=None, max_length=24)


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


@api.get("/ai/agent/modes")
async def list_modes(request: Request):
    """Available routing modes for the agent composer toggle. Each entry
    has `{id, label, blurb}`. The frontend renders one chip per mode and
    POSTs the `id` back via `/ai/agent/chat` as the `mode` field."""
    await get_current_user(request)
    return {"modes": USER_MODES}


@api.get("/ai/agent/conversations/recent")
async def recent_conversations(request: Request, limit: int = 5):
    """Latest agent chat threads for the calling user — one row per
    agent_id with their most recent prompt. Derived from `agent_summary`
    memory rows so we don't need a separate `conversations` collection.

    Powers the AI Team dashboard's "Active conversations" panel. Empty
    when the user is brand-new (no memory rows tagged `agent_summary` yet)."""
    user = await get_current_user(request)
    limit = max(1, min(20, int(limit or 5)))
    # Latest row per agent_id. Mongo's $first inside $group with a
    # pre-sort gives us the most recent prompt per agent.
    pipeline = [
        {"$match": {"user_id": user.user_id, "kind": "agent_summary"}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id":     "$meta.agent",
            "last_at": {"$first": "$created_at"},
            "preview": {"$first": "$text"},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": limit},
    ]
    raw_rows = await _db.cortex_memory.aggregate(pipeline).to_list(length=limit)
    rows = []
    for r in raw_rows:
        agent = AGENTS.get(r["_id"]) if r.get("_id") else None
        if not agent:
            continue
        # Trim the "User asked Atlas: " prefix the summary template uses
        # to keep the panel preview tight.
        preview = (r.get("preview") or "")
        if ": " in preview:
            preview = preview.split(": ", 1)[1]
        rows.append({
            "agent_id":   agent["id"],
            "agent_name": agent["name"],
            "last_at":    r.get("last_at"),
            "preview":    preview[:160],
        })
    return {"conversations": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Per-agent mode preferences (persisted on the user doc)
# ---------------------------------------------------------------------------
from core import db as _db  # noqa: E402


@api.get("/ai/agent/prefs")
async def get_agent_prefs(request: Request):
    """Return the user's saved per-agent mode preferences. Shape:
    `{prefs: {agent_id: mode_id, ...}}`. Missing entries default to 'auto'
    on the client."""
    user = await get_current_user(request)
    doc = await _db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "agent_prefs": 1},
    ) or {}
    return {"prefs": doc.get("agent_prefs") or {}}


class _PrefsRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=32)
    mode: str = Field(..., min_length=1, max_length=24)


@api.put("/ai/agent/prefs")
async def set_agent_pref(payload: _PrefsRequest, request: Request):
    """Persist the user's preferred mode for one agent. Both `agent_id`
    and `mode` are strictly validated — unknown values are 422'd so a
    typo'd frontend never silently writes junk."""
    user = await get_current_user(request)
    agent_id = payload.agent_id.lower()
    mode_id = payload.mode.lower()
    if agent_id not in AGENTS:
        raise HTTPException(status_code=422, detail="Unknown agent_id")
    # Allow USER_MODE_IDS plus the explicit "auto" sentinel.
    valid_modes = {m["id"] for m in USER_MODES}
    if mode_id not in valid_modes:
        raise HTTPException(status_code=422, detail="Unknown mode")
    await _db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {f"agent_prefs.{agent_id}": mode_id}},
    )
    return {"ok": True, "agent_id": agent_id, "mode": mode_id}


@api.post("/ai/agent/chat")
async def agent_chat(payload: _ChatRequest, request: Request):
    """Send a message to the selected agent. Single LLM call — the agent
    appends an inline `<<FUPS>>[...]<<END>>` block which we strip + parse
    server-side. Keeps total latency ~6s vs ~100s for a separate meta call.

    Also pulls the top-K relevant memories for the user's prompt and
    injects them into the system prompt so the agent gets sharper with
    every interaction.

    For long-running chats (slow Opus + handoff to Iris) use the
    `/ai/agent/chat/stream` SSE endpoint instead — same orchestration,
    just emits keepalive events so the request never trips a 100s
    ingress timeout from the browser."""
    user = await _gated_user(request)
    agent = AGENTS.get(payload.agent_id.lower())
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")

    final = None
    async for event, data in _orchestrate(user, agent, payload):
        if event == "complete":
            final = data
    return final


@api.post("/ai/agent/chat/stream")
async def agent_chat_stream(payload: _ChatRequest, request: Request):
    """Streaming variant of `/ai/agent/chat`. Emits Server-Sent Events
    describing each stage of the orchestration:

      event: started     data: {agent_id, mode, model}
      event: memories    data: {memories_used: [...]}
      event: thinking    data: {phase: "primary"|"handoff", agent: "Iris"}
      event: handoff     data: {agent_id, agent_name, question}
      event: complete    data: {answer, follow_ups, memories_used,
                                handoff, mode, model}
      event: error       data: {message}

    The connection also receives `: keepalive` comments roughly every 10s
    while a synchronous LLM call is in progress — this prevents the
    Cloudflare/Emergent ingress from closing the request after its 100s
    idle timeout when Atlas does a slow handoff to Iris (~60s total)."""
    user = await _gated_user(request)
    agent = AGENTS.get(payload.agent_id.lower())
    if not agent:
        raise HTTPException(status_code=404, detail="Unknown agent")

    async def event_stream():
        try:
            async for event, data in _orchestrate(user, agent, payload):
                yield _sse(event, data)
        except Exception as e:
            yield _sse("error", {"message": str(e)[:300]})

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Required for nginx-style proxies to flush each chunk instead of
        # buffering the whole response into one block.
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers,
    )


def _sse(event: str, data: dict) -> str:
    """Format one SSE record. Always JSON-encodes the data payload so the
    frontend can `JSON.parse` uniformly."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _orchestrate(user, agent: dict, payload: "_ChatRequest"):
    """Run one full agent turn and yield (event_name, data) tuples.

    Stages:
      started → memories → thinking(primary) → [handoff → thinking(handoff)]
      → complete

    While a synchronous LLM call is awaited, we periodically yield empty
    `keepalive` events (~every 10s) so the underlying SSE stream never
    goes idle long enough for the ingress proxy to close it.
    """
    # Resolve mode + memory block up front so the `started` event can
    # surface them to the UI immediately.
    provider, model, task_used = resolve_user_mode(payload.mode, agent["id"])

    yield ("started", {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "mode": task_used,
        "model": model,
    })

    # Memory retrieval — best-effort.
    memory_block = ""
    used_memories: list[dict] = []
    try:
        from routes.memory import retrieve_relevant, memories_to_prompt_block
        mems = await retrieve_relevant(user.user_id, payload.message, k=5)
        memory_block = memories_to_prompt_block(mems)
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

    yield ("memories", {"memories_used": used_memories})

    session_id = f"agent-{agent['id']}-{user.user_id}"
    system_prompt = (
        agent["system"] + _FUPS_INSTRUCTION + _HANDOFF_INSTRUCTION
    )
    if memory_block:
        system_prompt = system_prompt + "\n\n" + memory_block

    chat = await _llm_for_user(
        user.user_id, session_id, system_prompt,
        provider=provider, model=model,
    )

    # Primary LLM call — interleave keepalive pings so the stream stays
    # warm even when Opus takes 20-30s to think.
    yield ("thinking", {"phase": "primary", "agent": agent["name"]})
    primary_task = asyncio.create_task(chat.send_message(UserMessage(text=payload.message)))
    async for ping in _keepalive_while(primary_task):
        yield ping
    raw = primary_task.result()

    # Optional handoff
    handoff_done = None
    raw, handoff_info = _extract_handoff(raw)
    if handoff_info and handoff_info["agent_id"] == agent["id"]:
        handoff_info = None  # reject self-handoff
    if handoff_info:
        sub_agent = AGENTS.get(handoff_info["agent_id"]) or {}
        yield ("handoff", {
            "agent_id": handoff_info["agent_id"],
            "agent_name": sub_agent.get("name", handoff_info["agent_id"]),
            "question": handoff_info["question"],
        })
        yield ("thinking", {
            "phase": "handoff",
            "agent": sub_agent.get("name", handoff_info["agent_id"]),
        })
        try:
            ho_task = asyncio.create_task(_run_handoff(user.user_id, handoff_info))
            async for ping in _keepalive_while(ho_task):
                yield ping
            handoff_done = ho_task.result()
            if handoff_done:
                raw = raw.rstrip() + (
                    f"\n\n📡 **{handoff_done['agent_name']} reports:**\n"
                    f"{handoff_done['answer']}\n"
                )
        except Exception:
            handoff_done = None

    answer, follow_ups = _extract_followups(raw)

    # Persist a short conversation summary as memory — best-effort.
    try:
        from routes.memory import remember
        await remember(
            user.user_id, "agent_summary",
            f"User asked {agent['name']}: {payload.message[:200]}",
            meta={"agent": agent["id"]},
        )
    except Exception:
        pass

    await record_ai_generation(user.user_id, f"agent_chat:{agent['id']}")
    # Estimated cost accounting (best-effort, never raises) — powers the
    # admin spend dashboard.
    try:
        from routes.llm_spend import record_llm_call
        await record_llm_call(user.user_id, agent["id"], task_used, model)
    except Exception:
        pass
    yield ("complete", {
        "agent_id": agent["id"],
        "answer": answer,
        "follow_ups": follow_ups,
        "memories_used": used_memories,
        "handoff": handoff_done,
        "mode": task_used,
        "model": model,
    })


async def _keepalive_while(task: asyncio.Task, every: float = 10.0):
    """Yield `("keepalive", {})` events every `every` seconds while
    `task` is still running. Awaits the task before returning so the
    caller can read `.result()`. Cancels/propagates on error."""
    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=every)
        except asyncio.TimeoutError:
            yield ("keepalive", {})
    # surface exceptions
    if task.exception():
        raise task.exception()


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
    # Track sub-agent cost too (treat handoff as the "research"/etc task).
    try:
        from routes.llm_spend import record_llm_call
        from routes.model_router import AGENT_TASKS
        await record_llm_call(
            user_id, sub["id"],
            AGENT_TASKS.get(sub["id"], "default"), model,
        )
    except Exception:
        pass
    return {
        "agent_id": sub["id"],
        "agent_name": sub["name"],
        "question": handoff["question"],
        "answer": (answer or "").strip(),
    }
