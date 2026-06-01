"""Cortex hybrid memory.

Two-layer architecture per the product spec:

1. **Strategic Memory (Mongo)** — a distilled-down doc per user
   capturing their long-term business goals, recurring themes, and
   current bottlenecks. Updated by `update_strategy_summary()` every
   N turns (or via the nightly cron). Answers questions like:
       "What are Mike's current goals?"

2. **Semantic Memory (Qdrant local mode)** — every conversation turn
   is embedded with fastembed (BAAI/bge-small-en-v1.5, 384-dim) and
   stored in an on-disk Qdrant collection. Answers questions like:
       "What did Mike say about Etsy sellers three weeks ago?"

Both layers compose: every Cortex turn pulls (a) the strategy doc and
(b) the top-K semantically-similar prior turns, then injects them into
the system prompt so Cortex actually feels like a persistent partner.

Qdrant local mode requires no separate server — it persists to
`/app/backend/.qdrant_data/`. fastembed downloads the embedding model
on first use (~130MB) to `~/.cache/huggingface/`.

Public API:
    await record_turn(user_id, role, text, *, meta=None)
    await recall_semantic(user_id, query, *, k=5) -> list[dict]
    await get_strategy(user_id) -> dict | None
    await update_strategy_summary(user_id, *, force=False) -> dict
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded singletons — Qdrant + fastembed model are heavy to
# initialize, so we defer until first use to keep server startup fast.
_qdrant_client = None
_qdrant_ready = False
_qdrant_lock = asyncio.Lock()

COLLECTION = "cortex_memory"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, ~130MB ONNX
QDRANT_PATH = str(Path(__file__).parent.parent / ".qdrant_data")

# Production guardrail — Emergent K8s pods are capped at ~250m CPU /
# 1Gi RAM, which is too small to load fastembed's 130MB ONNX model
# without OOM-killing the pod mid-request. We default to DISABLED in
# production; semantic recall degrades to empty results (Mongo-backed
# strategic memory and conversation history both keep working — they
# don't touch Qdrant). Override via env var to re-enable when a bigger
# pod / managed vector DB is in place.
#
# To re-enable on a larger deployment:  CORTEX_VECTOR_MEMORY=enabled
_VECTOR_MEMORY_ENABLED = (
    os.environ.get("CORTEX_VECTOR_MEMORY", "").strip().lower()
    in {"1", "true", "yes", "enabled", "on"}
)


async def _get_qdrant():
    """Lazy-initialize the local Qdrant client + collection.
    Returns None if initialization fails OR if vector memory is
    disabled via env (default in production)."""
    if not _VECTOR_MEMORY_ENABLED:
        return None
    global _qdrant_client, _qdrant_ready
    if _qdrant_ready:
        return _qdrant_client
    async with _qdrant_lock:
        if _qdrant_ready:
            return _qdrant_client
        try:
            from qdrant_client import QdrantClient
            # Local file-backed Qdrant. Single-writer; we serialize via
            # _qdrant_lock for writes so it's safe in our async stack.
            Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=QDRANT_PATH)
            # `add()` (the high-level helper) auto-creates collections
            # with the right dim on first call. Set embedding model up
            # front so it's used consistently.
            try:
                client.set_model(EMBED_MODEL)
            except Exception:
                # Older qdrant-client uses set_default_embedding_model.
                if hasattr(client, "set_default_embedding_model"):
                    client.set_default_embedding_model(EMBED_MODEL)
            _qdrant_client = client
        except Exception:
            logger.exception("cortex.memory: failed to init Qdrant; semantic recall disabled")
            _qdrant_client = None
        _qdrant_ready = True
        return _qdrant_client


# ---------------------------------------------------------- write path
async def record_turn(user_id: str, role: str, text: str,
                       *, meta: Optional[dict] = None) -> Optional[str]:
    """Embed and store one conversation turn in Qdrant. Best-effort —
    failure logs and returns None so the chat endpoint never breaks
    just because the vector DB is sad."""
    if not text or not text.strip():
        return None
    client = await _get_qdrant()
    if client is None:
        return None
    point_id = uuid.uuid4().hex
    payload = {
        "user_id":    user_id,
        "role":       role,
        "text":       text[:4000],          # cap memory size per turn
        "created_at": datetime.now(timezone.utc).isoformat(),
        "meta":       meta or {},
    }

    def _do_add():
        try:
            client.add(
                collection_name=COLLECTION,
                documents=[text[:4000]],
                metadata=[payload],
                ids=[point_id],
            )
            return point_id
        except Exception:
            logger.exception("cortex.memory: qdrant add failed")
            return None

    # qdrant-client's `add()` is synchronous + does CPU embedding work,
    # so dispatch to a thread to avoid blocking the event loop.
    return await asyncio.to_thread(_do_add)


# ----------------------------------------------------------- read path
async def recall_semantic(user_id: str, query: str,
                           *, k: int = 5) -> list[dict]:
    """Return top-K semantically-similar past turns for this user.
    Each item: {text, role, created_at, score, meta}."""
    if not query or not query.strip():
        return []
    client = await _get_qdrant()
    if client is None:
        return []

    def _do_query():
        try:
            # qdrant-client 1.18 query_points helper with filter.
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            results = client.query(
                collection_name=COLLECTION,
                query_text=query[:1000],
                limit=max(1, min(k, 25)),
                query_filter=Filter(must=[
                    FieldCondition(key="user_id",
                                    match=MatchValue(value=user_id)),
                ]),
            )
            out: list[dict] = []
            for hit in results or []:
                meta = getattr(hit, "metadata", {}) or {}
                out.append({
                    "text":       meta.get("text", "")[:600],
                    "role":       meta.get("role", "user"),
                    "created_at": meta.get("created_at"),
                    "meta":       meta.get("meta") or {},
                    "score":      float(getattr(hit, "score", 0.0) or 0.0),
                })
            return out
        except Exception:
            logger.exception("cortex.memory: qdrant query failed")
            return []

    return await asyncio.to_thread(_do_query)


# ----------------------------------------------------------- strategy
async def get_strategy(user_id: str) -> Optional[dict]:
    """Return the user's current strategic-memory doc, or None."""
    from core import db
    doc = await db.cortex_strategy.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return None
    # Normalize datetime → ISO so callers can serialize easily.
    for k in ("updated_at", "created_at"):
        v = doc.get(k)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


