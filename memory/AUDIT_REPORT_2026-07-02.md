# CortexViral — Codebase Audit & Alignment Report
_Generated 2026-07-02 · scope: `/app` preview snapshot_

## TL;DR
CortexViral has **shipped the ambitious vision** — you have a working AI-first Command Center with an orchestrator (`Cortex`), real L0–L5 autonomy plumbing, 5 live OAuth integrations, semantic memory on OpenAI embeddings, R2-backed asset storage, autonomous campaigns, and a mission dashboard with a live optimization loop. **62/62 regression tests pass** and preview + production are both healthy.

The problems are almost entirely **entropy from rapid iteration**, not missing features:

* **371 backend endpoints across 92 route files** — but only 81 are actually mounted. 10 files (~2,650 lines) are dead code.
* **96 frontend page components** — but only 33 are actually routed to. Everything else lives in the tree but is unreachable from the app.
* **Multiple parallel implementations** of the same concept (`Compose.jsx` vs `Composer.jsx`, `Autonomy.jsx` vs `AutonomyControl.jsx`, `Overview.jsx` vs `Main.jsx` vs `CommandCenter.jsx` vs `LegacyCommandCenter.jsx`, `routes/performance.py` vs `routes/perf_metrics.py`, `routes/trends.py` vs `routes/trends_engine.py`).
* **~4-5 backend routes still ship synthetic mocked data** (`performance.py`, `analytics.py`, `channels.py` legacy publish paths).

## 1. Feature-by-feature status

| Intended pillar | Status | Where it lives | Notes |
|---|---|---|---|
| **AI-first Command Center** | ✅ Working | `frontend/pages/dashboard/CommandCenter.jsx` + `backend/routes/cortex_stream.py` | SSE-streamed, sub-7s response, StrandedAnalysisCard + NextStepsCard shipped |
| **Autonomous orchestrator** | ✅ Working | `backend/cortex/*.py`, `backend/routes/cortex.py`, `cortex_console.py` | 5-stage discovery → analysis → recommendation → execution → measurement |
| **Agent team layer (Scout/Creator/Operator/Intelligence)** | ✅ Working | `backend/routes/teams.py`, `mission_loop.py` | Event-driven relay, wired to real routes |
| **L0–L5 autonomy** | ✅ Working | `missions.py:AUTONOMY_LEVELS`, `optimization_loop.py:433` | Level checks propagate through mission loop + execution gate |
| **Campaign execution** | ✅ Working | `backend/routes/campaigns.py`, `cortex_campaigns.py`, `cortex/campaign_builder.py` | Autonomous Campaign Builder is real |
| **Social platform integrations** | ⚠️ **Mixed** | `oauth_meta.py` (709 lines, 32 real signals), `oauth_youtube.py`, `oauth_linkedin.py`, `oauth_tiktok.py`, `oauth_pinterest.py` | All 5 real OAuth flows exist. But **legacy `channels.py` still labels itself MOCKED** and `support.py` still says "channels-mocked" |
| **Onboarding missions** | ✅ Working | `routes/onboarding.py` + `routes/cortex_onboarding.py` + `dashboard/cortex/OnboardingOrchestrator.jsx` | Two separate onboarding routes — see §3 |
| **Executive dashboard / Mission Control** | ✅ Working | `dashboard/Missions.jsx` (recently upgraded with dismiss + succeed) | Live summary strip + RecommendedActionHero + card grid |
| **Semantic memory** | ✅ Working | `backend/cortex/memory.py` (OpenAI text-embedding-3-small, 1536-dim) | Just fixed the fastembed dead-code bug in `routes/memory.py` |
| **Asset storage** | ✅ Working | `backend/cortex/asset_storage.py` | R2 primary + disk fallback, `S3Storage` + `EmergentObjStorage` + `_HybridStorage` |
| **Performance analytics** | ❌ **Mocked** | `routes/performance.py` returns synthetic `_mock_series` | See §2 |

## 2. Mocked / synthetic surfaces (must fix before deep prod usage)

