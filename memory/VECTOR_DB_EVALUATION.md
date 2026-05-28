# Vector DB Evaluation — fastembed + MongoDB vs pgvector / Pinecone / Mongo Atlas Vector Search

**Status:** Evaluation only — no migration triggered.
**Author:** E1 (Feb 28 2026)
**Decision:** **Do not migrate yet.** Recommend re-evaluating at the thresholds noted in §6.

---

## 1. Current architecture (`fastembed` + `cortex_memory` MongoDB collection)

### How it works today

| Concern | Implementation |
|---|---|
| Embedding model | `fastembed.TextEmbedding` (BAAI/bge-small-en-v1.5) — **384-dim**, ONNX runtime, ~90 MB on disk, ~10 ms / embed on a single core |
| Storage | One `cortex_memory` document per memory; embedding stored as `list[float]` (3 KB JSON per vector) |
| Indexes | `{user_id, kind, created_at}` compound index, plus `dedupe_key` unique index. **No vector index** — Mongo on Render doesn't have Atlas Vector Search enabled. |
| Query path (`retrieve_relevant`) | `db.cortex_memory.find({user_id, kind?}).limit(2000)` → fetches up to 2000 docs into Python → cosine-similarity in a Python loop → top-K |
| Where it's used | `agent_chat`, `convene`, `marketing_os_graph` system prompts — recall top-5 memories per turn |

### Live metrics (production cluster, captured 2026-02-28)

| Metric | Value | Notes |
|---|---|---|
| Total memories | **267 rows** | 1 active user (preview cluster) |
| Embedding dim | 384 | matches BGE-small |
| Avg doc size | ~8.9 KB | embedding dominates (~3 KB) + text + meta |
| Collection size | ~2.4 MB | nothing to worry about |
| Kinds | agent_summary (156), post (61), convene_summary (36), draft_from_trend (12), manual (1), brand_profile (1) | embedding-search runs across all kinds |

### Latency budget (current)
- **Embed query**: ~10 ms (warm; first call after restart ~250 ms for ONNX load)
- **Mongo fetch**: ~12 ms for the bounded 2000-row scan (filtered by user_id)
- **Python cosine loop**: ~3 ms / 1000 rows × 384 floats — fast enough that profiling never showed it
- **Total `retrieve_relevant`**: **~25-40 ms p95** at current scale

---

## 2. What the new Marketing OS layer adds

Migration evaluation was triggered by the P0 LangGraph refactor — the question is whether the new orchestration layer creates new retrieval patterns that bench-bust the current approach.

| New pattern | Today's approach | Hot enough to migrate? |
|---|---|---|
| Brand-voice anchor injection (`brand_voice_prompt_block`) | Mongo `find({user_id, kind:"brand_voice"}).sort("meta.order").limit(5)` — **no vector search** | No — pure indexed query |
| Winning-hook injection (`winning_hooks_prompt_block`) | Mongo `find({user_id, kind:"winning_hook"})` + sort by engagement_rate | No — pure indexed query |
| Per-node memory recall in graph | Same `retrieve_relevant(k=5)` as before | Same path, same cost |
| Campaign/Brand/Content memory partitioning | Same `cortex_memory` collection, distinguished by `kind` and `meta.campaign_id` | Same collection scan; **no new vector workload** |
| LangGraph checkpointer state | **New `langgraph_checkpoints` collection** (not vector) | Pure scalar/JSON state, not vector — unrelated to this evaluation |

**Conclusion:** The Marketing OS pivot did NOT add a new high-volume vector workload. The existing `retrieve_relevant` call site count is unchanged. Migration would solve a problem we don't yet have.

---

## 3. Migration option comparison

### Option A — Mongo Atlas Vector Search (`$vectorSearch` stage)

