"""Marketing OS — LangGraph orchestration layer.

This module replaces the hand-rolled `_convene` linear chain (still
present in `routes/agent_chat.py` for the per-user "Convene the team"
modal on the AI Team page) with an explicit `StateGraph` for the
canonical 5-role Marketing OS run.

Why a graph instead of a list?
------------------------------
The original linear chain (`strategy → intelligence → content →
distribution → analytics`) was already implicit in `_convene`. Wrapping
it in `StateGraph` buys us four things the linear loop can't do
cleanly:

1.  **Explicit state**: the run's transcript / summary / step-index
    live in a single `TypedDict` instead of mutable local variables. A
    new role can be added without touching the orchestration code.
2.  **Conditional edges**: we can SKIP the Distribution role when the
    campaign has no connected platforms. The linear version had to run
    every node every time.
3.  **Checkpointing**: `MongoDBSaver` persists per-step state to the
    `langgraph_checkpoints` collection so partial runs survive backend
    restarts (and could later be resumed by hitting the same run_id).
4.  **Observability seam**: future per-node metrics, retries, or human
    approval gates all hang off the graph definition, not the calling
    code.

Streaming
---------
LangGraph's `astream_events` is powerful but emits a lot of internal
events. To keep the existing SSE contract stable (the frontend already
renders `agent_started` / `agent_done` / `summarizing` / `complete`),
each node pushes its own SSE-shaped tuple into a per-run
`asyncio.Queue`. The outer handler in `marketing_os.py` drains that
queue, frames it with `os_started` / `os_persisted`, and writes the
final run row to Mongo. No event-shape changes from the previous
`_convene`-based implementation.

Spend tracking
--------------
Each node still calls `record_llm_call` exactly as the old chain did,
so the admin LLM spend dashboard keeps working without any changes.
"""
import asyncio
import logging
import os
import uuid
from typing import Any, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from emergentintegrations.llm.chat import UserMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical 5-role chain (single source of truth — `marketing_os.py` reads
# this rather than redefining its own list).
# ---------------------------------------------------------------------------
CANONICAL_ROLES: list[dict] = [
    {"role": "strategy",     "agent_id": "strategy", "label": "Strategy",     "color": "blue"},
    {"role": "intelligence", "agent_id": "research", "label": "Intelligence", "color": "indigo"},
    {"role": "content",      "agent_id": "nova",     "label": "Content",     "color": "emerald"},
    {"role": "distribution", "agent_id": "kai",      "label": "Distribution", "color": "rose"},
    {"role": "analytics",    "agent_id": "angela",   "label": "Analytics",   "color": "violet"},
]
ROLE_TO_AGENT = {r["role"]: r["agent_id"] for r in CANONICAL_ROLES}
AGENT_TO_ROLE = {r["agent_id"]: r["role"] for r in CANONICAL_ROLES}
DEFAULT_CHAIN = ["strategy", "research", "nova", "kai"]  # agent ids; angela summarises


# ---------------------------------------------------------------------------
# Graph state — passed between nodes. Must be JSON-serialisable for
# checkpointing (no asyncio primitives in here — the events_queue lives
# in a separate module-level registry keyed by run_id).
# ---------------------------------------------------------------------------
class OSState(TypedDict, total=False):
    run_id:        str
    user_id:       str
    brief:         str
    chain:         list[str]    # remaining agent ids (in order)
    summarizer_id: str          # which agent role synthesises
    mode:          Optional[str]
    transcript:    list[dict]   # [{agent_id, agent_name, answer}]
    summary:       str
    last_model:    str
    last_mode:     str
    skip_distribution: bool
    error:         Optional[str]


# ---------------------------------------------------------------------------
# Per-run SSE queue registry.
# Nodes can't reach the FastAPI streaming response directly, so each
# node pushes its (event_name, data) tuples onto an `asyncio.Queue`
# stored here under the run_id. The outer handler drains it.
# Cleaned up after the run finishes (success or failure).
# ---------------------------------------------------------------------------
_RUN_QUEUES: dict[str, "asyncio.Queue"] = {}


async def _emit(run_id: str, event: str, data: dict) -> None:
    q = _RUN_QUEUES.get(run_id)
    if q is not None:
        await q.put((event, data))


# ---------------------------------------------------------------------------
# Node factory — every role node shares the same shape, only the
# agent_id and step number change. Building them with a closure keeps
# the graph definition tight and lets us add a new role in 2 lines.
# ---------------------------------------------------------------------------
def _build_role_node(agent_id: str, step_total: int):
    """Returns an async node function suitable for `graph.add_node`."""
    async def node(state: OSState) -> dict:
        # Import here to avoid a circular import at module load time
        # (agent_chat → marketing_os_graph → agent_chat).
        from routes.agent_chat import AGENTS, _FUPS_RE, _HANDOFF_RE
        from routes.ai import _llm_for_user, send_with_usage
        from routes.model_router import resolve_user_mode
        from routes.llm_spend import record_llm_call

        agent = AGENTS[agent_id]
        run_id = state["run_id"]
        user_id = state["user_id"]
        brief = state["brief"]
        transcript = state.get("transcript", []) or []
        step = len(transcript) + 1

        await _emit(run_id, "agent_started", {
            "agent_id": agent["id"], "agent_name": agent["name"],
            "step": step, "total": step_total,
        })

        # Each node sees the brief + every prior agent's contribution
        # so the chain builds rather than producing N independent
        # answers. Identical wording to the old `_convene` so the
        # behaviour is unchanged.
        if transcript:
            sections = [
                f"### {t['agent_name']} ({t['agent_id']})\n{t['answer']}"
                for t in transcript
            ]
            context_block = (
                "\n\n--- Prior team input ---\n" + "\n\n".join(sections) +
                "\n\n--- End prior input ---\n"
                "Build on the above. Reference their work where useful, "
                "but only add what's missing or sharpen what's there. Keep "
                "your reply under 350 words.\n"
            )
        else:
            context_block = (
                "\nYou are the first specialist on this brief. Keep your "
                "reply under 350 words. Be sharp and structured.\n"
            )

        provider, model, task_used = resolve_user_mode(state.get("mode"), agent["id"])
        session_id = f"osgraph-{agent['id']}-{user_id}"
        chat = await _llm_for_user(
            user_id, session_id,
            agent["system"] + context_block,
            provider=provider, model=model,
        )
        prompt = f"User brief:\n{brief}"

        try:
            text, usage = await send_with_usage(chat, UserMessage(text=prompt))
        except Exception as e:
            # Surface the error in state so the conditional edge can
            # short-circuit to END without further LLM calls.
            err = str(e)[:300]
            await _emit(run_id, "error", {"message": err, "agent_id": agent["id"]})
            return {"error": err}

        answer = (text or "").strip()
        answer = _FUPS_RE.sub("", answer)
        answer = _HANDOFF_RE.sub("", answer).strip()

        new_transcript = transcript + [{
            "agent_id": agent["id"], "agent_name": agent["name"],
            "answer": answer,
        }]

        await _emit(run_id, "agent_done", {
            "agent_id": agent["id"], "agent_name": agent["name"],
            "step": step, "total": step_total, "answer": answer,
        })

        try:
            await record_llm_call(user_id, agent["id"], task_used, model, usage)
        except Exception:
            logger.exception("record_llm_call failed for %s", agent["id"])

        return {
            "transcript": new_transcript,
            "last_model": model,
            "last_mode":  task_used,
        }
    return node


def _build_summarizer_node(agent_id: str):
    """Final analytics/synthesis node — same shape, different prompt."""
    async def node(state: OSState) -> dict:
        from routes.agent_chat import AGENTS, _FUPS_RE, _HANDOFF_RE
        from routes.ai import _llm_for_user, send_with_usage
        from routes.model_router import resolve_user_mode
        from routes.llm_spend import record_llm_call
        from routes.memory import remember
        from routes.plans import record_ai_generation

        agent = AGENTS[agent_id]
        run_id = state["run_id"]
        user_id = state["user_id"]
        brief = state["brief"]
        transcript = state.get("transcript", []) or []

        await _emit(run_id, "summarizing", {
            "agent_id": agent["id"], "agent_name": agent["name"],
        })

        # Synthesiser always runs `deep` unless the user explicitly
        # picked another mode — the synthesis is the highest-leverage
        # step of the chain.
        provider, model, task_used = resolve_user_mode(
            state.get("mode") or "deep", agent["id"],
        )
        sum_prompt_sys = agent["system"] + (
            "\n\nYou are synthesizing input from your team for the user's brief. "
            "Produce a single executive summary that:\n"
            "  1. Restates the brief in one sentence.\n"
            "  2. Surfaces the 3-5 strongest ideas from the team.\n"
            "  3. Resolves any conflicts between specialists.\n"
            "  4. Ends with a clear, ranked 'next 3 actions'.\n"
            "Tone: confident, decisive, no hedging. Use markdown headings.\n"
        )
        sections = [
            f"### {t['agent_name']} ({t['agent_id']})\n{t['answer']}"
            for t in transcript
        ]
        sum_input = (
            f"User's brief:\n{brief}\n\n"
            f"Team transcript:\n\n" + "\n\n".join(sections)
        )
        sum_chat = await _llm_for_user(
            user_id, f"osgraph-summary-{user_id}", sum_prompt_sys,
            provider=provider, model=model,
        )

        try:
            text, usage = await send_with_usage(sum_chat, UserMessage(text=sum_input))
        except Exception as e:
            err = str(e)[:300]
            await _emit(run_id, "error", {"message": err, "agent_id": agent["id"]})
            return {"error": err}

        summary = (text or "").strip()
        summary = _FUPS_RE.sub("", summary)
        summary = _HANDOFF_RE.sub("", summary).strip()

        try:
            await record_llm_call(user_id, agent["id"], task_used, model, usage)
        except Exception:
            logger.exception("record_llm_call failed for summariser %s", agent["id"])

        # Persist a memory of the run so future chats can recall it.
        try:
            await remember(
                user_id, "convene_summary",
                f"Marketing OS run on '{brief[:120]}' — chain: "
                f"{', '.join(t['agent_name'] for t in transcript)}.\n{summary[:600]}",
                meta={
                    "source": "marketing_os_graph",
                    "chain":  [t["agent_id"] for t in transcript],
                    "summarizer": agent["id"],
                },
            )
        except Exception:
            logger.exception("memory.remember failed for OS run %s", run_id)

        try:
            await record_ai_generation(user_id, "marketing_os")
        except Exception:
            pass

        await _emit(run_id, "complete", {
            "summary":    summary,
            "transcript": transcript,
            "summarizer": {"agent_id": agent["id"], "agent_name": agent["name"]},
            "mode":       task_used,
            "model":      model,
        })

        return {
            "summary":    summary,
            "last_model": model,
            "last_mode":  task_used,
        }
    return node


# ---------------------------------------------------------------------------
# Conditional edge — skip Distribution when the run is content-only.
# ---------------------------------------------------------------------------
def _route_after_content(state: OSState) -> str:
    """If the planner flagged `skip_distribution` (= no platforms
    connected and the brief doesn't request distribution), jump
    straight to the summariser. Otherwise run Kai. The conditional
    edge is the headline proof-of-graph value over the linear chain."""
    if state.get("error"):
        return "summariser"   # short-circuit on upstream LLM failure
    if state.get("skip_distribution"):
        return "summariser"
    return "distribution"


def _route_after_strategy(state: OSState) -> str:
    """Short-circuit straight to summariser on upstream LLM failure
    so we don't burn budget calling the next agent with empty input."""
    return "summariser" if state.get("error") else "intelligence"


def _route_after_intelligence(state: OSState) -> str:
    return "summariser" if state.get("error") else "content"


def _route_after_distribution(state: OSState) -> str:
    return "summariser"


# ---------------------------------------------------------------------------
# Graph builder — compiled once at import time. The conditional edges
# encode the canonical chain; alternate chains (user-specified `roles`
# subset) bypass the graph and use a dynamic linear walk instead (see
# `run_dynamic_chain` below) since LangGraph graphs are static.
# ---------------------------------------------------------------------------
def _build_canonical_graph():
    builder = StateGraph(OSState)
    builder.add_node("strategy",     _build_role_node("strategy",     step_total=4))
    builder.add_node("intelligence", _build_role_node("research",     step_total=4))
    builder.add_node("content",      _build_role_node("nova",         step_total=4))
    builder.add_node("distribution", _build_role_node("kai",          step_total=4))
    builder.add_node("summariser",   _build_summarizer_node("angela"))

    builder.add_edge(START, "strategy")
    builder.add_conditional_edges("strategy", _route_after_strategy, {
        "intelligence": "intelligence", "summariser": "summariser",
    })
    builder.add_conditional_edges("intelligence", _route_after_intelligence, {
        "content": "content", "summariser": "summariser",
    })
    builder.add_conditional_edges("content", _route_after_content, {
        "distribution": "distribution", "summariser": "summariser",
    })
    builder.add_conditional_edges("distribution", _route_after_distribution, {
        "summariser": "summariser",
    })
    builder.add_edge("summariser", END)

    # MongoDBSaver requires a sync pymongo client + works for the
    # canonical chain. We fall back to MemorySaver when the checkpoint
    # collection can't be reached (tests, mongo replica issues) so the
    # graph still runs — just without resumability.
    checkpointer = _make_checkpointer()
    return builder.compile(checkpointer=checkpointer)


def _make_checkpointer():
    """Returns a LangGraph checkpointer. Prefers MongoDB so partial
    runs survive a backend restart; falls back to in-memory if the
    Mongo saver can't be constructed (e.g. in pytest with mock URIs)."""
    try:
        from pymongo import MongoClient
        from langgraph.checkpoint.mongodb import MongoDBSaver
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]
        # Short timeout so a misconfigured Mongo doesn't block startup.
        sync_client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        # `MongoClient` is lazy — force a ping so we fall back fast on
        # auth/DNS failures.
        sync_client.admin.command("ping")
        return MongoDBSaver(
            sync_client,
            db_name=db_name,
            checkpoint_collection_name="langgraph_checkpoints",
            writes_collection_name="langgraph_checkpoint_writes",
        )
    except Exception as e:
        logger.warning("MongoDBSaver unavailable, using MemorySaver: %s", e)
        return MemorySaver()


