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

## Completed (latest session)
- 2026-06-03  **Asset storage migrated to managed object storage** (`EmergentObjStorage` + `_HybridStorage` wrapping legacy local-disk reads). New uploads go to Emergent's `/objstore/api/v1/storage` via `EMERGENT_LLM_KEY`. Selection driven by `ASSET_STORAGE_BACKEND=emergent`. Live e2e upload→download round-trip verified through `/api/cortex/assets/upload` + `/api/cortex/assets/file/{key}`.
- 2026-06-03  **Regression tests for bulk endpoints** added at `/app/backend/tests/test_bulk_endpoints.py` (18 tests) + `/app/backend/tests/test_asset_storage.py` (11 tests). All 29 pass plus 26 of 27 pre-existing asset-pipeline tests (1 skipped, pre-existing).
- 2026-06-03  Verified Cortex "Analyzing" right-rail card + in-chat FindingsCard progress bar render correctly (screenshot smoke test).
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
- P2: One-shot migration script to push pre-existing `/app/backend/uploads/assets/` files to Emergent obj storage (currently served via HybridStorage fallback).
- P3: Future S3-compatible adapter (Cloudflare R2 / Backblaze B2) if egress costs ever justify the switch — the AssetStorage protocol already supports a drop-in replacement.

## Notes
- Production vs Preview: prod bakes `REACT_APP_BACKEND_URL` at build time. ALWAYS ask the user whether a reported bug is on preview or prod before debugging.
- Performance: Claude Haiku 4.5 is intentional for triage stages (stages, intelligence extraction, bot bottleneck detection). Do not silently swap to Sonnet.
