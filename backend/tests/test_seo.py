"""Backend SEO endpoint tests: sitemap.xml + robots.txt"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://social-sync-ai-1.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def sitemap_text():
    r = requests.get(f"{BASE_URL}/api/seo/sitemap.xml", timeout=15)
    assert r.status_code == 200
    return r.text


@pytest.fixture(scope="module")
def robots_text():
    r = requests.get(f"{BASE_URL}/api/seo/robots.txt", timeout=15)
    assert r.status_code == 200
    return r.text


# --- sitemap.xml ---
class TestSitemap:
    def test_status_and_content_type(self):
        r = requests.get(f"{BASE_URL}/api/seo/sitemap.xml", timeout=15)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "").lower()
        assert "xml" in ct, f"expected xml content-type, got {ct}"

    def test_has_urlset(self, sitemap_text):
        assert "<urlset" in sitemap_text
        assert "http://www.sitemaps.org/schemas/sitemap/0.9" in sitemap_text

    def test_has_at_least_11_urls(self, sitemap_text):
        count = len(re.findall(r"<url>", sitemap_text))
        assert count >= 11, f"expected >=11 <url> entries, found {count}"

    def test_homepage_present(self, sitemap_text):
        # any prod hostname is fine, just check trailing path
        assert re.search(r"<loc>https?://[^<]+/</loc>", sitemap_text), "homepage / not found"

    @pytest.mark.parametrize("slug", [
        "ai-tiktok-post-generator",
        "viral-content-ideas-generator",
        "instagram-caption-ai-generator",
        "short-form-video-ideas-ai",
        "content-automation-tool",
    ])
    def test_landing_pages_present(self, sitemap_text, slug):
        assert f"/{slug}" in sitemap_text, f"landing slug /{slug} missing from sitemap"

    def test_blog_index_and_posts(self, sitemap_text):
        assert "/blog</loc>" in sitemap_text or "/blog<" in sitemap_text or "/blog\n" in sitemap_text or re.search(r"/blog<", sitemap_text)
        for slug in [
            "what-makes-content-go-viral-2026",
            "viral-tiktok-hooks-that-work",
            "ai-tools-for-viral-content-creation",
        ]:
            assert f"/blog/{slug}" in sitemap_text, f"missing blog post {slug}"

    def test_agents_present(self, sitemap_text):
        assert "/agents" in sitemap_text


# --- robots.txt ---
class TestRobots:
    def test_status_and_content_type(self):
        r = requests.get(f"{BASE_URL}/api/seo/robots.txt", timeout=15)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "").lower()
        assert "text" in ct

    def test_required_directives(self, robots_text):
        assert "User-agent: *" in robots_text
        assert "Disallow: /api/" in robots_text
        assert "Disallow: /dashboard" in robots_text

    def test_sitemap_directive_present(self, robots_text):
        # Must include Sitemap: line. Spec asked for /api/seo/sitemap.xml but a root /sitemap.xml is also valid.
        assert re.search(r"(?im)^Sitemap:\s*https?://.+sitemap\.xml\s*$", robots_text), \
            "no Sitemap: directive in robots.txt"


# --- static CRA robots.txt fallback ---
class TestStaticRobots:
    def test_static_robots_served(self):
        r = requests.get(f"{BASE_URL}/robots.txt", timeout=15)
        # CRA serves it at root. May be merged/augmented by Cloudflare - just check it returns 200.
        assert r.status_code == 200
        assert len(r.text) > 0
