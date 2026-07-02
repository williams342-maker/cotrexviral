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
- 2026-07-02  **P2 WordPress security hardening — SHIPPED.** Two fixes: (1) In-memory sliding-window rate limiter on `POST /api/wordpress/test` — 30/hour per user + 6 per 15-min per (user, target-host) — returns HTTP 429 with `Retry-After` header. Prevents using the endpoint as a WP-credentials brute-force oracle. (2) Rewrote `_wp_verify` as a two-step probe: base `/wp-json/wp/v2/users/me` first (proves the App Password is valid), then `?context=edit` for roles as best-effort. Hardened WP installs where security plugins block edit-context no longer get a false "Invalid credentials" — connection accepted with `roles_unknown=true` flag; UI shows a soft-warning copy in `wp-test-success`. Tests: 19 unit (`test_wordpress_selfhosted.py`) + 8 API (`test_wordpress_api.py`) + 2 live rate-limit (`test_wordpress_rate_limit_api.py`) = **29/29 pytest green**. Backend regression **79/79**. Testing agent iteration_36 → **12/12 scenarios PASS, zero bugs found**.
- 2026-07-02  **P1 WordPress Connect (Option A — self-hosted) SHIPPED.** New `routes/wordpress_selfhosted.py` implements Application-Password/Basic-Auth flow: `POST /api/wordpress/test` (verify without persist), `POST /api/wordpress/connect` (verify + Fernet-encrypt + upsert), `GET /api/wordpress/status`, and `publish_to_wordpress()` helper wired into `channels.publish()` dispatch for `platform="wordpress_selfhosted"`. Credentials stored encrypted under `db.channels.credentials.encrypted_app_password` using `CORTEXVIRAL_WORDPRESS_FERNET_KEY` (MultiFernet-ready for rotation). Refuses `http://` URLs, rejects subscribers (needs author/editor/admin), never leaks credentials in GET responses (`{credentials:0}` projection). New React `WordPressConnectDialog.jsx` modal intercepts the WP self-hosted card in `Channels.jsx` — three inputs + Test/Connect buttons + all data-testids, Connect disabled until Test succeeds. Tests: 13 unit (`tests/test_wordpress_selfhosted.py`) + 8 API (`tests/test_wordpress_api.py`, added by testing agent) = 21/21 passing. Backend regression 65/65. Testing agent iteration_35 → 12/12 scenarios PASS, zero bugs.
- 2026-07-02  **P1 second-pass frontend route cleanup — SHIPPED.** Deleted 5 orphan dashboard pages (`LegacyCommandCenter.jsx`, `Chatter.jsx`, `Studio.jsx`, `Main.jsx`, `AITeam.jsx`) and replaced their routes in `App.js` with `<Navigate replace/>` redirects: `/dashboard/legacy → /dashboard`, `/dashboard/chatter → /dashboard/growth-team`, `/dashboard/studio → /dashboard/compose`, `/dashboard/main → /dashboard`, `/dashboard/team → /dashboard/growth-team`. Pruned stale menu items + unused icon imports (Activity, Wand2, MessagesSquare) in `CommandPalette.jsx`. Repointed the Overview "Open Content Studio" quick-action to `/dashboard/compose`. Fixed React duplicate-key warning by switching Overview quickActions map key to `key={a.title}`. Testing agent verified all 5 redirects, palette contents, and no console errors. Backend regression pytest 52/52 passing.
- 2026-07-02  **P1 dead-code first pass** — see below.
- 2026-06-03  **Legacy Emergent → R2 migration completed.**
  - **Deleted `backend/routes/optimization.py`** (530 lines) — orphan module with 5 unmounted HTTP endpoints and 13 unreachable helper functions. Zero external references anywhere in the codebase. Frontend uses `/api/cortex/optimization/*` (from the different, live `cortex_optimization.py`).
  - **Quarantined analysis job types** `competitor_audit` + `content_audit`: removed from `JOB_TYPES` (routes/cortex_analysis_jobs.py) and `_RUNNERS` + `_PHASES` (cortex/analysis_runner.py). These previously routed to `_run_mock` which returned fake "preview complete" summaries. `_run_mock` function preserved as a documented scaffold for future job types (marked DEPRECATED, no active `_RUNNERS` entries reference it).
  - POST `/cortex/analysis-jobs` with quarantined types now returns HTTP 400 with a clear "Allowed: ['seo_scan', 'seller_discovery', 'site_scan']" error.
  - **Left alone in this pass** (Rule 3 — "possibly legacy but referenced"): `audit_pdf.py`, `brands.py`, `content_layer.py`, `cortex_recommendations.py`, `hitl_reminders.py`, `marketing_os_graph.py`, `model_router.py`, `plans.py`, `seller_emails.py` — all imported by production code paths despite declaring 0 endpoints themselves. Also frontend `Chatter.jsx`, `Studio.jsx`, `Overview.jsx`, `Main.jsx`, `AITeam.jsx`, `LegacyCommandCenter.jsx` — all currently routed in App.js.
  - **Left alone in this pass** (Rule 8): `billing.py` legacy `amount` field.
