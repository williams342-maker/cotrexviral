"""SEO endpoints: sitemap.xml + robots.txt (root paths + /api/seo aliases).

The sitemap is composed of three sections:
  1. Static SEO landing + cluster paths (SEO_LANDING_PATHS)
  2. Programmatic SEO combinations (4 tools × 8 niches)
  3. Optional Video Sitemap entries (BLOG_VIDEOS) — populated when a blog
     post embeds a YouTube/Vimeo/etc. clip. Leave empty if no real videos
     are embedded yet (fabricated entries can hurt SEO).
"""
from datetime import datetime, timezone

from fastapi import Response

from core import app
import os
from xml.sax.saxutils import escape as xml_escape


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
    ("/roadmap", "0.8", "weekly"),
    ("/ai-tiktok-post-generator", "0.9", "weekly"),
    ("/viral-content-ideas-generator", "0.9", "weekly"),
    ("/instagram-caption-ai-generator", "0.9", "weekly"),
    ("/short-form-video-ideas-ai", "0.9", "weekly"),
    ("/content-automation-tool", "0.9", "weekly"),
    ("/agents", "0.7", "monthly"),
    ("/privacy", "0.3", "yearly"),
    ("/terms", "0.3", "yearly"),
    ("/data-deletion", "0.3", "yearly"),
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
    ("/blog/building-an-ai-marketing-platform-2026", "0.7", "monthly"),
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


# -----------------------------------------------------------------------------
# VIDEO SITEMAP
# -----------------------------------------------------------------------------
# Map: blog-post path → list of embedded videos. Each video MUST be a real,
# publicly-watchable URL that is also visibly embedded on the page itself —
# Googlebot validates the page content. Empty by default; populate as the
# team uploads/embeds explainer videos.
#
# Schema per entry:
#   {
#     "title": "...",          # required
#     "description": "...",    # required
#     "thumbnail_loc": "...",  # required (absolute URL)
#     "content_loc": "...",    # optional (.mp4 etc.)
#     "player_loc": "...",     # required if no content_loc (YouTube embed URL)
#     "duration": 90,          # optional (seconds)
#     "publication_date": "2026-02-25T10:00:00+00:00",  # optional
#   }
BLOG_VIDEOS: dict[str, list[dict]] = {
    # Example (commented):
    # "/blog/viral-tiktok-hooks-that-work": [
    #     {
    #         "title": "10 Viral TikTok Hooks Explained in 60 Seconds",
    #         "description": "CortexViral's hook engineer breaks down the 10 hook patterns driving the most viral views in 2026.",
    #         "thumbnail_loc": "https://cortexviral.com/videos/hooks-thumb.jpg",
    #         "player_loc": "https://www.youtube.com/embed/EXAMPLE",
    #         "duration": 62,
    #         "publication_date": "2026-02-18T10:00:00+00:00",
    #     },
    # ],
}


def _video_xml_block(video: dict) -> str:
    """Render a single <video:video> child element."""
    parts = [
        f"    <video:thumbnail_loc>{xml_escape(video['thumbnail_loc'])}</video:thumbnail_loc>",
        f"    <video:title>{xml_escape(video['title'])}</video:title>",
        f"    <video:description>{xml_escape(video['description'])}</video:description>",
    ]
    if video.get("content_loc"):
        parts.append(f"    <video:content_loc>{xml_escape(video['content_loc'])}</video:content_loc>")
    if video.get("player_loc"):
        parts.append(
            f'    <video:player_loc allow_embed="yes">{xml_escape(video["player_loc"])}</video:player_loc>'
        )
    if video.get("duration"):
        parts.append(f"    <video:duration>{int(video['duration'])}</video:duration>")
    if video.get("publication_date"):
        parts.append(f"    <video:publication_date>{video['publication_date']}</video:publication_date>")
    inner = "\n".join(parts)
    return f"    <video:video>\n{inner}\n    </video:video>"


def _build_sitemap_xml() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url_blocks = []
    for path, priority, freq in SEO_LANDING_PATHS:
        video_blocks = ""
        if path in BLOG_VIDEOS and BLOG_VIDEOS[path]:
            video_blocks = "\n" + "\n".join(_video_xml_block(v) for v in BLOG_VIDEOS[path])
        url_blocks.append(
            f"  <url>\n"
            f"    <loc>{SITE_URL}{path}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{freq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"    <image:image>\n"
            f"      <image:loc>{SITE_URL}/cortex-logo.png</image:loc>\n"
            f"      <image:title>CortexViral — AI viral content generator</image:title>\n"
            f"    </image:image>"
            f"{video_blocks}\n"
            f"  </url>"
        )
    urls = "\n".join(url_blocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"\n'
        '        xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">\n'
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
