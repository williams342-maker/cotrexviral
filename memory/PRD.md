# CortexViral — Product Requirements (PRD)

## Original Problem Statement
Create an all-in-one AI marketing OS ("CortexViral"). Replace fragmented agent dashboards with a Mission Dashboard where a master orchestrator ("Cortex") coordinates teams.

PRODUCT REQUIREMENTS: Mission-focused architecture, Autonomy Control Center, Event-driven agent loop. Recent: Unified Marketing Asset Upload Center, Autonomous Campaign Builder, Direct Social Media Publishing, SEO Content Architecture sprint, and migration of semantic vector memory to fix prod OOM.

## Architecture (current)
- Frontend: React SPA (CRA + craco), Tailwind, Shadcn UI, framer-motion, react-snap (build-time static HTML for SEO).
- Backend: FastAPI, Motor (async Mongo), heavy use of `asyncio.gather` and `asyncio.create_task`.
- AI: Emergent LLM Key (Claude Haiku 4.5 for triage/classification, Claude Sonnet 4.5 / GPT-4o for generation, OpenAI text-embedding-3-small for vectors in Mongo).
- Integrations: Stripe (test), SendGrid, Meta/YouTube/LinkedIn/TikTok/Pinterest OAuth, Whisper, Nano Banana images.

## Key Files
- `frontend/src/pages/dashboard/CommandCenter.jsx`        ← Cortex chat orchestration (computes `thinkingTurn`)
- `frontend/src/pages/dashboard/cortex/CortexThinkingCard.jsx`  ← right-rail "Cortex is analyzing" card (NEW)
- `frontend/src/pages/dashboard/cortex/StageComponents.jsx`     ← in-chat FindingsCard with progress bar
- `frontend/src/pages/dashboard/cortex/OpportunityRail.jsx`     ← mounts CortexThinkingCard into the rail
- `frontend/src/index.css`                                       ← `cv-indeterminate` keyframe
- `frontend/src/lib/backendUrlGuard.js`                          ← runtime guard for prod backend-URL mismatch
- `backend/cortex/optimization_loop.py` & `backend/routes/cortex_stream.py` ← async optimized
- `backend/routes/public_tools.py`                                ← unauthenticated lead-magnet endpoints
- `backend/cortex/asset_storage.py`                               ← AssetStorage protocol + LocalDisk / EmergentObj / S3 backends + HybridStorage
- `backend/scripts/migrate_legacy_assets.py`                      ← one-shot disk→object-store migration CLI

## Completed (latest session)
- 2026-06-03  **Legacy Emergent → R2 migration completed.** New `backend/scripts/migrate_emergent_to_r2.py` reads from `EmergentObjStorage`, writes to `S3Storage` under identical storage_keys (so DB rows stay valid), and byte-verifies each transfer. Ran successfully: **9/9 active assets / 4.1 MiB moved in 5.3s, 0 failures**. R2 is now the canonical source of truth (88,226-byte PDF byte-identical between Emergent source and R2 destination, confirmed via live `/api/cortex/assets/file/{key}` proxy download).
- 2026-06-03  **Cloudflare R2 activated as primary asset storage** (P3 done). `ASSET_STORAGE_BACKEND=s3` + R2 creds set in `backend/.env` (bucket `cortexviral-assets`, endpoint `https://<account>.r2.cloudflarestorage.com`, region `auto`).
- 2026-06-03  **Post-mission "Next Steps" card** in `ChatMessage.jsx` — renders only on the last turn when stage=execution or _launched=true. Primary "↗ Track mission in sidebar" button + 4 starter-prompt chips. `cv-pulse-glow` keyframe in `index.css`. Screenshot-verified.
- 2026-06-03  **"Stranded analysis" bug fix** in `cortex/stages.py` (ANALYSIS DELIVERY RULE) + `ChatMessage.jsx` (StrandedAnalysisCard). Guard tests in `tests/test_stage_prompt_guards.py`.
- 2026-06-03  **Legacy disk → Emergent object storage migration completed.** Ran `python -m scripts.migrate_legacy_assets --delete-after` — 24 files / 16.2 MiB moved in 8.1s, 0 failures. `/app/backend/uploads/assets/` now empty. HybridStorage fallback remains as a safety net.
- 2026-06-03  **S3-compatible adapter shipped.** New `S3Storage` class (AWS S3, Cloudflare R2, Backblaze B2 via `AWS_S3_ENDPOINT_URL`). Activated by `ASSET_STORAGE_BACKEND=s3` + bucket/region/creds env vars. boto3 calls run via `asyncio.to_thread` so the event loop never blocks. Includes optional `presigned_get_url()` for large-video direct downloads.
- 2026-06-03  Tests: `test_migration_and_s3.py` (20 tests, all passing) covers iter/key helpers, dry-run, idempotency, delete-after, refuse-into-local safety, CLI subprocess smoke, and full S3Storage adapter unit coverage with boto3 patched out.
- 2026-06-03  **Asset storage migrated off local disk → managed object storage** (`EmergentObjStorage` + `_HybridStorage`). Selection driven by `ASSET_STORAGE_BACKEND=emergent`.
- 2026-06-03  **Regression tests for bulk endpoints**: `tests/test_bulk_endpoints.py` (18) + `tests/test_asset_storage.py` (11). 49/49 total new tests pass; 26/27 pre-existing asset-pipeline tests still green.
- 2026-06-03  Verified Cortex "Analyzing" right-rail card + in-chat FindingsCard progress bar render correctly.
- 2026-05-29..06-02
  - Cortex "Analyzing" progress bar + right-rail thinking card wired (`CortexThinkingCard`, `FindingsCard`, `cv-indeterminate` keyframe).
  - Optimized Cortex chat latency (~20s → ~4-7s) and optimization-loop scheduler (~100ms/user → ~2ms/user).
  - Document/Image upload chip pipeline parallelized with Claude Haiku 4.5 (45s → ~3s upload-to-chat).
  - Bulk select + bulk delete + bulk retry across Reports, Assets, Cortex Memory.
  - SEO Phases A & B: react-snap prerender, FAQ schema, Pricing, Case Studies, Comparisons, Free Viral Post Generator lead magnet.
  - Prod auth fix: `backendUrlGuard.js` to rewrite/warn on backend URL mismatch.
  - 90-day TTL index on `cortex_optimization_log`.
  - Mission cancel button in `ActiveMissionRail`.

## P0 / P1 / P2 backlog
- P1: WordPress Connect — Option A (self-hosted basic auth).
- P3: Activate S3-compatible backend in production (adapter ready — just flip `ASSET_STORAGE_BACKEND=s3` + AWS_S3_BUCKET/REGION/keys, or point at R2 via `AWS_S3_ENDPOINT_URL`).

## Notes
- Production vs Preview: prod bakes `REACT_APP_BACKEND_URL` at build time. ALWAYS ask the user whether a reported bug is on preview or prod before debugging.
- Performance: Claude Haiku 4.5 is intentional for triage stages (stages, intelligence extraction, bot bottleneck detection). Do not silently swap to Sonnet.