- 2026-07-02  **P0.5 repository trust audit complete.** Reclassified 224 grep hits; production-facing bucket is now 0. Fixed 6 user-visible strings across Listening.jsx (Capture → Add demo, DEMO badge on synthetic signals, honest empty state), Posts.jsx (analytics-vs-publishing clarification), AdminRoadmap.jsx (Instagram/Facebook/social listening/AI memory statuses updated from "todo/partial" to "shipped" to reflect actual code).
- 2026-07-02  **P0 UX + Stripe determinism refinements.**
  - Website Traffic empty state now renders as an intentional "COMING SOON" card with a ✓ Google Analytics / ✓ Search Console / ✓ Pixel checklist + "Connect Analytics" CTA (per user spec).
  - Added canonical `amount_cents` field to `payment_transactions` on all new writes; **backfilled all 48 existing rows** (`amount_cents = amount`); revenue aggregation is now deterministic (`amount_cents` preferred, `amount` fallback, both treated as cents — no heuristic).
- 2026-07-02  **P0 trust fixes shipped.** support.py FAQ + system prompt (9 articles reflecting reality), performance.py rewritten with real Mongo aggregates + not_configured sentinel for unavailable metrics, Channels.jsx subtitle now enumerates all 6 live OAuth flows, Compose.jsx toast + footer honest about what publishes live vs saves to calendar. New `backend/scripts/migrate_emergent_to_r2.py` reads from `EmergentObjStorage`, writes to `S3Storage` under identical storage_keys (so DB rows stay valid), and byte-verifies each transfer. Ran successfully: **9/9 active assets / 4.1 MiB moved in 5.3s, 0 failures**. R2 is now the canonical source of truth (88,226-byte PDF byte-identical between Emergent source and R2 destination, confirmed via live `/api/cortex/assets/file/{key}` proxy download).
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
- P2 (next up): **Real Google Analytics ingestion** — replace the "COMING SOON" Website Traffic card with real numbers from the user's connected GA4 property (needs OAuth playbook consult first).
- P3: Persist WordPress rate-limit counters to Mongo (currently in-memory per backend pod — fine at P2, needed if we ever run multi-pod behind a load balancer).
- P3: Surface `Retry-After` header to WordPress users as a UI countdown timer (currently just shown as detail text).
- P3: Activate S3-compatible backend in production (adapter ready — flip `ASSET_STORAGE_BACKEND=s3` + AWS_S3_BUCKET/REGION/keys, or point at R2 via `AWS_S3_ENDPOINT_URL`).

## Notes
- Production vs Preview: prod bakes `REACT_APP_BACKEND_URL` at build time. ALWAYS ask the user whether a reported bug is on preview or prod before debugging.
- Performance: Claude Haiku 4.5 is intentional for triage stages (stages, intelligence extraction, bot bottleneck detection). Do not silently swap to Sonnet.
