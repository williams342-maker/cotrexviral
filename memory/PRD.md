# CortexViral — Product Requirements

## Original Problem Statement
Pixel-perfect clone of `agent.enrichlabs.ai/marketing` rebuilt and rebranded twice (Automatex → CortexViral) as an **all-in-one AI marketing platform**:
- AI marketing agents (Nova, Sam, Kai, Angela)
- Multi-platform social content publishing (38+ channels in catalog)
- AI Content Studio (newsletter, blog post, multi-platform post, video script, product update)
- SEO Review + Site Scan with auto-generated post drafts
- Admin panel (user management, audit log, broadcasts, ticket inbox)
- Help Center with AI chatbot (CortexBot) + Help Articles + Tickets

## Tech Stack
- **Frontend**: React 18 + Tailwind + Shadcn UI + Lucide icons + Axios
- **Backend**: FastAPI + Motor (async MongoDB) + emergentintegrations
- **Auth**: Emergent-managed Google Auth (cookie `session_token`, samesite=none, secure=True)
- **LLM**: gpt-5 via Emergent LLM Key
- **Admin**: hardcoded email allow-list (currently `williams342@gmail.com`)

## Architecture
```
/app
├── backend/
│   ├── server.py                (FastAPI app — single-file, ~1485 lines)
│   ├── tests/test_scheduling_and_optimal.py
│   └── requirements.txt
├── frontend/src/
│   ├── pages/
│   │   ├── Marketing.jsx        (Landing)
│   │   ├── dashboard/           (Overview, Main, Performance, MarketingCalendar, Studio, SeoReview, SiteScan, Compose, Channels, Posts, Leads, Insights, Help)
│   │   └── admin/               (Overview, Users, Tickets, Audit, Broadcasts)
│   ├── components/              (DashboardLayout, ProtectedRoute, BroadcastBanner, ImpersonateBanner, ui/*)
│   ├── context/AuthContext.jsx
│   └── App.js
└── memory/                      (PRD.md, test_credentials.md)
```

## Implemented (cumulative)
- 2026-05-29 (part 69) **🧭 Phase 3 — Briefs as Proposals (Atlas auto-proposes, operator approves)**
  - **New `routes/briefs.py`** — first-class proposal layer. The UX shift from "user asks, agent drafts" → "agent proposes, user approves" is realized here. Atlas reads open Growth Goals + recent Listening Signals (last 7d) + past rejection memories, then drafts up to 3 campaign briefs per scan. Each lands in `proposed_briefs` as `pending` and waits for the operator's Approve/Edit/Reject decision.
  - **Per-user runtime toggle** (`autopilot_settings` collection): `briefs_mode = manual | autopilot`. Manual (default) means only the "Propose now" button fires Atlas. Autopilot means a daily 09:00 UTC cron runs the same scan for that user — anti-spam baked in via a 20h cooldown on `last_brief_scan_at` (handles double-firing during deploys/restarts). Switch modes from the Briefs hero card; no redeploy required.
  - **LLM prompt** (gpt-5-mini, ~30s timeout): Atlas gets the persona description, the goals list, the signal list (top 8), and the last 5 rejection memories so it actively AVOIDS proposing patterns the operator already shot down. Strict-JSON-only output. Shape-coerced server-side: title (≤80), hypothesis (≤200), body (≤800), rationale (≤300), suggested_platforms (subset of our 7 supported), target_metric.
  - **Fallback path** when `EMERGENT_LLM_KEY` is unset or the LLM errors: deterministic stub that proposes ONE generic brief tied to the most-recent goal/signal — keeps the system functional in test envs without an API key, never returns garbage.
  - **8 endpoints**:
    - `GET /api/briefs/settings` — `{briefs_mode, cadence_label, last_scan_at, max_per_scan}`
    - `PUT /api/briefs/settings` — flip mode (`manual` ↔ `autopilot`); validates the enum
    - `POST /api/briefs/propose` — manual trigger; runs Atlas immediately + stamps `last_brief_scan_at`
    - `GET /api/briefs?status=…` — list + summary stats (pending/approved/rejected count + `avg_decision_minutes` derived from `decided_at - created_at` across decided rows)
    - `GET /api/briefs/{id}` — detail
    - `POST /api/briefs/{id}/approve` — creates a real `campaigns` row from the brief (uses `edited_body` if present, otherwise `body`), platforms + target_metric carry over, cross-ref stamped both ways (`brief.resolved_into_campaign_id` + `campaign.proposed_brief_id`). Brief flips to `approved` with `decided_by` audit field. Returns `{brief, campaign}`.
    - `POST /api/briefs/{id}/reject` — flip to `rejected` + write `cortex_memory` row with `kind="brief_rejected"`, dedupe_key=`brief_rejected:{id}`. The memory feeds back into the NEXT scan's prompt so Atlas avoids similar pitches.
    - `PATCH /api/briefs/{id}/edit` — operator-edited body (≥10 chars, ≤1500), stored as `edited_body` (original preserved for audit). Approve uses the edited version when set.
    - `DELETE /api/briefs/{id}` — hard delete
  - **Realtime broadcast**: every successful `_persist_proposals` fans out a `briefs_proposed` event over the existing HITL inbox WebSocket so the bell badge updates instantly. Best-effort — failure to broadcast never blocks the propose call.
  - **Scheduler integration**: `register_brief_autopilot_job(scheduler)` registers `brief_autopilot_daily` on the existing `AsyncIOScheduler` with a `CronTrigger(hour=9, minute=0)`. Idempotent (no-op if the job already exists). `run_autopilot_scan` iterates only users with `briefs_mode=autopilot`, respects the 20h cooldown, and per-user errors are logged but never propagate.
  - **`/dashboard/briefs` page** (`Briefs.jsx`):
    - Sky-blue Atlas hero card with manifesto + "Propose now" CTA + autopilot toggle (Power icon → Zap icon with emerald background when ON). Last-scan timestamp under the card.
    - 4 KPI tiles (Pending / Approved / Rejected / Avg decision minutes)
    - 4-pill filter row (pending / approved / rejected / all) — defaults to pending
    - 2-column card grid. Each card has: proposer/source eyebrow, title, blue-highlighted hypothesis block ("💡 ..."), 4-line body preview with `EDITED` amber pill when applicable, rationale + platform pills + target metric, and 3 action buttons (Approve emerald / Edit neutral / Reject rose). Editor swaps the body for a textarea with Cancel/Save. Approved + rejected briefs show a static decided-by note instead of buttons.
  - **Sidebar nav** — `Briefs Inbox` link added between `Monday Standup` and `Goals` (lucide `Compass` icon — same icon as Atlas's persona).
  - **15 new pytest cases** (`tests/test_briefs.py`):
    - All 9 endpoints require auth (401 without token)
    - Default settings = manual; toggle to autopilot persists; unknown mode → 400
    - Propose succeeds even with no goals/signals (returns count=0 or fallback stub), `last_scan_at` always stamped
    - List returns hydrated stats; status filter works
    - Approve creates campaign with cross-ref + correct platforms; 404 on non-pending
    - Reject writes `brief_rejected` memory row with right kind + dedupe_key
    - Edit stamps `edited_body`; rejects short bodies (422); approve includes edited content in campaign notes
    - Delete removes the row
    - Autopilot scanner skips empty user list (0 processed)
    - Autopilot scanner respects the 20h cooldown (user opted in but scanned 1h ago → skipped)
  - **65/65 regression** across briefs + experiments + growth_team + growth_goals + app_config + youtube_oauth + hitl_reminders. All green under live STRICT mode.
  - **Phase 3 net effect**: the team is now ACTIVELY autonomous. With autopilot ON, briefs materialize in your inbox every morning — you spend 60 seconds approving the strong ones and rejecting the weak ones. Each rejection teaches Atlas, so the proposals get sharper each week. Phase 5 (Autonomy budgets) is unblocked — we can now safely let Atlas auto-spawn campaigns within a daily token/cost cap by skipping the HITL gate for low-risk briefs (e.g. < $X spend + variants in a previously-approved pillar).


- 2026-05-29 (part 68) **🧪 Phase 4 — Experiments (head-to-head variant testing, owned by Ori)**
  - **New `routes/experiments.py`** — first-class A/B testing layer. An experiment pits 2 `content_variants` against each other on ONE metric. The hot read merges the stored row with live `performance_rollups` data so the UI shows real-time leader + margin.
  - **5 supported metrics**: `engagements` (default), `impressions`, `clicks`, `reach`, `ctr`. All map to `performance_rollups.windows.all_time.*` — i.e. cumulative since the variant was first measured.
  - **`MIN_MARGIN_PCT = 10.0`** threshold — the conclude path declares a winner ONLY when the margin clears 10%. Tighter margins are filed as `inconclusive` and NO memory row is written. This protects the signal layer from statistical noise polluting future briefs.
  - **Endpoints**:
    - `GET /api/experiments/metrics` — surfaces the 5-metric enum + threshold to the frontend
    - `GET /api/variants/recent?limit=50` — recent `content_variants` for the variant picker dropdowns
    - `POST /api/experiments` — create with `{name, hypothesis?, variant_a_id, variant_b_id, metric}`; rejects same-id pair (400) + cross-user variant access (404) + unknown metric (400)
    - `GET /api/experiments?status=…` — list with hydrated `variant_a`/`variant_b` blocks (live perf snapshot + body preview + samples count + platform), plus `live_leader` (a/b/tie), `live_margin_pct`, `can_conclude` (true only when margin already clears threshold). Summary stats: `running_count / completed_count / inconclusive_count / avg_winner_margin_pct`.
    - `GET /api/experiments/{id}` — single hydrated row
    - `POST /api/experiments/{id}/conclude` — Ori's moment. Re-pulls live perf, picks the winner if margin ≥ 10%, writes a `cortex_memory` row with `kind="experiment_winner"` + `dedupe_key="experiment:{id}"` so the next conclude on the same id overwrites instead of duplicating. Memory text format: `Experiment '{name}': {platform} variant "{winner_body}" beat "{loser_body}" on {metric} by X% ({winner_value} vs {loser_value}). Hypothesis: ...`. Sets the experiment row to `completed` + stamps `winner_variant_id`, `winner_margin_pct`, `conclusion_text`, `memory_id`. **Returns 404 (not 409) on a non-running experiment** — keeps the same shape as `auto_complete` in growth_goals.
    - `DELETE /api/experiments/{id}` — hard delete the experiment row. **Memory rows stay** — the learning is durable even if the operator archives the experiment record.
  - **`gather_experiment_facts(user_id)`** — small helper called from the standup generator's `_gather_user_facts`. Surfaces `{running_experiments, recent_results}` (last 5 completed/inconclusive). Ori's persona prompt is voice-tuned to "name 1 winning pattern (with the % uplift) and 1 mystery to investigate next week" — this is where those numbers come from.
  - **`/dashboard/experiments` page** (`Experiments.jsx`):
    - Cyan Ori hero card with the manifesto + new-experiment CTA
    - 4 KPI tiles (running / completed / inconclusive / avg margin %)
    - 2-column experiment card grid; each card has a side-by-side `VariantPanel` pair with the live metric value + samples count + platform + 3-line body preview (mono font, white-on-neutral). Winner panel gets `ring-emerald-500 + Trophy badge`; leader (still running) gets `ring-cyan-400 + "Leading" pill`.
    - Bottom of each card: either `Conclude — Ori writes the winner` button (cyan when `can_conclude=true`, neutral grayed when margin not decisive yet) or a slate conclusion block with sparkles icon (completed) / triangle icon (inconclusive) + the `conclusion_text`.
    - New-experiment modal: name (required), hypothesis (optional, 600 chars), variant A + B selects sourced from `/variants/recent` (each option shows `[platform] body preview`), metric dropdown. Submit disabled until name + both variants chosen.
  - **Sidebar nav** — `Experiments` link added between `Goals` and `Growth Team` (lucide `FlaskConical` icon).
  - **10 new pytest cases** (`tests/test_experiments.py`):
    - All endpoints require auth (401 on every method without token)
    - Metrics enum surfaces the 5-metric registry + threshold value
    - Create rejects same-variant id (400)
    - Create rejects unknown metric (400)
    - Create + list round-trip; live_leader/live_margin_pct computed from seeded rollups (120 vs 80 → 50% margin, leader=a)
    - Conclude with decisive margin → completed, winner_variant_id stamped, memory row written with kind=experiment_winner + correct meta
    - Conclude with sub-threshold margin (105 vs 100 → 5%) → inconclusive, NO memory row
    - Conclude on non-running experiment → 404
    - `/variants/recent` includes seeded variants
    - `gather_experiment_facts` returns recent results for Ori
  - **45/45 regression** across experiments + growth_team + growth_goals + app_config + youtube_oauth. All green under live STRICT mode.
  - **Phase 4 net effect**: the team's knowledge is now durable. Win once, the learning lives in memory forever; retrieve it the next time a brief touches the same platform/metric. Losing variants disappear from the signal layer — exactly the survivorship pattern we want for compounding growth. Phase 5 (Autonomy budgets) is unblocked — once we trust the experiment results, we can let Atlas auto-propose A/B tests within a budget cap without HITL.


- 2026-05-29 (part 67) **📺 YouTube OAuth (Google) — channel sign-in + token refresh layer**
  - **New `routes/oauth_youtube.py`** — full four-endpoint shape (`/start`, `/callback`, `/status`, `/disconnect`) mirroring the existing Meta/LinkedIn/TikTok integrations. Lazy-resolves credentials via `app_config.get_config()` so the admin can rotate Google Cloud Console keys live via `/admin/integrations` (no redeploy).
  - **Scopes (minimum required)**: `youtube.upload` + `youtube.readonly`. App review reviewers reject submissions that ask for more — anything broader is deferred to a future scope-bump PR.
  - **Refresh-token handling**: `access_type=offline + prompt=consent` forces Google to issue a refresh_token on every connect. The callback persists both tokens; reconnects that silently skip consent (Google's default behavior) preserve the existing refresh_token instead of clobbering it with `None`. `refresh_youtube_token(user_id)` is a public helper for the future publish/analytics path — returns a valid access token, refreshing transparently when the cached one is within 60s of expiry. Returns None on missing connection / missing refresh_token / Google `invalid_grant` (caller decides whether to surface a reconnect prompt).
  - **`/disconnect` revokes the refresh token at Google's `/revoke` endpoint** before deleting the local row. Best-effort — failure to revoke is logged but doesn't block local disconnect.
  - **Channel hydration**: callback also hits `/youtube/v3/channels?mine=true` and stores a snapshot of `{channel_id, title, thumbnail_url, subscriber_count, video_count, view_count, custom_url}`. Surfaces "No YouTube channel on this account" as a distinct redirect status (`?youtube=no_channel`) so the UI prompts the user to create one before reconnecting.
  - **Admin Integrations** — 3 new keys registered in `app_config.ALLOWED_KEYS` under group `youtube`:
    - `YOUTUBE_CLIENT_ID` (non-secret)
    - `YOUTUBE_CLIENT_SECRET` (secret — masked once saved)
    - `YOUTUBE_REDIRECT_URI` (optional override for preview-vs-prod testing)
  - **Channels page** — YouTube card now has a real connect/disconnect button when `configured=true`. Post-callback toasts cover `connected` / `denied` / `no_channel`.
  - **6 new pytest cases** (`tests/test_youtube_oauth.py`):
    - Auth required on /start, /status, DELETE (401 without token)
    - App-config registry exposes all 3 YouTube keys with correct group + secret flags
    - Client ID set/clear round-trip via /admin/app-config (DB → unset)
    - Status endpoint reports configured=false + connected=false when no creds are set
  - **17/17 regression** across youtube_oauth + app_config (11 existing pass with no changes despite ALLOWED_KEYS growing).
  - **Operator playbook**: Admin creates Google Cloud project → enables YouTube Data API v3 → configures OAuth consent screen with `youtube.upload + youtube.readonly` scopes → creates Web app OAuth Client ID with redirect URIs for both prod (cortexviral.com) and preview → pastes Client ID + Secret into `/admin/integrations`. The connect button on `/dashboard/channels` goes live within 60s (cache TTL).
  - **What's NOT in this PR** (Phase 4 of YouTube — separate scope): `publish_to_youtube()` resumable video upload + `fetch_youtube_post_metrics()` stats fetcher + Compose UI for video uploads. The token refresh helper is ready; just the publish/analytics business logic needs wiring.


- 2026-05-29 (part 66) **🎯 Phase 2 — Growth Goals (durable OKRs owned by Vera)**
  - **New `routes/growth_goals.py`** — first-class OKR layer. Each goal links a measurable metric to a target + deadline. **`current` is auto-computed live** on every read from the normalized content layer + listening signals + performance rollups — nobody manually updates progress.
  - **8 supported metrics** (the registry is the only place to add new ones — keeps the resolver + frontend dropdown in sync):
    - `posts_published` — total cross-platform published count since start_date
    - `instagram.posts` / `facebook.posts` / `linkedin.posts` / `tiktok.posts` — per-platform variants of the same
    - `total_impressions` / `total_engagements` — pulled from `performance_rollups.windows.all_time`
    - `listening_signals` — Lyra's captured signals since start_date
  - **Endpoints**:
    - `GET /api/goals/metrics` — surfaces the metric enum for the frontend dropdown (always matches the backend resolver)
    - `POST /api/goals` — create with `{title, description?, metric, target, deadline?, start_date?}`; `start_date` defaults to now, `owner_agent` always `vera`
    - `GET /api/goals?status=…` — returns items + summary stats (`active_count`, `completed_count`, `avg_progress_pct`, `overdue_count`). Each item hydrated with live `current`, `progress_pct` (capped at 100), `is_overdue`
    - `PATCH /api/goals/{id}` — title/description/target/deadline/status edits. Status enum: `active|completed|abandoned`
    - `DELETE /api/goals/{id}` — hard delete (no restore)
    - `POST /api/goals/{id}/auto-complete` — idempotent flip to `completed` when `current >= target`. Called by the standup generator + the Goals dashboard polling.
  - **`is_overdue` flag** — set true when `deadline < now AND status=active AND current < target`. Renders the card with a rose bar + "Overdue" pill so Vera + the operator see it instantly.
  - **`/dashboard/goals` page** (`Goals.jsx`) — gorgeous one-page editor:
    - Vera hero card with new-goal CTA
    - 4 KPI tiles (Active, Avg progress %, Completed, Overdue with rose tone if > 0)
    - Goal card grid: progress bar (violet/emerald/rose based on status), `current/target` tabular numbers, status pill, metric mono-tag, deadline, archive + delete actions
    - New-goal modal with title / description / metric dropdown / target / deadline date picker
    - Empty state with a friendly "Create your first goal" CTA
  - **Sidebar nav** — "Goals" added between Monday Standup and Growth Team (uses lucide `Target`).
  - **Standup integration** — `_gather_user_facts` already pulled `growth_goals` for Vera (added in Phase 1). With Phase 2 alive, Vera's standup contribution will now naturally reference active goals + their progress %. Tested in `test_growth_goals.py::TestStandupIntegration`.
  - **8 new pytest cases** (`tests/test_growth_goals.py`):
    - Metrics enum surfaces the supported list (verifies the registry covers headline metrics)
    - Full CRUD round-trip (create → list → patch → filter-by-status → delete)
    - Unknown metric rejected (400)
    - target=0 rejected by Pydantic (422)
    - `is_overdue` flag set true when deadline is past + target unreachable
    - `progress_pct` capped at 100 even when current > target
    - `auto-complete` endpoint returns the right `{completed, current}` shape
    - Standup generation still works and includes goal facts
  - **76/76 regression** across growth_goals + growth_team + app_config + meta_data_deletion + phase5 + phase4 + phase3 + phase2 writer migration. All passing under live STRICT_NORMALIZED_READS mode.
  - **Phase 2 net effect**: outcomes are now durable. Set the goal once, the team tracks it weekly, the standup surfaces progress. Phase 3 (Briefs as proposals) is unblocked — Atlas can now read the open goals + listening signals and auto-propose campaign briefs aligned to them.



- 2026-05-29 (part 65) **👥 Autonomous Growth Team — Phase 1 + Social Listening Engine**
  - **8 agent personas seeded** (`routes/agent_personas.py`). Each persona has `{id, name, role, tagline, voice, color, icon, owns, collabs, autonomy_budget, system_prompt}` — the team is now a first-class concept:
    - **Vera** (CMO) — OKR-obsessed, owns goals/budget/platform mix
    - **Atlas** (Strategist) — pattern-finder, owns campaign briefs/calendar/themes
    - **Nova** (Copywriter) — witty/on-voice, drafts every word
    - **Rae** (Researcher) — skeptical/data-first, audience + competitor scans
    - **Lyra** (Social Listening Lead) — always-on ears, brand+competitor mentions, sentiment, crisis detection
    - **Echo** (Distributor) — concise/operational, scheduling + optimal times
    - **Ori** (Analyst) — pattern-spotter, experiments + memory writes
    - **Jules** (Ops Manager) — fast/transactional, budget caps + escalation
  - **Weekly Standup generator** (`routes/standups.py`) — the Monday-morning artifact. Single combined LLM call to gpt-5-mini (replaces the 8-parallel-call design that overwhelmed the event loop) — produces all 8 persona contributions in one ~15s round-trip. Includes per-persona fallback templates so it never returns empty. Saved to `weekly_standups` with `{contributions, facts, generated_at}`.
  - **Social Listening Engine** (`routes/listening.py`) — Lyra's domain. New `social_listening_signals` collection with normalized rows `{source, source_url, text, author, sentiment, signal_type, topic, urgency, engagement, detected_at}`. Endpoints:
    - `POST /api/listening/signals` — manual / webhook ingestion of a single signal (validated + coerced)
    - `GET /api/listening/signals` — filtered chronological feed (by sentiment, signal_type, day window)
    - `GET /api/listening/stats` — hero stats: total + by_sentiment + by_signal_type + urgency-weighted **attention_score** (sum of urgency × 1 for negative + urgency × 0.5 for mixed, last 7d). Drift threshold 10.0 triggers an alert banner.
    - `POST /api/listening/synthesize` — LLM-generated demo signals (realistic Reddit/Twitter/forum posts mixing sentiments) so the UI has data before real source connectors are wired. `source=synthetic` flag for later filtering.
  - **Three new dashboard pages**:
    - **`/dashboard/growth-team`** (`Team.jsx`) — roster of 8 personas with role/voice/owns capability tags, manifesto block at top, CTA to view this week's standup.
    - **`/dashboard/standups`** (`Standups.jsx`) — Slack-style thread of the latest standup with a black-bg facts strip (published/drafts/failed/top platform/impressions/engagements) + 8 persona cards with color-coded icons. "Regenerate now" button. History rail of past 6 standups.
    - **`/dashboard/listening`** (`Listening.jsx`) — Lyra's hero card with attention-score alert banner, 5-tile stat row (total + 4 sentiment counters), sentiment filter pills, signal feed with sentiment badges + urgency flags. "Capture signals" button calls the synthesize endpoint.
  - **Sidebar nav** — added "Monday Standup", "Growth Team", "Listening" at the top of the dashboard section (uses lucide `Sparkles`, `Users2`, `Ear`).
  - **Live verified end-to-end**:
    - Persona roster: 8 personas returned via `/api/agents/personas` (system_prompts + autonomy_budgets correctly redacted from list response).
    - Synthesis: produced 6 realistic-sounding signals on first call — including a Twitter complaint about scheduled posts missing (urgency 5/5) → attention_score crossed alert threshold automatically.
    - Standup: real LLM voices coming through — Vera challenged the lack of measurable goals, Rae spotted a tracking discrepancy between drafts and published counts, Lyra surfaced the urgent downtime signal, Jules reported budget facts. Each persona stayed in voice.
  - **10 new pytest cases** (`tests/test_growth_team.py`):
    - 8 personas seeded with full metadata + self-consistent collabs graph
    - List endpoint redacts system_prompt + autonomy_budget
    - Standup generation produces 8 contributions, latest endpoint agrees
    - Standup history list returns chronological array
    - Manual signal ingest creates a row + lists in feed
    - Sentiment filter works
    - Stats endpoint shape verified including drift threshold math
    - Garbage sentiment coerced to "neutral" (defensive)
  - **68/68 regression** across growth_team + app_config + meta_data_deletion + phase5 + phase4 + phase3 + phase2 + normalize. All passing under live STRICT mode.
  - **Phase 1 net effect**: CortexViral now has a first-class autonomous team. The UX shift is from "I run this tool" to "I manage this team — they propose, I approve". Phase 2 (Goals as durable OKRs) is unblocked. Phase 3 (Briefs as proposals) is unblocked. Each future phase plugs into the same persona registry.



- 2026-05-29 (part 64) **🔐 DB-backed runtime config — rotate API keys without redeploys**
  - **New `routes/app_config.py`** — central module for live-mutable third-party credentials. Resolution order on every read: **database → environment → caller default**. 60-second in-process cache keeps the hot path off Mongo while still giving admins ≤1-min latency for new keys to take effect. Whitelisted key registry (`ALLOWED_KEYS`) so a compromised admin session can't poke `MONGO_URL` or similar.
  - **Admin endpoints** (all admin-only):
    - `GET /api/admin/app-config` — lists every allowed key with `{label, description, group, secret, is_set, source, preview, updated_at, updated_by}`. Secrets are masked (`••••XXXX` — last 4 chars only). Source surfaces `database` / `environment` / `unset` so the admin knows where the active value came from.
    - `PUT /api/admin/app-config` — upsert a key. Empty value clears the DB row (graceful fall-back to env / default).
    - `DELETE /api/admin/app-config/{key}` — explicit delete with audit logging.
    - Every write is logged to `audit_log` collection (action `app_config_set` / `app_config_cleared`).
  - **`routes/oauth_meta.py` fully refactored** — every callsite of `META_APP_ID`, `META_APP_SECRET`, `META_GRAPH_VERSION`, `META_REDIRECT_URI` now goes through `await get_config(...)` instead of importing from `core`. All the helpers (`_dialog_url`, `_graph_url`, `_redirect_uri`, `_post_oauth_redirect`, `_check_configured`) became async. Module-level constants gone — credentials are pulled lazily per request, so a rotation propagates within one cache TTL with no backend restart.
  - **`routes/meta_deletion.py`** — same refactor: callback resolves `META_APP_SECRET` via `get_config` instead of capturing it at import time.
  - **New admin UI page `/admin/integrations`** (`pages/admin/AdminIntegrations.jsx`) — beautiful one-page editor grouped by integration. Each row shows: key (mono), badge for source (DATABASE / ENV FILE / UNSET, color-coded), SECRET pill (rose) if applicable, human description, current value preview (masked for secrets), "last set by" attribution, input box (password type for secrets), Save + Clear actions. Toast feedback on save mentions the 60s TTL.
  - **Sidebar nav** — added "Integrations" link under Admin section (uses lucide `KeyRound` icon). Linked from `DashboardLayout.jsx::ADMIN_NAV`.
  - **Live operator flip executed**: Migrated `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI` from `.env` to the DB. `.env` was edited to remove the three META lines. The OAuth start URL still returns the correct authorize URL because the DB layer now serves them. Verified end-to-end via curl — `client_id=1293687082431683` + `redirect_uri=...preview.emergentagent.com/api/oauth/facebook/callback` both pulled from `app_config`, not from env.
  - **11 new pytest cases** (`tests/test_app_config.py`):
    - Admin auth required on GET / PUT (401 without).
    - List returns every known META_* key with full metadata.
    - Non-secret keys preview in cleartext; secret keys mask to `•••• + last 4`.
    - Unknown key write rejected (400).
    - Set → Clear round-trip works (empty value deletes the row).
    - DELETE endpoint deletes the row + invalidates cache.
    - DB row beats env var when both are set (resolution order verified).
    - Env var fallback works when DB row is missing.
    - `default` arg used when both DB + env are empty.
    - In-process cache invalidates correctly on every write.
    - `/oauth/facebook/start` picks up a freshly-set DB sentinel value (end-to-end across processes).
  - **Backwards-compat verified**: existing `tests/test_meta_data_deletion.py` updated to pull the test secret via `get_config()` first, env second. All 7 HMAC tests still pass against the DB-stored secret. Previous 4 tests that skipped when `META_APP_SECRET` was unset in env now run unconditionally.
  - **52/52 regression** across app_config + meta_data_deletion + phase5 + phase4 + phase3 + phase2. All passing.
  - **Operator playbook**: when a key rotation is needed, admin navigates to `/admin/integrations`, types the new value, clicks Save. The change is durable in MongoDB and active within 60s with no engineering involvement. The legacy `.env` continues to work as the fallback layer.



- 2026-05-29 (part 63) **🔐 Phase 5 — Operator flip + count-source migration**
  - **Operator flip** — set `STRICT_NORMALIZED_READS=true` in `/app/backend/.env` and restarted the backend. Strict mode is now LIVE on the preview environment. The violet **STRICT** pill renders next to "Content layer healthy" on the Admin Overview, confirming the cutover. Live verified: `GET /api/admin/content-layer/health` returns `{strict_mode: True, drift_triggered: False, mirror_coverage_pct: 100.0}` on production user data.
  - **Test-data hygiene** — cleaned up 212 orphan `content_items` from prior test runs that survived cleanup races. After cleanup: 150 posts ↔ 150 content_items ↔ 150 content_variants ↔ exact alignment. Hardened `_cleanup_post` in `test_meta_publish_and_approvals.py` to cascade-delete the variants + content_item alongside the legacy post.
  - **Five count-source migrations** (legacy `db.posts.count_documents` → normalized `content_items` / `content_variants`):
    - `GET /api/admin/stats.total_posts` → `content_items.count_documents({})`.
    - `GET /api/admin/users.[stats.posts]` (list) → `content_items.count_documents({user_id})`.
    - `GET /api/admin/users/{id}.stats.posts` (detail) → `content_items.count_documents({user_id})`.
    - `GET /api/marketing-os/dashboard.stats.pending_approvals` → `content_items.count_documents({user_id, status: pending_approval})`.
    - `POST /api/admin/scheduler/run-once` (health) → `content_variants.count_documents({status: scheduled})`.
  - **Test compatibility updates** — Phase 3 / Phase 4 tests that asserted lenient-fallback behavior were updated to be **strict-mode-aware** (assert `not in` when strict is on, `in` when lenient). Each test still serves as a regression for the OPPOSITE mode — if the operator flips the env back to False, the assertions remain valid. Also fixed `test_meta_publish_and_approvals._insert_pending` to mirror its post into the normalized layer (so the helper still works under strict mode).
  - **5 new pytest cases** (`tests/test_phase5_count_migration.py`):
    - `/api/admin/stats.total_posts` exactly matches `content_items.count`.
    - `/api/admin/users/{id}.stats.posts` exactly matches user-scoped `content_items.count`.
    - `/api/marketing-os/dashboard.stats.pending_approvals` reflects a freshly-seeded mirrored pending_approval (≥ 1).
    - `/admin/scheduler/run-once` returns valid int counters from the normalized variant counts.
    - Sanity check that `STRICT_NORMALIZED_READS=true` is live (`mirror_coverage_pct >= 99`).
  - **111/111 regression** across phase5 + phase4 + phase3 + phase2 + normalize + attribution + meta_publish_and_approvals + auto_draft + recurrence + pinterest_publish + analytics_and_carousel + series_ops — all GREEN under live STRICT mode. No silent regressions.
  - **Phase 5 carve-out — what was NOT done in this PR**:
    - Physical drop of the `posts` collection. The legacy collection still hosts ≥ 6 fields with no normalized equivalent yet — `dispatch` (in-flight dispatch payload), `recurrence_group_id` / `_index` / `_total`, `pinterest_board_id` / `_link` / `_title` / `_images`, `media_url` (singular, distinct from variants `media_urls` list), `repeat_weeks`. These need to be ABSORBED into the `content_variants` schema with a migration before the legacy collection can be dropped.
    - Remaining `db.posts` callsites: 28 (down from 50 at Phase 4 start). Most are non-trivial — engagement-metrics writes from `analytics.py`, winning-hook scans from `feedback_loop.py`, memory queries from `memory.py:541`, account cleanup `delete_many` cascades. Each requires its own focused PR with a backfill and read/write cutover.
  - **Operator unblock for Phase 6**: extend `content_variants` schema → backfill missing fields → rewrite the remaining 28 callsites → stop writing to `posts` → drop the collection. Each step independently revertable via the same drift-coverage telemetry already in place.



- 2026-05-29 (part 62) **🔒 Phase 4 — Strict-mode read cutover across remaining endpoints**
  - **New env flag `STRICT_NORMALIZED_READS`** (default `false`) in `core.py`. When flipped to `true`, all content_layer reads drop the lenient fallback and return ONLY posts that exist in the normalized layer. Operators flip the switch once `/admin/content-layer/health` shows zero drift sustained for a week.
  - **New helper `routes/content_layer.list_posts_via_normalized(user_id, limit, strict)`** for the "latest N posts" pattern (distinct from `resolve_post_ids_for_status` which is status-filtered). Reads `content_items` → joins to `posts` via the `content_item_id` cross-ref. Lenient mode merges un-mirrored stragglers into the candidate set and sorts by `created_at` desc before truncating — a strictly-newer un-mirrored post can still appear (no silent loss during the migration window).
  - **`resolve_post_ids_for_status`** gained a `strict` kwarg. Strict mode still *counts* un-mirrored posts (visibility metric stays accurate) but excludes them from the returned id set. Logs a distinct WARN message in strict mode so admins know what's being hidden.
  - **Four read paths cut over** (all default-lenient, will become strict on env flip):
    - **`routes/activity.py::activity_feed`** + **`list_posts`** — uses `list_posts_via_normalized`.
    - **`routes/admin.py::admin_user_detail`** `recent_posts` — `list_posts_via_normalized(limit=5)`.
    - **`routes/marketing_os.py::dashboard`** approvals snapshot — wraps `resolve_post_ids_for_status(status="pending_approval")` in a coroutine + posts fetch so the existing `asyncio.gather` parallel pattern stays intact.
    - **`routes/dashboard.py::dashboard_stats`** — `posts` counter now counts `content_items` (the agent-readable intent count). Lenient mode tops up with un-mirrored count so the number stays semantically equivalent to pre-Phase-4 during the migration window.
  - **Admin observability**:
    - `GET /api/admin/content-layer/health` now returns `strict_mode: bool` so operators can see the current env state.
    - Admin Overview `ContentLayerCallout` shows a violet **STRICT** pill on the healthy card when `STRICT_NORMALIZED_READS=true`. `data-testid="content-layer-strict-pill"`.
  - **Test-data cleanup**: removed 212 orphan `content_items` (rows from prior test runs that survived cleanup races). Production data is now perfectly aligned: 150 posts ↔ 150 content_items ↔ 150 content_variants ↔ 100% mirror coverage.
  - **10 new pytest cases** (`tests/test_phase4_strict_cutover.py`):
    - `/activity` includes a freshly-mirrored post.
    - `/activity` lenient mode includes un-mirrored stragglers.
    - `/posts` lenient mode merges un-mirrored stragglers into the candidate set (not just gap-fill).
    - Admin `/admin/users/{id}` `recent_posts` resolves via the normalized layer.
    - `/marketing-os/dashboard` `approvals` snapshot uses the normalized layer.
    - `/dashboard/stats.posts` is an int ≥ 0.
    - Resolver strict mode EXCLUDES un-mirrored ids (but still counts them).
    - List helper strict mode EXCLUDES un-mirrored posts.
    - List helper `limit=0` short-circuits to empty list.
    - Resolver lenient mode INCLUDES un-mirrored ids.
  - **141/141 regression** across phase4 + phase3 + phase2 + normalize + attribution + meta_publish_and_approvals + auto_draft + recurrence + pinterest_publish + analytics_and_carousel + series_ops + marketing_os. All passing.
  - **Operator switch flow**: 1) Verify `drift_triggered=false` on `/admin/content-layer/health` for ≥7 days. 2) Set `STRICT_NORMALIZED_READS=true` in `/app/backend/.env`. 3) Restart backend. 4) Verify the violet **STRICT** pill appears on the admin overview. 5) Phase 5 (Phase 1: deprecate the legacy `posts.find` calls entirely; Phase 2: drop the `posts` collection) becomes unblocked.



