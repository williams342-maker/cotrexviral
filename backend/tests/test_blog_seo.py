"""Regression test: verify all 15 blog post URLs are present in the sitemap."""
import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]

EXPECTED_BLOG_SLUGS = [
    "what-makes-content-go-viral-2026",
    "viral-tiktok-hooks-that-work",
    "ai-tools-for-viral-content-creation",
    "how-to-write-instagram-captions-that-convert",
    "tiktok-algorithm-2026-explained",
    "short-form-video-scripts-that-work",
    "going-viral-as-a-small-account",
    "best-ai-tools-for-creators-2026",
    "how-ai-is-changing-content-marketing",
    "automating-social-media-growth-with-ai",
    "ai-content-platforms-vs-chatgpt",
    "best-time-to-post-on-instagram-2026",
    "how-to-grow-on-linkedin-as-a-founder",
    "content-calendar-for-small-businesses",
    "case-study-skincare-brand-zero-to-100k",
]


def test_all_15_blog_posts_in_sitemap():
    r = httpx.get(f"{API_URL}/api/seo/sitemap.xml", timeout=10)
    r.raise_for_status()
    body = r.text
    missing = [slug for slug in EXPECTED_BLOG_SLUGS if f"/blog/{slug}" not in body]
    assert not missing, f"missing blog slugs in sitemap: {missing}"
    # Sanity: total page <loc> entries should be at least 56
    assert len(re.findall(r"<url>\s*\n\s*<loc>", body)) >= 56


def test_blog_paths_use_production_domain():
    r = httpx.get(f"{API_URL}/api/seo/sitemap.xml", timeout=10)
    body = r.text
    for slug in EXPECTED_BLOG_SLUGS:
        assert f"https://cortexviral.com/blog/{slug}" in body