_CANONICAL_GRAPH = None


def get_canonical_graph():
    """Lazy singleton — built on first use so the module imports cheap.
    Tests can call `reset_canonical_graph()` to force a rebuild."""
    global _CANONICAL_GRAPH
    if _CANONICAL_GRAPH is None:
        _CANONICAL_GRAPH = _build_canonical_graph()
    return _CANONICAL_GRAPH


def reset_canonical_graph():
    global _CANONICAL_GRAPH
    _CANONICAL_GRAPH = None


# ---------------------------------------------------------------------------
# Public entrypoint — async generator yielding (event, data) tuples for
# the SSE handler.
# ---------------------------------------------------------------------------
async def run_os_graph(
    user_id: str, brief: str, mode: Optional[str] = None,
    skip_distribution: bool = False,
    roles: Optional[list[str]] = None,
    run_id: Optional[str] = None,
):
    """Drives the canonical 5-role graph (or a user-specified subset).

    Yields SSE-shaped `(event_name, data_dict)` tuples that the FastAPI
    handler can format with `_sse()` and stream to the browser.

    `roles` accepts either canonical role names ("strategy",
    "content"...) or internal agent ids. When set, we run a
    *dynamic linear walk* through those agents in order (graph
    requires a static topology). The canonical path remains the
    headline use case.

    `run_id` is optional — when omitted, we generate a fresh uuid4.
    The caller can pass one in so the outer `os_started` SSE event and
    persisted row use the same id from the start.
    """
    if not run_id:
        run_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue()
    _RUN_QUEUES[run_id] = q

    yield ("graph_started", {"run_id": run_id})

    # Decide path: canonical graph vs dynamic walk.
    if roles:
        runner = asyncio.create_task(_run_dynamic_chain(
            run_id=run_id, user_id=user_id, brief=brief,
            mode=mode, roles=roles,
        ))
    else:
        runner = asyncio.create_task(_run_canonical(
            run_id=run_id, user_id=user_id, brief=brief, mode=mode,
            skip_distribution=skip_distribution,
        ))

    # Drain the queue until the runner signals completion. Sentinel
    # tuple `("__END__", None)` is pushed by `_run_*` in their finally
    # block.
    try:
        while True:
            ev, data = await q.get()
            if ev == "__END__":
                break
            yield (ev, data)
    finally:
        _RUN_QUEUES.pop(run_id, None)
        if not runner.done():
            runner.cancel()
            try:
                await runner
            except (asyncio.CancelledError, Exception):
                pass


