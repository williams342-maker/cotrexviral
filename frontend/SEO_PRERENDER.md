# SEO Prerendering — react-snap

CRA + CRACO doesn't server-side-render by default — Googlebot, social-share
crawlers, and many AI bots get a near-empty `<div id="root">` shell on first
load. This script generates a fully-rendered static HTML file for every
public SEO route at build time so they don't have to wait for hydration.

## Routes prerendered (~63 pages)

| Group | Count | Examples |
|---|---|---|
| Core | 7 | `/`, `/pricing`, `/agents`, `/blog`, `/privacy`, `/terms`, `/sitemap` |
| AI tool landings | 5 | `/ai-tiktok-post-generator`, `/viral-content-ideas-generator`, … |
| Niche programmatic | 32 | `/tools/viral-content-ideas-for-fitness-coaches`, … |
| Blog posts | 12 | `/blog/what-makes-content-go-viral`, … |
| Static | 2 | `/200.html`, `/404.html` (CRA fallbacks) |

Dashboard / admin / authenticated pages are deliberately **not** prerendered.

## How to run it

```bash
cd /app/frontend
yarn build:seo
```

Output goes to `build/`. Every route becomes a real `<route>/index.html`
with the full React-rendered DOM, JSON-LD blocks, and meta tags inlined.
Static assets (JS / CSS bundles) are untouched.

## Production deploys

The default `yarn build` is **unchanged** — it still just runs CRACO with
no prerender step. To turn on prerendering for production deploys, swap
the deploy command in Emergent's deploy config (or your hosting platform):

```diff
- yarn build
+ yarn build:seo
```

The prerender adds ~30 seconds to the build (one headless-Chrome page load
per route). Output `build/` shape is identical to a plain CRA build, so no
hosting changes are needed.

## Why react-snap and not Next.js?

- Zero changes to the React app — same React Router, same dev server,
  same dependencies. A Next.js migration would touch ~200 files.
- Static HTML on disk is the cheapest, most cacheable form of SEO. No
  server-rendering cost at request time, no cold-starts.
- React still hydrates client-side after first paint, so all interactivity
  (modal open, Stripe checkout, dashboard nav) works exactly as before.

## Caveats

- **Trade-off**: the JS bundle still loads after first paint; we just send
  the rendered HTML earlier. Interactive Largest Contentful Paint barely
  changes; Bot-visible content goes from empty to full.
- **Trade-off**: any per-request data (e.g. `Bearer` API calls during
  render) won't show in the static HTML. None of our SEO routes make
  authenticated calls, so this is fine.
- **Trade-off**: the `react-snap` package is unmaintained (last release
  2020). It works fine against our current CRA setup, but if a future
  CRA/CRACO upgrade breaks it, the fallback is to write a tiny custom
  prerender script using Playwright (already available on the host).

## Config location

See the `reactSnap` key in `package.json`. Key settings:

```json
"reactSnap": {
  "inlineCss": false,
  "puppeteerExecutablePath": "/usr/bin/google-chrome",
  "puppeteerArgs": ["--no-sandbox", "--disable-setuid-sandbox"],
  "skipThirdPartyRequests": true,
  "crawl": true,
  "include": [ "/", "/pricing", … ]
}
```

`skipThirdPartyRequests: true` blocks the VisitTracker ping and any other
backend call during render — keeps prerender deterministic and bot-safe.
