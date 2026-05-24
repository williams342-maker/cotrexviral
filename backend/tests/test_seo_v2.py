"""Backend SEO v2 tests: expanded sitemap (56+ URLs), production domain, image:image, robots."""
import os
import re
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://social-sync-ai-1.preview.emergentagent.com").rstrip("/")

PROG_TOOLS = [
    "instagram-caption-generator",
    "tiktok-script-generator",
    "viral-content-ideas",
    "linkedin-post-generator",
]
PROG_NICHES = [
    "fitness-coaches",
    "real-estate",
    "saas-founders",
    "e-commerce-brands",
    "restaurants",
    "beauty-creators",
    "consultants",
    "agencies",
]


def _sitemap():
    r = requests.get(f"{BASE_URL}/api/seo/sitemap.xml", timeout=15)
    assert r.status_code == 200
    return r.text


def _robots():
    r = requests.get(f"{BASE_URL}/api/seo/robots.txt", timeout=15)
    assert r.status_code == 200
    return r.text


# --- sitemap shape ---
class TestSitemapV2:
    def test_total_loc_entries(self):
        text = _sitemap()
        loc_count = len(re.findall(r"<loc>https?://[^<]+</loc>", text))
        page_loc_count = len(re.findall(r"<url>\s*\n\s*<loc>", text))
        # 12 core + 32 programmatic + 12 blog posts = 56 (lower-bound; grows over time)
        assert page_loc_count >= 56, f"expected at least 56 page <loc> entries, got {page_loc_count}; total loc={loc_count}"

    def test_uses_production_domain(self):
        text = _sitemap()
        # all <loc> for pages must be on cortexviral.com
        page_locs = re.findall(r"<url>\s*\n\s*<loc>([^<]+)</loc>", text)
        assert len(page_locs) > 0
        for loc in page_locs:
            assert loc.startswith("https://cortexviral.com"), f"non-prod domain: {loc}"

    def test_has_image_namespace_and_entries(self):
        text = _sitemap()
        assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in text
        assert "<image:image>" in text
        assert "<image:loc>" in text
        # at least one image:image per url (56+)
        assert len(re.findall(r"<image:image>", text)) >= 56

    def test_pricing_present(self):
        text = _sitemap()
        assert "https://cortexviral.com/pricing" in text

    def test_all_32_programmatic_combos_present(self):
        text = _sitemap()
        missing = []
        for t in PROG_TOOLS:
            for n in PROG_NICHES:
                url = f"https://cortexviral.com/tools/{t}-for-{n}"
                if url not in text:
                    missing.append(url)
        assert not missing, f"missing programmatic urls: {missing[:5]} (total {len(missing)})"

    def test_core_marketing_still_present(self):
        text = _sitemap()
        for path in [
            "/", "/agents", "/blog",
            "/ai-tiktok-post-generator",
            "/viral-content-ideas-generator",
            "/instagram-caption-ai-generator",
            "/short-form-video-ideas-ai",
            "/content-automation-tool",
            "/blog/what-makes-content-go-viral-2026",
            "/blog/viral-tiktok-hooks-that-work",
            "/blog/ai-tools-for-viral-content-creation",
        ]:
            full = f"https://cortexviral.com{path}"
            assert f"<loc>{full}</loc>" in text, f"missing {full}"


# --- robots ---
class TestRobotsV2:
    def test_has_both_sitemap_directives(self):
        text = _robots()
        # /sitemap.xml
        assert re.search(r"(?im)^Sitemap:\s*https://cortexviral\.com/sitemap\.xml\s*$", text), \
            f"missing /sitemap.xml directive in:\n{text}"
        # /api/seo/sitemap.xml
        assert re.search(r"(?im)^Sitemap:\s*https://cortexviral\.com/api/seo/sitemap\.xml\s*$", text), \
            f"missing /api/seo/sitemap.xml directive in:\n{text}"

    def test_status_200(self):
        r = requests.get(f"{BASE_URL}/api/seo/robots.txt", timeout=15)
        assert r.status_code == 200