async def _run_canonical(*, run_id, user_id, brief, mode, skip_distribution):
    """Invokes the compiled StateGraph and pushes a sentinel onto the
    queue when finished."""
    try:
        graph = get_canonical_graph()
        initial: OSState = {
            "run_id":  run_id,
            "user_id": user_id,
            "brief":   brief,
            "mode":    mode,
            "transcript": [],
            "summary": "",
            "skip_distribution": bool(skip_distribution),
            "error":   None,
        }
        config = {"configurable": {"thread_id": run_id}}
        await graph.ainvoke(initial, config=config)
    except Exception as e:
        logger.exception("Graph run %s crashed", run_id)
        await _emit(run_id, "error", {"message": str(e)[:300]})
    finally:
        q = _RUN_QUEUES.get(run_id)
        if q is not None:
            await q.put(("__END__", None))


async def _run_dynamic_chain(*, run_id, user_id, brief, mode, roles: list[str]):
    """Runs a user-specified subset of roles as a flat linear chain
    (no graph — LangGraph graphs are static). Same node functions, no
    conditional edges. Last agent in the chain acts as the summariser
    unless one of the canonical roles is included explicitly, in which
    case Angela synthesises.

    This is rare (the default Marketing OS run uses the canonical
    chain) but keeps backwards compatibility with the existing
    `/marketing-os/run/stream?roles=...` API."""
    try:
        # Resolve to agent ids.
        resolved: list[str] = []
        for r in roles:
            key = r.strip().lower()
            if key in ROLE_TO_AGENT:
                resolved.append(ROLE_TO_AGENT[key])
            elif key in AGENT_TO_ROLE:
                resolved.append(key)
            else:
                await _emit(run_id, "error", {"message": f"Unknown role: {r}"})
                return
        # Dedupe in-order.
        seen: set[str] = set()
        resolved = [a for a in resolved if not (a in seen or seen.add(a))]
        if not resolved:
            await _emit(run_id, "error", {"message": "At least one role required"})
            return

        # Always reserve a summariser. If Angela's in the chain, pop her
        # to the end as the synthesiser; otherwise use Angela as
        # external summariser to keep the contract identical.
        summariser_id = "angela"
        chain_for_run = [a for a in resolved if a != summariser_id]
        if not chain_for_run:
            chain_for_run = [resolved[0]]
            summariser_id = "strategy" if resolved[0] != "strategy" else "angela"

        state: OSState = {
            "run_id":  run_id,
            "user_id": user_id,
            "brief":   brief,
            "mode":    mode,
            "transcript": [],
            "summary": "",
            "skip_distribution": False,
            "error":   None,
        }
        total = len(chain_for_run)
        for agent_id in chain_for_run:
            node = _build_role_node(agent_id, step_total=total)
            update = await node(state)
            state.update(update)  # type: ignore[arg-type]
            if state.get("error"):
                break

        if not state.get("error"):
            sum_node = _build_summarizer_node(summariser_id)
            update = await sum_node(state)
            state.update(update)  # type: ignore[arg-type]
    except Exception as e:
        logger.exception("Dynamic chain %s crashed", run_id)
        await _emit(run_id, "error", {"message": str(e)[:300]})
    finally:
        q = _RUN_QUEUES.get(run_id)
        if q is not None:
            await q.put(("__END__", None))
