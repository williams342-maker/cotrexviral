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
- 2026-02 (this session)
  - **AI optimal time button on Compose** — visible only when exactly one channel checkbox is selected; auto-fills datetime-local and shows violet meta line, cleared on manual edit
  - **Bulk lasso multi-select on Marketing Calendar** — toggle "Bulk select" → drag rectangle (Shift adds), floating bottom action bar with **−1w / −1d / +1d / +1w / Cancel / Clear**, runs PATCH/DELETE in parallel
  - Backend cleanup: `performance/*` endpoints now use `period: str = Query("24h", alias="range")` (no more builtin shadowing) — public URL signature unchanged
  - Backend regression suite added: `/app/backend/tests/test_scheduling_and_optimal.py` (9 tests, all pass)
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

### P1
- **Real OAuth + publishing** for Instagram / X / LinkedIn / TikTok / Facebook / YouTube / Threads / Pinterest (blocked: needs user-supplied developer credentials)
- Background scheduler/cron to flip `status: scheduled → published` and (post-OAuth) push to live APIs at `scheduled_at`
- Per-post analytics (views, likes, CTR) once real OAuth is connected

### P2
- Refactor `server.py` into `/app/backend/routes/` and `/app/backend/models/`
- Drag from one post to multiple cells (multi-day duplicate)
- Calendar month view: collapse all platforms into a single row-per-day with stacked dots
- Email digest for admin broadcasts (Resend integration)
- Stripe billing (Pro tier unlocks live posting + higher AI quotas)

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
