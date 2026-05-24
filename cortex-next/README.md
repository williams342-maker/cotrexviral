# CortexViral Next.js Migration — Phase 1

This directory contains the **Phase 1 Next.js scaffold** for migrating CortexViral's public marketing/SEO surfaces to true server-side rendering (SSR).

## Why migrate?

The current React SPA (`/app/frontend/`) renders everything client-side. While `react-helmet-async` injects SEO tags into the initial HTML, **Google's renderer still has to execute JavaScript** to see the page body. This works, but:

- **Slower indexing**: programmatic pages (`/tools/*`, `/blog/*`) take days-to-weeks to be indexed.
- **No streaming SEO content** to crawlers — they need to wait for the JS bundle.
- **Risk of incomplete indexing** when Google's renderer hits a JS error.

Next.js Server Components (with the App Router) render the marketing/SEO pages on the server, ship pre-rendered HTML, and only hydrate where needed.

## Architecture

```
[ User / Crawler ] → cortexviral.com
        ↓
   Vercel / Next.js host
   ├─ /              → SSR Next.js (landing, marketing, blog, tools, pricing, privacy, terms, sitemap)
   ├─ /api/*         → proxied to FastAPI backend (Kubernetes pod)
   └─ /dashboard/*   → proxied to existing React SPA (Kubernetes pod) OR ported in Phase 2
```

## Phase rollout

### ✅ Phase 1A (this scaffold)
- Next.js 14+ project init with App Router + TypeScript + Tailwind
- Port `/` (landing page) as the proof-of-concept SSR surface
- Set up `next.config.js` proxying:
   - `/api/*` → FastAPI backend
   - `/dashboard/*` → existing React SPA (interim)
- Shared design tokens (Tailwind config matches CortexViral dark theme)
- Mirror the most-used CV components (CVNavbar, CVFooter, CVBackdrop) as React Server Components

### 🚧 Phase 1B (next session)
Port these public pages to Next.js, one by one:
- [ ] `/pricing` — Server Component + client-side checkout button
- [ ] `/privacy` and `/terms` — Server Components (static text)
- [ ] `/sitemap` (the human one — not the XML)
- [ ] `/blog` index + `/blog/[slug]` (Markdown / posts.js → MDX)
- [ ] `/tools/[combo]` — programmatic SEO pages (huge SEO win)
- [ ] 5 keyword landing pages (`/ai-tiktok-post-generator`, etc.)

### 📋 Phase 2 (separate session)
- Port `/dashboard/*` (currently 14 SPA pages) — bigger lift, can stay SPA-only longer.
- Or keep dashboard as SPA and just proxy. Both work.

### 🚀 Phase 3 (deployment)
- Push Next.js to Vercel (free tier OK for early stage).
- Update DNS so `cortexviral.com` → Vercel.
- Keep FastAPI on its current Emergent pod.
- `/dashboard/*` proxied (Phase 1) or fully ported (Phase 2).

## Local development

```bash
cd /app/cortex-next
yarn install
yarn dev   # → http://localhost:3001
```

## What's stable already (do not touch)
- `/app/backend/` — FastAPI + all routes. Phase-1 scaffold proxies to it.
- `/app/frontend/` — current React SPA. Stays live until Phase 2 ports it.
- The XML sitemap (`/api/seo/sitemap.xml`) — already SSR-rendered by the backend.

## Next.js Phase 1A status

| Surface | Status |
|---|---|
| `next.config.js` + Tailwind | ✅ |
| Root layout + dark theme | ✅ |
| Homepage SSR `/` | ✅ |
| `/api/*` proxy to FastAPI | ✅ |
| `/dashboard/*` proxy to SPA | ✅ |
| Pricing | ⏳ Phase 1B |
| Blog index / posts | ⏳ Phase 1B |
| Programmatic `/tools/*` | ⏳ Phase 1B |

## Why this scaffold isn't running by default

This directory is **opt-in**. The current production stack is unchanged:
- `cortexviral.com` still serves the React SPA via Emergent's pod.
- This Next.js project is a **future deployment target**, not currently behind the prod URL.

To activate it in production, you'll need to:
1. Run `yarn install && yarn build` in `/app/cortex-next/`.
2. Deploy to Vercel (or Next.js standalone) and point DNS.
3. Decommission the SPA's marketing routes (keep the dashboard route group).

I deliberately did **not** wire this into supervisor — switching production hosts is your decision, not a code-level change.