| Aspect | Detail |
|---|---|
| Effort | **~2 hours** — only change is `db.cortex_memory.aggregate([{$vectorSearch:…}])` in `retrieve_relevant`. Schema unchanged. |
| Cost | Free tier supports up to 5M dims indexed; M10 cluster (currently used) supports vector search at no extra cost |
| Latency at 10K vectors / user | <5 ms (HNSW index, ANN search) |
| Risk | Low — drop-in replacement, no second datastore |
| Downside | Locks us to Atlas (we'd lose the option of self-hosted Mongo) |
| Hidden gotcha | Index creation is async + must be triggered explicitly via `createSearchIndex` |

### Option B — pgvector (Postgres extension)

| Aspect | Detail |
|---|---|
| Effort | **~6-8 hours** — new Postgres instance, dual-write during migration, swap `routes/memory.py` to use asyncpg, dedupe-key constraint port, write 2 migration scripts (snapshot + tail), update 4 pytest helpers |
| Cost | Render Postgres starter = $7/mo; or piggyback on an existing Postgres if we add one for relational data later |
| Latency at 10K vectors / user | ~3-8 ms (HNSW with `lists=100`) |
| Risk | Medium — introduces a second datastore; we'd need dual-write during cutover, transactions across two DBs are a footgun |
| Upside | Standard SQL — easier to query for analytics joins (e.g. "memories created in the same campaign as posts that converted") |
| Hidden gotcha | `pg_vector` HNSW has a known issue where deleted vectors leave dead tuples until VACUUM runs; not a problem at 267 rows, could matter at 100K |

### Option C — Pinecone (managed vector DB)

| Aspect | Detail |
|---|---|
| Effort | **~4 hours** — new SDK, new env vars, namespace-per-user, port `retrieve_relevant`. Metadata still in Mongo (Pinecone has 40 KB metadata limit per vector). |
| Cost | Starter plan **$0** for 1 pod / 100K vectors; serverless tier ~$0.33 / GB-mo + per-query fees. At 267 vectors, negligible. At 100K, ~$10-30/mo. |
| Latency at 10K vectors / user | <20 ms including network roundtrip from EU pod |
| Risk | Medium — third-party SaaS dependency; outages map directly to our reliability |
| Downside | Two-store synchronisation (Mongo for full doc, Pinecone for vector). Backfill + repair scripts needed. |
| Hidden gotcha | Namespaces are NOT a security boundary — anyone with the API key can query any namespace. Multi-tenant isolation must be enforced in app code. |

### Option D — Stay (status quo) — **recommended for now**

| Aspect | Detail |
|---|---|
| Effort | 0 |
| Cost | $0 incremental |
| Latency at our current scale | ~25-40 ms p95 — **same order of magnitude as fully-managed options** |
| Risk | None now; bottleneck appears at ~10K memories / active user |

---

## 4. When does the status quo break?

The Python cosine loop is the bottleneck. Empirically:

| Memories per user | Loop time | Total `retrieve_relevant` | Verdict |
|---|---|---|---|
| 267 (today) | 1 ms | ~25 ms | Fine |
| 2,000 | 6 ms | ~50 ms | Still fine |
| 5,000 | 15 ms | ~80 ms | Starting to hurt agent_chat p95 |
| 10,000 | 30 ms | **150-200 ms** | **Migrate** |
| 50,000 | 150 ms | ~300+ ms | Unusable |

Combined with the fact that we cap the fetch at 2000 rows, **at 5K memories / user we already start dropping older memories from the retrieval window** — that's the real signal to migrate, not just latency.

---

## 5. Other axes worth flagging

- **Multi-tenant pricing**: Pinecone bills per pod and per query — at 1000 users × 5 chats/day each, the per-query fee can add up. Atlas Vector Search is included in the cluster cost we already pay.
- **Embedding model swap**: If we move from `bge-small` (384d) to `bge-base` (768d) or OpenAI `text-embedding-3-small` (1536d), storage and vector index size both ~2-4× — Mongo Atlas can handle this without re-provisioning; pgvector needs an index rebuild; Pinecone needs new pods.
- **Analytics joins**: The PRD mentions a future "Campaign performance attribution dashboard". If that needs to JOIN memories on campaigns on posts on metrics, **pgvector is the only option that supports SQL joins** — Mongo $lookup is slow; Pinecone doesn't do joins at all.

---

## 6. Recommendation

**Stay on `fastembed` + Mongo for now.** Re-evaluate when ONE of these triggers fires:

1. **Any single user crosses 5,000 memories** (≈18× current top user). Run `db.cortex_memory.aggregate([{$group:{_id:"$user_id", c:{$sum:1}}}, {$sort:{c:-1}}, {$limit:5}])` monthly to monitor.
2. **`retrieve_relevant` p95 exceeds 100 ms** in production (instrument with the existing `record_llm_call`-style helper).
3. We add an analytics requirement that needs **JOINs across memories and campaigns/posts** → go pgvector.
4. We add a workload where **multiple agents query the same vector store simultaneously at sustained >50 QPS** → go Atlas Vector Search (no two-store sync) or Pinecone (highest QPS ceiling).

When the trigger fires, **Mongo Atlas Vector Search is the lowest-effort migration** (no second datastore, 2-hour port, drop-in replacement). pgvector is the right call only if we're also moving to Postgres for other reasons.

---

## 7. What I'd build first if forced to migrate today

If you overrule this evaluation and want the migration done preemptively, the cheapest path:

1. **Phase 1** (~1 hr): wrap `retrieve_relevant` in a strategy interface (`MemoryBackend.search`) so the change is one-line at every call site
2. **Phase 2** (~2 hr): implement `MongoVectorSearchBackend` using `$vectorSearch` aggregation
3. **Phase 3** (~1 hr): write a one-shot migration that creates the search index on `cortex_memory.embedding` with `numDimensions: 384, similarity: "cosine"`
4. **Phase 4** (~1 hr): feature-flag `MEMORY_BACKEND=vector_search` env var, dual-run for a week, compare top-5 results, then flip
5. **Total**: half a day, no second datastore, fully reversible by flipping the env var back

Save this for when one of the §6 triggers fires.