| File | Line | What's mocked | Impact |
|---|---|---|---|
| `routes/performance.py` | 13-26 | `_mock_series` — sessions + revenue are synthetic per-request random walks | Any user who looks at Performance Analytics sees fake trends. **HIGH-VISIBILITY LIE.** |
| `routes/analytics.py` | mixed | Some per-post metrics use synthetic fallbacks when platform APIs fail | Lower risk — Pinterest live, others degrade gracefully |
| `routes/channels.py` | comments only | Legacy publish path was mocked before OAuth landed | The 5 `oauth_*.py` modules are real and superseded this — just misleading language |
| `routes/support.py` | 45-47, 74 | Support FAQ text still says "channels are MOCKED" | Wrong copy. Real OAuth works; the FAQ tells users otherwise. |
| `cortex/analysis_runner.py` | 8-12, 96, 208-258 | `_run_mock` is the runner for `competitor_audit` + `content_audit` job types | Explicitly labeled "SAFE MOCK". Long-form job UI works, but the outputs are simulated. |
| `routes/marketing_os_graph.py` | 487 | Mongo saver fallback when pytest mock URIs used | Test-only — leave as-is |

## 3. Duplicate / parallel implementations

### Backend

| Concept | Files | Recommendation |
|---|---|---|
| Memory | `routes/memory.py` + `cortex/memory.py` | KEEP both — `routes/memory.py` is the legacy public shim (now delegates to `cortex/memory.py`). Consider merging in a future sweep once no callers reference `routes/memory.py` directly. |
| Recommendations | `routes/cortex_recommendation_bridge.py` (6 endpoints) + `routes/cortex_recommendations.py` (**0 endpoints — DEAD**) + `cortex/recommendation_bridge.py` | DELETE `routes/cortex_recommendations.py` (560 lines, never imported by server.py, 0 endpoints declared). |
| Onboarding | `routes/onboarding.py` + `routes/cortex_onboarding.py` | KEEP both — different purposes (profile capture vs mission-driven first-run tour). Just document which is which in a top comment. |
| Optimization | `routes/cortex_optimization.py` (mounted, live) + `routes/optimization.py` (**NOT mounted, 5 endpoints, 530 lines**) | DELETE `routes/optimization.py` OR mount it and delete `cortex_optimization.py`. Pick one. Currently the unmounted one is dead code. |
| Analytics | `routes/analytics.py` + `routes/perf_metrics.py` + `routes/performance.py` | Merge to two: keep `perf_metrics.py` (time-series) + `analytics.py` (per-post platform metrics). **DELETE `performance.py` — it's the mock endpoint.** |
| Campaigns | `routes/campaigns.py` + `routes/cortex_campaigns.py` | KEEP both — first is manual, second is autonomous. Same UX; different execution paths. |
| Trends | `routes/trends.py` (TikTok trending) + `routes/trends_engine.py` (Reddit + Google Trends) | KEEP both — different data sources; combined into the same UI. |
| Admin | `routes/admin.py` (17 endpoints) + `routes/admin_settings.py` + `routes/admin_seller_os.py` | Fine — properly split by domain. |

### Backend — files NOT imported by `server.py` (dead code)

Total: **~2,650 lines of unused code across 10 files**.

```
audit_pdf.py            98 lines,  0 endpoints
brands.py               78 lines,  0 endpoints
content_layer.py       473 lines,  0 endpoints  ← historical Phase 3 experiment
cortex_recommendations.py 560 lines, 0 endpoints  ← duplicated by cortex_recommendation_bridge.py
hitl_reminders.py      192 lines,  0 endpoints
marketing_os_graph.py  749 lines,  0 endpoints  ← was an experimental LangGraph rewrite
model_router.py        110 lines,  0 endpoints
optimization.py        530 lines,  5 endpoints  ← duplicated by cortex_optimization.py
plans.py               244 lines,  0 endpoints
seller_emails.py       271 lines,  0 endpoints
```

### Frontend — likely-orphan pages worth investigating

All the following ARE technically routed but appear to be **historical artifacts of iteration**:

