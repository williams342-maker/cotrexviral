"""Cortex hybrid memory.

Two-layer architecture per the product spec:

1. **Strategic Memory (Mongo)** — a distilled-down doc per user
   capturing their long-term business goals, recurring themes, and
   current bottlenecks. Updated by `update_strategy_summary()` every
   N turns (or via the nightly cron). Answers questions like:
       "What are Mike's current goals?"

2. **Semantic Memory (Mongo + OpenAI embeddings)** — every conversation
   turn is embedded with OpenAI `text-embedding-3-small` (1536-dim) and
   stored alongside the rest of your Cortex data in the
   `cortex_memory_v2` Mongo collection. Recall is a cosine-similarity
   sweep over the user's last N stored vectors, computed in numpy
   (~5ms for 500 vectors of 1536 dims). Answers questions like:
       "What did Mike say about Etsy sellers three weeks ago?"

   This is a deliberate trade-off vs Atlas Vector Search:
   - + No managed-vendor dependency, works on Emergent's 1Gi pods
   - + Survives pod restarts (data is in Mongo, not ephemeral disk)
   - + Same `MONGO_URL` you already use — no schema migration drama
   - − Linear scan, fine up to ~10k vectors per user. Past that,
       upgrade to MongoDB Atlas Vector Search or Pinecone (the
       `_cosine_topk` swap is a one-liner).

Both layers compose: every Cortex turn pulls (a) the strategy doc and
(b) the top-K semantically-similar prior turns, then injects them into
the system prompt so Cortex actually feels like a persistent partner.

Public API (unchanged from the previous fastembed/Qdrant implementation
— callers in `routes/cortex_stream.py`, `routes/cortex_console.py`, and
the strategic-memory cron see the same coroutine signatures):
    await record_turn(user_id, role, text, *, meta=None)
    await recall_semantic(user_id, query, *, k=5) -> list[dict]
    await get_strategy(user_id) -> dict | None
    await update_strategy_summary(user_id, *, force=False) -> dict

Required env var:
    OPENAI_API_KEY — used for the embedding API. The Emergent LLM key
    does NOT proxy embeddings (probed and confirmed 404). Costs are
    ~$0.00002 per turn at text-embedding-3-small pricing.

Optional env var:
    CORTEX_MEMORY_PER_USER_CAP — max vectors to keep per user (default
    500). Older vectors are pruned on insert so cosine scans stay fast.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---- numpy is OPTIONAL — degrade gracefully if missing -------------
try:
    import numpy as _np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _np = None  # type: ignore
    _HAS_NUMPY = False


COLLECTION_V2     = "cortex_memory_v2"     # new Mongo-backed memory
COLLECTION_LEGACY = "cortex_memory"        # historical Qdrant name
EMBED_MODEL       = "text-embedding-3-small"
EMBED_DIM         = 1536

_PER_USER_CAP = int(os.environ.get("CORTEX_MEMORY_PER_USER_CAP", "500"))
_OPENAI_KEY   = os.environ.get("OPENAI_API_KEY", "").strip()

# Shared httpx client for embedding calls — connection-reuse is what
# keeps per-call latency down to ~200ms after the first cold call.
_http_client: Optional[httpx.AsyncClient] = None
_http_lock = asyncio.Lock()


async def _get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None:
        return _http_client
    async with _http_lock:
        if _http_client is None:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                headers={"Authorization": f"Bearer {_OPENAI_KEY}"},
                http2=False,  # http2 deps are heavy; http1.1 keep-alive is plenty
            )
        return _http_client


async def _embed(text: str) -> Optional[list[float]]:
    """Embed a single text via OpenAI text-embedding-3-small. Returns
    None on error (callers degrade to no-semantic-recall, never crash)."""
    if not _OPENAI_KEY:
        logger.warning("cortex.memory: OPENAI_API_KEY not set; semantic memory disabled")
        return None
    if not text or not text.strip():
        return None
    try:
        client = await _get_http()
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            json={"model": EMBED_MODEL, "input": text[:4000]},
        )
        if r.status_code != 200:
            logger.warning("cortex.memory: embed HTTP %d: %s",
                            r.status_code, r.text[:200])
            return None
        return r.json()["data"][0]["embedding"]
    except Exception:
        logger.exception("cortex.memory: embed failed")
        return None


def _cosine_topk(query_vec: list[float], candidates: list[dict],
                  k: int) -> list[dict]:
    """Pure-Python cosine top-K. Used both as the primary search path
    AND as the documented swap-point if/when this collection outgrows
    the in-memory scan (target: replace with MongoDB Atlas Vector Search
    `$vectorSearch` stage or a hosted vector DB).

    Each candidate must have a `vector` key (list[float]). Returns a
    new list of {text, role, created_at, meta, score} sorted high→low."""
    if not candidates or not query_vec:
        return []
    k = max(1, min(k, len(candidates)))

    if _HAS_NUMPY:
        q = _np.asarray(query_vec, dtype=_np.float32)
        # Build matrix; skip any rows with the wrong dim defensively.
        rows = [c.get("vector") for c in candidates
                if isinstance(c.get("vector"), list)
                and len(c["vector"]) == len(query_vec)]
        if not rows:
            return []
        M = _np.asarray(rows, dtype=_np.float32)
        # Cosine = dot / (|q| · |row|). Vectorize.
        q_norm = _np.linalg.norm(q) or 1.0
        row_norms = _np.linalg.norm(M, axis=1)
        row_norms[row_norms == 0] = 1.0
        scores = (M @ q) / (row_norms * q_norm)
        # argpartition for O(n) top-K, then sort the top slice.
        idx = _np.argpartition(-scores, kth=k - 1)[:k]
        idx = idx[_np.argsort(-scores[idx])]
        out = []
        for i in idx:
            c = candidates[i]
            out.append({
                "text":       (c.get("text") or "")[:600],
                "role":       c.get("role", "user"),
                "created_at": (c.get("created_at").isoformat()
                                if isinstance(c.get("created_at"), datetime)
                                else c.get("created_at")),
                "meta":       c.get("meta") or {},
                "score":      float(scores[i]),
            })
        return out

    # numpy missing — degrade to a Python loop (still correct, just slower).
    import math
    q_norm = math.sqrt(sum(x * x for x in query_vec)) or 1.0
    scored: list[tuple[float, dict]] = []
    for c in candidates:
        v = c.get("vector")
        if not isinstance(v, list) or len(v) != len(query_vec):
            continue
        v_norm = math.sqrt(sum(x * x for x in v)) or 1.0
        dot = sum(a * b for a, b in zip(query_vec, v))
        scored.append((dot / (v_norm * q_norm), c))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, c in scored[:k]:
        out.append({
            "text":       (c.get("text") or "")[:600],
            "role":       c.get("role", "user"),
            "created_at": (c.get("created_at").isoformat()
                            if isinstance(c.get("created_at"), datetime)
                            else c.get("created_at")),
            "meta":       c.get("meta") or {},
            "score":      score,
        })
    return out


# ---------------------------------------------------------- write path
async def record_turn(user_id: str, role: str, text: str,
                       *, meta: Optional[dict] = None) -> Optional[str]:
    """Embed and store one conversation turn. Best-effort — failure
    logs and returns None so the chat endpoint never breaks just
    because the vector layer is sad."""
    if not text or not text.strip():
        return None
    vec = await _embed(text)
    if vec is None:
        return None

    from core import db
    point_id = uuid.uuid4().hex
    doc = {
        "id":         point_id,
        "user_id":    user_id,
        "role":       role,
        "text":       text[:4000],
        "vector":     vec,
        "dim":        len(vec),
        "model":      EMBED_MODEL,
        "created_at": datetime.now(timezone.utc),
        "meta":       meta or {},
    }
    try:
        await db[COLLECTION_V2].insert_one(doc)
    except Exception:
        logger.exception("cortex.memory: insert failed")
        return None

    # Prune oldest beyond the per-user cap so cosine scans stay fast.
    # Pinned turns are excluded from prune candidates — they're the
    # ones the user explicitly told us to keep around forever.
    try:
        n = await db[COLLECTION_V2].count_documents({
            "user_id": user_id,
            "$or": [{"pinned": {"$exists": False}}, {"pinned": {"$ne": True}}],
        })
        if n > _PER_USER_CAP:
            cutoff_cur = db[COLLECTION_V2].find(
                {"user_id": user_id,
                 "$or": [{"pinned": {"$exists": False}}, {"pinned": {"$ne": True}}]},
                {"_id": 0, "id": 1, "created_at": 1},
            ).sort("created_at", -1).skip(_PER_USER_CAP).limit(1)
            cutoff = await cutoff_cur.to_list(length=1)
            if cutoff:
                cutoff_ts = cutoff[0]["created_at"]
                await db[COLLECTION_V2].delete_many({
                    "user_id":    user_id,
                    "created_at": {"$lt": cutoff_ts},
                    "$or": [{"pinned": {"$exists": False}},
                             {"pinned": {"$ne": True}}],
                })
    except Exception:
        logger.exception("cortex.memory: prune skipped (non-fatal)")

    return point_id


# ----------------------------------------------------------- read path
async def recall_semantic(user_id: str, query: str,
                           *, k: int = 5) -> list[dict]:
    """Return top-K semantically-similar past turns for this user."""
    if not query or not query.strip():
        return []
    qvec = await _embed(query)
    if qvec is None:
        return []

    from core import db
    # Pull this user's recent vectors (capped at _PER_USER_CAP). The
    # `vector` field is large (~6KB per row at 1536 floats) so we cap
    # the candidate set rather than streaming the whole collection.
    cur = db[COLLECTION_V2].find(
        {"user_id": user_id},
        {"_id": 0, "text": 1, "role": 1, "vector": 1,
         "created_at": 1, "meta": 1},
    ).sort("created_at", -1).limit(_PER_USER_CAP)
    candidates = await cur.to_list(length=_PER_USER_CAP)
    return _cosine_topk(qvec, candidates, k=k)


# ------------------------------------------------ index bootstrap ----
async def ensure_indexes() -> None:
    """Idempotent — create the indexes we rely on for recall + prune.
    Safe to call multiple times. Called once from cortex_stream on its
    first request (lazy) since memory.py has no startup hook."""
    from core import db
    try:
        await db[COLLECTION_V2].create_index(
            [("user_id", 1), ("created_at", -1)],
            name="user_created",
            background=True,
        )
    except Exception:
        logger.exception("cortex.memory: ensure_indexes failed (non-fatal)")
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
                                    min_turns: int = 3) -> dict:
    """Distill recent conversation history into a strategy doc using
    Cortex's primary LLM. Idempotent — won't re-run if updated <30min
    ago unless `force=True`. Returns the latest strategy doc (or {} on
    error). Stored in `cortex_strategy` Mongo collection per user_id.

    Refresh policy is intentionally aggressive (30min cooldown,
    `min_turns=3`) because on production with semantic recall sized
    to ~500 vectors per user, the strategy doc is what makes Cortex
    feel like it actually remembers across days. The LLM call is one
    cheap classifier call per user every ~30min of activity — well
    inside the cost envelope.

    Schema written:
        { user_id, summary, goals: [...], bottlenecks: [...],
          recent_themes: [...], updated_at }
    """
    from core import db
    existing = await db.cortex_strategy.find_one({"user_id": user_id}) or {}
    now = datetime.now(timezone.utc)
    if not force and existing.get("updated_at"):
        last = existing["updated_at"]
        if isinstance(last, datetime) and (now - last) < timedelta(minutes=30):
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
    from core import db
    info: dict = {
        "embed_model":   EMBED_MODEL,
        "embed_dim":     EMBED_DIM,
        "openai_key_set": bool(_OPENAI_KEY),
        "numpy":          _HAS_NUMPY,
        "per_user_cap":   _PER_USER_CAP,
    }
    try:
        info["stored_turns"] = await db[COLLECTION_V2].count_documents({})
    except Exception:
        info["stored_turns"] = -1
    return info