async def update_strategy_summary(user_id: str,
                                    *, force: bool = False,
                                    min_turns: int = 6) -> dict:
    """Distill recent conversation history into a strategy doc using
    Cortex's primary LLM. Idempotent — won't re-run if updated <2h ago
    unless `force=True`. Returns the latest strategy doc (or {} on
    error). Stored in `cortex_strategy` Mongo collection per user_id.

    Schema written:
        { user_id, summary, goals: [...], bottlenecks: [...],
          recent_themes: [...], updated_at }
    """
    from core import db
    existing = await db.cortex_strategy.find_one({"user_id": user_id}) or {}
    now = datetime.now(timezone.utc)
    if not force and existing.get("updated_at"):
        last = existing["updated_at"]
        if isinstance(last, datetime) and (now - last) < timedelta(hours=2):
            existing.pop("_id", None)
            return existing  # too fresh — skip

    # Pull recent conversation turns (cortex_conversations is the
    # existing collection populated by routes/cortex_console.py).
    cur = db.cortex_conversations.find(
        {"user_id": user_id}, {"_id": 0, "role": 1, "message": 1,
                                 "intent": 1, "created_at": 1},
    ).sort("created_at", -1).limit(80)
    rows = await cur.to_list(length=80)
    if len(rows) < min_turns:
        # Not enough conversation history yet — write a stub doc the UI
        # can render, but skip the LLM call.
        stub = {
            "user_id":       user_id,
            "summary":       "",
            "goals":         [],
            "bottlenecks":   [],
            "recent_themes": [],
            "turn_count":    len(rows),
            "updated_at":    now,
            "created_at":    existing.get("created_at") or now,
        }
        await db.cortex_strategy.update_one(
            {"user_id": user_id}, {"$set": stub}, upsert=True,
        )
        stub["updated_at"] = stub["updated_at"].isoformat()
        if isinstance(stub.get("created_at"), datetime):
            stub["created_at"] = stub["created_at"].isoformat()
        return stub

    # Compose a transcript and ask Cortex to distill.
    rows.reverse()  # oldest-first
    transcript = "\n".join(
        f"[{r.get('role','user')}] {(r.get('message') or '')[:300]}"
        for r in rows
    )[:6000]

    from cortex.llm_provider import cortex_tool_call
    system = (
        "You are Cortex's strategic memory engine. Distill the user's "
        "recent conversations into a structured strategy doc capturing "
        "their long-term business strategy. Be concise. Strip filler. "
        "Use plain prose, no emojis."
    )
    strategy_tool = {
        "name": "record_strategy",
        "description": (
            "Persist the distilled strategic memory for this user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary":       {"type": "string",
                                   "description": "3-5 sentence executive summary of where they are right now."},
                "goals":         {"type": "array", "items": {"type": "string"},
                                   "description": "3-6 short bullet strings of durable goals."},
                "bottlenecks":   {"type": "array", "items": {"type": "string"},
                                   "description": "2-4 bullets — what is blocking growth."},
                "recent_themes": {"type": "array", "items": {"type": "string"},
                                   "description": "3-5 bullets — what they keep coming back to."},
            },
            "required": ["summary", "goals", "bottlenecks", "recent_themes"],
        },
    }
    try:
        args, _label, _mode = await cortex_tool_call(
            system=system,
            user_text=f"Conversation transcript (oldest → newest):\n{transcript}",
            tool=strategy_tool,
            session_id=f"cortex-strategy-{user_id}",
            user_id=user_id,
            prefer="claude",
            required=["summary"],
        )
        data = args or {}
    except Exception:
        logger.exception("cortex.memory: strategy distillation tool-call failed")
        existing.pop("_id", None)
        return existing or {}

    doc = {
        "user_id":       user_id,
        "summary":       str(data.get("summary") or "")[:1500],
        "goals":         [str(g)[:200] for g in (data.get("goals") or [])][:6],
        "bottlenecks":   [str(b)[:200] for b in (data.get("bottlenecks") or [])][:5],
        "recent_themes": [str(t)[:200] for t in (data.get("recent_themes") or [])][:5],
        "turn_count":    len(rows),
        "updated_at":    now,
        "created_at":    existing.get("created_at") or now,
    }
    await db.cortex_strategy.update_one(
        {"user_id": user_id}, {"$set": doc}, upsert=True,
    )
    # Serialize for return.
    out = {**doc, "updated_at": now.isoformat()}
    if isinstance(out.get("created_at"), datetime):
        out["created_at"] = out["created_at"].isoformat()
    return out