| Page | Status | Recommendation |
|---|---|---|
| `LegacyCommandCenter.jsx` | Routed at `/dashboard/legacy` — literally named "legacy" | DELETE + remove the route. The current `CommandCenter.jsx` is the replacement. |
| `Overview.jsx` + `Main.jsx` | Both routed but both are old "dashboard home" attempts | Pick one, delete the other. `CommandCenter.jsx` is now the default `/dashboard` route so both are probably dead. |
| `AITeam.jsx` + `Agents.jsx` + `Team.jsx` | Three names for "team roster" | Consolidate into `Team.jsx`. |
| `AgentWorkspace.jsx` + `CortexWorkspace.jsx` | Both handle `/dashboard/agent/:id` and `/dashboard/cortex/:id` — different concepts, but overlapping | Rename `AgentWorkspace` if it's still needed; delete if superseded by mission workspace. |
| `Compose.jsx` (page) + `cortex/Composer.jsx` (chat composer widget) | Different purposes; the naming collides | Rename `Compose.jsx` → `ComposePost.jsx`. |
| `Studio.jsx` | "Content Studio" — old writing UI | If Cortex Console + Creator team now cover this, retire. |
| `Chatter.jsx` | Old agent chat UI | Superseded by Cortex Console. Delete. |
| `Autonomy.jsx` (per-agent) + `AutonomyControl.jsx` (global slider) | Different scopes but confusingly named | Rename `Autonomy.jsx` → `AgentBudgets.jsx`. |
| `SiteScan.jsx` + `SeoReview.jsx` | Both scan sites for SEO | Pick one. |

## 4. What's currently working (keep as-is)

✓ **Cortex Console + streaming chat** (`cortex_stream.py`, `CommandCenter.jsx`)
✓ **Mission dashboard** with dismiss + succeed actions (just shipped)
✓ **R2 asset storage** with hybrid disk fallback + migration scripts
✓ **Semantic memory** on OpenAI embeddings, TTL-indexed, per-user capped
✓ **5 real OAuth integrations** (Meta, YouTube, LinkedIn, TikTok, Pinterest)
✓ **Autonomous campaign builder** (`cortex_campaigns.py` + `campaign_builder.py`)
✓ **Optimization loop** — parallelized, Haiku-triaged, sub-2ms/user
✓ **Landing / SEO surface** — prerendered, FAQ schema, pricing, case studies, lead-magnet tools
✓ **Password + Google auth**, session cookies, `backendUrlGuard.js` for prod URL mismatch
✓ **Test suite** — 62/62 pass covering memory, assets, migration, bulk endpoints, prompt guards

## 5. What appears incomplete

* **WordPress Connect (P1 backlog item)** — never started.
* **Real per-post metrics for Instagram / Facebook / LinkedIn / TikTok / YouTube** — only Pinterest is live per `analytics.py`; others return placeholder metrics.
* **`_run_mock` in `analysis_runner.py`** for `competitor_audit` and `content_audit` job types — should be replaced with real LLM-driven scans (Scout already handles seller discovery in real code).
* **`RecommendedActionHero` in `Missions.jsx`** has an eslint `set-state-in-effect` warning — race condition risk if the recommendation feed changes mid-mount.
* **Some pages (`Studio.jsx`, `Compose.jsx`) exist but haven't been touched since May 24-29 2026** — likely stale UX that never got promoted from experiments.

## 6. What should be REMOVED (delete without ceremony)

**Backend (~2,650 lines of dead code):**
```
backend/routes/audit_pdf.py
backend/routes/brands.py
backend/routes/content_layer.py
backend/routes/cortex_recommendations.py   ← duplicate of cortex_recommendation_bridge
backend/routes/hitl_reminders.py
backend/routes/marketing_os_graph.py       ← old LangGraph experiment
backend/routes/model_router.py
backend/routes/optimization.py             ← duplicate of cortex_optimization
backend/routes/plans.py
backend/routes/seller_emails.py
```

**Backend — replace mock with real or remove:**
```
backend/routes/performance.py              ← MOCKED synthetic series, actively misleading
backend/cortex/analysis_runner.py: _run_mock  ← keep the mock as a fallback, but stop routing real audit jobs into it
```

**Frontend (candidates for deletion after confirming no bookmarks in the wild):**
```
frontend/src/pages/dashboard/LegacyCommandCenter.jsx  (also remove route /dashboard/legacy)
frontend/src/pages/dashboard/Chatter.jsx
frontend/src/pages/dashboard/Studio.jsx (if superseded by Cortex Console)
frontend/src/pages/dashboard/Main.jsx (retain Overview.jsx OR retire both)
frontend/src/pages/dashboard/AITeam.jsx (fold into Team.jsx)
```

Also update `support.py` FAQ so it doesn't tell users channels are mocked when 5 real OAuth flows are live.

## 7. What should be KEPT

