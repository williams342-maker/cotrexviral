"""SEO endpoints: sitemap.xml + robots.txt (root paths + /api/seo aliases)."""
from datetime import datetime, timezone

from fastapi import Response

from core import app
import os


# These must live at the site root for search engines. The Kubernetes ingress
# routes non-/api paths to the frontend by default, so we expose them via
# /api/seo/* and ALSO mount aliases at /robots.txt and /sitemap.xml. The
# frontend `_redirects` (or ingress rules) should rewrite the root paths to
# these backend endpoints; in this preview pod both /robots.txt and
# /sitemap.xml are caught by the frontend SPA fallback, so search engines
# crawl the /api/seo aliases linked from the HTML head as fallback.

SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://cortexviral.com")

SEO_LANDING_PATHS = [
    ("/", "1.0", "weekly"),
    ("/pricing", "0.95", "weekly"),
    ("/ai-tiktok-post-generator", "0.9", "weekly"),
    ("/viral-content-ideas-generator", "0.9", "weekly"),
    ("/instagram-caption-ai-generator", "0.9", "weekly"),
    ("/short-form-video-ideas-ai", "0.9", "weekly"),
    ("/content-automation-tool", "0.9", "weekly"),
    ("/agents", "0.7", "monthly"),
    ("/privacy", "0.3", "yearly"),
    ("/terms", "0.3", "yearly"),
    ("/sitemap", "0.4", "monthly"),
    ("/blog", "0.8", "weekly"),
    # ----- Cluster: viral content -----
    ("/blog/what-makes-content-go-viral-2026", "0.7", "monthly"),
    ("/blog/viral-tiktok-hooks-that-work", "0.7", "monthly"),
    ("/blog/how-to-write-instagram-captions-that-convert", "0.7", "monthly"),
    ("/blog/tiktok-algorithm-2026-explained", "0.7", "monthly"),
    ("/blog/short-form-video-scripts-that-work", "0.7", "monthly"),
    ("/blog/going-viral-as-a-small-account", "0.7", "monthly"),
    # ----- Cluster: AI marketing tools -----
    ("/blog/ai-tools-for-viral-content-creation", "0.7", "monthly"),
    ("/blog/best-ai-tools-for-creators-2026", "0.7", "monthly"),
    ("/blog/how-ai-is-changing-content-marketing", "0.7", "monthly"),
    ("/blog/automating-social-media-growth-with-ai", "0.7", "monthly"),
    ("/blog/ai-content-platforms-vs-chatgpt", "0.7", "monthly"),
    # ----- Cluster: social media growth -----
    ("/blog/best-time-to-post-on-instagram-2026", "0.7", "monthly"),
    ("/blog/how-to-grow-on-linkedin-as-a-founder", "0.7", "monthly"),
    ("/blog/content-calendar-for-small-businesses", "0.7", "monthly"),
    ("/blog/case-study-skincare-brand-zero-to-100k", "0.7", "monthly"),
]

# Programmatic SEO: 4 tools × 8 niches = 32 long-tail landing pages.
# Must stay in sync with /app/frontend/src/pages/programmatic/data.js.
_PROG_TOOLS = [
    "instagram-caption-generator",
    "tiktok-script-generator",
    "viral-content-ideas",
    "linkedin-post-generator",
]
_PROG_NICHES = [
    "fitness-coaches",
    "real-estate",
    "saas-founders",
    "e-commerce-brands",
    "restaurants",
    "beauty-creators",
    "consultants",
    "agencies",
]
for _t in _PROG_TOOLS:
    for _n in _PROG_NICHES:
        SEO_LANDING_PATHS.append((f"/tools/{_t}-for-{_n}", "0.6", "monthly"))


def _build_sitemap_xml() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = "\n".join(
        f"  <url>\n"
        f"    <loc>{SITE_URL}{path}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"    <image:image>\n"
        f"      <image:loc>{SITE_URL}/cortex-logo.png</image:loc>\n"
        f"      <image:title>CortexViral — AI viral content generator</image:title>\n"
        f"    </image:image>\n"
        f"  </url>"
        for path, priority, freq in SEO_LANDING_PATHS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        f"{urls}\n"
        "</urlset>\n"
    )


def _build_robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
        f"Sitemap: {SITE_URL}/api/seo/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
async def sitemap_xml():
    return Response(content=_build_sitemap_xml(), media_type="application/xml")


@app.get("/robots.txt")
async def robots_txt():
    return Response(content=_build_robots_txt(), media_type="text/plain")


# Aliases under /api/seo so the ingress routes them to the backend even if
# the SPA fallback intercepts the root-level paths. Registered on `app`
# directly (not the api router, which is already included above).
@app.get("/api/seo/sitemap.xml")
async def api_sitemap_xml():
    return Response(content=_build_sitemap_xml(), media_type="application/xml")


@app.get("/api/seo/robots.txt")
async def api_robots_txt():
    return Response(content=_build_robots_txt(), media_type="text/plain")
