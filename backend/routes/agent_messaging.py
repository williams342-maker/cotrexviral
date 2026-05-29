"""Agent ↔ Agent messaging — Phase 6 of the Autonomous Growth Team.

Lets one agent query another before routing to the operator. The bus is
LLM-mediated and async; every message is persisted to `agent_messages`
for the audit log + the /dashboard/chatter UI.

Why not a direct function call? The personas have voice + opinions
baked into their system_prompts. Routing a question through the
persona's prompt makes the answer feel like that agent reasoned about
it, not like a deterministic lookup. The audit log is also valuable for
operators auditing autonomous decisions ("WHY did Atlas merge those 3
briefs?" → because Lyra said they share a theme).

Standard MVP integration (this PR):
  Atlas → Lyra: "Given these {n} listening signals, what's the strongest
                shared theme worth ONE brief instead of N?"

  Atlas reads Lyra's answer and steers its brief proposal accordingly —
  fewer redundant briefs, sharper rationales, better operator trust.

The bus is generic — future PRs can wire Atlas → Ori (have we tested
this before?), Atlas → Rae (does the audience care?), etc.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from routes.agent_personas import PERSONAS

logger = logging.getLogger(__name__)


_PERSONAS_BY_ID: dict[str, dict] = {p["id"]: p for p in PERSONAS}


# ---------------------------------------------------------------------
# Low-level persistence
# ---------------------------------------------------------------------
async def _record_message(
    *,
    user_id: str,
    from_agent: str,
    to_agent: str,
    query: str,
    response: Optional[str],
    thread_id: Optional[str],
    status: str,
    context_summary: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    """Insert one row + return its id."""
    mid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await db.agent_messages.insert_one({
        "id":               mid,
        "user_id":          user_id,
        "from_agent":       from_agent,
        "to_agent":         to_agent,
        "thread_id":        thread_id or mid,  # solo messages = own thread
        "query":            (query or "").strip()[:2000],
        "response":         (response or "").strip()[:3000] if response else None,
        "context_summary":  (context_summary or "").strip()[:500] or None,
        "status":           status,  # "pending" | "answered" | "errored"
        "error":            (error or "")[:500] or None,
        "created_at":       now,
        "responded_at":     now if status in {"answered", "errored"} else None,
    })
    return mid


# ---------------------------------------------------------------------
# Public helper — the bus
# ---------------------------------------------------------------------
async def query_agent(
    *,
    user_id: str,
    from_agent: str,
    to_agent: str,
    query: str,
    context_str: str = "",
    thread_id: Optional[str] = None,
) -> dict:
    """One agent asks another. Returns {message_id, response, ok}.

    Errors are caught + persisted as `errored` rows so the audit log
    captures failures. Caller decides whether to fall back gracefully.
    """
    sender = _PERSONAS_BY_ID.get(from_agent)
    target = _PERSONAS_BY_ID.get(to_agent)
    if not sender or not target:
        msg_id = await _record_message(
            user_id=user_id, from_agent=from_agent, to_agent=to_agent,
            query=query, response=None, thread_id=thread_id,
            status="errored", error="unknown agent",
        )
        return {"message_id": msg_id, "response": None, "ok": False}

    from core import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        # Fall back to a deterministic acknowledgement so the bus still works.
        canned = (f"[{target['name']}] I'd need the live model to give a real answer "
                  f"on '{query[:80]}'. Falling back to no-op.")
        msg_id = await _record_message(
            user_id=user_id, from_agent=from_agent, to_agent=to_agent,
            query=query, response=canned, thread_id=thread_id, status="answered",
            context_summary=context_str[:500],
        )
        return {"message_id": msg_id, "response": canned, "ok": True}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage
        import asyncio as _asyncio

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"a2a_{thread_id or uuid.uuid4().hex[:8]}",
            system_message=(
                f"{target['system_prompt']}\n\n"
                "You're now answering a teammate's direct question. Stay in your "
                "voice. Reply in 1–3 sentences. Be specific, actionable, no fluff. "
                "If the question is ambiguous or there's no data to ground an answer, "
                "say so honestly rather than hallucinating."
            ),
        ).with_model("openai", "gpt-5-mini")

        prompt = (
            f"{sender['name']} ({sender['role']}) asks {target['name']}:\n"
            f"\"{query}\"\n\n"
            f"Context they shared:\n{context_str or '(no extra context)'}"
        )
        text, _usage = await _asyncio.wait_for(
            send_with_usage(chat, UserMessage(text=prompt),
                            agent_id=to_agent,
                            user_id=user_id,
                            model="gpt-5-mini"),
            timeout=20,
        )
        response = (text or "").strip() or "(no reply)"

        mid = await _record_message(
            user_id=user_id, from_agent=from_agent, to_agent=to_agent,
            query=query, response=response, thread_id=thread_id,
            status="answered", context_summary=context_str[:500],
        )
        return {"message_id": mid, "response": response, "ok": True}
    except Exception as exc:
        logger.warning("query_agent %s→%s failed: %s", from_agent, to_agent, exc)
        mid = await _record_message(
            user_id=user_id, from_agent=from_agent, to_agent=to_agent,
            query=query, response=None, thread_id=thread_id,
            status="errored", error=str(exc)[:400],
        )
        return {"message_id": mid, "response": None, "ok": False}


# ---------------------------------------------------------------------
# HTTP API — inspect the audit log
# ---------------------------------------------------------------------
@api.get("/agent-messages")
async def list_agent_messages(request: Request, limit: int = 50,
                              from_agent: Optional[str] = None,
                              to_agent: Optional[str] = None):
    """Most-recent agent-to-agent messages for this user. Filter by either
    side of the conversation. Default 50, capped at 200."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 200))
    query: dict = {"user_id": user.user_id}
    if from_agent:
        query["from_agent"] = from_agent
    if to_agent:
        query["to_agent"] = to_agent
    docs = await db.agent_messages.find(query, {"_id": 0})\
        .sort("created_at", -1).to_list(length=limit)
    # Summary stats for the UI hero row
    total = await db.agent_messages.count_documents({"user_id": user.user_id})
    answered = await db.agent_messages.count_documents(
        {"user_id": user.user_id, "status": "answered"})
    errored = await db.agent_messages.count_documents(
        {"user_id": user.user_id, "status": "errored"})
    return {
        "items":         docs,
        "count":         len(docs),
        "total":         total,
        "answered":      answered,
        "errored":       errored,
    }


@api.get("/agent-messages/{message_id}")
async def get_agent_message(message_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.agent_messages.find_one(
        {"id": message_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")
    # Pull the full thread so the UI can render the back-and-forth.
    thread = await db.agent_messages.find(
        {"thread_id": doc["thread_id"], "user_id": user.user_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(length=20)
    return {"message": doc, "thread": thread}