Basically all of the `cortex/*.py` module, all of `cortex_*` routes that are mounted, all 5 `oauth_*.py` routes, `missions.py`, `campaigns.py`, `cortex_campaigns.py`, `agent_personas.py`, `standups.py`, `experiments.py`, `briefs.py`, `growth_goals.py`, `listening.py`, `feedback_loop.py`, `mission_loop.py`, all `seller_*.py` routes, `marketing_os.py` (Marketing OS is different from `marketing_os_graph.py`), `metered_billing.py`, `sendgrid_webhook.py`, `meta_deletion.py`, `magic_link.py`, `password_auth.py`, `auth.py`, `account.py`, `email.py`, `oauth_*.py`, and the entire `frontend/src/pages/landing/*` + `frontend/src/pages/tools/*` + `frontend/src/pages/insights/*` trees.

## 8. What should be REBUILT

1. **`routes/performance.py`** — replace mock series with a real time-series query over `mission_events` + `agent_usage_ledger` + platform-metric rollups.
2. **Non-Pinterest analytics adapters** in `routes/analytics.py` — use the live OAuth tokens to fetch real per-post insights for Instagram Graph / Meta Ads / YouTube Analytics / LinkedIn / TikTok.
3. **`analysis_runner.py:_run_mock` for `competitor_audit` + `content_audit`** — currently these UI job types produce simulated output.
4. **The "dashboard home" surface** — decide once: is it `CommandCenter.jsx`, `Overview.jsx`, or `Main.jsx`? Kill the other two. Right now this is your #1 UX confusion source.

## 9. Top 5 highest-priority fixes (in order)

### P0 · Retire the performance mock
`routes/performance.py` returns synthetic random-walk data to every request. This is the single most user-visible dishonesty in the codebase. Either wire it to real Mongo aggregates or hide the "Performance" page until it has real data.
_Effort: 2-4 hours. Value: eliminates a trust-breaking bug on every dashboard load._

### P0 · Fix the "channels are MOCKED" copy in support.py + tour text
Real OAuth flows exist and work. The FAQ, support tour, and help copy still tell users otherwise. Users read "MOCKED" and assume the whole app is a demo.
_Effort: 30 minutes. Value: enormous — it's directly undermining conversion._

### P1 · Delete the 10 dead route files (~2,650 lines) + de-route Legacy pages
`optimization.py`, `cortex_recommendations.py`, `marketing_os_graph.py`, `content_layer.py`, `plans.py`, `seller_emails.py`, `hitl_reminders.py`, `brands.py`, `model_router.py`, `audit_pdf.py`. Plus remove the `/dashboard/legacy` route + delete `LegacyCommandCenter.jsx`, `Chatter.jsx`, `Studio.jsx`, `Main.jsx`, `AITeam.jsx`.
_Effort: 2 hours (test after each). Value: cuts codebase surface area ~15%, makes future refactors safer, cleans up the file tree so contributors don't confuse dead code with live paths._

### P1 · Consolidate dashboard-home ambiguity
Pick one landing page: `CommandCenter.jsx` (the current default `/dashboard` target) or `Overview.jsx`. Delete the other. Update the sidebar's default nav accordingly.
_Effort: 3 hours (mostly regression-testing the flows). Value: eliminates confusion about "which is the actual home page"._

### P2 · Wire real per-post analytics for at least one more platform (Instagram Graph)
Meta OAuth is live and has the tokens. Add an `/api/analytics/instagram/refresh` job that pulls `insights` for each post on the connected account. This unblocks the real feedback loop for the biggest platform in `channels.py`.
_Effort: 4-6 hours. Value: turns the feedback loop from "conceptual" into "measurable", enabling real optimization-loop decisions._

---

**Recommendation on cadence:** knock out P0-#1 and P0-#2 today (~2.5h total). Batch P1-#1 + P1-#2 into a single "cleanup PR" this week. Then move to P1 backlog (WordPress Connect) with a much cleaner house.

## Appendix — Numbers at a glance

* **371 total API endpoints** across 92 backend route files (81 mounted)
* **96 frontend page components** with 33 explicitly routed in `App.js`
* **62/62 regression tests pass** (memory, assets, migration, bulk endpoints, prompt guards)
* **~4,100 lines of Cortex core** (`backend/cortex/*.py`) — well-organized, actively maintained
* **~2,650 lines of dead backend routes** — recommended for deletion
* **5 live OAuth integrations** + Stripe + SendGrid + Nano Banana + OpenAI + Claude + Gemini + OpenAI Whisper
* **R2 + HybridStorage** for assets; MongoDB + OpenAI embeddings for memory
* Test file at `/app/memory/PRD.md` — current, up-to-date
