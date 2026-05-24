"""SEO v3 tests: video sitemap namespace + breadcrumb-ready sitemap XML."""
import os
import re
import requests
from importlib import import_module

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL") or "https://social-sync-ai-1.preview.emergentagent.com"
).rstrip("/")


def _sitemap():
    r = requests.get(f"{BASE_URL}/api/seo/sitemap.xml", timeout=15)
    assert r.status_code == 200
    return r.text


class TestVideoSitemap:
    def test_video_namespace_present(self):
        text = _sitemap()
        assert 'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1"' in text, (
            "video sitemap namespace missing on <urlset>"
        )

    def test_no_video_blocks_when_registry_empty(self):
        """BLOG_VIDEOS is empty by default — sitemap should not contain
        <video:video> blocks until a real video is registered."""
        # Reimport module to read current state of BLOG_VIDEOS
        seo = import_module("routes.seo")
        if not seo.BLOG_VIDEOS:
            text = _sitemap()
            assert "<video:video>" not in text

    def test_video_block_renders_when_registered(self):
        """Builder helper renders a well-formed <video:video> block."""
        seo = import_module("routes.seo")
        block = seo._video_xml_block(
            {
                "title": "Test & Sample <Video>",
                "description": "Quick demo",
                "thumbnail_loc": "https://cortexviral.com/thumb.jpg",
                "player_loc": "https://www.youtube.com/embed/abc",
                "duration": 90,
            }
        )
        assert "<video:video>" in block
        assert "<video:title>Test &amp; Sample &lt;Video&gt;</video:title>" in block
        assert "<video:thumbnail_loc>https://cortexviral.com/thumb.jpg</video:thumbnail_loc>" in block
        assert 'allow_embed="yes"' in block
        assert "<video:duration>90</video:duration>" in block


class TestLegalAndSitemapIndexedRoutes:
    def test_privacy_terms_sitemap_present(self):
        text = _sitemap()
        for path in ["/privacy", "/terms", "/sitemap"]:
            assert f"<loc>https://cortexviral.com{path}</loc>" in text, f"missing {path}"

    def test_well_formed_xml_count(self):
        """<url> opens and closes match — guards against broken concat."""
        text = _sitemap()
        opens = len(re.findall(r"<url>", text))
        closes = len(re.findall(r"</url>", text))
        assert opens == closes and opens > 0
