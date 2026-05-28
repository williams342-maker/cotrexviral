"""Memory system v1 — semantic recall for the CortexViral agents.

What it does
------------
Stores tagged pieces of user context (brand profile, published posts,
agent conversation summaries) as 384-dim vector embeddings. On every
agent chat we retrieve the top-K most relevant memories and inject them
into the agent's system prompt so replies get sharper with every
interaction.

Why local embeddings
--------------------
The Emergent LLM proxy currently doesn't expose embedding models, and
asking the user for a second API key just for embeddings would slow
adoption. `fastembed` runs locally (ONNX runtime, ~90MB model on first
run, ~10ms per embed), so we ship today with zero new external vendors.

Swap path
---------
The `embed_text` and `retrieve_relevant` functions are the only places
that touch the embedding model + similarity math. To move to
Pinecone/Qdrant/pgvector later, change those two functions — everything
upstream (ingestion hooks, retrieval API, frontend) stays the same.

Storage
-------
MongoDB collection `cortex_memory`:
    {
      "id": str (uuid),
      "user_id": str,
      "kind": "brand_profile" | "post" | "hook" | "agent_summary" | "manual",
      "text": str,            # the canonical phrasing we embed
      "embedding": list[float],  # 384 floats
      "meta": dict,           # platform, post_id, engagement, ...
      "created_at": datetime,
    }
"""
import asyncio
import logging
import math
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import db, api
from deps import get_current_user


# ---------------------------------------------------------------------------
# Lightweight p95 instrumentation for `retrieve_relevant`.
# In-process rolling window (no Mongo writes on the hot path). Read via
# `GET /api/admin/memory-perf`. Reset on process restart — that's fine,
# we sample continuously and the threshold check fires the moment p95
# crosses 100 ms (which is one of the migration triggers documented in
# /app/memory/VECTOR_DB_EVALUATION.md §6).
# ---------------------------------------------------------------------------
_RETRIEVE_LATENCIES_MS: "deque[float]" = deque(maxlen=1000)
_RETRIEVE_LATENCIES_BY_KIND: dict = {}  # for future per-kind breakdown


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding model — lazy-loaded so the worker boots fast
# ---------------------------------------------------------------------------
_EMBED_MODEL = None
_EMBED_LOCK = asyncio.Lock()


async def _get_embed_model():
    """Lazy + singleton. First call downloads the ONNX weights (~90 MB)
    and takes ~2s. Subsequent calls are instant."""
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL
    async with _EMBED_LOCK:
        if _EMBED_MODEL is not None:
            return _EMBED_MODEL

        def _load():
            from fastembed import TextEmbedding
            return TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        # Run blocking download/load in a thread so we don't stall the event loop.
        _EMBED_MODEL = await asyncio.to_thread(_load)
    return _EMBED_MODEL


async def embed_text(text: str) -> list[float]:
    """Return a normalized embedding vector for `text`."""
    if not text or not text.strip():
        return []
    model = await _get_embed_model()
    # fastembed yields ndarray rows; we materialise + cast to list[float] so
    # MongoDB can BSON-encode it.
    vecs = await asyncio.to_thread(lambda: list(model.embed([text])))
    if not vecs:
        return []
    return [float(x) for x in vecs[0]]


