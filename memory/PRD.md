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