# -------------------------------------------------------- prompt block
def render_memory_block(strategy: Optional[dict],
                          recalled: list[dict]) -> str:
    """Render strategy + semantic recalls into a system-prompt block
    for the chat endpoint to inject. Returns "" if nothing to share."""
    parts: list[str] = []
    if strategy and (strategy.get("summary") or strategy.get("goals")):
        parts.append("CURRENT BUSINESS STRATEGY (distilled from prior conversations):")
        if strategy.get("summary"):
            parts.append(f"  Summary: {strategy['summary']}")
        if strategy.get("goals"):
            parts.append("  Active goals:")
            for g in strategy["goals"][:6]:
                parts.append(f"    - {g}")
        if strategy.get("bottlenecks"):
            parts.append("  Known bottlenecks:")
            for b in strategy["bottlenecks"][:4]:
                parts.append(f"    - {b}")
    if recalled:
        parts.append("\nSEMANTICALLY RELEVANT PRIOR MESSAGES:")
        for r in recalled[:5]:
            when = r.get("created_at", "")[:10]
            role = r.get("role", "user")
            parts.append(f"  [{when} · {role}] {r.get('text','')[:240]}")
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------- diagnostics
async def health() -> dict:
    """Quick health snapshot used by admin /memory/health endpoint."""
    client = await _get_qdrant()
    info = {"qdrant_ready": client is not None,
            "embed_model":  EMBED_MODEL,
            "path":         QDRANT_PATH}
    if client is not None:
        try:
            cols = client.get_collections()
            info["collections"] = [c.name for c in cols.collections]
        except Exception:
            info["collections"] = []
    return info