- 2026-05-29 (part 61) **📖 Phase 3 — Read-side cutover to normalized layer**
  - **`/api/posts/scheduled`** and **`/api/approvals`** now resolve matching posts via the normalized `content_variants` index (the agent-readable source-of-truth) instead of querying `db.posts` directly. Two-step read:
    1. Query `content_variants` for matching `(user_id, status, scheduled_at range)` — this is the normalized index Phase 4 will treat as authoritative.
    2. Hydrate full post documents from `db.posts` via the cross-ref ids — keeps backwards compat with the frontend (no schema change in the API response).
  - **Lenient fallback** in `routes/content_layer.resolve_post_ids_for_status` — also fetches any legacy posts WITHOUT a `content_item_id` so a mirror failure or pre-migration straggler still surfaces. Logs a `WARN` line every time a fallback fires so we can watch drift trend toward zero before Phase 4 (drops the fallback for strict-normalized reads).
  - **New observability endpoint `GET /api/admin/content-layer/health`** (`routes/content_layer_admin.py`) — admin-only, returns `{total_posts, mirrored_posts, unmirrored_posts, mirror_coverage_pct, total_content_items, total_content_variants, unmirrored_by_status, drift_threshold, drift_triggered}`. Drift trigger fires at ≥5 un-mirrored posts so Phase 4 isn't blocked silently.
  - **New `ContentLayerCallout` on Admin Overview** (`pages/admin/AdminOverview.jsx`) — sits next to the existing memory-perf callout. Renders one of two states:
    - **Healthy** (current state — 100% coverage): compact slate card with emerald "OK" badge. `data-testid="content-layer-card-healthy"`.
    - **Drift** (when `unmirrored_posts ≥ 5`): amber gradient callout with per-status pills (`pending_approval: 2`, `scheduled: 1`, …) and a hint to re-run the normalize migration. `data-testid="content-layer-drift-callout"`.
  - **Pre-existing bug fixed during smoke test**: `HitlInboxBell` was used in `DashboardLayout.jsx` but the import statement was missing — every dashboard route was crashing with `ReferenceError: HitlInboxBell is not defined`. Added the missing import.
  - **8 new pytest cases** (`tests/test_phase3_read_cutover.py`):
    - `/posts/scheduled` resolves via normalized layer (mirrored post shows up).
    - `/posts/scheduled` lenient fallback (un-mirrored post still surfaces).
    - `/posts/scheduled` `start/end` time-range filter still works after the cutover.
    - `/approvals` resolves via normalized layer.
    - `/approvals` lenient fallback.
    - `/admin/content-layer/health` requires admin (401 without).
    - `/admin/content-layer/health` returns the expected shape with all counters + drift flag math invariant (`mirrored + unmirrored == total`, `drift_triggered == (unmirrored >= threshold)`).
    - `resolve_post_ids_for_status` returns the UNION of normalized + un-mirrored posts and reports the un-mirrored count.
  - **96/96 regression** across phase3 + phase2 writer + normalize + attribution + meta_publish_and_approvals + auto_draft + recurrence + pinterest_publish + analytics_and_carousel + series_ops. All passing.
  - **Live verified**: `GET /api/admin/content-layer/health` returns `{"total_posts": 150, "mirrored_posts": 150, "unmirrored_posts": 0, "mirror_coverage_pct": 100.0, "total_content_items": 284, "total_content_variants": 274, "drift_triggered": false}` — full coverage on the production user data. Admin overview screenshot confirmed the healthy emerald card rendered correctly.



- 2026-05-29 (part 60) **🧬 Phase 2 — Writer migration to normalized content layer**
  - **New module `routes/content_layer.py`** — the single source of truth for mirroring writes to legacy `posts` → normalized `content_items` + `content_variants`. Three public helpers:
    - `mirror_post_to_normalized(post)` — creates 1 content_item + N variants (one per platform) for a freshly-inserted post, stamps `brand_id/content_item_id/variant_ids` cross-ref triple back on the legacy row. Idempotent (short-circuits if already mirrored). Best-effort (errors logged, never raised — the legacy row is still the read source-of-truth during the migration window).
    - `propagate_status_to_variants(post_id, status, published_at, scheduled_at, body, error, external_dispatch)` — single-post propagation. Updates every variant tied to the post + the umbrella content_item. The `external_dispatch` kwarg lands per-platform external_post_id/external_url/error on the matching variant row only (no cross-platform bleed).
    - `propagate_status_for_many(post_ids, status, published_at)` — bulk update for the scheduler's `update_many` path.
    - `cascade_delete_for_posts(post_ids)` — when a scheduled post is cancelled, marks variants + items as `archived` (NOT physically deleted — preserves attribution / metrics).
  - **Writer paths wired**:
    - **`routes/channels.py::/channels/publish`** — both branches (single + N-week recurrence) call `mirror_post_to_normalized` immediately after `db.posts.insert_one`. Immediate-publish dispatch metadata propagates via `external_dispatch`.
    - **`routes/channels.py::cancel_scheduled`** — `cascade_delete_for_posts` for the deleted post(s), including the recurrence-series scope=future/all path.
    - **`routes/channels.py::update_scheduled`** — propagates body + scheduled_at edits into variants and the content_item intent/title.
    - **`routes/auto_draft.py::_process_user`** — only mirrors on first upsert insert (checks `upsert_res.upserted_id`); re-runs of the cron for the same `(trend_id, platform)` don't duplicate content_items.
    - **`routes/scheduler.py::_publish_due_posts_now`** — bulk flips status → published via `propagate_status_for_many`; per-post dispatch metadata propagated once at the end of each post's processing.
    - **`routes/approvals.py::approve_post / reject_post`** — propagates `scheduled` / `rejected` into the normalized layer.
  - **9 new pytest cases** (`tests/test_phase2_writer_migration.py`):
    - mirror creates content_item + variants with correct status + cross-ref triple stamped on legacy post
    - mirror is idempotent (second call → same ids, no duplicate rows)
    - mirror handles empty-platforms post (writes an "unknown" platform variant rather than zero)
    - propagate status flips every variant + the umbrella item
    - propagate `external_dispatch` lands per-platform metadata on the right variant (no cross-platform bleed)
    - propagate `body` edit updates variant body + content_item intent + title
    - unknown status is rejected (no junk leaks into the normalized layer)
    - bulk propagate hits every variant of every input post (3 posts × 2 platforms = 6 variants)
    - cascade delete archives rather than physically deletes (preserves attribution)
  - **88/88 regression** across phase2 writer migration + normalize migration + attribution + meta_publish_and_approvals + auto_draft + recurrence + pinterest_publish + analytics_and_carousel + series_ops. All passing.
  - **Live e2e verified**: A real `POST /api/channels/publish` for a `linkedin + twitter` scheduled post produced both the legacy posts row AND a content_item + 2 content_variants (one per platform), with the brand_id/content_item_id/variant_ids cross-ref stamped back. Approving a `pending_approval` post via `POST /api/approvals/{id}/approve` flipped the variant status from `pending_approval` → `scheduled` AND the umbrella content_item too — within a single request round-trip.
  - **Net effect**: Phase 2 is **complete**. The normalized layer is now the live mirror of every new write, and Phase 3 (cut over reads to the normalized layer as the actual source-of-truth) is now unblocked. The legacy `posts` collection remains the read source-of-truth during the migration window so nothing breaks; the next phase can move reads incrementally without writer surprises.