async def embed_many(texts: list[str]) -> list[list[float]]:
    """Batch variant — much faster than calling embed_text in a loop."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return []
    model = await _get_embed_model()
    vecs = await asyncio.to_thread(lambda: list(model.embed(texts)))
    return [[float(x) for x in v] for v in vecs]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ---------------------------------------------------------------------------
# Public helpers — called from other modules to ingest memories
# ---------------------------------------------------------------------------
async def remember(
    user_id: str,
    kind: str,
    text: str,
    *,
    meta: Optional[dict] = None,
    dedupe_key: Optional[str] = None,
) -> Optional[str]:
    """Ingest a memory. Returns the memory id (or None if text was empty).
    Pass `dedupe_key` to keep at most one memory of that key per user
    (e.g. dedupe_key=f"post:{post_id}" so we overwrite when a post is
    re-published instead of duplicating)."""
    text = (text or "").strip()
    if not text:
        return None

    vec = await embed_text(text[:1500])  # cap embed input — model max is 512 tokens
    if not vec:
        return None

    mem_id = str(uuid.uuid4())
    doc = {
        "id": mem_id,
        "user_id": user_id,
        "kind": kind,
        "text": text,
        "embedding": vec,
        "meta": meta or {},
        "created_at": datetime.now(timezone.utc),
    }
    if dedupe_key:
        doc["dedupe_key"] = dedupe_key
        await db.cortex_memory.update_one(
            {"user_id": user_id, "dedupe_key": dedupe_key},
            {"$set": doc},
            upsert=True,
        )
    else:
        await db.cortex_memory.insert_one(doc)
    return mem_id


async def forget(user_id: str, mem_id: str) -> bool:
    res = await db.cortex_memory.delete_one({"id": mem_id, "user_id": user_id})
    return res.deleted_count > 0


async def retrieve_relevant(
    user_id: str,
    query: str,
    *,
    k: int = 5,
    kinds: Optional[list[str]] = None,
    min_score: float = 0.25,
) -> list[dict]:
    """Top-K cosine-similar memories for `query`. Filters by `kinds` if
    given (e.g. ["post", "hook"]). Memories with score below `min_score`
    are dropped to avoid polluting the prompt with irrelevant noise.

    Latency is sampled into an in-process rolling window
    (`_RETRIEVE_LATENCIES_MS`, last 1000 calls) so the admin
    /memory-perf endpoint can surface p50/p95/p99. When p95 crosses
    100 ms we're at one of the migration triggers documented in
    `/app/memory/VECTOR_DB_EVALUATION.md`."""
    started = time.perf_counter()
    try:
        if not query or not query.strip():
            return []
        q_vec = await embed_text(query[:1500])
        if not q_vec:
            return []

        filt: dict = {"user_id": user_id}
        if kinds:
            filt["kind"] = {"$in": kinds}

        # MongoDB without Atlas Vector Search → we score in app. Bounded fetch
        # so the loop stays O(N) for N≤ a few thousand memories per user.
        rows = await db.cortex_memory.find(
            filt, {"_id": 0, "embedding": 1, "text": 1, "kind": 1,
                   "meta": 1, "id": 1, "created_at": 1},
        ).limit(2000).to_list(length=2000)

        scored = []
        for r in rows:
            sc = _cosine(q_vec, r.get("embedding") or [])
            if sc < min_score:
                continue
            scored.append((sc, r))
        scored.sort(key=lambda x: x[0], reverse=True)

        out = []
        for sc, r in scored[:k]:
            r = {**r}
            r.pop("embedding", None)
            r["score"] = round(float(sc), 4)
            out.append(r)
        return out
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _RETRIEVE_LATENCIES_MS.append(elapsed_ms)


def memories_to_prompt_block(memories: list[dict]) -> str:
    """Render retrieved memories as a single tagged text block ready to be
    appended to an agent's system prompt."""
    if not memories:
        return ""
    lines = ["<memory>"]
    for m in memories:
        kind = m.get("kind", "note")
        meta_bits = []
        meta = m.get("meta") or {}
        if meta.get("platform"):
            meta_bits.append(meta["platform"])
        if meta.get("engagement"):
            meta_bits.append(f"engagement={meta['engagement']}")
        tag = f"[{kind}" + (f", {', '.join(meta_bits)}" if meta_bits else "") + "]"
        lines.append(f"{tag} {m.get('text','')}")
    lines.append("</memory>")
    lines.append(
        "Use the memory above to keep your reply consistent with what you "
        "already know about this user. Reference specific facts (brand, "
        "niche, past results) when relevant. Do not invent details that "
        "contradict the memory."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
class _RememberRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    kind: str = Field("manual", min_length=1, max_length=32)
    meta: Optional[dict] = None


class _SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    k: int = Field(5, ge=1, le=25)
    kinds: Optional[list[str]] = None


@api.get("/memory/list")
async def list_memories(request: Request, limit: int = 100):
    """Return the calling user's stored memories, newest first."""
    user = await get_current_user(request)
    rows = await db.cortex_memory.find(
        {"user_id": user.user_id},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1).limit(min(500, max(1, limit))).to_list(length=500)
    return {"memories": rows, "total": len(rows)}


@api.post("/memory/remember")
async def add_memory(payload: _RememberRequest, request: Request):
    user = await get_current_user(request)
    mem_id = await remember(
        user.user_id, payload.kind, payload.text, meta=payload.meta or {},
    )
    if not mem_id:
        raise HTTPException(status_code=400, detail="Could not embed text")
    return {"ok": True, "id": mem_id}


@api.post("/memory/search")
async def search_memory(payload: _SearchRequest, request: Request):
    user = await get_current_user(request)
    results = await retrieve_relevant(
        user.user_id, payload.query, k=payload.k, kinds=payload.kinds,
    )
    return {"results": results, "count": len(results)}


@api.delete("/memory/{mem_id}")
async def delete_memory(mem_id: str, request: Request):
    user = await get_current_user(request)
    ok = await forget(user.user_id, mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


class _PromoteHookRequest(BaseModel):
    hook_id: str = Field(..., min_length=1, max_length=64)


@api.post("/memory/promote-hook")
async def promote_hook_to_brand_voice(payload: _PromoteHookRequest, request: Request):
    """Take a `winning_hook` memory row and write a derivative
    `brand_voice` memory so it shapes every future Nova generation
    (not just embedding-retrieval-dependent).

    Behaviour:
      - Looks up the winning_hook by id (scoped to the caller).
      - Strips the `[platform]` prefix and `(engagement rate:...)` tail
        for clean canon storage.
      - Inserts a `brand_voice` row with `meta.source_hook_id` set so
        idempotent re-promotion is a no-op via the dedupe key.

    Returns 404 when the hook doesn't belong to the user."""
    user = await get_current_user(request)
    row = await db.cortex_memory.find_one(
        {"id": payload.hook_id, "user_id": user.user_id, "kind": "winning_hook"},
        {"_id": 0, "embedding": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Hook not found")

    import re as _re
    raw = row.get("text") or ""
    cleaned = _re.sub(r"^\s*\[[^\]]+\]\s*", "", raw)
    cleaned = _re.sub(r"\s*\(engagement rate:[^)]+\)\s*$", "", cleaned).strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Hook text is empty after cleaning")

    meta = row.get("meta") or {}
    brand_voice_text = (
        f"This user's audience reacts strongly to this hook style — "
        f"prefer this voice/length/cadence in new content: \"{cleaned}\""
    )
    new_id = await remember(
        user.user_id, "brand_voice", brand_voice_text,
        meta={
            "source_hook_id":   payload.hook_id,
            "platform":         meta.get("platform"),
            "engagement_rate":  meta.get("engagement_rate"),
        },
        dedupe_key=f"promoted_hook:{payload.hook_id}",
    )
    if not new_id:
        raise HTTPException(status_code=400, detail="Could not embed hook")
    return {"ok": True, "id": new_id}


@api.get("/memory/brand-voice")
async def list_brand_voice(request: Request):
    """List the user's promoted brand-voice anchors. Powers a viewer
    panel on the dashboard. Sorted by `meta.order` asc (drag-reorder)
    with `created_at` desc as fallback for legacy rows."""
    user = await get_current_user(request)
    rows = await db.cortex_memory.find(
        {"user_id": user.user_id, "kind": "brand_voice"},
        {"_id": 0, "embedding": 0},
    ).limit(50).to_list(length=50)
    # In-memory secondary sort. Rows WITH meta.order land first (asc);
    # rows WITHOUT order come after, sorted by created_at desc.
    def _key(r: dict):
        meta = r.get("meta") or {}
        order = meta.get("order")
        ts = (r.get("created_at").timestamp() if r.get("created_at") else 0)
        return (1, 0, -ts) if order is None else (0, order, 0)
    rows.sort(key=_key)
    return {"brand_voice": rows, "count": len(rows)}


class _NewAnchorRequest(BaseModel):
    text:     str = Field(..., min_length=4, max_length=600)
    platform: Optional[str] = Field(default=None, max_length=32)


@api.post("/memory/brand-voice")
async def create_brand_voice_anchor(payload: _NewAnchorRequest, request: Request):
    """Write a brand-voice anchor *from scratch* — without an existing
    winning_hook. Lets users seed voice patterns before they have any
    winners, or capture aspirational copy from external sources."""
    user = await get_current_user(request)
    text = payload.text.strip()
    template = (
        f"This user's audience reacts strongly to this hook style — "
        f"prefer this voice/length/cadence in new content: \"{text}\""
    )
    new_id = await remember(
        user.user_id, "brand_voice", template,
        meta={
            "platform": (payload.platform or "").lower() or None,
            "source":   "manual",
        },
        # No dedupe_key — manual anchors are intentionally additive.
    )
    if not new_id:
        raise HTTPException(status_code=400, detail="Could not embed anchor")
    return {"ok": True, "id": new_id}


class _ReorderRequest(BaseModel):
    ids: list[str] = Field(..., max_length=50)


@api.patch("/memory/brand-voice/reorder")
async def reorder_brand_voice(payload: _ReorderRequest, request: Request):
    """Persist a drag-reordered priority for brand-voice anchors.
    Writes `meta.order` (0 = highest priority) so the prompt block
    builder emits the most-wanted patterns first."""
    user = await get_current_user(request)
    for idx, mem_id in enumerate(payload.ids):
        await db.cortex_memory.update_one(
            {"id": mem_id, "user_id": user.user_id, "kind": "brand_voice"},
            {"$set": {"meta.order": idx}},
        )
    return {"ok": True, "count": len(payload.ids)}


class _TestVoiceRequest(BaseModel):
    topic: str = Field(..., min_length=4, max_length=240)


@api.post("/memory/brand-voice/test")
async def test_brand_voice(payload: _TestVoiceRequest, request: Request):
    """Generate a tiny Nova preview that applies the user's current
    brand-voice anchors. Cheap by design (`fast` route = haiku, ~60
    words) so the modal can offer instant "what does my voice sound
    like" feedback without burning LLM budget."""
    from routes.ai import _gated_user, _llm, send_with_usage
    from routes.feedback_loop import brand_voice_prompt_block
    from routes.model_router import for_task
    user = await _gated_user(request)
    bv = await brand_voice_prompt_block(user.user_id, limit=5)
    if not bv:
        raise HTTPException(
            status_code=422,
            detail="No brand voice anchors set — add one first.",
        )
    system = (
        "You are Nova, the user's copy specialist. Produce ONE short "
        "draft (max 60 words, single paragraph, no hashtags, no "
        "preamble). The output MUST audibly echo the brand-voice "
        "anchors below."
        + bv
    )
    provider, model = for_task("fast")  # haiku for cost control
    session_id = f"bv_test:{user.user_id}"
    try:
        chat = _llm(session_id, system, model=model, provider=provider)
        # 25s timeout so a budget-capped key doesn't hang the request
        # past the ingress idle limit. Frontend gets a clean 504 it can
        # toast on.
        text, usage = await asyncio.wait_for(
            send_with_usage(chat, f"Draft a {payload.topic.strip()} hook."),
            timeout=25,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="LLM took too long — the universal key may be over budget. Try again in a few minutes.",
        )
    except Exception as e:
        msg = str(e)
        # LiteLLM surfaces budget-cap errors with the word "budget" in
        # the response body; map those to 429 so the UI shows a
        # friendlier "rate limited" toast instead of generic 503.
        if "budget" in msg.lower() or "rate limit" in msg.lower() or "429" in msg:
            raise HTTPException(
                status_code=429,
                detail="LLM budget cap reached for the universal key. Add balance in Profile → Universal Key, or try again later.",
            )
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {msg[:200]}")
    return {
        "draft":  (text or "").strip(),
        "model":  f"{provider}/{model}",
        "tokens": usage.get("total_tokens", 0),
    }


@api.post("/memory/reindex")
async def reindex_memories(request: Request):
    """Re-ingest the user's brand profile + latest 50 published posts.
    Idempotent — uses dedupe keys to overwrite existing entries.
    Useful after the user updates their onboarding or as a manual seed."""
    user = await get_current_user(request)
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    inserted = 0

    # 1. Brand profile
    if user_doc:
        bits = []
        if user_doc.get("brand_name"):
            bits.append(f"Brand: {user_doc['brand_name']}")
        if user_doc.get("website"):
            bits.append(f"Website: {user_doc['website']}")
        if user_doc.get("niche"):
            bits.append(f"Niche: {user_doc['niche']}")
        if user_doc.get("goals"):
            bits.append("Goals: " + ", ".join(user_doc["goals"]))
        if user_doc.get("platforms"):
            bits.append("Platforms: " + ", ".join(user_doc["platforms"]))
        if user_doc.get("challenge"):
            bits.append(f"Biggest challenge: {user_doc['challenge']}")
        if bits:
            await remember(
                user.user_id, "brand_profile",
                ". ".join(bits),
                meta={"source": "onboarding"},
                dedupe_key="brand_profile",
            )
            inserted += 1

    # 2. Latest 50 published posts
    cursor = db.posts.find(
        {"user_id": user.user_id, "status": "published"},
        {"_id": 0, "id": 1, "content": 1, "platforms": 1,
         "created_at": 1, "metrics": 1},
    ).sort("created_at", -1).limit(50)
    async for p in cursor:
        text = (p.get("content") or "").strip()
        if not text:
            continue
        meta = {
            "post_id": p.get("id"),
            "platform": (p.get("platforms") or [""])[0],
            "created_at": p.get("created_at"),
        }
        # If we have analytics, surface the headline engagement number
        m = p.get("metrics") or {}
        pin_m = m.get("pinterest") or {}
        if pin_m:
            meta["engagement"] = (
                f"impr={pin_m.get('impressions',0)} "
                f"saves={pin_m.get('saves',0)} "
                f"clicks={pin_m.get('clicks',0)}"
            )
        await remember(
            user.user_id, "post", text[:1500], meta=meta,
            dedupe_key=f"post:{p.get('id')}",
        )
        inserted += 1

    return {"ok": True, "indexed": inserted}



# ---------------------------------------------------------------------------
# Admin: retrieval latency observability — surfaces the migration trigger
# documented in /app/memory/VECTOR_DB_EVALUATION.md §6.
# ---------------------------------------------------------------------------
@api.get("/admin/memory-perf")
async def memory_perf(request: Request):
    """Returns the in-process rolling window of `retrieve_relevant`
    latencies with p50/p95/p99 + the migration-trigger flag.

    Sampled in-process; resets on backend restart. No Mongo writes on
    the hot path, so this is safe to call frequently from the admin
    dashboard."""
    from deps import require_admin
    await require_admin(request)
    samples = list(_RETRIEVE_LATENCIES_MS)
    n = len(samples)
    p50 = _percentile(samples, 50)
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    avg = (sum(samples) / n) if n else 0.0

    # 100 ms p95 is the migration trigger from VECTOR_DB_EVALUATION.md
    # §6. Once we cross it, the admin UI can surface a banner pointing
    # at the migration plan.
    p95_threshold_ms = 100.0
    migration_triggered = (n >= 50) and (p95 >= p95_threshold_ms)

    total_memories = await db.cortex_memory.count_documents({})
    distinct_users = len(await db.cortex_memory.distinct("user_id"))

    # Top 3 users by memory count — if any crosses 5000, that's also
    # a migration trigger.
    top_users = await db.cortex_memory.aggregate([
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 3},
    ]).to_list(length=3)
    top_user_count = top_users[0]["count"] if top_users else 0
    capacity_triggered = top_user_count >= 5000

    return {
        "samples":            n,
        "window_size":        _RETRIEVE_LATENCIES_MS.maxlen,
        "avg_ms":             round(avg, 2),
        "p50_ms":             round(p50, 2),
        "p95_ms":             round(p95, 2),
        "p99_ms":             round(p99, 2),
        "p95_threshold_ms":   p95_threshold_ms,
        "migration_triggered": migration_triggered,
        "capacity_triggered":  capacity_triggered,
        "total_memories":     total_memories,
        "distinct_users":     distinct_users,
        "top_user_memory_count": top_user_count,
        "migration_doc":      "/app/memory/VECTOR_DB_EVALUATION.md",
    }
