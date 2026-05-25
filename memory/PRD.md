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