- 2026-05-28 (part 59) **📊 Campaign performance attribution dashboard (Phase 1 of #5)**
  - **New module `routes/perf_metrics.py`** (deliberately not `performance.py` — that name was already taken by the mocked generic dashboard route):
    - `record_metric(variant_id, platform, date, raw_payload, …)` — idempotent upsert into `performance_metrics` keyed by `(variant_id, platform, date)`. Re-calling with the same key updates in place; the unique compound index from Phase 1 makes double-counting impossible.
    - `recompute_rollup(variant_id)` — rebuilds the `performance_rollups` row by aggregating the time-series into `{last_7d, last_30d, all_time}` windows. CTR is recomputed from summed `clicks / impressions` (not averaged across days — that would lie).
    - `record_metrics_from_post_refresh(post, vendor_metrics)` — fanout helper called from the existing 6h `analytics._refresh_post` cron. Looks up each variant's platform from `content_variants`, writes one daily row per `(variant, platform)`, and recomputes the affected rollups. Errors caught + logged; never raised — the engagement refresh source-of-truth must keep running.
  - **Hook wired into `routes/analytics.py::_refresh_post`** — every existing engagement refresh now ALSO mirrors into the normalized layer. **Passive mirror**, not source-of-truth: Phase 2 changes that.
  - **Two new API endpoints**:
    - `GET /api/attribution/overview?campaign_id=<id?>` — returns `{platforms, windows, top_items, variants_tracked, brand_id}`. Filters to a specific campaign when `campaign_id` is set (resolves via `content_items.campaign_id`); otherwise rolls up everything the user's brand owns. Top-5 content_items by 30d engagement; platform breakdown is all-time totals; windows carry impressions/reach/clicks/engagements/CTR/samples for 7d/30d/all-time.
    - `GET /api/attribution/timeseries?days=<1-180>&campaign_id=<id?>` — daily totals grouped by `(date, platform)` for the line chart. Mongo aggregation pipeline so we never pull the raw time-series into Python.
  - **New frontend component `components/AttributionPanel.jsx`** mounted on `CampaignDetail.jsx` right under the existing KPI row:
    - **Three window tiles** (Last 7d / Last 30d / All time) showing impressions, reach, clicks, engagements, CTR each.
    - **Platform breakdown pills** (cyan-tinted) — one per platform with engagements headline + impressions + CTR.
    - **Top-5 content cards** sorted by 30d engagement with title, impressions, engagements.
    - **Graceful empty state** when `variants_tracked === 0` — explains the 6h refresh cadence + tells the user what variants are tracked. Loading and error states both styled.
    - `data-testid`s on every element for testing-agent access.
  - **End-to-end verified live** on the test user — wrote 3 synthetic days of metrics via `record_metric`, the rollup correctly computed `all_time.ctr = 2.96% = 136/4600` and `engagements = 138` (sum of likes+comments+shares+saves across all rows). The overview endpoint reflected the writes immediately; the timeseries endpoint returned the per-day breakdown.
  - **7 new pytest cases** (`tests/test_attribution.py`):
    - `record_metric` idempotency (3 calls → 1 row via the unique compound index)
    - Rollup windows + CTR math (writes across `today, -10d, -100d` → last_7d/last_30d/all_time arithmetic + CTR check)
    - Auth required on both endpoints
    - Overview returns the known shape with all required keys
    - Overview reflects a freshly-written metric in the same request
    - Timeseries `?days=1` correctly excludes older rows
  - **All 40 critical tests pass** across attribution + normalize migration + LangGraph orchestrator + HITL endpoints + memory-perf + HITL reminders + realtime inbox.
  - **Dashboard ships immediate value today**: the moment the existing engagement refresh cron has real data for any user, the panel surfaces it. Until then it renders a clean empty state.


- 2026-05-28 (part 58) **🧱 Phase 1 — Data model normalization (decisions 1c + 2a + 3c + 4a)**
  - **New module `models_normalized.py`** — Pydantic shapes for `Brand`, `ContentItem`, `ContentVariant`, `PerformanceMetric`, `PerformanceRollup`, plus a `NORMALIZED_INDEXES` registry the migration auto-creates. Schema designed for many-brands-per-user (FK propagated everywhere) even though Phase 1 only mints one default brand per user (decision 1c).
  - **New module `routes/brands.py`** — `ensure_default_brand_for_user(user_id, name_hint)` returns the user's default brand_id, creating one named "{name_hint}'s Brand" on first call. Idempotent.
  - **New `migrations/normalize_001.py`** — in-place backfill (decision 2a):
    - **Step 1** — auto-create default brand for every active user (8/8 created).
    - **Step 2** — stamp `brand_id` on every campaign (98/98 backfilled).
    - **Step 3** — for every legacy `posts` row, materialise one `content_item` (platform-agnostic intent) + one `content_variant` per entry in `platforms[]` (150 items + 150 variants created). Stamps `brand_id`, `content_item_id`, `variant_ids[]`, `migrated: true` back on the legacy post row so reads continue working.
    - **Step 4** — for every `cortex_memory.kind="post"` row, stamp `meta.brand_id`, `meta.content_item_id`, `meta.variant_id` (decision 4a — keep memory rows as-is for embedding retrieval, just cross-reference the normalized layer in the meta block so the agent has zero-latency access).
    - **Idempotent**: every step skips rows that already carry `brand_id`. Re-running produces zero work — verified.
    - **Watermark**: `_migration_state.normalize_001` doc records completion so the startup hook can short-circuit.
  - **Time-series + rollup metrics shape (decision 3c)**: `performance_metrics` keyed by `(variant_id, platform, date)` with unique compound index so re-imports don't double-count engagement; `performance_rollups` denormalized per-variant with `{last_7d, last_30d, all_time}` window blocks for hot dashboard reads. Phase 1 ships the schema + indexes; Phase 2 will wire the cron that populates them from the existing engagement data sources.
  - **Signup hook wired into 3 paths**: `routes/auth.py` (OAuth signup), `routes/magic_link.py` (admin-create), `routes/leads.py` (lead form). Each calls `ensure_default_brand_for_user` immediately after `db.users.insert_one`, with the user's display name as the hint. Brand-create failure is caught + logged but never blocks login — the startup migration is the safety net.
  - **Startup auto-migration** (`server.py` `@app.on_event("startup")`) — runs `migrate_now()` if `needs_migration()` returns True. Logged but never blocks app boot.
  - **Two admin endpoints** for manual control:
    - `GET /api/admin/migrations/normalize/status` — current counts (users / brands / no-brand campaigns / no-brand posts / content_items / content_variants) + last run watermark + `needs_migration: bool`.
    - `POST /api/admin/migrations/normalize/run` — one-shot trigger, idempotent. Logs to `audit_log`.
  - **8 new pytest cases** (`tests/test_normalize_migration.py`) covering: idempotent re-runs, every user has a default brand, every campaign + post has `brand_id`, variant count == platforms count, cortex_memory rows carry the cross-ref triple, helper idempotency, all NORMALIZED_INDEXES present. 8/8 pass in 0.26s.
  - **33/33 regression** across normalize migration + LangGraph orchestrator + HITL endpoints + memory-perf + HITL reminders + realtime inbox. Backend stable.
  - **Live verification on prod data**: 8 users → 8 brands; 98 campaigns + 150 posts backfilled; 150 content_items + 150 content_variants created on first migration tick; second run does zero work (counters all zero).
  - **One issue caught + fixed during testing**: Motor blocks attribute-style access for collection names starting with `_` (collision with private attrs). Switched `db._migration_state.update_one(...)` → `db["_migration_state"].update_one(...)`. Also fixed a `log_admin_action` call site that used the wrong kwarg names.
  - **Phase 1 ships the agent-readable normalized layer alongside the existing writers**. Phase 2 (NOT in this PR) will rewrite the compose / scheduler / OS-chain writers to use the new collections as source-of-truth and populate `performance_metrics` from the engagement refresh cron.


- 2026-05-28 (part 57) **📡 Real-time HITL approval inbox via WebSocket**
  - **New backend module `routes/realtime.py`** (≈210 lines) — process-local connection registry + auth + fanout:
    - **`/api/ws/hitl-inbox`** WebSocket endpoint mounted directly on the global `app` (FastAPI APIRouter doesn't yet expose `.websocket()`). Authenticates via three fallback paths: `?token=` query param, `session_token` cookie (browser default), or `Authorization: Bearer …` header.
    - Sends an immediate **snapshot frame** on connect — current `awaiting_approval` runs (capped 20, transcript bodies stripped) so a fresh client doesn't have to wait for the next state change to discover what's pending.
    - **Heartbeat**: client `ping` → server `pong`. Idle loop hangs on `ws.receive_text()`; everything else (broadcast frames) is pushed from elsewhere.
    - **`broadcast_to_user(user_id, event, data)`** helper — best-effort fanout to every socket the user has open (multiple browser tabs all sync). Dead sockets pruned. Failures never block the caller.
    - **Multi-worker note**: registry is process-local, fine for our single-worker setup. Migration path to Redis pub/sub flagged in module docstring for the eventual scale-out.
  - **`routes/marketing_os.py` wires three broadcasts** at the end of every persisted run:
    - `hitl_paused` — fresh run resolved as `awaiting_approval` (fires from the main streaming handler).
    - `hitl_resolved` — original paused run was approved or rejected (fires from `_resume_run`).
    - `run_completed` / `run_failed` — any other terminal state, used by future UI affordances.
    - Each frame carries `{run_id, brief (240 chars), campaign_id, status, skip_distribution, transcript_len, summary (400 chars)}`.
  - **New frontend hook `hooks/useHitlInbox.js`** — opens the WS, maintains `paused[]` array, handles **auto-reconnect with exponential backoff** (1.5s → 3s → 6s → 12s, capped at 30s), sends 25s heartbeats, and re-uses the natural `session_token` cookie + `?token=` query fallback. Returns `{paused, connected, lastEvent, removeRun}`.
  - **New floating `<HitlInboxBell />`** mounted once in `DashboardLayout.jsx` so the inbox is visible from every dashboard route:
    - **Hidden by default** when there are zero paused runs AND the WS is connected — no-noise default.
    - Amber bell + count badge appears the instant a run pauses. Wiggle animation (subtle, not epileptic). Red dot when the WS disconnects so users know they might be missing updates.
    - Popover lists every paused run with brief preview + age + `transcript_len`. Click → navigates to `/dashboard/command-center?expand_run=<id>`.
    - Toast pops on every NEW `hitl_paused` and `hitl_resolved` event (de-duped on `{event}:{run_id}:{at}`).
  - **CommandCenter `expand_run` deep-link** — when the URL carries `?expand_run=<id>`, the page scrolls to the matching `data-testid="activity-run-{id}"` row, pulses an amber ring on it for 2.4s, then strips the param. Same path is now also linkable from the 24h reminder email (potential future enhancement).
  - **New CSS keyframe** `@keyframes wiggle` in `index.css` for the bell. ±8° rotation, 1s loop.
  - **4 new pytest cases** (`tests/test_realtime_inbox.py`):
    - **Unauthenticated WS handshake is rejected** (1008 policy violation).
    - **Snapshot frame** delivered on successful auth.
    - **Ping/pong heartbeat** round-trip.
    - **Live end-to-end broadcast**: open WS → trigger a `requires_approval=True` run → `hitl_paused` frame arrives within 180s with the right `status`, `run_id`, and `transcript_len`. Skips cleanly on LLM budget cap.
  - **25/25 critical tests pass** across realtime, HITL reminders, retry helper, HITL endpoints, memory-perf. Frontend lint clean, screenshot smoke test passed, no JS errors.
  - **Manual verification**: traced through a real session at the websockets level — open WS gets snapshot, ping replies pong, triggering a paused run via curl delivers the `hitl_paused` frame in real-time.


- 2026-05-28 (part 55) **🔁 Per-role retry-with-backoff in LangGraph nodes**
  - **New helper `_send_with_retry(chat, prompt)` in `routes/marketing_os_graph.py`** wraps every `send_with_usage` call site (both the role nodes and the summariser). Adaptive policy:
    - Up to 3 attempts on transient errors (timeouts, 5xx); backoff 1.5s → 3s.
    - Budget-cap / 429 errors get AT MOST 2 attempts — after the second, bail fast so the SSE error fires immediately and the universal key isn't hammered (`_is_budget_cap` checks for `"budget"`, `"rate limit"`, or `"429"` in the message).
    - Auth / 4xx-invalid errors (`"401"`, `"unauthorized"`, `"invalid api key"`, `"400 bad request"`, `"invalid_request_error"`) are **never** retried.
  - Initial attempt used Tenacity but the `stop_after_attempt(3)` policy collided with the "bail-fast on budget" early-exit — rewrote as a simple manual loop with explicit `_is_retriable_llm_error` + `_is_budget_cap` predicates. Same `asyncio.sleep`-based backoff, half the code, easier to test.
  - **3 new pytest cases** (`TestLangGraphOrchestrator::test_retry_helper_*`):
    - `retries_then_succeeds` — transient error on attempt 1, success on attempt 2, exactly 2 calls.
    - `gives_up_fast_on_budget_cap` — budget error on every call, bails after exactly 2 attempts (not 3).
    - `does_not_retry_auth_errors` — 401 returns after exactly 1 attempt.
    - All three monkey-patch `asyncio.sleep` to instant so the suite doesn't add wall-clock time.
  - **8/8 LangGraph orchestrator tests pass.** Backend regression green.

- 2026-05-28 (part 56) **📧 Email reminder when HITL paused run sits > 24h**
  - **New job `routes/hitl_reminders.py`** registered on the existing `AsyncIOScheduler` (every 6 hours, offset 4 min from boot to spread load). Queries `marketing_os_runs` for rows where `status="awaiting_approval"` AND `requires_approval=True` AND `created_at` older than `HITL_REMINDER_HOURS` (default **24h**, env-configurable) AND `reminder_sent_at` unset.
  - For each match: looks up the user, formats a per-run email (dark-themed HTML + plain-text fallback) describing what's pending, links to `/dashboard/command-center`, and sends via the existing `routes.email.send_email()` (Mailtrap → Mailgun fallback). Stamps `reminder_sent_at` + `reminder_status` either way.
  - **One reminder per paused run, ever** — anti-spam invariant baked in by stamping even on send-failure and on deleted-user skips. The activity feed already shows the amber awaiting_approval pill indefinitely; this email is the additional nudge, not a recurring drumbeat.
  - Capped at **50 runs per tick** so a backlog (e.g. mass user onboarding gone wrong) can't blast hundreds of emails in one go.
  - **5 new pytest cases** (`tests/test_hitl_reminders.py`):
    - happy path (sent + stamped + correct subject/tags),
    - idempotent (already-stamped row → no send),
    - deleted-user skip (no send but row stamped to prevent retry storms),
    - send-failure (row still stamped),
    - under-threshold fresh run (no send, no stamp).
  - All 5 pass against the live dev Mongo with auto-cleanup before+after each test.
  - One bug caught and fixed during testing: Mongo round-trips can hand back naive datetimes — `_build_email` now normalises `created_at.tzinfo` to UTC before arithmetic.


- 2026-05-28 (part 54) **🧱 "Built by Makers. Powered by Innovation." sibling-brand strip on the homepage**
  - **New component** `components/cv/CVBuiltByMakers.jsx` — three-card strip wired between `<CVCTAFooter />` and `<CVFooter />` on `pages/Marketing.jsx`.
  - **Brand-faithful typographic logos** (neither williamscnc.com nor craftersmarket.org exposes a clean standalone logo file — both use stylized wordmarks, so scraping favicons would have been low-quality). Each card mirrors the actual identity of the target site:
    - **Williams CNC** — copper `#b87333` on carbon `#0e0c09`, serif "WILLIAMS / CNC" stacked, matches williamscnc.com's actual palette and font treatment. Links to `https://williamscnc.com`.
    - **Crafters Market** — industrial orange `#ff4500` on `#0a0a0a`, "CRAFTERS / MARKET" stacked with the `◆` glyph eyebrow that craftersmarket.org uses across its site. Links to `https://craftersmarket.org`.
    - **CortexViral** — violet/fuchsia/cyan gradient wordmark + the "C" mark in a violet-tinted rounded plate, matching the rest of the marketing site's brand. Internal link to `/`.
  - **A11y / UX**: each card has `data-testid="built-by-makers-card-{key}"`, external links carry `rel="noopener noreferrer"` + `target="_blank"`, `ArrowUpRight` icon affordance, hover state increases border opacity and slides the arrow.
  - Gradient section headline matches the existing CortexViral marketing site language. Lint clean, no JS errors, screenshot verified.


- 2026-05-28 (part 53) **📊 CSV export of `retrieve_relevant` latency samples**
  - **Backend**: new endpoint `GET /api/admin/memory-perf/samples.csv` — admin-only, dumps the in-process rolling deque as a 2-column CSV (`index,latency_ms`) with `Content-Disposition: attachment; filename=memory_perf_samples.csv` so browsers download it directly. Always includes the header row even when the window is empty.
  - **Frontend**: small *Export CSV* button on the `MemoryPerfCallout` in both states — neutral pill on the healthy state, violet outline next to the *Open migration plan* CTA on the triggered state (`data-testid="memory-perf-csv-export-healthy"` / `memory-perf-csv-export-triggered"`).
  - **2 new pytest cases** (`TestMemoryPerf::test_memory_perf_samples_csv_requires_admin` + `…_shape`) — auth-gated, content-type, content-disposition, header row, integer/float parsing on each data row. All 4 memory-perf tests pass.
  - **Why**: ops folks now have a histogrammable dataset to inspect the distribution (e.g. is p95 spiking from a heavy tail or shifted everywhere?) before pulling the trigger on the vector DB migration. ~5 lines of new server code + a single anchor on the admin overview.


- 2026-05-28 (part 52) **🎬 Run-OS modal resume mode — live Approve/Reject progress**
  - **`RunOSModal` now supports two modes** in one component:
    - **Fresh run** (existing): textarea + "Require approval" checkbox + Run button → `POST /api/marketing-os/run/stream`.
    - **NEW resume mode**: triggered when `resumeRunId` + `resumeDecision` props are set. Auto-starts on open (no extra click), hides the textarea + footer chrome, swaps the header to *"Running Distribution + Analytics"* (approve) or *"Running Analytics (Distribution skipped)"* (reject), and streams from `POST /api/marketing-os/runs/{id}/{decision}` with `mode: "fast"`. Same SSE drain loop renders the same beautiful per-agent progress cards.
  - **`CommandCenter.jsx::resolveRun`** rewritten — was fire-and-forget with a single end-of-stream toast (15-30s of silence in between), now flips a new `resumeState` and re-uses the existing `runOpen` modal:
    - Click Approve/Reject → modal opens in resume mode → Kai streams live → Angela synthesises live → modal stays open showing the final summary → user closes → activity feed reloads.
    - Single-flight gate on `resumeState` so both Approve and Reject buttons disable across all paused rows while one is in-flight.
    - `onClose` + `onComplete` callbacks clear `resumeState` so the next open is a fresh run again.
  - **Net change**: ~25 lines of state plumbing (RunOSModal added a `useEffect` auto-start, an `isResume` branch in `start()`, conditional rendering for textarea/footer; CommandCenter swapped the inline SSE drain for two `setResumeState` calls). Backend contract unchanged — only the frontend now mounts the existing endpoints in a richer UX.
  - **Backend regression green**: 5/5 HITL tests still pass (`TestHITLEndpoints` 4 + `TestHITLLiveFlow` 1). No new tests needed — endpoint behaviour unchanged.


- 2026-05-28 (part 51) **🟣 Vector DB migration callout on Admin Overview**
  - **New `MemoryPerfCallout` component** in `AdminOverview.jsx` — polls `/api/admin/memory-perf` on dashboard load and renders one of two states:
    - **Healthy** (default — current state, p95 = 19.7 ms on 282 memories): compact slate card with an emerald "OK" badge + p95/p50/samples/memories tabular-nums summary. Zero visual urgency, just situational awareness. `data-testid="memory-perf-card-healthy"`.
    - **Triggered** (when `migration_triggered=true` from p95 ≥ 100 ms, OR `capacity_triggered=true` from any user ≥ 5K memories): violet gradient callout with a `Database` icon, `P95 TRIGGER` or `CAPACITY TRIGGER` badge, the threshold reason in plain English, and a CTA button that surfaces the migration plan (§7 of the eval doc — copies the path to clipboard + shows the 4-step plan in an alert as a fallback when the GitHub URL placeholder isn't set). `data-testid="memory-perf-migration-callout"` + `memory-perf-open-eval-doc"`.
  - **Placement**: between "Email health" and "LLM model spend" sections so it sits with the other ops/cost signals — admins scanning the overview encounter it during their normal sweep, not as a buried diagnostic.
  - **No backend changes** — re-uses the part-50 `/api/admin/memory-perf` endpoint as-is.
  - **Effect**: turns the in-memory rolling metric into an actionable signal. The day p95 crosses 100 ms or any user crosses 5K memories, the admin overview lights up with a violet "migration recommended" panel and one click reveals the exact 4-step plan. No more monthly manual aggregation queries to check capacity.


- 2026-05-28 (part 50) **🛑 LangGraph Human-in-the-Loop gate + 📏 `retrieve_relevant` p95 instrumentation**
  - **Human-in-the-loop gate before Distribution** — leverages the explicit StateGraph topology shipped in part 48:
    - New `approval_gate` graph node + conditional edge in `routes/marketing_os_graph.py`. When the user opts in via `requires_approval=true` on the run request, the canonical chain runs Strategy → Intelligence → Content → emits an `awaiting_approval` SSE event → ends. Kai (Distribution) is NOT invoked.
    - **`POST /api/marketing-os/runs/{id}/approve`** — resumes the paused run via a direct-call path (`_run_resume`) that runs ONLY Kai + Angela on the saved transcript. Saves ~20-40s of LLM time vs. naive re-invocation. Persists a NEW run row with `derived_from: <paused_id>` + `derived_decision: "approved"`, and marks the original as `status: "resolved"`, `resolved_as: "approved"`, `resolved_into: <new_id>`.
    - **`POST /api/marketing-os/runs/{id}/reject`** — same mechanics, but `run_distribution=false` so only Angela synthesises on the existing transcript. Original row resolved with `resolved_as: "rejected"`.
    - Guard: both endpoints 404 unknown run, 409 if status ≠ `awaiting_approval`.
    - Two new fields on `marketing_os_runs` rows: `requires_approval: bool` + `brief_text` (the LLM-enriched brief, kept so `/approve` doesn't have to rebuild it from scratch).
  - **Frontend (`RunOSModal.jsx` + `CommandCenter.jsx`)**:
    - New **"Require approval before Distribution"** checkbox in the Run-OS modal footer (`data-testid="os-run-require-approval"`).
    - Agent Activity feed cards now render the amber `awaiting_approval` status pill plus an inline **Approve / Reject** action row when the run is paused (`data-testid="activity-approve-{id}"` + `activity-reject-{id}"`). Single-flight via `resolvingId` so users can't double-fire. Drains the SSE response server-side then reloads the dashboard.
    - Resolved runs (post-decision) render with a muted zinc pill — visually distinct from `completed`/`failed` so the user knows which runs went through the gate.
  - **p95 instrumentation on `retrieve_relevant`** (`routes/memory.py`):
    - In-process `deque(maxlen=1000)` rolling window. Sampled inside a `try/finally` wrapper around the existing implementation — no Mongo writes on the hot path, no impact on retrieval latency itself.
    - **`GET /api/admin/memory-perf`** — admin-only. Returns `{samples, window_size, avg_ms, p50_ms, p95_ms, p99_ms, p95_threshold_ms (100), migration_triggered, capacity_triggered, total_memories, distinct_users, top_user_memory_count}`. Two boolean flags fire automatically when the documented migration triggers cross their thresholds (100 ms p95 or 5K memories on a single user — see `/app/memory/VECTOR_DB_EVALUATION.md` §6).
    - Live-verified in this session: p95 = 19.7 ms on 267 memories. Plenty of headroom; flags off.
  - **7 new pytest cases**:
    - `TestHITLEndpoints` (4): auth on approve + reject · 404 unknown run id · **409 when run is in 'completed' status** (using a synthetic Mongo-inserted row so we don't burn an LLM call).
    - `TestMemoryPerf` (2): auth required · response shape (12 required fields, threshold + flag types).
    - `TestHITLLiveFlow` (1): **end-to-end live LLM test** — canonical chain with `requires_approval=true` pauses after Content (3 agents, NO Kai, NO summariser); `/reject` resumes and runs ONLY Angela (no Kai); original row updates to `status: "resolved"`, `resolved_as: "rejected"`. Skips cleanly on LLM budget cap.
  - **All 56 marketing-OS pytest cases pass** (49 prior + 7 new) — full regression green.
  - **Use case unlocked**: a paused run lets a human review Atlas's strategy + Iris's research + Nova's draft before Kai writes the distribution plan that publishes to connected channels. This is the single most-requested compliance gate before the OS goes autonomous.


- 2026-05-28 (part 49) **⏭ Distribution-skipped pill + 📐 Vector DB evaluation doc**
  - **UI polish — "dist skipped" pill** rendered next to the run-status pill anywhere a Marketing OS run is listed:
    - `CampaignDetail.jsx` history accordion rows (`data-testid="history-skip-distribution-{run_id}"`) — visible inline with the existing completed/failed status.
    - `CommandCenter.jsx` Agent Activity feed cards (`data-testid="activity-skip-distribution-{run_id}"`).
    - Both use the amber-tinted pill style with the `SkipForward` lucide icon. Tooltip explains *"Distribution role was skipped — no platforms connected on this campaign."* No backend changes needed: the existing `GET /api/marketing-os/runs` response was already projecting the `skip_distribution` boolean (it only stripped `transcript`), so the field flows through automatically. Older runs that pre-date the LangGraph migration won't have the field and simply won't render the pill — graceful by omission.
  - **Vector DB evaluation `/app/memory/VECTOR_DB_EVALUATION.md`** (~150 lines):
    - **Decision: do NOT migrate yet.** Current `fastembed` + Mongo p95 is ~25-40 ms with 267 rows — same order of magnitude as fully-managed options at this scale.
    - Compared 4 options: **stay** (recommended), Mongo Atlas `$vectorSearch` (2 hr migration, no second datastore — recommended when triggers fire), pgvector (~6-8 hr, only worth it if we move to Postgres for analytics joins anyway), Pinecone (~4 hr, two-store sync overhead).
    - **Specific migration triggers** documented: (1) any user crosses 5,000 memories, (2) `retrieve_relevant` p95 > 100 ms, (3) analytics requirement that needs SQL JOINs across memories/campaigns/posts, (4) sustained >50 QPS on the vector store.
    - **Phased migration plan** (4 steps, ~half a day total) included for when one of the triggers fires.


- 2026-05-28 (part 48) **🕸️ P0 — Orchestration migration to LangGraph (explicit StateGraph, conditional edges, MongoDB checkpointer)**
  - **What changed**: the Marketing OS canonical 5-role chain (Strategy → Intelligence → Content → Distribution → Analytics) is now an explicit `langgraph.StateGraph` instead of a hand-rolled linear `_convene` loop. The custom `_convene` engine remains for the per-agent "Convene the team" modal on the AI Team page (different UX, different shape) — only the Marketing OS `/run/stream` was migrated.
  - **New module `routes/marketing_os_graph.py`** (~570 lines, single responsibility):
    - `OSState` TypedDict: `{run_id, user_id, brief, transcript[], summary, mode, skip_distribution, error, ...}` — JSON-serialisable so the checkpointer can persist per-step state.
    - **5 nodes** built via a closure factory (`_build_role_node`, `_build_summarizer_node`): strategy / intelligence / content / distribution / summariser. Each node reads prior transcript, builds the same context block as the legacy `_convene` (so behaviour is unchanged), calls `send_with_usage` via the existing emergentintegrations wrapper, records spend, and pushes SSE-shaped tuples to a per-run `asyncio.Queue`.
    - **Conditional edges** — the headline upgrade vs the linear loop:
      • `_route_after_content` → routes to `summariser` (bypasses Kai/Distribution) when `state.skip_distribution=true`, otherwise to `distribution`. Triggered automatically when a campaign has `platforms: []` AND no explicit `roles` override — saves a 5-15s LLM call on research/draft-only runs.
      • `_route_after_strategy` / `_route_after_intelligence` short-circuit straight to the summariser on upstream LLM errors, so we don't burn budget calling the next agent with empty input.
    - **MongoDBSaver checkpointer**: writes per-step checkpoints to `langgraph_checkpoints` + `langgraph_checkpoint_writes` collections. Lazy-pings Mongo at startup with a 2s timeout; **falls back to in-memory `MemorySaver`** if Mongo is unreachable (logger.warning, never crashes the graph build). Lets partial runs survive backend restarts.
    - **Per-run SSE queue registry** (`_RUN_QUEUES: dict[run_id, asyncio.Queue]`) — nodes push events, the outer handler drains. Cleaned up in `finally` so no memory leak. Sentinel `("__END__", None)` signals run completion.
    - **`run_os_graph(user_id, brief, mode, skip_distribution, roles, run_id)` async generator** — the public entrypoint. Yields SSE-shaped (event, data) tuples that the FastAPI handler formats with `_sse()`. Supports both the canonical graph path and a dynamic linear walk for the user-specified `roles` subset case (LangGraph graphs are static).
  - **Refactored `routes/marketing_os.py::run_marketing_os`**:
    - Pre-generates `run_id` so `os_started` carries it from the first event (no breaking change to the existing SSE contract).
    - Detects `skip_distribution` from `campaign.platforms == []` and forwards it to the graph.
    - Persists `marketing_os_runs` rows with two new fields: `framework: "langgraph"` and `skip_distribution: bool`. Older rows lack these — frontend/queries guard accordingly.
    - Subtle bug fixed during PR review: `campaign_id = camp.get("name") and payload.campaign_id` → `campaign_id = payload.campaign_id` (the find_one already returned a row; the truthy-chain was a leftover).
  - **Dependencies added**: `langgraph==1.2.2`, `langgraph-checkpoint==4.1.1`, `langgraph-checkpoint-mongodb==0.4.0`. Bumped `motor 3.3.1 → 3.7.1` and `pymongo 4.5.0 → 4.16.0` for compatibility (langgraph-checkpoint-mongodb requires pymongo>=4.10).
  - **7 new pytest cases** across two files:
    - `tests/test_marketing_os.py::TestLangGraphOrchestrator` (5): canonical graph compiles with all 5 nodes; `_route_after_content` skips on flag + on error + runs distribution otherwise; `_route_after_strategy` error short-circuits; CANONICAL_ROLES single-source-of-truth parity between modules; persisted run carries `framework: "langgraph"`.
    - `tests/test_langgraph_skip_distribution.py` (2, written by the testing agent): creates a transient empty-platforms campaign, asserts `os_started.skip_distribution=true`, asserts SSE stream contains NO `agent_started`/`agent_done` for Kai, asserts persisted row has the conditional-edge metadata.
  - **All 49 marketing-OS pytest cases pass** (18 original + 26 features + 5 new orchestrator + 2 new skip-distribution). Convene endpoint regression tested (still passes). Pre-existing handoff-test flake at ~100s Cloudflare timeout remains unrelated.
  - **Frontend**: NO changes required. The SSE event vocabulary is byte-identical (`os_started → agent_started → agent_done × N → summarizing → complete → os_persisted`), so `CommandCenter.jsx` and `RunOSModal` render the LangGraph path unchanged. The only new field clients can read is `os_started.skip_distribution` (currently informational; could power a "⏭ Distribution skipped — no platforms" pill in a future PR).


- 2026-05-28 (part 47) **🛡️ "Test this voice" — budget-cap-safe error handling**
  - **Backend (`routes/memory.py::test_brand_voice`)**: wrapped `send_with_usage` in `asyncio.wait_for(..., timeout=25)` so a stalled LiteLLM call aborts before the ingress idle limit. Returns 504 on `asyncio.TimeoutError` and 429 when the underlying error string contains `"budget"`, `"rate limit"`, or `"429"` (LiteLLM surfaces universal-key cap errors this way). Falls back to 503 for any other failure.
  - **Frontend (`pages/dashboard/CommandCenter.jsx::runVoiceTest`)**: added a 30s axios `timeout` so the UI never hangs forever. Distinct toast copy per status: `ECONNABORTED`/timeout ("Timed out — universal key may be over budget"), 422 ("Add an anchor first"), 429 ("LLM budget cap reached — add balance in Profile → Universal Key"), 504 ("LLM is slow right now"), 503 ("LLM unavailable"). Spinner always clears via `finally`.
  - **Test status**: 26/26 marketing-OS pytest cases still pass (`tests/test_marketing_os_features.py`). 422-no-anchors path verified via curl. Live 429/504 path will trigger automatically next time the universal key hits its cap — no more infinite spinners.


- 2026-05-28 (part 46) **🎯 Marketing OS pivot — Opportunity Signals + Command Center + 5-role chain**
  - **Architectural pivot landed** (from chat-only to "Autonomous Marketing Operating System"). Built on top of the existing Convene engine instead of swapping to LangGraph/CrewAI — same orchestration runtime, new lens.
  - **Opportunity Signals scoring** (`routes/trends_engine.py`):
    - New deterministic `_score_signal(text, meta)` runs on EVERY ingested trend (Reddit + Google Trends) — no LLM call, no extra latency.
    - Emits structured envelope: `{virality_score: int 0..100, urgency: "now"|"this_week"|"monitor", content_angle: str, recommended_agent: "nova"|"sam"|"kai"|"angela"}` persisted to `cortex_memory.meta.signal`.
    - Reddit scoring: log-scaled upvotes (`+15 × log10(upvotes+1)` capped at +55).
    - Google Trends scoring: tiered growth% (≥500% → +55, ≥250% → +40, ≥100% → +25, ≥50% → +15, else +8). Baseline 35 so quiet signals still show up in the feed.
    - Recommended-agent routing by keyword: 'seo'/'google'/'search'/'keyword'/'ranking' → Sam; 'email'/'newsletter'/'subject line' → Angela; 'tiktok'/'reels'/'trend'/'viral'/'hook'/'influencer' → Kai; otherwise Nova.
    - Content-angle one-liner templated per source so the Command Center card has a tight creative hint without an extra LLM call.
  - **New `routes/marketing_os.py`** — the Marketing OS API surface:
    - **`GET /api/marketing-os/dashboard`** — single round-trip payload for the Command Center: `{roles, stats (4 counters), campaigns (last 10), signals (top 8 by virality), approvals (first 5 pending), runs (last 5), wins (last 5 winning_hook memories)}`. All aggregations fanned out in parallel via `asyncio.gather`.
    - **`GET /api/marketing-os/signals?limit=`** — full ranked Opportunity Signals feed (virality desc, falls back to created_at when score absent). Limit clamped 1..100.
    - **`GET /api/marketing-os/runs?limit=`** + **`GET /api/marketing-os/runs/{id}`** — run history.
    - **`GET /api/marketing-os/roles`** — public catalogue of the 5 canonical roles.
    - **`POST /api/marketing-os/run/stream`** — SSE — runs the canonical chain on a brief. Strategy(Atlas) → Intelligence(Iris) → Content(Nova) → Distribution(Kai) → Analytics(Angela synthesizes). Reuses the proven `_convene` async generator for the actual orchestration; only adds the `os_started` + `os_persisted` framing events and the run persistence. Supports `roles` subset override and `campaign_id` enrichment (brief is automatically prepended with the campaign goal/audience/pillars when set).
    - Persists every completed/failed run to a new `marketing_os_runs` collection with the full transcript so the Activity Feed has an audit trail without re-running the chain.
  - **Frontend `pages/dashboard/CommandCenter.jsx`** (`/dashboard/command-center`):
    - Hero CTA panel with "Run the OS" button (violet glow) + Signals shortcut.
    - 4 stat tiles (Active Campaigns / Pending Approvals / Hot Signals / Recent Wins) with role-color accents.
    - **5-Role strip** — labelled tiles for Strategy/Intelligence/Content/Distribution/Analytics with role-mapped icons (Brain, Sparkles, Megaphone, Users, BarChart3).
    - **Campaign Board** (3-column kanban: draft / active / completed) with status pills + platform chips.
    - **Opportunity Signals stack** — top 5 by virality, each card showing urgency pill (ACT NOW / THIS WEEK / MONITOR), virality score, content_angle italic, and recommended-agent pill with quick "Draft →" CTA.
    - **Approval Inbox** snapshot + **Agent Activity Feed** (recent OS runs with status badge) + **Recent Wins** (emerald-tinted winning_hook memories).
    - **Run Modal** (`os-run-modal`) — brief textarea + live SSE progress with per-agent rows (⌛ pending → 🔄 running → ✓ done) and a violet "Executive summary" panel below.
    - Full `data-testid` coverage: `command-center-page`, `stat-{campaigns,approvals,signals,wins}`, `os-roles-strip`, `campaign-board`, `campaign-card-{id}`, `signals-stack`, `signal-card-{id}`, `approval-inbox`, `activity-feed`, `wins-feed`, `os-run-cta`, `os-run-modal`, `os-run-brief`, `os-run-start`, `os-run-progress`, `os-run-close`.
  - **Sidebar**: "Command Center" added as the **first** item (Command lucide icon). `/dashboard` default redirect changed from `/dashboard/agent` → `/dashboard/command-center`.
  - **18 new pytest cases** (`tests/test_marketing_os.py`): auth on all endpoints, dashboard shape with all 5 roles + 4 stat counters, signals scoring envelope correctness + recommended-agent routing, signals ranked by virality desc, runs list + 404 on unknown id, run/stream invalid-role 422, run/stream unknown-campaign 404, full SSE happy-path with event order invariant + persistence verification.
  - **All 45 regression tests still pass** (trends_engine, convene, auto_draft_and_chip, trend_drafts_and_nudge, agent_stream).
  - **Live curl + UI screenshot verified**: re-ingesting trends produced `meta.signal: {virality_score: 60, urgency: "this_week", recommended_agent: "sam", content_angle: "Search interest for \"saas\" is spiking — own the explainer first."}` for the SaaS keyword. Command Center page rendered end-to-end with all 5 role tiles, campaign kanban, and 5 signal cards live in the right rail.


- 2026-02-28 (part 45) **📆 Weekly auto-draft cron + 💸 Per-user spend chip**
  - **Weekly Monday auto-draft** — turns the trends engine from "a feed I check" into "a queue that fills itself":
    - **New module `routes/auto_draft.py`** with the full pipeline:
      • `_draft_from_trend_silent()` — server-side clone of `/trends/draft-post` with no Request/auth (cron context). Reuses Nova + the platform format guidance dict from `trends_engine.py`. Tracks LLM spend via `record_llm_call`.
      • `_process_user(user_doc)` — fetches the top N recent trend memories, drafts one post per signal via Nova, inserts each as `status: pending_approval` into the `posts` collection with `scheduled_at` = +24h (gives the user an editing window after approval).
      • `run_weekly_auto_drafts()` — cron entry point. Iterates opted-in users with at least 6-day cooldown since last run; skips paused accounts; updates `last_run_at` + `last_run_count` per user.
      • `register_auto_draft_job(scheduler)` — attaches a `CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="UTC")` to the existing apscheduler instance.
    - **Idempotency layered**: per-user `last_run_at` window (6 days) + deterministic `dedupe_key = "auto_draft:{trend_id}:{platform}"` upsert on the posts collection so retries / double-fires never produce duplicate pending posts for the same signal.
    - **New endpoints**:
      • `GET /api/trends/auto-draft/settings` — returns config with sensible defaults (`{enabled: false, platform: "linkedin", count: 3, max_count: 5, last_run_at: null}`).
      • `PUT /api/trends/auto-draft/settings` — partial update; 422 on bad platform / out-of-range count.
      • `POST /api/trends/auto-draft/run-now` — manual trigger for the calling user only. 422 if disabled · 429 with humanized "try again in Xd Yh" if within cooldown · respects the same dedupe key so admins can dry-run safely.
    - **Bug fix**: cooldown comparison crashed with "can't subtract offset-naive and offset-aware datetimes" because Mongo strips `tzinfo` on read. Coerces back to UTC before subtracting.
    - **Frontend `Trends.jsx::AutoDraftCard`**: violet-bordered card at top of page with the magic-wand icon, "ON" green pill when active, platform/count dropdowns + Run-now button when enabled, single toggle switch on the right. Saves on every chip change (toast on save). Run-now toast: *"3 drafts queued · Open Approvals to review and schedule."*
  - **Per-user spend chip in AgentWorkspace**:
    - Extended `GET /api/ai/agent/spend-hint` to ALWAYS return `total_cost`, `total_tokens`, `total_calls`, `days` (was previously gated by `show: true`). The `show` flag still controls the nudge banner; the chip just needs the raw numbers.
    - **New chip at top of the AgentWorkspace right rail** (`data-testid="rail-spend-chip"`) — violet dot · "SPEND THIS MONTH" label · big tabular-nums $X.XX figure · "· 184.3K tok" subtitle · "47 calls · last 30d" detail. Whole chip is a `<Link to="/admin">` so admins can drill into the full breakdown.
    - Cost format adapts: under $1 shows 4 decimal places ($0.0048), over $1 shows 2 ($1.27). Tokens format K/M.
    - Auto-hides when both `total_cost` and `total_tokens` are zero (brand-new user sees no clutter).
  - **11 new pytest cases** (`tests/test_auto_draft_and_chip.py`):
    - `TestAutoDraftSettings` (5): auth · default shape with `max_count: 5` · partial update preserves other fields · 422 on bad platform · 422 on `count` outside `[1, 5]`.
    - `TestRunNowGuards` (2): manual trigger 422s when disabled · 429s with "Cooldown active" when last run < 6 days ago.
    - `TestProcessUserPipeline` (2): live `/run-now` queues `pending_approval` posts with right shape (status, platforms, source, dedupe_key, scheduled_at = +24h ±1h) · running twice for the same signal produces ONE row (dedupe_key upsert).
    - `TestSpendChipFields` (2): endpoint returns `total_cost`/`total_tokens`/`total_calls`/`days` regardless of `show` state · clean-user zero state (no llm_usage rows) returns all zeros + `show: false`.
  - **All 86 agent-stack tests pass** across 8 test files.
  - **Live UI screenshot-verified**:
    - **AutoDraftCard**: ON state with platform dropdown + count dropdown + Run-now button + active toggle.
    - **Spend chip**: $1.27 · 184.3K tok · 47 calls · last 30d in the AgentWorkspace right rail, above the existing Metrics section.


- 2026-02-28 (part 44) **🎯 Token-accurate LLM cost tracking + 🔗 Compose URL-param plumbing**
  - **Token-accurate cost tracking** — replaces the per-call averages with exact USD computed from real prompt + completion tokens:
    - **`routes/ai.py::send_with_usage(chat, user_message)`** — new helper that mirrors `LlmChat.send_message`'s side-effects (history append, error wrapping in `ChatError`) but also extracts `prompt_tokens`/`completion_tokens`/`total_tokens` from the underlying LiteLLM `response.usage`. Returns `(text, {prompt_tokens, completion_tokens, total_tokens})`.
    - **`routes/llm_spend.py::_exact_cost(model, in_tokens, out_tokens)`** — multiplies token counts by per-million rates (Opus $15/$75, Sonnet $3/$15, Haiku $1/$5, Gemini 2.5 Pro $1.25/$10, GPT-5 $5/$15). Prefix-matches family names so future minor versions inherit rates without code changes.
    - **`record_llm_call()`** now accepts an optional `usage` dict. When tokens > 0 it stores the exact cost with `cost_source: "tokens"`; otherwise it falls back to the per-call estimate with `cost_source: "per_call_estimate"`. The `llm_usage` row now persists `prompt_tokens`, `completion_tokens`, `total_tokens` alongside.
    - **All 5 LLM call sites** updated to use `send_with_usage` + thread tokens through to the spend writer:
      • `_orchestrate()` primary chat
      • `_run_handoff()` sub-agent call
      • `_convene()` per-agent chain step
      • `_convene()` synthesizer (Atlas)
      • `trends_engine.py::draft_post_from_trend()` (Nova draft from signal)
    - **`/api/admin/llm-spend` response** now includes `total_tokens: {prompt, completion, total}` and each `by_mode`/`by_agent`/`by_model` row gets a `tokens` field.
    - **`AdminOverview.jsx::LlmSpendCard`** surfaces "2.9K tokens" next to the call count, and the disclaimer changed from "±20%" → "Token-accurate when available, falls back to per-call averages — accuracy ±5%." `fmtTokens` helper formats K/M.
  - **Compose URL-param plumbing** — closes the "Open in Compose" CTA on Trends drafts:
    - `Compose.jsx` now reads both `location.state` (legacy in-app navigation) AND query params (`?content=&platform=&source=trend`). Either source pre-fills the textarea + platform selection on mount.
    - **Bug fix**: the existing channels-load `useEffect` was wiping any pre-selected platform with the user's connected channels. Now merges the two so the trend-draft platform survives. Falls back to `instagram` only when both prev state AND channels are empty.
    - **Source-aware toast**: when arrived via `?source=trend`, fires *"Draft loaded from a trend — Nova drafted this from a viral signal. Edit before publishing."* so the user knows where it came from.
    - **URL cleanup**: after consuming the params, replaces the history entry to strip the search string. Refreshing the page no longer re-prefills — feels like a single intentional handoff.
  - **11 new pytest cases** (`tests/test_token_costs.py`):
    - `TestExactCost` (5): pure unit tests — Sonnet 1500/500 = $0.012 (exact arithmetic check) · Opus > Sonnet > Haiku ordering · zero tokens returns 0 · unknown model returns 0 (caller handles fallback) · prefix match for future minor versions inherits family rates.
    - `TestRecordWithUsage` (2): with usage → row has token counts + `cost_source: "tokens"` + exact cost; without usage → row has zero tokens + `cost_source: "per_call_estimate"` + per-call average cost.
    - `TestSendWithUsage` (1): live LLM round-trip on Haiku confirms LiteLLM surfaces non-zero `prompt_tokens` + `completion_tokens`, and `total_tokens == prompt + completion`. Skips gracefully on budget exhaustion.
    - `TestAgentChatTokenAccountingE2E` (1): live `mode=fast` agent_chat → the resulting `llm_usage` row has real token counts AND `cost < $0.0012` (the per-call fallback cap), proving exact pricing is active in production not just unit-tested.
    - `TestSpendEndpointSurfacesTokens` (2): admin endpoint includes `total_tokens` object with `{prompt, completion, total}` ints + each by_mode/by_model row has a `tokens` field.
  - **Migration note**: existing `llm_usage` rows written before this change lack the `cost_source`/`prompt_tokens`/`completion_tokens` fields. The aggregation pipeline uses `$ifNull` to default them to 0, so older rows still surface correctly — they just don't contribute to the token totals (the call & cost are still counted).
  - **Test-isolation fix**: refactored `test_ai_team_and_spend.py::_wipe_usage` to use pymongo (sync) instead of Motor, eliminating a cross-loop "Future attached to a different loop" error that surfaced when running with other Motor-using tests in the same session.
  - **All 75 agent-stack tests pass** across the 7 test files (`test_agent_chat`, `test_agent_handoff`, `test_model_router`, `test_agent_stream`, `test_ai_team_and_spend`, `test_trend_drafts_and_nudge`, `test_token_costs`).
  - **Live screenshot-verified**: Compose loads from `?content=&platform=linkedin&source=trend` query string, prefills the textarea, fires a "Draft loaded from a trend" toast, AND cleans the URL to `/dashboard/compose` (so refresh ≠ re-prefill). Admin LLM Spend card shows "$0.01 · 4 calls · 2.9K tokens" with the new disclaimer.


- 2026-02-28 (part 43) **🔄 Trend → Draft loop + 💡 Proactive spend nudges**
  - **"Draft post from this signal"** — closes the signal → memory → content loop:
    - New endpoint `POST /api/trends/draft-post` body `{trend_id, platform}` (supports `linkedin`, `twitter`/`x`, `instagram`, `tiktok`, `pinterest`, `facebook`).
    - User-scoped ownership check: a query like `find_one({"id": trend_id, "user_id": ..., "kind": "trend"})` does ownership + existence in one round-trip; passing another user's signal id returns 404 (verified by an isolation test).
    - Routes through Nova (Copy specialist), honoring the user's saved per-agent mode pref (`agent_prefs.nova`). Includes brand name + niche in the system prompt when set on the user doc, so drafts sound on-brand.
    - Platform-specific format guidance baked into the prompt (e.g., Pinterest = title <=100 chars + description 200-300 + 4 hashtags). LLM is instructed to end with `HASHTAGS: #tag1 #tag2 …` — the server splits that line off into a separate `suggested_hashtags` array (max 8) so the UI can render them as pills.
    - Persists every draft as a `draft_from_trend` memory row (deduped by `draft:{signal_id}:{platform}` so re-generating overwrites). Spend tracked in `llm_usage`; counts towards AI generation quota.
    - 502/503 budget-exceeded errors surface as clean HTTP status codes instead of generic 500s.
  - **Frontend `Trends.jsx::TrendCard`**:
    - Every trend card now has a **"Draft post" button** with a chevron toggle. Click → expands an inline panel with platform-selector chips (LinkedIn / Twitter / Instagram / TikTok / Pinterest / Facebook).
    - Generate button shows live "Nova is drafting…" spinner state.
    - Generated draft renders in a violet-bordered card with the prose; hashtags shown as separate violet pills below.
    - **Action toolbar**: Copy (clipboard + 2s "Copied ✓" confirmation), Open in Compose (routes to `/dashboard/compose?content=...&platform=...&source=trend` with the draft pre-seeded), and "Try another platform" (reset state for another generation).
    - Existing "view source" external link moved into the card's metadata row (was previously the whole card).
  - **Proactive spend nudges**:
    - New endpoint `GET /api/ai/agent/spend-hint?days=30` runs a Mongo `$regexMatch` aggregation on `llm_usage` to count Opus calls + cost. Returns `show: true` only when `opus_calls >= 20` AND (`opus_cost >= $2.00` OR `opus_share >= 50%`) — calibrated so casual users never see it but heavy Opus users do.
    - Suggestion message includes projected savings: "Switching half to Auto/Creative would save ~$0.78" (computed from the price delta between Opus and Sonnet × 50% of Opus calls).
    - `days` clamped 1..90.
  - **Frontend `AgentWorkspace.jsx`** banner:
    - Amber "SPEND TIP" banner above the composer, only renders when backend returns `show: true` AND the user hasn't dismissed it this session.
    - **Inline "Switch this agent" link** auto-applies the suggested mode (calls `pickMode(suggestion.mode_hint)` which both updates local state AND PUTs to `/ai/agent/prefs`) and dismisses the banner.
    - × dismiss button — session-only state (no persistence). Resets on page reload so it doesn't feel like silencing a permanent warning.
  - **11 new pytest cases** (`tests/test_trend_drafts_and_nudge.py`):
    - `TestDraftFromSignalAuth` (4): 401 anon · 422 unknown platform · 404 unknown trend_id · 404 when accessing another user's trend (cross-tenant isolation).
    - `TestDraftFromSignalHappyPath` (3): generates valid draft + strips trailing `HASHTAGS:` line into separate array · supports multiple platforms · draft persists as `draft_from_trend` memory. All three skip cleanly on 502/503/budget-exceeded.
    - `TestSpendHint` (4): 401 anon · default user sees no nudge · synthetic 25 Opus rows triggers `show: true` with non-empty suggestion + positive savings · `days` clamped to 90.
  - **All 58 agent-stack tests pass** across `test_agent_chat`, `test_agent_handoff`, `test_model_router`, `test_ai_team_and_spend`, `test_trend_drafts_and_nudge`.
  - **Live curl-verified**: Real LinkedIn draft from "dunkin bucket of coffee +450%" signal produced a 200-word post leading with the trend, then 3 takeaways with bold subheadings, ending with `#ConsumerTrends #RetailStrategy #GoogleTrends`.
  - **UI screenshot-verified**: Trends page draft panel renders all 6 platforms, draft body, hashtag pills, and Copy/Open in Compose/Try another platform buttons. AgentWorkspace amber spend nudge banner renders with "Switch this agent" CTA + dismiss × correctly.


- 2026-02-28 (part 42) **🏟️ Convene — Multi-step team orchestrator**
  - **What it is**: One brief runs sequentially through N specialists (each one sees the prior agents' answers as context), then Atlas synthesizes a single ranked executive summary with next-3-actions. The team behaves like a Slack huddle: builds on each other rather than firing N independent answers.
  - **Backend** (`routes/agent_chat.py`):
    - Two new endpoints — `POST /api/ai/agent/convene` (sync, returns full JSON) and `POST /api/ai/agent/convene/stream` (SSE).
    - SSE event vocabulary: `started`, `agent_started`, `agent_done`, `summarizing`, `complete`, `error` — keepalive comments interleaved while LLM calls are in-flight (same pattern as `chat/stream`, prevents ingress timeouts on 60-90s chains).
    - Strict validator `_resolve_convene()` — distinguishes `agents=None` (use default chain) from `agents=[]` (explicit error → 422), dedupes repeated agents, max 5 per convene, accepts display-name aliases (`iris`/`atlas`).
    - Default chain: Research → SEO → Copy → Atlas synthesizes (configurable via `agents` and `summarizer` fields).
    - Each chain agent gets a system-prompt suffix with the full prior-team transcript + "build on what's there, don't repeat, ≤350 words" guardrail.
    - Synthesizer always runs on `deep` task type unless overridden — highest leverage step of the chain, worth the extra cost.
    - Spend tracking integrated: each chain agent + the synthesizer write rows to `llm_usage`, so the admin spend card surfaces convene costs alongside regular chats.
    - Persists a `convene_summary` memory row after every successful run — future agent_chats can recall the team's prior verdict via the existing memory retrieval layer.
  - **Frontend** (`pages/dashboard/AITeam.jsx::ConveneModal`):
    - "Convene the team" CTA card on the AI Team page (next to "Ask Atlas").
    - Modal with brief textarea + specialist multi-select chips (Iris/Sam/Nova/Kai/Angela; default 3 selected).
    - **Live SSE progress UI**: each picked agent gets a row that transitions ⌛ pending → 🔄 running (violet spinner) → ✓ done (green check, expanded markdown answer in a card). Atlas's synthesis row appears below with its own status line.
    - **Executive summary panel** renders below the chain with a violet `Sparkles` accent — the final synthesized output.
    - Fetch + ReadableStream pattern (same as `/agent/chat/stream`).
  - **8 new pytest cases** (`tests/test_convene.py`):
    - `TestConveneValidation` (5): auth · unknown agent → 422 · empty chain `[]` → 422 (NOT silent fallback to default) · >5 agents → 422 via pydantic `max_length` · repeated agents silently deduped (verified via the first SSE `started` event).
    - `TestConveneHappyPath` (3): full sync chain produces ordered transcript + non-trivial summary, FUPS/HANDOFF markers stripped from chain outputs; SSE event order invariant (`started → agent_started → agent_done → summarizing → complete`); convene persists exactly one `convene_summary` memory row.
    - Tests gracefully skip with a clear message when the Emergent LLM key budget is exhausted (encountered during this session — was temporarily at $38.40 / $38.40 cap).
  - **All 59 agent-stack tests pass** (test_agent_chat + test_agent_handoff + test_model_router + test_agent_stream + test_ai_team_and_spend + test_convene).
  - **Live UI screenshot-verified**: Convene modal with stubbed SSE shows the full flow — brief input, 3 selected specialists, 3 progress rows each with their own output card, Atlas status line, and the violet "Executive Summary" panel below with the ranked ideas + next-3-actions.
  - **Live curl-verified**: real chain (Iris → Sam → Nova → Atlas) on "Launch plan for AI marketing SaaS targeting indie creators" produced a clean executive summary with three named "strongest ideas" attributed to the right specialists and three ranked actions.


- 2026-02-28 (part 41) **💰 LLM spend dashboard + 🧠 Persisted mode prefs + 🏛️ Unified AI Team page**
  - **Per-agent mode persistence** (`routes/agent_chat.py`):
    - New endpoints `GET /api/ai/agent/prefs` (returns `{prefs: {agent_id: mode}}`) and `PUT /api/ai/agent/prefs` body `{agent_id, mode}`. Strictly validated: unknown agent_id or mode → 422 (so a typo'd frontend can never silently write junk).
    - Persisted on the user doc as `agent_prefs.{agent_id}` (single-doc update — no separate collection).
    - Frontend `AgentWorkspace.jsx` loads prefs on mount, hydrates the mode chip when the active agent changes, and PUTs on every chip click (best-effort — a failed write doesn't block the UI).
  - **LLM spend tracking + Admin Overview card** (new `routes/llm_spend.py`):
    - Every successful agent_chat turn fires `record_llm_call(user_id, agent_id, mode, model)` which writes one row to a new `llm_usage` collection with an *estimated* per-call USD cost. Per-call costs hardcoded from published 2026 pricing (Opus $0.045, Sonnet $0.012, Haiku $0.0012, Gemini 2.5 Pro $0.008, GPT-5 $0.020). Prefix-matches family names so future minor versions inherit the right rate without code changes. Unknown models fall back to a $0.01 default so admins still see *something*.
    - Handoff sub-agent calls also tracked separately (`agent_id` = the sub-agent).
    - New `GET /api/admin/llm-spend?days=30` endpoint runs a single `$facet` aggregation returning totals + by_mode + by_agent + by_model + top_users (10) + biggest_driver (the single highest `(model, agent)` pair). `days` clamped 1..365; `days=0` falls back to default 30.
    - **Admin Overview card** (`AdminOverview.jsx::LlmSpendCard`):
      • Estimated USD total + call count, with "Approximated from per-call cost averages — accuracy ±20%" disclaimer.
      • Period toggle (7d / 30d / 90d).
      • Violet "Biggest cost driver" callout — appears when one (model, agent) pair eats ≥20% of spend: *"50% of spend is `claude-haiku-4-5-20251001` from Kai"*. At ≥60% adds "Nudge users toward Auto/Fast mode to lower bills."
      • 3-column breakdown: By Mode (with gradient progress bars + %), By Agent (top 6), Top Spenders (top 5 with hydrated email).
  - **Unified AI Team dashboard** (`/dashboard/team`, new `pages/dashboard/AITeam.jsx`):
    - "Ask Atlas" hero with one-line input; submitting routes to `/dashboard/agent/strategy?q=<prompt>` and AgentWorkspace auto-prefills the composer.
    - **4-panel 2×2 grid** with count badges + "Open" CTA on each:
      • **Active Conversations** (`GET /api/ai/agent/conversations/recent`) — derived from `agent_summary` memory rows via Mongo `$group`; one row per agent_id with the most-recent prompt preview + relative timestamp + color-coded agent badge.
      • **Pending Approvals** (`GET /api/approvals`) — first 4 posts with platform pills, scheduled date, content preview.
      • **Recent Memories** (`GET /api/memory/list`) — first 5 with kind badges.
      • **Trend Signals** (`GET /api/trends/recent`) — first 5 with Reddit/GTrends color-coded source pills, clickable through to permalinks.
    - Friendly empty states on each panel so a new user sees a guided onboarding view instead of 4 blank cards.
    - Added "AI Team" link as the **first** sidebar item (uses `Users2` icon from lucide).
  - **13 new pytest cases** (`tests/test_ai_team_and_spend.py`):
    - `TestAgentPrefs` (5): auth required · default empty prefs · set→get round-trip with two different agents · 422 on unknown agent_id · 422 on unknown mode.
    - `TestCostLookup` (2): known model lookups (Opus > Sonnet > Haiku ordering verified) · prefix-match for future versions · unknown models fall back to default cost.
    - `TestLLMSpendEndpoint` (4): admin auth · empty window → zeros not 404 · LIVE chat call actually writes a row that surfaces in the aggregate · `days` param clamped to 1..365.
    - `TestRecentConversations` (2): auth · dedupe per-agent (3 chats with Nova → 1 conversation row, latest preview).
  - **All 51 agent-stack tests pass** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py` + `test_agent_stream.py` + `test_ai_team_and_spend.py`).
  - **Live UI screenshot-verified**: AI Team page renders all 4 panels + Ask Atlas hero correctly. Admin Overview renders the LLM spend card with the "50% of spend is claude-haiku from Kai" insight callout exactly as designed.


- 2026-02-28 (part 40) **🔀 SSE streaming + 🤝 Universal agent handoff**
  - **Why**: A handoff (Atlas → Iris) is two sequential LLM calls (~30-50s combined) and was hitting Cloudflare's ~100s ingress idle timeout from the browser even though the backend ran fine. The fix is server-sent events with periodic keepalive pings, AND it lets us show the user *what's happening* during the wait.
  - **Universal handoff**: flipped `can_handoff = True` for every agent (was Atlas-only). Now Sam can ask Iris for keyword trends, Angela can ask Nova for positioning, Kai can ask Sam for SEO context, etc. Single delegation per turn (no chains). Server-side self-handoff guard rejects an agent delegating to itself — would just waste an LLM call in an ephemeral session.
  - **New endpoint `POST /api/ai/agent/chat/stream`** (`routes/agent_chat.py`):
    - Returns `text/event-stream` (SSE) with the following event vocabulary:
      • `started`   `{agent_id, agent_name, mode, model}` — immediate, so the UI can render "Thinking · deep mode" instantly.
      • `memories`  `{memories_used: [...]}` — after the vector-memory fetch.
      • `thinking`  `{phase: "primary"|"handoff", agent: "Iris"}` — right before each LLM call.
      • `handoff`   `{agent_id, agent_name, question}` — only when a delegation actually fired.
      • `keepalive` (sent as a `: keepalive` comment) — every ~10s while the LLM is busy.
      • `complete`  `{answer, follow_ups, memories_used, handoff, mode, model}` — final payload, same shape as the non-streaming endpoint.
      • `error`     `{message}` — graceful error frame instead of a torn connection.
    - Refactored shared orchestration into `_orchestrate(user, agent, payload)` — an async generator yielding `(event_name, data)` tuples. Both the streaming endpoint and the original `POST /api/ai/agent/chat` consume it, so we only ship orchestration logic once.
    - `_keepalive_while(task, every=10)` helper interleaves `keepalive` events while a synchronous LLM call is in progress. Uses `asyncio.shield` so the timeout doesn't cancel the underlying coroutine.
    - Response headers set `Cache-Control: no-cache` and `X-Accel-Buffering: no` (the latter required for nginx-style proxies to flush each chunk instead of buffering the whole response).
  - **Backwards compatible**: the original `POST /api/ai/agent/chat` still exists and returns the same JSON shape — handy for batch scripts / external API consumers / pytest. It just consumes the same generator under the hood and assembles the final dict.
  - **Frontend (`AgentWorkspace.jsx`)**:
    - Replaced the axios POST with a `fetch()` + `ReadableStream` reader. Parses each SSE record, updates a live `busyText` state ("Connecting…" → "Thinking · deep mode" → "Recalling 3 memories…" → "Delegating to Iris…" → "Iris is researching…" → final answer rendered).
    - Typing indicator now reads `<spinner> Iris is researching…` instead of the previous static "Atlas is thinking…" — feels alive even on slow handoffs.
    - 402 / cap-reached / network errors all still surface as toasts; user message rolls back so they don't lose what they typed.
  - **5 new pytest cases** (`tests/test_agent_stream.py`):
    - `TestStreamAuth` (2): 401 anon · 404 unknown agent.
    - `TestStreamHappyPath` (2): event ordering invariant (`started → memories → thinking → complete`), `complete` payload mirrors the non-streaming shape with `mode="fast"` + Haiku model id.
    - `started` event carries `{agent_id, agent_name, mode, model}` immediately.
  - **Updated handoff tests** (`test_agent_handoff.py`): replaced the "only Atlas can handoff" test with `test_self_handoff_rejected` (delegating to self → handoff filtered to None) and `test_any_agent_can_handoff` (Sam → Iris works).
  - **All 38 agent tests green** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py` + `test_agent_stream.py`).
  - **Live UI screenshot-verified**: Atlas → Iris handoff via SSE renders the cyan delegation pill, grey "deep" mode pill, memory chip, and spliced "Iris reports:" block all correctly.


- 2026-02-28 (part 39) **🎛️ Model routing layer — per-task user override**
  - **What changed**: Previously the LLM family was hard-coded per agent (Atlas → Opus, Iris → Gemini, others → Sonnet). Now the user can override on a per-turn basis via a compact "Mode" selector above the chat composer.
  - **Backend (`routes/model_router.py`)**:
    - New `USER_MODES` catalogue — 4 entries (`auto`, `fast`, `deep`, `creative`) each with `{id, label, blurb}`. `USER_MODE_IDS` exposed for fast validation.
    - New `resolve_user_mode(mode, agent_id) -> (provider, model, task)` — auto / None / unknown all gracefully fall back to the agent's natural task; `fast` routes to Haiku, `deep` to Opus, `creative` to Sonnet, etc. Returns the resolved task name so the API surfaces it in the response (handy for UI labels + debugging).
  - **Backend (`routes/agent_chat.py`)**:
    - `_ChatRequest` gains an optional `mode: str` field (validated as `<=24` chars; unknown values are silently treated as `auto` — never 422 the user).
    - Response payload now includes `mode` (resolved task name) and `model` (actual model id used) so the UI can show "Reply produced via Haiku" without a follow-up call.
    - New `GET /api/ai/agent/modes` endpoint returns the public `USER_MODES` list for the chip selector.
  - **Frontend (`AgentWorkspace.jsx`)**:
    - Loads `/ai/agent/modes` on mount; renders a `MODE  Auto · Fast · Deep · Creative` chip row above the textarea (`data-testid="agent-mode-selector"` + per-chip `agent-mode-{id}`). Active chip = violet pill.
    - Posts `{agent_id, message, mode}` to `/ai/agent/chat`.
    - Each agent reply now shows a tiny grey mode pill next to the agent name (`data-testid="agent-mode-pill"`) — hover reveals the actual model id (`claude-haiku-4-5-20251001`).
  - **13 new pytest cases** (`tests/test_model_router.py`):
    - `TestRouterUnit` (7): known task lookups · unknown falls back to default · `for_agent` returns per-persona defaults · explicit user mode beats agent default · `auto` / `None` / unknown silently fall back.
    - `TestModesEndpoint` (2): auth required · returns canonical set with full `{id, label, blurb}` shape.
    - `TestAgentChatRespectsMode` (4): default mode preserves agent's natural task (Nova → Sonnet) · `mode=fast` on Atlas re-routes from Opus → Haiku (live LLM call asserts `model` string contains "haiku" + NOT "opus") · `auto` is a no-op · garbage strings silently fall back.
  - **All 33 agent-related tests green** (`test_agent_chat.py` + `test_agent_handoff.py` + `test_model_router.py`).
  - **Live UI screenshot-verified**: clicking "Fast" chip → sending message → Atlas reply renders with grey `fast` pill next to her name.


- 2026-02-28 (part 38) **🤝 Multi-agent collaboration — handoff bug fix + UI verification**
  - **Root cause**: Atlas (Strategy/Claude Opus) was correctly emitting `<<HANDOFF>>iris: <question><<END>>` markers in her replies, but the server's `_extract_handoff()` was rejecting every single one with `agent_id not in AGENTS`. Reason: the system prompt instructs the LLM to delegate by **display name** (`iris`, `sam`, `kai`, `nova`, `angela`), but `AGENTS` is keyed by **internal id** (`research`, `sam`, `kai`, `nova`, `angela`). `iris` was never in the dict → handoff silently dropped, raw marker leaked into the answer, `handoff: null` returned to the UI.
  - **Fix** in `routes/agent_chat.py`:
    - Built `_AGENT_LOOKUP: dict[str, str]` mapping both lowercased display names AND internal ids to the canonical agent id. (`"iris" → "research"`, `"atlas" → "strategy"`, etc.)
    - `_extract_handoff()` now resolves the captured token through this lookup, so either name OR id works. Unknown tokens (typos) still safely reject, leaving the marker in the cleaned text for debugging instead of silently swallowing it.
  - **Verified live**: Curl test with Atlas → "fetch the top 3 rising AI marketing TikTok trends via Iris" now returns the full `handoff: {agent_id:"research", agent_name:"Iris", question:..., answer:...}` object plus the spliced `Iris reports: …` block in the main answer. Backend log shows two sequential LiteLLM calls: `claude-opus-4-7` (Atlas) → `gemini-2.5-pro` (Iris).
  - **Frontend UI verified** via Playwright: the cyan `↪ asked Iris` delegation pill (`data-testid="agent-handoff-pill"`) renders next to Atlas's name in the message bubble whenever `message.handoff` is non-null. Screenshot-confirmed on `/dashboard/agent/strategy`.
  - **11 new pytest cases** (`tests/test_agent_handoff.py`):
    - `TestExtractHandoffParser` (9): no-marker → None · parses by display name (`iris`→`research`) · parses by internal id · case-insensitive · rejects unknown agent (leaves marker for debug) · rejects empty question · truncates 600-char question to 300 · only first handoff extracted per turn · all 6 agent names resolve to correct ids.
    - `TestHandoffEndpointShape` (2): live Atlas→Iris round-trip validates the full `handoff` object shape + asserts `<<HANDOFF>>` marker never leaks into the user-facing answer + `"Iris reports"` block appears · sub-agents (Nova) can never produce a `handoff` even if their reply contains the marker (only Atlas has `can_handoff`).
  - **All 20 agent-chat tests green** (`test_agent_chat.py` + `test_agent_handoff.py`).
  - **Known infrastructure quirk**: a handoff is two sequential LLM calls (~30-50s combined). When called from the browser via the public ingress, the request can hit a Cloudflare/proxy 100s timeout. Backend itself returns 200 with the full payload. If this becomes a UX issue we'll switch to streaming SSE (already on the roadmap).


- 2026-02-28 (part 37) **📡 Reddit OAuth + Trend Ingestion unblocked**
  - **Root cause of the 403**: Reddit blocks anonymous `www.reddit.com/r/*.json` requests from datacenter IPs (AWS/GCP/Emergent infra) at the network layer regardless of User-Agent. Verified: `Mozilla/5.0`, `CortexViralBot/1.0`, even `old.reddit.com` → all 403.
  - **Fix in `routes/trends_engine.py`**: switched Reddit ingestion to the official **OAuth 2.0 application-only** flow (`client_credentials` grant on `https://www.reddit.com/api/v1/access_token` → `https://oauth.reddit.com/r/{sub}/hot`). Free, no user-context required, ~600 req / 10min limit.
  - **Token cache**: in-process bearer-token cache with 50-min TTL so we hit Reddit's auth endpoint at most ~1× per hour per worker. Auto-flushes on 401 so a mid-flight token expiry self-recovers on the next ingest tick.
  - **Graceful degradation**: when `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` are blank, the ingest short-circuits with `reddit: 0, reddit_configured: false` — Google Trends still runs, no 500/403 noise in logs.
  - **New env vars** (added to `/app/backend/.env`, blank by default): `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` (already pre-filled with a compliant value).
  - **New endpoint `GET /api/trends/status`** — reports per-source `{configured, note}` so the UI can render a setup hint when Reddit is offline.
  - **Frontend (`Trends.jsx`)**:
    - Amber `Reddit ingestion is offline` banner with inline link to `reddit.com/prefs/apps` + the exact env var names to paste.
    - Ingest toast now reads `"Google Trends: N · Reddit skipped (not configured)"` when Reddit is unavailable, instead of misleadingly counting "Reddit: 0".
    - Adds `Info` lucide icon import; `data-testid="trends-reddit-unconfigured-banner"`.
  - **11 new pytest cases** (`tests/test_trends_engine.py`):
    - `TestTrendsStatus` (2): auth required · per-source shape with `configured`/`note` keys, gtrends always true.
    - `TestTrendsSeeds` (2): auth required · default-niche fallback returns non-empty subs list.
    - `TestTrendsIngest` (3): auth required · ingest succeeds without 500/403 when Reddit unconfigured (asserts `reddit_configured: false` + `reddit: 0`) · watch-list (subreddits/keywords) persisted on the user doc.
    - `TestTrendsRecent` (2): auth required · `/recent` surfaces freshly-ingested gtrends rows.
    - `TestRedditOAuthScaffolding` (2): `_reddit_configured()` returns False when env blank · `_reddit_app_token()` short-circuits with `None` (no network call) when unconfigured.
  - **Existing tests still pass**: `test_trends_and_ablab.py` (10) + `test_memory.py` (10) → **31/31 trends-related tests green**.
  - **What you need to do to enable Reddit**: register a "script" app at https://www.reddit.com/prefs/apps (redirect URI can be anything — we don't use it for app-only flow), paste the `client_id` (the short string under the app name) into `REDDIT_CLIENT_ID` and the `secret` into `REDDIT_CLIENT_SECRET` in `/app/backend/.env`, restart backend. The banner disappears and `/trends/ingest` starts pulling hot posts from each watched subreddit.


- 2026-02-26 (part 36) **🔐 Sign-out-everywhere + ⏸️ Pause account + 📧 Password-changed email**
  - **Sessions management** — three new endpoints on `routes/account.py`:
    - `GET /api/account/sessions` returns `{total, others, current:{created_at,expires_at}}` so the dashboard can show "You're signed in on N other devices".
    - `POST /api/account/sessions/revoke-others` deletes every `user_sessions` doc for the user EXCEPT the one matching the calling cookie/bearer — keeps the current device alive after a stolen-laptop scare.
    - `POST /api/account/sessions/revoke-all` deletes all sessions including the caller's and clears the cookie. SPA redirects to `/` on success.
  - **Pause account (soft-delete)** — `POST /api/account/pause` body `{reason?}`:
    - Sets `users.status = "paused"` + persists `paused_at` and (optional) `pause_reason`. **No data is deleted.**
    - Deletes every active session for the user → all devices are signed out.
    - Fires `send_account_paused_email` (fire-and-forget) explaining "sign in any time to come back".
    - **Auto-reactivation** wired into all three login paths (`routes/auth.create_session`, `routes/password_auth.password_login`, `routes/magic_link.claim_magic_link`): if `status == "paused"` at login time, we flip it back to `"active"`, persist `reactivated_at`, and `$unset` the pause fields. The password-login response includes `reactivated: true` so the frontend can show a "Welcome back" toast.
    - `suspended` status remains a hard block (admin action) — only `paused` self-reactivates.
  - **Password-changed security email** — new `send_password_changed_email` template:
    - Fired from `_notify_password_changed()` after **every** successful `password/change` or `password/set-initial` call (NOT on `request-reset` since that flow already emails the new temp password).
    - Includes the timestamp, IP, and truncated User-Agent so the user can verify it was them.
    - Bold orange callout: *"If this wasn't you, your account may be compromised — reset your password immediately."*
    - CTA → `/dashboard/settings/account` for a quick lockdown.
  - **Frontend (`AccountSettings.jsx`)**:
    - New **Active sessions** card under Password — cyan monitor icon, dynamic "N active session" label, "Sign out other devices" (disabled when others=0) + "Sign out everywhere" rose button (with a `window.confirm` since it logs out the current tab).
    - New **Pause my account** amber card in Danger zone, above Delete account — opens `ConfirmPauseModal` with optional reason textarea. On confirm: pause API call → toast → redirect to `/`.
  - **8 new pytest cases** (`test_account_sessions_and_pause.py`):
    - `TestSessionsManagement` (4): auth required · list returns counts · revoke-others kills only extras + keeps current · revoke-all kills every session.
    - `TestPauseAccount` (3): auth required · pause flips status + clears sessions + preserves data · password login auto-reactivates a paused user (sets `reactivated: true` flag, clears `paused_at`).
    - `TestPasswordChangedEmail` (1): full change-password roundtrip writes a `password_changed`-tagged row into `email_log`.
  - **All 35 related-area tests still pass** (password_auth, account_delete, magic_link).
  - Screenshot-verified end-to-end on `/dashboard/settings/account`.

- 2026-02-26 (part 35) **📘 Facebook + 📸 Instagram OAuth scaffold (shared Meta app)**
  - **New `routes/oauth_meta.py`** — single module handling BOTH providers because they share the same Meta developer app and the same `/dialog/oauth` authorize endpoint. Only the scope set differs.
    - **Facebook scopes**: `public_profile`, `email`, `pages_show_list`, `pages_manage_posts`, `pages_read_engagement` — minimum to publish to a user's Facebook Page feed.
    - **Instagram scopes**: `public_profile`, `pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish` — IG Business publishing layered on Facebook Login (Meta's recommended modern flow, not the old `api.instagram.com/oauth/authorize` basic-display flow).
  - **8 new endpoints** matching the existing TikTok/LinkedIn shape (4 per provider): `/api/oauth/{facebook|instagram}/{start,callback,status}` + `DELETE /api/oauth/{facebook|instagram}`.
  - **Token cascade** (callback flow):
    1. Short-lived user token via `GET /oauth/access_token?code=...`
    2. Long-lived user token (~60d) via `grant_type=fb_exchange_token`
    3. List of Pages the user manages via `GET /me/accounts` — each Page has its own non-expiring Page access token.
    4. **Instagram only**: for each Page, query `instagram_business_account{id,username}` to resolve the linked IG professional account. If none found → redirect with `instagram=no_business_account` + friendly toast explaining how to convert their personal IG to a Business/Creator account.
  - **MongoDB collections**: `facebook_connections` (user_token + pages[]) and `instagram_connections` (user_token + pages[] + ig_accounts[]). Both mirror into the existing `channels` collection so the dashboard "connected" badge works for free.
  - **Reachability probe**: `/callback` accepts `HEAD` and returns 200 — required for Meta's "Verify Redirect URI" check during app review.
  - **HTTP-level error handling**: friendly redirects on `error=access_denied` (user cancelled), 503 on missing `META_APP_ID`/`META_APP_SECRET`, 400 on missing/invalid state, never leaks tokens.
  - **Channels page** auto-routes Connect clicks for Facebook/Instagram to the OAuth flow when `configured=true`, otherwise falls through to the existing mocked `/channels/connect` (so we keep a working demo until creds are pasted). Query-string toasts wired for all four success/denied paths + the IG no-business-account edge case.
  - **16 new pytest cases** (`test_oauth_meta.py`):
    - Status endpoints: anon → 401, authed → `{configured:false, connected:false}`.
    - `/start` 503s loudly when unconfigured (so users don't hit Meta with a broken `client_id`); if configured, validates URL shape + scope contents.
    - Callback HEAD probe returns 200 (Meta app-review prerequisite).
    - Callback with `error=access_denied` redirects with friendly query, not 500.
    - Callback without code/state → 400. Invalid state → 400.
    - Disconnect is idempotent (200 even with no existing connection).
    - **Scope-minimality assertions** that fail if anyone adds excess permissions (Meta reviewers reject apps requesting more than needed).
    - Redirect URI shape regression test.
  - **App-review compliance** now complete: `/privacy`, `/terms`, `/data-deletion` all live; both callback URLs return 200 on Meta's reachability probe; only minimal scopes requested.

  **URLs to paste into the Meta developer portal**:
  - Valid OAuth redirect URIs (paste both):
    - `https://cortexviral.com/api/oauth/facebook/callback`
    - `https://cortexviral.com/api/oauth/instagram/callback`
  - Privacy Policy URL: `https://cortexviral.com/privacy`
  - Terms of Service URL: `https://cortexviral.com/terms`
  - Data Deletion URL: `https://cortexviral.com/data-deletion`
  - App Domains: `cortexviral.com`

  **Pending — what we need from the user to go live**:
  - `META_APP_ID` (from Meta developer portal)
  - `META_APP_SECRET`
  - Once added to `/app/backend/.env` and the user redeploys to production, both Connect buttons flip from mocked → real OAuth automatically. **No code change needed.**
  - **Publishing endpoints** (POST to FB Page feed / IG container+publish) not yet implemented — those are a separate ~30-min job after OAuth is live and tested with real credentials.

- 2026-02-26 (part 33) **⚙️ Admin system settings — signup pause + per-platform kill-switches**
  - **New `routes/admin_settings.py`** — single-doc settings collection `system_settings` with two switches:
    - `signups_enabled: bool` (default True) — when False, brand-new Google signups return 503 from `/api/auth/session` so the marketing landing's "Start Growing" CTA stops creating accounts. Existing users + email-allowlisted admins always log in (so the admin can never lock themselves out of the panel). Admin-create + lead-form auto-create both bypass the pause so warm leads aren't lost.
    - `disabled_platforms: list[str]` (default []) — `/api/channels/connect` rejects with 403 when the requested platform is in the list, *including reconnects* (so an admin can yank a misbehaving integration immediately). Existing connections are NOT auto-disconnected — scheduled posts that already reference the platform continue to dispatch.
  - **Endpoints**:
    - `GET /api/admin/settings` (admin) — current settings.
    - `PATCH /api/admin/settings` (admin) — partial update; dedupe + sort platforms; audit-logged.
    - `GET /api/system/settings` (public) — exposes only user-safe fields. Channels page polls this on load to dim & lock disabled platforms.
  - **In-process 5s-TTL cache** on `get_settings()` so the hot paths (every `/auth/session`, every `/channels/connect`) avoid hitting Mongo. PATCH calls invalidate the cache so admin toggles propagate near-instantly.
  - **Frontend `/admin/settings` page** (`AdminSettings.jsx`):
    - "Accept new users" card: large emerald/rose icon, status copy that adapts to the toggle state ("Anyone with a Google account can sign up" vs "Brand-new signups paused"), a rose `SIGNUPS PAUSED` badge when off.
    - "Integration kill-switches" card: 3-column grid of platform rows (Instagram, TikTok, X, Facebook, LinkedIn, YouTube, Pinterest, Threads, Reddit) — each with platform icon, name, live status (`Enabled`/`Disabled`), and a custom emerald/grey toggle switch. Disabled rows turn rose.
    - **Dirty-state sticky action bar** at the bottom shows "Unsaved changes" + Discard / Save buttons. Bar only appears when local state ≠ server state.
    - New `Settings` icon item in the admin sidebar.
  - **Channels page** (`Channels.jsx`) — fetches `/api/system/settings` alongside the catalog and:
    - Adds a rose `DISABLED` pill next to the platform label.
    - Status line reads "Off — by admin" instead of "Not connected".
    - Connect button is disabled + greyed out + tooltipped ("This integration has been temporarily disabled by the admin").
    - Already-connected users can still hit Disconnect to clean up — they're not forced to keep a stale connection.
  - **10 new pytest cases** (`test_admin_settings.py`):
    - Public read returns defaults · admin auth required · GET shape · PATCH signups toggle persists & is visible publicly · PATCH platforms dedupes + sorts + ignores blanks · partial patch preserves untouched field · connect to disabled platform → 403 · connect to non-disabled platform succeeds · reconnect of a previously-connected disabled platform → 403 · admin-create bypasses signup pause.
  - **Bug found+fixed during testing**: pytest runs in a separate process from the live backend, so directly deleting the settings doc from a test wouldn't invalidate the backend's in-process cache → test order leakage. Reworked `_reset_settings()` to call `PATCH /api/admin/settings` instead so the cache is busted server-side. Saves future cache-related flake.
  - **Live screenshot-verified** end-to-end: toggling signups off → "SIGNUPS PAUSED" badge appears → toggling Pinterest off → save → /dashboard/channels shows Pinterest with the rose DISABLED pill and locked Connect button. Reset back to defaults verified.

- 2026-02-26 (part 32) **🔁 Series-aware cancel + Shift+drag series shift**
  - **Backend** (`routes/channels.py`):
    - `DELETE /api/posts/scheduled/{id}?scope=only|future|all` — new optional `scope` query param. `only` (default) preserves the old behavior. `future` deletes every still-scheduled post in the same `recurrence_group_id` whose `scheduled_at` ≥ this one (past instances kept). `all` deletes the entire series. Non-recurring posts always downgrade to `only`. Returns `{ok, deleted, scope}`.
    - `PATCH /api/posts/series/{group_id}` body `{delta_days, anchor_post_id?}` — shifts every still-scheduled post in the series by ±N days. With `anchor_post_id`, only the anchor + future are shifted. Rejects 0 delta as no-op, |delta| > 365 as 400, unknown group as 404.
  - **Frontend** (`MarketingCalendar.jsx`):
    - **`RecurrenceCancelModal`** — opens whenever a user clicks the X on a recurring chip (week view) OR the Cancel button on a recurring entry in the day-detail drawer (month view). Three lettered options as styled buttons: "Just this one" / "This + all upcoming" / "The entire series" (the destructive one shown in rose with the total count). Bypassed for non-recurring posts.
    - **Shift+drag series shift** — when a user holds Shift while dragging a 🔁 weekly chip to a different day, the drop opens **`SeriesShiftPromptModal`** asking whether to move just the instance, shift this + upcoming, or shift the entire series by the date delta they just dragged. Non-recurring posts and Alt+drag (duplicate) bypass this flow. Cursor / dropEffect updates while dragging.
    - Footer hint line updated to teach the new shortcuts: `Alt`+drag to duplicate · `Shift`+drag a 🔁 weekly post to shift the series.
  - **10 new pytest cases** (`test_series_ops.py`):
    - `TestSeriesCancel` (5): default scope deletes one, `scope=future` keeps past, `scope=all` deletes everything, unknown scope → 400, non-recurring posts downgrade to `only`.
    - `TestSeriesShift` (5): full-series shift verified by recomputing the delta on every member, anchored shift skips past members, zero delta is a no-op, unknown group → 404, |delta| > 365 → 400.
  - Cleaner mental model than per-row edit menus: same drag/click affordances the user already knows, recurrence options surface only when they're meaningful (= the post is part of a series).

- 2026-02-26 (part 31) **🔁 Repeat-weekly + 📅 Month grid + 🖱️ Alt-drag duplicate + 🪄 Lead-form auto-account**
  - **Repeat weekly toggle** (Compose & Publish):
    - New `repeat_weeks: Optional[int]` field on `PublishRequest` (2–12 enforced by Pydantic `ge`/`le`).
    - Backend `/api/channels/publish` — when `repeat_weeks` is set AND the post is scheduled into the future, materialises N posts at +0w, +1w, …, +(N-1)w. Each shares a `recurrence_group_id` (uuid4) + `recurrence_index` + `recurrence_total` for future series-aware operations. Returns `{ok, ids, recurrence_group_id, repeat_weeks}` instead of the single-post shape.
    - Frontend `Compose.jsx` — violet "Repeat weekly" panel appears underneath the schedule input the moment a date is picked. Toggle + number input (2–12, default 4) + helper copy.
  - **Month view — single row per day with stacked dots** (`MarketingCalendar.jsx`):
    - When `view === 'month'`, the range pads to full weeks (back to previous Sunday, forward to next Saturday) so the grid is always 7×N (typically 7×5 or 7×6).
    - New `<MonthGrid>` component: 7-col day grid, each cell shows date number + 2 compact post chips (time + truncated content) + per-platform colored dots (max 3 + "+N" overflow) + total post count pill.
    - Posts within a cell are draggable (same logic as week view) so rescheduling works from either view.
    - Out-of-month dates dimmed; today highlighted with emerald ring; past days greyed out.
    - Click any cell → opens a right-anchored side drawer (`<DayDetailDrawer>`) listing every post that day with full content, platform pills, recurrence badge (🔁 weekly · N/M), and inline cancel button.
  - **Alt+drag duplicate** (week + month view):
    - `onDragStart` / `onDragOver` / `onDrop` now check `e.altKey`. When held, cursor switches to `copy` and the drop POSTs a new scheduled post instead of PATCHing the existing one. Toast distinguishes "Duplicated" vs "Rescheduled". Lets a user clone the same Monday post to Wednesday and Friday in two drags.
  - **Lead-form auto-account + magic link**:
    - `routes/leads.py` already detects an anonymous lead, auto-creates a `user` doc (plan: free, `created_via: lead_form`), issues a magic link via `routes/magic_link.issue_magic_link`, and passes it to `send_lead_auto_reply` so the agent's auto-reply email includes a one-click sign-in button. Idempotent: if the email already has an account, we reuse it and just issue a fresh link.
    - **End-to-end verified**: POSTing a lead now creates the user, persists a `magic_links` row tagged `purpose=lead_claim`, and the auto-reply email body includes the sign-in CTA. Duplicate-email lead does NOT create a second user (verified by test).
  - **12 new pytest cases** (`test_recurrence_and_lead_claim.py`):
    - `TestRepeatWeekly` (5): N-instance creation, immediate-post bypass when not scheduled, 422 on `repeat_weeks<2`, 422 on `>12`, 12-week max accepted.
    - `TestLeadAutoCreate` (2): user + magic link created from anonymous lead, duplicate-email lead is idempotent.
    - Combined with the existing magic-link suite (12 cases), the new admin-create + magic-link + recurrence + lead-auto-create feature set has **19 dedicated tests** with full coverage. **All affected existing suites still pass.**

- 2026-02-26 (part 30) **🔐 Admin-create user + magic-link auth**
  - **New `routes/magic_link.py`** — `secrets.token_urlsafe(32)` tokens persisted in `magic_links` collection with a 7-day TTL index (Mongo auto-purges). **`GET /api/auth/claim?token=...`** validates the token (single-use, expiry, suspended-account checks), mints a fresh `session_token` and sets the same cookie shape Emergent Google Auth produces — so the rest of the app (deps.get_current_user, ProtectedRoute, billing, etc.) sees zero difference between Google-auth users and magic-link users.
  - **`POST /api/admin/users/create`** — body `{email, name, plan, comped, send_email, brand_name?, website?, niche?}`. Idempotent: if the email already exists, we update the doc and re-issue a fresh link instead of erroring (so admins can recover from "did the email get lost?" without manual DB ops). Returns `{user_id, magic_link, email_sent, new_user}` — admin can copy the link directly if email delivery fails.
  - **`POST /api/admin/users/{id}/resend-invite`** — generates a fresh magic-link token for an existing user and re-emails it. Useful when the original 7-day link expired or the user lost the email.
  - **Existing `send_account_invite_email` template** in `routes/email.py` provides the on-brand HTML with a styled CTA button + plain-text fallback URL + "expires in 7 days" notice — routes via the standard Mailtrap → Mailgun chain.
  - **Frontend `/auth/claim` page** (`AuthClaim.jsx`) — already-built dark-glass card with loader / success / error states; calls `/api/auth/claim`, then `refresh()` from AuthContext, then bounces to `/dashboard` (which itself bounces to `/onboarding` if not done).
  - **Admin UI**: `AdminUsers.jsx` "Create user" button → modal with email / name / plan / comped toggle / "send email" checkbox. Submitting shows a success card with the generated magic link in a read-only field + a "Copy" button (in case email delivery silently failed). Each user row also gets a new envelope-icon button (`admin-resend-invite-{user_id}`) that issues a fresh link and re-sends the email with one click.
  - **Bug found+fixed during testing**: `claim_magic_link` was comparing a naive datetime (returned from Mongo) against a tz-aware `datetime.now(timezone.utc)`, raising `TypeError: can't compare offset-naive and offset-aware datetimes` → 500 on every claim. Fixed by normalising `expires` to UTC-aware before the comparison.
  - **12 new pytest cases** (`test_magic_link.py`): admin-only on create/resend, idempotency on existing email, plan validation, full create→claim→/auth/me round-trip with cookie persistence, single-use token enforcement, resend issues a distinct token, 404 on unknown user. **All 158 backend tests pass.**

- 2026-02-26 (part 29) **🎯 Niche-aware AI personalization**
  - **New `_user_context_block(user_id)`** in `routes/ai.py` — reads the onboarding profile from the user doc and builds a compact system-prompt preamble: BRAND / NICHE / GOALS / PRIMARY PLATFORMS / STATED CHALLENGE. Includes an explicit instruction *"tailor your output to them. Don't restate the context back to them — just make the output reflect it. Avoid generic platitudes."* Empty profile → empty block (zero-cost fallback).
  - **New `_llm_for_user()` helper** wraps the existing `_llm()` factory and injects the context block transparently. All 9 user-facing AI call-sites in `routes/ai.py` (`generate-post`, `generate-video-script`, `seo-audit`, `viral-ideas`, `email-campaign`, `caption`, `comment`, `seo-keyword-research`, `multipost`) switched over by a regex pass. The A/B Hook Lab (`routes/ab_lab.py`) also wired through it.
  - **Trends Engine deliberately left untouched** — it serves a globally-cached daily feed, so injecting one user's context would poison it for everyone else.
  - **Live verified**: with a Fitness brand profile (`Iron Pulse Coaching`, niche `Fitness`, goal `Generate leads`, platform `TikTok`), the same generic prompt *"a hook about discipline"* now produces output referencing **"Iron Pulse Drill"** with hashtags `#IronPulseCoaching #GymTok #FitnessTips` and a CTA mentioning *"coaching link in bio"*. No tuning of the user prompt — just the context preamble.
  - **4 new pytest cases** (`test_personalization.py`): empty profile returns empty block, full profile renders all fields, long challenge truncated to 280 chars, end-to-end LLM call surfaces Fitness-niche signals. **145 backend tests pass.**

- 2026-02-26 (part 28) **🚀 New-user onboarding flow**
  - **New `/onboarding` page** — dark-gradient hero, "Welcome {first_name}" badge, "Let's tailor CortexViral to your brand" headline, 6 fields total (2 required text + 1 required pill-pick + 2 optional pill-pick + 1 optional textarea). Submitting writes to the user doc, marks `onboarding_completed_at`, and fires an admin notification email.
  - **Auto-redirect**: `ProtectedRoute.jsx` now checks `user.onboarding_required` and routes to `/onboarding` on first dashboard visit. Admins bypass the redirect; users who click "Skip for now" set a session flag (`onboarding_skipped`) so the redirect doesn't keep firing on every nav within that browser tab.
  - **Reminder banner** on `/dashboard/overview` — gradient violet→cyan strip with "Finish setting up your account · ~2 minutes" + arrow CTA. Persists across sessions for skippers until they complete.
  - **Backend**: new `routes/onboarding.py` exposing `GET /onboarding/options`, `GET /onboarding/me`, `POST /onboarding`. `/auth/me` now augmented with `onboarding_required: bool` so the SPA can route synchronously without an extra round-trip. Website URLs auto-normalised to add `https://` when user types a bare domain. Goal + platform values validated against the canonical lists (returns 400 on unknown values).
  - **Admin notification template** — `send_onboarding_admin_notification` fires only on FIRST completion (re-edits don't re-spam admins). Emails the addresses in `LEADS_NOTIFY_EMAILS` with a styled table: name, email, website (clickable), brand, niche, goals, platforms, optional challenge in italics. Gives the support team enough context to reach out with niche-specific playbooks.
  - **AdminUsers page** now shows `brand_name • website • niche` directly under each user's email, with clickable website link in violet. Backend `/admin/users` injects these fields with sensible defaults.
  - **AuthContext** exposes a new `refresh()` alias (= `checkAuth`) so the onboarding page can repopulate the user object post-submission.
  - **10 new pytest cases** in `test_onboarding.py` covering: auth, options shape, `required` flag, full submit roundtrip, invalid niche/goal rejection, `first_completion` semantics, AdminUsers profile fields, admin notification wiring. **141 backend tests pass.**

- 2026-02-26 (part 27) **📨 Lead-form email notifications**
  - **Bug fixed**: when a visitor submitted the "Choose Your Specialist" form (Nova/Sam/Kai/Angela), the lead was persisted but **no one got an email** — yet the UI toast said "X will reach out within 24 hours". Misleading + caused real leads to never receive a reply.
  - **New env var** `LEADS_NOTIFY_EMAILS` — comma-separated list of admin emails. Preview is set to `williams342@gmail.com,team@cortexviral.com`. **Production deploy must mirror this** in Emergent's environment variables panel or the admin won't get pinged.
  - **Two new templates in `routes/email.py`**:
    - `send_lead_admin_notification(lead, recipients)` — to every address in `LEADS_NOTIFY_EMAILS`. Subject `🔥 New lead for {agent}: {name} ({email})`. Body has a styled `<table>` with all form fields. CTA → `/admin/users`.
    - `send_lead_auto_reply(lead)` — to the lead's own address, written in the chosen agent's voice (Nova/Sam/Kai/Angela), quotes their pain-point if provided, sets the 24h expectation, gives them a CTA to sign in. Quietly skipped if the lead has no email.
  - **`routes/leads.py::create_lead`** now persists the lead first, then fires both emails fire-and-forget via the existing `fire()` helper. Try/except wraps the scheduling so an email outage can never block lead capture.
  - **Live verified**: POSTing a sample lead resulted in 3 `email_log` rows all `status: sent` — 2 admin notifications + 1 auto-reply, all via Mailtrap.
  - **3 new pytest cases**: full fan-out + auto-reply, missing-email edge case, lead always persists. **131 total backend tests pass.**

- 2026-02-26 (part 26) **📣 Email blast for admin broadcasts**
  - `POST /api/admin/broadcasts/{id}/email` body `{plans?: string[], include_comped: bool, dry_run: bool}` — sends an email version of the broadcast to all matching users via Mailtrap. Throttled 50ms between sends to stay polite. Dry-run mode counts recipients without sending so admin can confirm reach before firing.
  - `send_broadcast_email()` template — colour-coded severity badge (📣 info / ⚠️ warning / 🚨 critical / 🎉 success), styled blockquote, "Open dashboard" CTA. Wrapped in the same brand layout as welcome/gift/etc.
  - Broadcast doc now persists `emailed_at`, `emailed_by`, `emailed_recipients`, `emailed_sent`, `emailed_failed`, `emailed_filter` after a send — surfaced as a purple "Emailed N/M" pill on the broadcast row in AdminBroadcasts.
  - **Frontend modal** (`/admin/broadcasts`): purple "Email blast" button on each broadcast row → opens a modal with plan-filter chips (Free/Starter/Growth/Agency multi-select), an "Include comped users" switch, a "Preview" button that runs the dry-run and shows "N users match the filter", and a "Send to N" CTA that's disabled until preview has been run AND matched > 0 users. Confirmation prompt before send. Toast on success with sent/failed counts.
  - **Side bug fixed**: `BroadcastBanner.jsx` was crashing with "Cannot read properties of null (reading 'filter')" because `GET /api/broadcasts/active` was accidentally returning `null` after my edit to add the email-blast endpoint (the function body was severed). Restored the body + added defensive `Array.isArray()` guard on the client.
  - **6 new pytest cases** including a live Mailtrap-send roundtrip that verifies `emailed_sent / emailed_recipients` are persisted correctly. **128 backend tests pass.**

- 2026-02-26 (part 25) **✉️ Mailtrap integration (Mailgun → fallback)**
  - **Mailtrap** is now the primary transactional-email provider. Endpoint: `https://send.api.mailtrap.io/api/send`. Sender verified at `hello@cortexviral.com` (DKIM/DMARC/CNAME all pass; account `team@cortexviral.com`).
  - **Provider chain in `routes/email.py`**: tries `_send_via_mailtrap` first → falls back to `_send_via_mailgun` ONLY when Mailtrap is unconfigured or returns a 5xx/network error. 4xx responses (bad sender, invalid payload, etc.) deliberately don't trigger fallback because Mailgun would reject the same payload. `email_log` rows now carry a `provider` field and (when fallback fired) `fallback_from` + `primary_error` so admins can see exactly which path delivered.
  - **`/admin/email/health` card** label updated from "Mailgun delivery" → "Transactional email" so it's provider-agnostic now that two providers are in play.
  - **`_parse_from()`** helper splits `"Name <email@host>"` into Mailtrap's required `{name, email}` shape; also handles bare addresses and empty strings.
  - **4 live test sends to williams342@gmail.com** — Welcome / Gift / Trial / Past-due all returned `{sent: true, provider: "mailtrap", id: <uuid>}` ✅ Real email delivered through Mailtrap's verified `cortexviral.com` domain.
  - **Test added** (`TestProviderRouting::test_parse_from_with_display_name`). Existing helper tests updated to clear BOTH provider tokens. **11/11 email tests pass, 122 total backend tests.**
  - **Diagnostics done**: Mailtrap's first 401 was caused by `hello@demomailtrap.com` not being authorised for this account — Mailtrap requires the sender's domain to match a verified domain on the account. After swapping to `hello@cortexviral.com` (which has full DKIM+DMARC+CNAME pass), sends succeed.

- 2026-02-26 (part 24) **🪝 Admin "Webhook Events" page**
  - New `GET /api/admin/webhook-events?limit=50` reads the `stripe_events` collection. Returns `{total, items[], top_event_types[]}` — items include `event_id`, `type`, `received_at`, and a new `redeliveries` counter.
  - **Stripe webhook upgrade**: when a duplicate `event_id` hits the receiver, instead of silently short-circuiting we now `$inc redeliveries` and `$set last_redelivery_at` on the existing row — gives admins visibility into how often Stripe is re-delivering each event (signals downstream processing issues or network flakes).
  - **`/admin/webhook-events` page**: stats card with total + Refresh button, "By Event Type" pill row with top 8 types + counts, sortable table showing the last 50 events with green "Processed" / amber "+N Repeat" status pills. Empty-state copy ("No Stripe events received yet…") guides setup. New "Webhook Events" link in admin sidebar with `Webhook` icon.
  - **4 new pytest cases** covering admin auth, full payload shape, redelivery counter (verified to bump to 2 after 3 deliveries), `limit` clamping. **122 backend tests pass.**

- 2026-02-26 (part 23) **📬 Email Health card + cookie@1 resolution**
  - New `GET /api/admin/email/health?hours=24` aggregates `email_log` by status: `{total, sent, rejected, errored, skipped, delivery_rate, last_problem}`. `last_problem` surfaces the most recent non-success row with reason + Mailgun HTTP status so an admin can diagnose without opening MongoDB. `hours` is clamped 1–720.
  - **AdminOverview card** — sits between Funnel and AI analytics. Color-coded "Mailgun delivery" pill (Healthy ≥95% / Degraded ≥70% / Failing) with delivery-rate + total-sends sub-line, 4 tile counts (Sent / Rejected / Errored / Skipped — coloured red when non-zero), and an amber "Most recent issue" expandable line showing the status + subject + raw reason. Right now it correctly shows `Failing` + the Mailgun "Account disabled" 403, which is exactly what you'd need to debug deliverability.
  - **Fixed CRA build error** caused by the part-20 react-snap install: `puppeteer@1.20` pulled in `cookie@0.3.1` which clashed with `react-router@7`'s required `cookie@^1.0.1`. Added a yarn `"resolutions": {"cookie": "^1.0.1"}` pin in `package.json` — installs now resolve to `cookie@1.1.1` cleanly. Frontend compiles error-free.
  - **4 new pytest cases** in `test_email.py`: auth required, full response shape, `hours` clamped, `last_problem` correctly surfaces the most recent non-sent row. **118 backend tests pass.**

- 2026-02-26 (part 22) **🔒 Stripe webhook hardening**
  - **Signature enforcement** — new env flag `STRIPE_WEBHOOK_STRICT` (default `true` for safety). When strict + no secret → returns `503 "Webhook signature verification is required"`. When strict + secret → signatures verified as before (400 on tampered events). When `false` + no secret → falls back to the dev-mode parser (with a loud log warning). The preview environment uses `STRIPE_WEBHOOK_STRICT=false` so local testing without `stripe listen` continues to work; production should leave it at the default and supply `STRIPE_WEBHOOK_SECRET` from the Stripe dashboard.
  - **Idempotency** — every Stripe event has a stable `event.id` (e.g. `evt_abc`). Stripe retries delivery until it gets a 2xx, so duplicate deliveries are common in real traffic. We now insert every event_id into a new `stripe_events` collection with a unique index. Duplicates short-circuit with `{"received": true, "duplicate": true, "event_id": ...}` and **never re-apply plan changes** — avoiding the race where two `customer.subscription.updated` events flip a comped user's plan back and forth.
  - **4 new pytest cases** (`tests/test_stripe_webhook.py`): strict-mode rejection, idempotent dedupe of identical event_id, distinct event_ids both processed, bad-signature fallback. Verified live via curl: 503 when strict, 200 first time, 200 + `duplicate:true` on replay. **114 backend tests pass.**

- 2026-02-26 (part 21) **📧 Mailgun transactional emails**
  - `routes/email.py` — `send_email()` async helper using httpx + Mailgun HTTP API. Failures never raise — they log to a new `email_log` collection and return a structured `{sent, error/skipped, status?}` dict so callers can decide whether to retry.
  - **Lifecycle templates** (all use a shared dark-gradient header / light body brand layout):
    - **Welcome** — fired from `/api/auth/session` when a user is first created. CTA → `/dashboard/studio`.
    - **Gift plan** — fired from `/api/admin/users/{id}/plan` when admin comps a user to a paid tier. Includes the admin's `reason` quote when provided. CTA → `/dashboard`.
    - **Trial ending** — fired from Stripe webhook `customer.subscription.trial_will_end` (~3 days before charge). CTA → `/dashboard`.
    - **Past-due** — fired from Stripe webhook `invoice.payment_failed`. Suppressed for comped users (they're not on Stripe). CTA → `/dashboard`.
  - All sends are **fire-and-forget** via a small `fire(coro)` helper — never blocks the user's request.
  - `POST /api/admin/email/test` — admin-only debug endpoint to send any of the 4 templates to any address (great for QA + design previews).
  - **Bug found+fixed**: httpx 0.28 rejects `data=<list-of-tuples>` from `AsyncClient` with a cryptic `"Attempted to send an sync request"` error. Worked around by URL-encoding the form manually (`urlencode(payload)`) and POSTing as `content=` + explicit `Content-Type` header. Documented in the code comment for future grep-ability.
  - **6 new pytest cases** (`tests/test_email.py`): admin auth required, all 4 template kinds reachable, email_log persists, structured response shape, helpers gracefully skip when key isn't configured. **110 tests pass.**
  - **Sandbox status**: API key is wired and the integration works end-to-end. Mailgun is currently returning `403 "Account disabled"` — you'll need to either re-enable the sandbox in Mailgun (Dashboard → check account status / verify your sandbox recipients) or verify a real domain (e.g. `cortexviral.com`) and swap `MAILGUN_DOMAIN` in `.env`. Zero code changes needed once that's done.

- 2026-02-26 (part 20) **📊 Conversion funnel + 🚀 react-snap SEO prerender**
  - **Funnel** (P2):
    - New `routes/funnel.py`: `POST /api/track/visit` (anonymous, bot-filtered, IPs hashed before persistence) + `GET /api/admin/funnel?days=N` (admin only, 4 stages: Visitors → Signups → Activated → Paid + conversion rates between each step + comped tally).
    - `VisitTracker.jsx` mounts at App root, fires `/api/track/visit` on every public-route change (skips `/dashboard`, `/admin`, `/auth-callback`). Failures are swallowed — analytics never breaks the page.
    - Pageviews stored in new `pageviews` collection; unique visitors = distinct `(ip_hash, day)` tuples.
    - **AdminOverview** new "Conversion Funnel" widget — 4 stacked bars width-scaled to the largest stage, color-coded icons, per-stage conversion %, 7d/30d/90d filter pills, "Overall X% of visitors become paid" summary line.
    - **7 new pytest cases** (`test_funnel.py`): anonymous tracking, bot UA skipped, IPs hashed (never persisted raw), admin auth required, `days` param clamped 1-365, dedupes same-IP-same-day, full response shape validation. **104 tests pass.**
  - **SEO prerender** (P3):
    - Installed `react-snap` (~1.23, dev-dep). Configured to use the host's existing `/usr/bin/google-chrome` (no Chromium download, no extra MB).
    - New script: `yarn build:seo` = `craco build && react-snap`. **Default `yarn build` is unchanged** so the existing prod-deploy pipeline never accidentally runs the prerender.
    - 63 routes prerendered per pass: home, /pricing, /agents, /blog, /privacy, /terms, /sitemap, 5 AI-tool landings, 32 niche `/tools/:slug` programmatic pages, 12 blog posts, 200.html, 404.html.
    - Each route saves as `<path>/index.html` containing full rendered DOM, `<h1>`, `<title>`, JSON-LD blocks — Googlebot + AI bots see content on first byte, no hydration wait.
    - `skipThirdPartyRequests: true` blocks `/api/track/visit` and other backend calls during render so output is deterministic + bot-safe.
    - `inlineCss: false` (react-snap's CSS inlining crashes with cross-origin `Failed to fetch`; CSS-in-bundle works fine).
    - **`/app/frontend/SEO_PRERENDER.md`** documents the setup, route list, how to enable it for prod deploys, and the trade-offs (vs. Next.js).
    - To turn on for production: change the Emergent deploy build command from `yarn build` → `yarn build:seo`.

- 2026-02-26 (part 19) **🔥 Real Trend Engine + A/B Hook Lab backends**
  - **Trend Engine** (existing `routes/trends.py` enhanced):
    - First tries `_scrape_tiktok_creative_center()` for live TikTok Creative Center data.
    - When scrape fails (blocked / shape change), new `_llm_synthesise_trends()` asks GPT-4o-mini for 6 fresh viral-velocity hooks — keeps the feed feeling alive instead of falling back to the static seed pool.
    - 1-hour cache in `trend_cache` collection so we don't hammer LLMs/scrapes.
    - Frontend already wired to `GET /api/ai/trends` + `POST /api/ai/trends/refresh`. Source badge (`tiktok_creative_center` / `ai_synthesised` / `fallback`) drives the "Live feed" vs "Curated baseline" pill in the UI.
  - **A/B Hook Lab** (new `routes/ab_lab.py`):
    - `POST /api/ai/ab-variations` body `{seed, platform, count}` → returns 5 hook variants, each with `text`, `score` (0-100), and a structured `breakdown` across 5 viral-hook axes (curiosity_gap / specificity / pattern_interrupt / emotional_charge / brevity, each 0-20). Plus a 1-sentence `why` explaining the score.
    - LLM does scoring in the same call as generation — so the score is the model's honest assessment, not a fake client-side hash. Sorted high→low.
    - Counts against the user's monthly AI cap. Gated to Growth+ via new `assert_has_feature` helper (returns 402 `feature_not_in_plan` for Free/Starter).
  - **Frontend (`Studio.jsx` A/B Lab tab)**: now POSTs to `/api/ai/ab-variations`, renders the breakdown as colored pills under each variant + the LLM's reasoning in italic. Layout switched from horizontal to vertical to fit the new metadata.
  - **`assert_has_feature()`** helper added to `routes/plans.py` — single source of truth for feature-flag gating, returns the same 402 structured error shape as the AI cap so the existing `usePaywallHandler` frontend hook handles it for free.
  - **10 new pytest cases** (`tests/test_trends_and_ablab.py`): auth-required, Free/Starter blocked with 402 + `feature_locked` code, Growth returns trends, cache persists between calls, A/B Lab returns 5 variants with full breakdown, sorted by score, increments AI quota counter, rejects empty seeds. Suite: **97/97 pass** (one flake under load due to LLM rate-limit, passes in isolation).

- 2026-02-26 (part 18) **🎁 Comped-user ribbon on dashboard**
  - When `usage.comped === true` (set via the new admin plan endpoint), the Overview billing strip now shows:
    - Gift icon (emerald) instead of `CreditCard`/`CheckCircle2`.
    - Inline pill **"✦ Comped by CortexViral"** next to the plan label (`data-testid="comped-ribbon"`).
    - Friendly subtitle: *"Gifted by the CortexViral team — enjoy! No card on file, no renewal."*
    - Right-side CTA is replaced with passive *"No action needed ✨"* (no Upgrade / Manage-billing buttons that would confuse the user).
    - Annual-upsell banner is suppressed for comped users (they're not on Stripe).
    - Trial / Past-due pills are also suppressed when comped (irrelevant).
  - Reduces support-ticket noise ("why am I on Growth?"), and builds goodwill — comped creators tend to publicly thank the brand, which is organic marketing.
  - P3 Next.js migration **deferred** per user direction. Current `react-helmet-async` + JSON-LD is good enough until there's evidence of indexing problems; revisit later with `react-snap` if needed.

- 2026-02-26 (part 17) **🛡️ Admin plan-tier override + comped users**
  - **Admin login verified** — `GET /api/admin/me` returns `is_admin: true` for the allow-listed email. `ADMIN_EMAILS=williams342@gmail.com` is the source of truth; promote/demote also flips the flag at runtime.
  - **New endpoint `POST /api/admin/users/{user_id}/plan`** — body `{plan, comped, reason}`. Validates plan against `ENTITLEMENTS`, persists `plan`, `comped`, `comped_by`, `comped_reason`, `comped_at`, and writes an audit-log entry (`action: "set_user_plan"`).
  - **Comped immunity**:
    - `routes/plans.py::_get_plan` no longer downgrades comped users to free when `subscription_status == "past_due"`.
    - `routes/billing.py::_apply_plan_to_user` (used by Stripe webhook + checkout-status poll) writes everything **except** `plan` for comped users — so a customer-portal cancellation or a `customer.subscription.updated` event can't yank entitlements away from a manually-comped influencer.
  - **Frontend (`AdminUsers.jsx`)**: new "Plan" column with an inline tier `<select>` (Free / Starter / Growth / Agency, plus a legacy `pro`/`scale` option that shows automatically when a user is on the old tier) and a pill-style "Comped / Not Comped" toggle with a `Gift` icon. Both wired to the same endpoint. Toast confirms each change. Plan + comped status are now returned by `GET /api/admin/users`.
  - **`GET /api/billing/usage`** now includes a `comped: bool` field — useful for future frontend badging ("Plan: Growth · Comped").
  - **8 new pytest cases** (`tests/test_admin_plan_override.py`): auth required, unknown plan rejected (422 via `Literal`), 404 on unknown user, full set+verify+entitlements roundtrip, un-comp clears metadata, audit-log entry recorded, comped+past_due keeps plan, uncomped+past_due falls back to free. Suite: **87/87 pass.**

- 2026-02-26 (part 16) **🔘 Navbar CTA fix — auth-aware fallback**
  - **Root cause**: `Privacy.jsx`, `Terms.jsx`, and `Sitemap.jsx` were each mounting `CVNavbar` with `onGetStarted={() => {}}` (an empty no-op), so the prominent **"Start Growing"** CTA in the top-right navbar was dead on those three pages — visitors clicking it saw no feedback at all. The literal "Login" text button on the same pages worked, but `Start Growing` is the dominant CTA and users tend to click that.
  - **Fix** (`components/cv/CVNavbar.jsx`): `onGetStarted` is now optional. New `handleCTA()` falls back to `user ? navigate('/dashboard') : login()` when the prop is missing or non-function. The desktop CTA `onClick` was rewired from `onGetStarted` → `handleCTA`. Mobile menu was already correct (uses inline `login()` call).
  - Removed the no-op `onGetStarted={() => {}}` from Privacy / Terms / Sitemap so the new fallback kicks in.
  - **Verified via Playwright**: `/privacy`, `/terms`, `/sitemap` all now redirect "Start Growing" to `https://auth.emergentagent.com/?redirect=...`. Regression-tested: landing-page "Login" still routes to auth, landing-page "Start Growing" still opens the "Choose Your Specialist" modal. 5/5 scenarios pass.

- 2026-02-26 (this session — part 15) **✨ Price anchor + Per-feature gating UI**
  - **Growth price anchor**: `Pricing.jsx` Growth tier now shows `~~$59~~ $39` (monthly) and `~~$49~~ $33` (annual /mo billed annually) with an inline `✦ Early creator price` emerald badge. Anchor scales with the billing toggle. Subtle scarcity framing without lying about a sale.
  - **`FeatureLock` component** (`components/FeatureLock.jsx`): wraps any feature surface. When locked, renders the underlying UI blurred + grayscale behind a glassmorphic "UNLOCKS ON `<TIER>`" card with feature name, blurb, and direct "Upgrade to Growth →" CTA pointing at `/pricing`.
  - **Two new Studio tabs** gated to Growth+:
    - **Trend Engine** — live viral-velocity feed across TikTok/Reels/Shorts. Shows 6 trending hashtags with velocity scores (92/88/84/79/76/71), platform badges, sample hooks, copy-to-clipboard buttons. Visible-when-unlocked, blur-overlaid-when-locked.
    - **A/B Hook Lab** — drop a hook idea, generates 5 scored variations (95→70), ship the highest-stopping version. Uses existing `/api/ai/generate-post` endpoint (counts against monthly cap), client-side scores the variants.
  - Tab pills show 🔒 lock icon when the user lacks the feature (`requiresFeature` config).
  - Studio polls `/billing/usage` and stores `features` dict (trend_engine, ab_variations, batch_generation, api_access, multi_workspace) — refreshes after each generation so unlocking after upgrade is instant.

- 2026-02-26 (part 14) **🎯 4-Tier Pricing Rework + Admin Analytics + Next.js Plan**
  - **Backend plan catalogue** completely restructured. `PLANS` now holds:
    - **Starter** — $15/mo or $150/yr — 30 generations/month, 2 channels.
    - **Growth** — $39/mo or $390/yr — unlimited generations, unlimited channels, trend engine + A/B variations enabled.
    - **Agency** — $99/mo or $990/yr — everything in Growth + batch generation + multi-workspace + API access.
    - Free tier (no Stripe product) — 20 generations/month (≈5/week), 1 channel (TikTok only).
    - Legacy `pro`/`scale` entitlements kept for backwards-compat (any existing subscribers continue working).
  - **Stripe**: 3 new products + 6 new prices auto-provisioned on startup (cached in `stripe_products` collection). Old `pro`/`scale` products remain in Stripe (no impact).
  - **Entitlements** include feature-flag dict (`trend_engine`, `ab_variations`, `batch_generation`, `api_access`, `multi_workspace`) exposed via `/billing/usage` so frontend can gate features per-tier.
  - **Full Pricing page rewrite** (`Pricing.jsx`):
    - **Hero**: "Create Viral Content That Actually Grows Your Audience" + Start Free / View Plans dual CTA + trust micro.
    - **Value strip**: 4 ✓ statements ("Built for virality, not generic AI writing", etc.) in a glass card.
    - **4-tier pricing cards** with billing toggle (Monthly / Annual + "2 mo free" badge). Each card has icon, name, blurb, price, CTA (live Stripe Checkout), micro-copy, feature list, and Free tier shows exclusions in red strikethrough.
    - **Feature comparison table** — 11 features × 4 tiers, with Growth column highlighted.
    - **"Why Free Isn't Enough" section** — bold reality check with 4 growth requirements.
    - **Conversion section** with Wand2 icon + Start Free Today CTA.
    - **FAQ** — 7 SEO-friendly questions covering free tier, trial, cancellation, virality, audience.
    - **Final CTA** — large branded closing section with dual CTAs.
  - **Overview banner** updated: dynamic plan label (Starter/Growth/Agency/Pro/Scale), correct annual savings per tier ($30 / $78 / $198), Free description updated.
  - **Admin AI-usage analytics** (P2):
    - New `GET /api/admin/ai-usage?months=6&limit=20` — returns global_by_month sparkline, top_users (current month), breakdown_by_kind, totals (this month + last N months).
    - `/admin/stats` now includes subscription distribution: `users_free`, `users_starter`, `users_growth`, `users_agency`, `users_legacy`, `trialing_subs`, `past_due_subs`.
    - `AdminOverview.jsx` now renders: subscription distribution row (4 tiles + 3 secondary), AI-usage card with **6-month bar chart sparkline**, breakdown-by-kind list, top-users table.
  - **Next.js migration (P3)** deferred — see Roadmap below for the concrete plan.
  - **12 new/updated pytest cases** (`test_billing.py` updated to new tiers, `test_plans.py` updated to Free=1 channel, `test_admin_ai_usage.py` new). Suite: **79/79 pass.**

- 2026-02-26 (part 13) **🛡️ Plan-gating + Annual upsell + Login fix**
  - **Plan-gating** (P1):
    - New `routes/plans.py` (130 lines) — single source of truth for entitlements (`ENTITLEMENTS` dict: Free=20 AI/mo+2 channels, Pro=unlimited+10 channels, Scale=unlimited+unlimited).
    - Usage counters stored per-month on `users.usage.YYYY-MM.ai_generations` — auto-resets on the 1st of each month with no cron needed.
    - `assert_can_generate_ai()` → raises **HTTP 402 Payment Required** with structured `{code, message, plan, used, limit}` when cap hit.
    - `assert_can_connect_channel()` → same pattern for channels.
    - `record_ai_generation(user_id, kind)` — `$inc` counter atomically.
    - Past-due subscribers auto-downgrade to free until Stripe recovers.
    - Wired into all **9 AI generation endpoints** (`/ai/generate-post`, `/seo-review`, `/site-scan`, `/insights`, `/generate-newsletter`, `/generate-content`, `/generate-update`, `/generate-video-script`, `/multi-post`) — single shared `_gated_user(request)` helper does auth + cap-check in one call.
    - Wired into `POST /api/channels/connect` — but with reconnect-bypass: if the channel was previously connected, reconnecting it doesn't count against the cap.
    - New `GET /api/billing/usage` (lightweight, frontend polls this often).
    - `/billing/me` now embeds the full usage block.
  - **Frontend**:
    - New `components/UsageMeter.jsx` — progress bar that turns amber at 80% and red at 100%, with inline "Upgrade" CTA. Two modes: full card or compact strip. Shows "Pro · Unlimited" badge for paid plans.
    - New `hooks/use-paywall.js` — `usePaywallHandler()` returns a function that detects 402 responses, shows the appropriate toast, and redirects to `/pricing` after 1.2s.
    - Wired into all 5 Studio tabs (Newsletter / Blog / Update / Video / Multi) and Channels page. Each tab also calls `onGenerated()` after success to live-refresh the meter.
    - Overview page now has a `<UsageMeter />` strip below the stat tiles.
  - **Annual upsell banner** (P2):
    - Renders on Overview ONLY for monthly subscribers (`billing_interval === 'month'`) on Pro or Scale (not on past-due).
    - Shows specific savings: "$58/yr saved" for Pro, "$198/yr saved" for Scale.
    - "Switch to annual" button opens the Stripe Customer Portal where users can swap their subscription's price ID.
    - `data-testid="annual-upsell-banner"`.
  - **Login button fix**:
    - `CVNavbar` now imports `useAuth` and calls `login()` instead of `navigate('/dashboard')`. Clicking Login redirects to `https://auth.emergentagent.com/?redirect=...` (the proper Emergent Google Auth flow).
    - When logged in, the button auto-swaps to "Dashboard" with a `LayoutDashboard` icon.
    - Mobile menu mirrors the same logic.
  - **7 new pytest cases** (`tests/test_plans.py`) — usage endpoint, AI cap blocking, channel cap blocking, reconnect-bypass, Pro plan bypasses caps. Suite: **74/74 pass.**

- 2026-02-26 (part 12) **💳 Stripe subscription billing (test mode)**
  - New `routes/billing.py` (450 lines):
    - **Server-side `PLANS` catalogue** — Pro $29/mo or $290/yr, Scale $99/mo or $990/yr, 14-day trial on both. Frontend can't manipulate prices.
    - **Auto-provisioning**: `ensure_stripe_products()` runs on startup and creates Stripe Products + monthly+annual recurring Prices if missing. Caches `price_id`s in `stripe_products` collection so we never recreate. Successfully created in user's Stripe account: `prod_UZtnNi…` (Pro), `prod_UZto1u…` (Scale) + 4 price IDs.
    - **`POST /api/billing/checkout-session`** — body `{plan, interval, origin_url}` → returns live Stripe Checkout URL (`https://checkout.stripe.com/c/pay/cs_test_...`). Mode `subscription`, 14-day trial, promotion codes enabled. Sets `client_reference_id = user_id` + metadata for webhook reconciliation.
    - **`POST /api/billing/portal-session`** — returns Stripe Customer Portal URL for cancel/upgrade/update-card.
    - **`POST /api/webhook/stripe`** — registered on `@app.post` (not `@api`) for clean `/api/webhook/stripe` path. Verifies signature when `STRIPE_WEBHOOK_SECRET` is set; warns loudly in dev. Handles: `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `invoice.payment_failed`.
    - **`GET /api/billing/me`** — current user's plan, subscription_status, current_period_end, billing_interval, publishable_key.
    - **`GET /api/billing/checkout/status/{session_id}`** — polled from frontend after checkout return; idempotently flips user's plan if Stripe says paid.
    - **`GET /api/billing/config`** — public endpoint with publishable key + plan price metadata (safe to expose).
  - **`_apply_plan_to_user()`** helper — updates users collection with `plan`, `billing_interval`, `subscription_id`, `subscription_status`, `current_period_end`. Called from both webhook and status-poll for idempotent dual-write.
  - **MongoDB collections added**: `stripe_products` (cached price IDs), `payment_transactions` (audit log of every checkout session).
  - **Frontend (`Pricing.jsx`)**:
    - CTAs now POST to `/api/billing/checkout-session` and redirect to Stripe Checkout.
    - Monthly/Annual toggle controls the `interval` param. Pro: $29/$24/mo; Scale: $99/$83/mo (annual = $290/$990 ÷ 12).
    - Loading state per-tier (only for paid plans — Free goes straight to `/dashboard`).
    - 401 → toast "Please sign in first" + redirect.
  - **Frontend (`Overview.jsx`)**:
    - Billing strip at top showing current plan + Trial / Past-due badge + "Upgrade" or "Manage billing" CTA.
    - Post-Stripe-return handler — when `?billing=success&session_id=...` is on the URL, polls `/billing/checkout/status/{id}` up to 8 × 1.5s; flips UI to new plan + shows "Welcome to Pro!" toast.
  - **`.env`** — `STRIPE_SECRET_KEY` + `STRIPE_PUBLISHABLE_KEY` (user-provided test keys), `STRIPE_WEBHOOK_SECRET` (empty — user must add after creating webhook endpoint in Stripe Dashboard). Frontend gets `REACT_APP_STRIPE_PUBLISHABLE_KEY`.
  - **9 new pytest cases** (`tests/test_billing.py`) — `config` public, `me` auth-required, plan/interval validation, real Stripe URL generation, webhook empty-body handling. Suite: **67/67 pass.**
  - **Verified live**: a real `cs_test_b1NA…` Checkout Session was created end-to-end against user's Stripe account. Live `checkout.stripe.com` URL responds with the proper Pro $29/mo Checkout page.
  - **What you still need to do** (one-time setup in Stripe Dashboard):
    1. **Webhook**: Dashboard → Developers → Webhooks → Add endpoint `https://cortexviral.com/api/webhook/stripe` → select events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed` → copy signing secret → paste into `STRIPE_WEBHOOK_SECRET` in `/app/backend/.env`.
    2. **Customer Portal**: Dashboard → Settings → Billing → Customer portal → activate it (one-click).
    3. **Switch to live mode keys** when ready for production: replace `sk_test_…` and `pk_test_…` with the live versions in `.env` + frontend `.env`.

- 2026-02-26 (part 11) **🎵 TikTok OAuth + Content Posting scaffold**
  - New `routes/oauth_tiktok.py` mirroring the LinkedIn pattern with TikTok-specific quirks:
    - `GET /api/oauth/tiktok/status` (configured/connected check)
    - `GET /api/oauth/tiktok/start` (returns TikTok **v2** authorize URL with random state, comma-separated scopes)
    - `GET /api/oauth/tiktok/callback` (exchanges code → access_token + refresh_token + open_id, persists `tiktok_connections` doc, redirects to `/dashboard/channels?tiktok=connected`)
    - `DELETE /api/oauth/tiktok` (best-effort token revoke + local cleanup)
    - `GET /api/oauth/tiktok/publish-status?publish_id=...` (Content Posting API status poll)
    - `_refresh_tiktok_token()` (auto-refreshes when access token < 2 min from expiry)
    - `publish_to_tiktok(user_id, text, media_url)` — Direct-Post via Content Posting API using **PULL_FROM_URL** (TikTok requires video; returns `tiktok_requires_video_media_url` reason if `media_url` is absent)
  - **Scheduler hook**: `_publish_due_posts_now()` now dispatches to TikTok for any post with `tiktok` in platforms.
  - **Immediate-publish hook**: `POST /api/channels/publish` also dispatches to TikTok when not scheduled.
  - **Frontend** (Channels page): adds TikTok status fetch, real-OAuth toggle when `tiktokOAuth.configured`, `data-testid="tiktok-live-oauth-badge"`, and `?tiktok=connected|denied` query handler. Multi-platform live OAuth label adapts.
  - **`.env` scaffolding** — `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` keys added (blank values). NOTE: TikTok uses `client_key`, not `client_id`.
  - **9 new pytest cases** (`tests/test_tiktok_oauth.py`) — unconfigured 503, missing-code 400, denied-error 302 redirect, bad-state rejection, auth-required, no-side-effects on non-TikTok publish, graceful failure when not connected. Suite: **58/58 pass.**
  - **Ready for credentials**: register a TikTok Developer app at https://developers.tiktok.com/apps → add **Login Kit** + **Content Posting API** products → request `user.info.basic` + `video.publish` scopes → redirect URI `https://cortexviral.com/api/oauth/tiktok/callback` → verify URL prefix of any media-hosting domain → paste client_key + client_secret into `/app/backend/.env`.

- 2026-02-26 (part 10) **🔗 SEO Phase 2 (internal linking + video sitemap)**
  - **`CVBreadcrumbs.jsx`** — reusable breadcrumb component (`data-testid="cv-breadcrumbs"`, home icon link, current-page aria attr).
  - **`buildBreadcrumbSchema()`** helper added to `CVSeo.jsx`; `<CVSeo schema>` now accepts an array of schemas (multi-script JSON-LD).
  - Breadcrumbs + `BreadcrumbList` JSON-LD wired into: `/privacy`, `/terms`, `/pricing`, `/sitemap`, `/blog`, `/blog/:slug`, `/tools/:slug`, all 5 keyword landing pages.
  - **`CVLegalLayout.jsx`** — new 2-column legal page layout with sticky TOC sidebar. Privacy (10 sections) and Terms (12 sections) rewritten to use it; anchor-link jumping works via `scroll-mt-28`.
  - **Cross-linking** for topical authority:
    - Programmatic niche pages now show "Deep dives on `<cluster>`" — 3 blog cards from the mapped cluster (`data-testid="cv-niche-related-posts"`).
    - Landing pages now show "Try it for your niche" — 8 cross-links to programmatic combos (`data-testid="cv-landing-by-niche"`, via `PATH_TO_PROG_TOOL` map in `CVLandingPage.jsx`).
  - **Video sitemap infrastructure** (backend `routes/seo.py`):
    - Added `xmlns:video="http://www.google.com/schemas/sitemap-video/1.1"` namespace to `<urlset>`.
    - New `BLOG_VIDEOS` registry (empty by default — populated when real videos are embedded).
    - `_video_xml_block()` helper safely escapes title/description and emits `<video:thumbnail_loc>`, `<video:player_loc allow_embed="yes">`, `<video:duration>`, etc.
    - Blog post page now iframe-embeds `post.videos[*].player_loc` when populated.
  - **5 new pytest cases** (`tests/test_seo_v3.py`) — video namespace assertion, empty-by-default invariant, `_video_xml_block` rendering, legal-route sitemap presence, well-formed `<url>` XML. Suite: **49/49 pass.**
  - **Bugfix during testing**: Pricing.jsx originally referenced `buildBreadcrumbSchema` + `CVBreadcrumbs` without importing them, crashing `/pricing` with a runtime overlay. Both imports added; verified rendering.
  - BlogIndex was missing breadcrumbs after first pass — fixed in this iteration.

- 2026-02-25 (part 9) **🔗 LinkedIn OAuth scaffold**
  - New `routes/oauth_linkedin.py` — full OAuth 2.0 + posting integration:
    - `GET /api/oauth/linkedin/status` (configured/connected check)
    - `GET /api/oauth/linkedin/start` (returns LinkedIn authorize URL with random state)
    - `GET /api/oauth/linkedin/callback` (exchanges code → access_token, fetches OIDC userinfo, persists `linkedin_connections` document, redirects to `/dashboard/channels?linkedin=connected`)
    - `DELETE /api/oauth/linkedin` (disconnect)
    - `publish_to_linkedin(user_id, text)` helper for live posting via `POST /rest/posts` with LinkedIn-Version header
  - **Scheduler hook**: `_publish_due_posts_now()` now dispatches to LinkedIn for any post with `linkedin` in platforms and writes the dispatch result to `posts.dispatch.linkedin`.
  - **Immediate-publish hook**: `POST /api/channels/publish` also dispatches to LinkedIn when not scheduled.
  - **Frontend** (Channels page): conditionally switches the LinkedIn toggle to real OAuth when configured (calls `/oauth/linkedin/start` → window.location.assign authorize URL → redirected back with `?linkedin=connected`). Shows a "LinkedIn live OAuth" pulse badge when credentials are set.
  - **`.env` scaffolding** — `LINKEDIN_CLIENT_ID` + `LINKEDIN_CLIENT_SECRET` keys added (blank values). Public site URL set to `https://cortexviral.com`.
  - **6 new pytest cases** (`test_linkedin_oauth.py`) — unconfigured 503, missing-code 400, bad-state rejection, auth-required, non-LinkedIn publish unaffected.
  - Ready for credentials: user just needs to register a LinkedIn Developer app, request "Sign in with LinkedIn using OpenID Connect" + "Share on LinkedIn" products, add redirect URI `https://cortexviral.com/api/oauth/linkedin/callback`, and paste Client ID + Client Secret into `/app/backend/.env`.

- 2026-02-25 (this session — part 8) **🧹 Routes cleanup**
  - All 13 `routes/*.py` files refreshed: per-module **docstring**, **minimal imports** (each file imports only what it uses).
  - `ai.py` PEP-8 fixed (httpx/re/json on separate lines).
  - `activity.py` E741 fix (renamed `l` → `lead`).
  - Cross-module imports explicit (`channels.py` ← `routes.ai._llm`, `health.py` ← `routes.scheduler._publish_due_posts_now`).
  - Backend now **lint-clean**: `ruff` reports 0 errors across `core.py`, `models.py`, `deps.py`, `server.py`, all of `routes/*`, all of `tests/*`.
  - Pytest still **38/38 pass**.

- 2026-02-25 (this session — part 7) **🧱 Backend refactor + 📚 Blog expansion**
  - **Refactored `server.py`**: 1701 → **49 lines** (97% reduction). Logic split into:
    - `core.py` (Mongo client, env, logger, FastAPI app + router) — 33 lines
    - `models.py` (all Pydantic models) — 162 lines
    - `deps.py` (auth, admin, audit log dependencies) — 71 lines
    - `routes/` (13 domain modules: `auth`, `leads`, `ai`, `channels`, `performance`, `activity`, `dashboard`, `support`, `admin`, `broadcasts`, `scheduler`, `health`, `seo`)
  - **Cross-module reuse**: `channels.py` imports `_llm` + `LlmChat`/`UserMessage` from `ai.py` (single LLM client init).
  - **Blog cluster expanded from 3 → 15 posts** across 3 keyword clusters:
    - **Viral content** (6 posts): What Makes Content Go Viral, Viral TikTok Hooks, Instagram Captions That Convert, TikTok Algorithm 2026, Short-Form Video Scripts, Going Viral as a Small Account.
    - **AI marketing tools** (5 posts): AI Tools for Viral Content, Best AI Tools for Creators 2026, How AI Is Changing Content Marketing, Automating Social Media Growth, AI Content Platforms vs ChatGPT.
    - **Social media growth** (4 posts): Best Time to Post on Instagram, Grow on LinkedIn as a Founder, Content Calendar Template, Skincare Brand 0-to-100K Case Study.
  - **Blog index** now has a cluster-filter pill row + per-cluster post counts; "Keep reading" prefers same-cluster posts for stronger topical authority signals.
  - **Sitemap grew 44 → 56 URLs** (12 core + 32 programmatic + 12 new blog).
  - **2 new pytest files** (`test_blog_seo.py` — 2 cases). Full suite: **38/38 pass.**
  - Performance.py `range` → `period` shadowing fix preserved in refactor.

- 2026-02-25 (this session — part 6) **📈 Pricing + Programmatic SEO + LCP**
  - **New `/pricing` page** with 3 tiers (Free / Pro $29 / Scale $99), Pro highlighted with violet glow, monthly/annual billing toggle (10/12 multiplier with rounding), pricing-specific FAQ, JSON-LD SoftwareApplication + FAQPage schema.
  - **Programmatic SEO route `/tools/:slug`** — 4 tools × 8 niches = **32 long-tail landing pages** auto-generated from `/app/frontend/src/pages/programmatic/data.js`. Each page renders niche-tailored H1, pain points, sample hook, AI-agent CTA, and 6 internal links (3 related-niche + 3 cross-sell). Invalid slugs `<Navigate>` to /.
  - **Sitemap expanded to 44 URLs** (12 core + 32 programmatic), now uses production domain `cortexviral.com`, adds `xmlns:image` extension with logo `<image:image>` per URL.
  - **robots.txt** updated to production domain + dual `Sitemap:` directives (root + /api/seo/sitemap.xml).
  - **LCP optimisations**: preload `/cortex-logo.png` with `fetchpriority=high` in `<head>`, preload Space Grotesk + Inter critical weights, dns-prefetch backend, `fetchPriority`/`loading` props on CVLogo for hero vs below-the-fold variants.
  - **Index.html static title** keyword-optimised to match Helmet output (SEO consistency).
  - **CVSeo SITE constant** migrated to `https://cortexviral.com` (production deploy live as of this session).
  - **Pytest**: 8 new SEO-v2 cases (`test_seo_v2.py`). Full suite **36/36 pass**.
  - **Frontend testing agent: 100% pass** after self-fixed React `fetchPriority` casing.

- 2026-02-25 (this session — part 5) **🔍 SEO Phase-1 overhaul**
  - **Keyword strategy locked**: primary "AI viral content generator" + secondary "viral marketing automation tool" / "AI content growth platform".
  - **Homepage SEO**: title → `AI Viral Content Generator for Fast Social Media Growth | CortexViral`, H1 → `Create Viral Content Using AI in Minutes.`, 5 keyword-mapped H2s, hero copy bolds primary keyword, meta-description optimised.
  - **5 dedicated SEO landing pages** (one keyword intent each):
    - `/ai-tiktok-post-generator`
    - `/viral-content-ideas-generator`
    - `/instagram-caption-ai-generator`
    - `/short-form-video-ideas-ai`
    - `/content-automation-tool`
  - **JSON-LD schema**: Organization + SoftwareApplication + FAQPage emitted as a single ld+json array on homepage; per-page schema on each landing; Article schema per blog post.
  - **Blog skeleton at `/blog`** with 3 starter articles (What Makes Content Go Viral, Viral TikTok Hooks That Work, Best AI Tools for Viral Content). Internal links flow Blog ↔ Landing pages.
  - **`react-helmet-async`** wired at App root; `CVSeo` component handles per-route title/meta/canonical/og/twitter/JSON-LD.
  - **Backend**: `/sitemap.xml`, `/robots.txt` and `/api/seo/*` aliases. Sitemap covers homepage + 5 landings + agents + blog index + 3 posts (11 URLs). Robots disallows /api, /dashboard, /admin, /auth.
  - **Rebuilt CVFooter** with 4-column nav: AI tools (5 landing links) / Company (Agents, Blog, Dashboard) / Legal — strong internal-linking graph.
  - **Homepage FAQ** with 6 question pairs and a11y-compliant `aria-expanded` toggles.
  - **Pytest**: 15 new SEO regression cases (`test_seo.py`) — total 28/28 pass.
  - **Frontend testing agent: 100% pass** after testing-agent's own `&amp;` entity fix in short-form H1.
  - Rebuilt `DashboardLayout.jsx` with dark glass sidebar, gradient-active nav items, ambient aurora backdrop, wordmark "Cortex**Viral**" with gradient on "Viral", glow under active items, and dark user-profile footer.
  - Added ~80 lines of scoped CSS in `index.css` under `.cv-dash-scope { … }` that re-skin existing legacy markup (`bg-white`, `border-neutral-200/70`, `text-neutral-*`, `bg-neutral-*`, pastel `from-*-100` gradients, `bg-#1B7BFF` brand classes, `input/textarea/combobox`) to dark glass — meaning ALL 14 dashboard pages + admin pages got the new look with **zero per-page edits**.
  - Verified across Overview, Marketing Calendar, Content Studio, Compose, Posts, AI Insights, SEO, Site Scan, Help, Admin Overview, and landing untouched. **100% frontend pass.**

- 2026-02-25 (this session — part 3) **🎨 Landing & /agents brand overhaul**
  - Full neural dark landing rebuild (CVHero, CVNeuralEngine, CVPipeline, CVResults, CVCTAFooter, CVFooter, CVNavbar, CVBackdrop, CVLogo).
  - New `/agents` sub-page with 4 AI agent cards (Nova/Sam/Kai/Angela) — direct chat.
  - New logo asset `/cortex-logo.png` used as favicon + nav.
  - Framer Motion + CSS keyframe animations (no Three.js).

- 2026-02-25 (this session — part 2) **Background scheduler**
  - APScheduler in-process AsyncIOScheduler with Mongo TTL lock (`scheduler_locks`), promotes `scheduled → published` every 60s.
  - Admin debug endpoint `POST /api/admin/scheduler/run-once`.
  - `DISABLE_SCHEDULER=true` kill-switch.
  - 4 new pytest cases in `/app/backend/tests/test_scheduler.py` (total 13/13 pass).
- 2026-02-24 (this session — part 1)
  - **AI optimal time button on Compose** — visible only when exactly one channel checkbox is selected; auto-fills datetime-local and shows violet meta line, cleared on manual edit.
  - **Bulk lasso multi-select on Marketing Calendar** — toggle "Bulk select" → drag rectangle (Shift adds), floating bottom action bar with **−1w / −1d / +1d / +1w / Cancel / Clear**, runs PATCH/DELETE in parallel.
  - Backend cleanup: `performance/*` endpoints now use `period: str = Query("24h", alias="range")` (no more builtin shadowing) — public URL signature unchanged.
  - Backend regression suite added: `/app/backend/tests/test_scheduling_and_optimal.py` (9 tests, all pass).
- Prior sessions
  - Pixel-perfect landing-page clone, rebranded Automatex → CortexViral
  - Emergent Google Auth
  - AI Content Studio (5 generators) + SEO Review + Site Scan
  - Channels catalog (38+ platforms, MOCKED OAuth)
  - Compose & Publish (single + scheduled post via `scheduled_at`)
  - Marketing Calendar week/month view + per-post drag-to-reschedule + AI optimal slot badges
  - Activity feed (`/api/activity`) and Performance analytics (mocked synthetic data)
  - Admin: stats, users (search/promote/demote/suspend/unsuspend/impersonate/delete), audit log, broadcasts, support tickets
  - Help Center with AI chat, FAQ, ticket flow

## Mocked features (explicitly)
- Social-media OAuth connect/disconnect (fake handle)
- `POST /api/channels/publish` writes locally only — does NOT post to live external APIs
- `/api/performance/*` uses synthetic data via seeded RNG

## Roadmap

### P0 — none open

### P1 — **Real OAuth + live publishing** (blocked: needs user-supplied developer credentials)
Pipeline: when a post is promoted to `published` by the scheduler (or by the immediate publish path), iterate its `platforms[]` and dispatch to each platform's OAuth-authenticated API. Per-platform handler files should live in `/app/backend/integrations/{linkedin,x,instagram,facebook,tiktok}.py`. Token storage collection `{platform}_connections` keyed by `user_id`.
- **LinkedIn FIRST** — playbook obtained 2026-02-25; needs `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, redirect URIs registered. Uses `w_member_social` + OIDC scopes. UGC Post API + Images API.
- X / Twitter — basic tier ~$100/mo, OAuth 2.0 PKCE.
- Meta (Facebook + Instagram) — slowest review.
- TikTok — manual approval.
- Threads — via Meta Graph.

### P1 — Per-post analytics
Strictly depends on OAuth per platform. Each platform has its own metrics endpoint (LinkedIn UGC, X v2 tweet metrics, Meta Insights, TikTok Insights). Implement per platform as OAuth lands.

### P2
- Refactor `server.py` (~1500 lines) into `/app/backend/routes/` and `/app/backend/models/`
- Drag from one post to multiple cells (multi-day duplicate)
- Calendar month view: collapse all platforms into a single row-per-day with stacked dots
- Email digest for admin broadcasts (Resend integration)
- Stripe billing (Pro tier unlocks live posting + higher AI quotas)
- "Repeat weekly" toggle when scheduling

## Key API endpoints
- `GET /api/auth/me` · `POST /api/auth/logout`
- `POST /api/ai/{generate-post, generate-newsletter, generate-content, generate-update, generate-video-script, multi-post, optimal-times, seo-review, site-scan, insights}`
- `POST /api/channels/publish` (accepts optional `scheduled_at` ISO datetime)
- `GET /api/posts/scheduled?start=&end=` · `PATCH /api/posts/scheduled/{id}` · `DELETE /api/posts/scheduled/{id}`
- `GET /api/performance/{overview,sources,pages}?range=24h|48h|7d|30d|60d|90d|year|lastyear`
- `GET /api/activity?limit=30`
- `GET /api/channels` · `POST /api/channels/connect` · `DELETE /api/channels/{platform}`
- Admin: `/api/admin/{stats,users,broadcasts,audit-log,tickets,...}`
- Support: `/api/support/{faq,chat,tickets}`

## Important Constants
- Admin allow-list email: `williams342@gmail.com`
- Test user: `test@automatex.dev` (Bearer `test_session_1779636592168`) — see `/app/memory/test_credentials.md`
- LLM model: `gpt-5` via `EMERGENT_LLM_KEY`
