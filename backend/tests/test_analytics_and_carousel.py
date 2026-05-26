"""Tests for per-post analytics and Pinterest carousel pin support."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import httpx
import pytest

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _admin_user_id():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        sess = await db.user_sessions.find_one({"session_token": ADMIN_TOKEN}, {"_id": 0})
        return sess["user_id"] if sess else None
    return asyncio.get_event_loop().run_until_complete(go())


def _insert_test_post(*, with_pin: bool, pin_id: str | None = None):
    """Drop a fake post doc into MongoDB and return its id."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    user_id = _admin_user_id()
    assert user_id, "admin token not bound to a user"
    post_id = f"posttest_{secrets.token_hex(6)}"
    doc = {
        "id": post_id,
        "user_id": user_id,
        "content": "Carousel test content",
        "platforms": ["pinterest"] if with_pin else ["tiktok"],
        "status": "published",
        "created_at": datetime.now(timezone.utc),
    }
    if with_pin:
        doc["dispatch"] = {"pinterest": {"ok": True, "pin_id": pin_id or "pin_123", "permalink": "https://pinterest.com/pin/pin_123"}}
    else:
        doc["dispatch"] = {"tiktok": {"ok": True}}

    async def go():
        await db.posts.insert_one(doc)
    asyncio.get_event_loop().run_until_complete(go())
    return post_id, user_id


def _cleanup_post(post_id: str):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.posts.delete_one({"id": post_id})
    asyncio.get_event_loop().run_until_complete(go())


class TestMetricsEndpoints:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/posts/metrics?post_id=x", timeout=10)
        assert r.status_code == 401

    def test_404_unknown_post(self):
        r = httpx.get(f"{API_URL}/api/posts/metrics?post_id=does_not_exist", headers=H, timeout=10)
        assert r.status_code == 404

    def test_returns_metrics_shape(self):
        post_id, _ = _insert_test_post(with_pin=True)
        try:
            r = httpx.get(f"{API_URL}/api/posts/metrics?post_id={post_id}", headers=H, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert data["post_id"] == post_id
            assert data["platforms"] == ["pinterest"]
            assert isinstance(data["metrics"], dict)
        finally:
            _cleanup_post(post_id)

    def test_refresh_endpoint_returns_count(self):
        r = httpx.post(f"{API_URL}/api/posts/metrics/refresh", headers=H, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "refreshed" in body


class TestAnalyticsRefresh:
    """Drive the underlying refresh logic with a mocked Pinterest API call."""

    def test_refresh_post_writes_metrics_when_api_returns_data(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes import analytics as anal_mod

        post_id, user_id = _insert_test_post(with_pin=True, pin_id="pin_999")
        try:
            mock_data = {
                "impressions": 1234,
                "saves": 56,
                "clicks": 78,
                "outbound_clicks": 9,
                "fetched_at": datetime.now(timezone.utc),
            }
            with patch("routes.oauth_pinterest.fetch_pinterest_pin_metrics",
                       new=AsyncMock(return_value=mock_data)):
                async def go():
                    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                    await anal_mod._refresh_post(post)
                    return await db.posts.find_one({"id": post_id}, {"_id": 0})
                updated = asyncio.get_event_loop().run_until_complete(go())
            m = updated.get("metrics") or {}
            assert m.get("pinterest", {}).get("impressions") == 1234
            assert m.get("pinterest", {}).get("saves") == 56
            assert m.get("last_refreshed_at") is not None
        finally:
            _cleanup_post(post_id)

    def test_refresh_post_no_op_when_api_returns_none(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes import analytics as anal_mod

        post_id, _ = _insert_test_post(with_pin=True)
        try:
            with patch("routes.oauth_pinterest.fetch_pinterest_pin_metrics",
                       new=AsyncMock(return_value=None)):
                async def go():
                    post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                    return await anal_mod._refresh_post(post)
                result = asyncio.get_event_loop().run_until_complete(go())
            assert result is None
        finally:
            _cleanup_post(post_id)

    def test_refresh_skips_posts_without_pinterest_dispatch(self):
        """TikTok-only post (no analytics module yet) should produce empty result."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes import analytics as anal_mod

        post_id, _ = _insert_test_post(with_pin=False)
        try:
            async def go():
                post = await db.posts.find_one({"id": post_id}, {"_id": 0})
                return await anal_mod._fetch_for_post(post)
            metrics = asyncio.get_event_loop().run_until_complete(go())
            assert metrics == {}
        finally:
            _cleanup_post(post_id)


class TestPinterestCarousel:
    """Direct unit-test of publish_to_pinterest's carousel branch using
    monkeypatched httpx + token lookup."""

    def test_carousel_uses_multiple_image_urls(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_pinterest as pin_mod

        captured = {}

        class FakeResp:
            def __init__(self):
                self.status_code = 201
                self.text = ""

            def json(self):
                return {"id": "carousel_pin_1", "link": None}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                captured["url"] = url
                captured["body"] = json
                return FakeResp()

        async def fake_token(user_id):
            return "tok"

        with patch.object(pin_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})), \
             patch.object(pin_mod, "get_fresh_pinterest_token", new=AsyncMock(side_effect=fake_token)):
            res = asyncio.get_event_loop().run_until_complete(pin_mod.publish_to_pinterest(
                user_id="u1",
                text="A carousel",
                images=[
                    "https://example.com/a.jpg",
                    "https://example.com/b.jpg",
                    "https://example.com/c.jpg",
                ],
                board_id="b1",
            ))
        assert res["ok"] is True
        assert res["pin_id"] == "carousel_pin_1"
        assert res["carousel_slides"] == 3
        body = captured["body"]
        assert body["media_source"]["source_type"] == "multiple_image_urls"
        assert len(body["media_source"]["items"]) == 3
        assert body["media_source"]["items"][0]["url"] == "https://example.com/a.jpg"

    def test_single_image_still_uses_image_url(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_pinterest as pin_mod

        captured = {}

        class FakeResp:
            status_code = 201
            text = ""
            def json(self):
                return {"id": "single_pin_1"}

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None):
                captured["body"] = json
                return FakeResp()

        with patch.object(pin_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})), \
             patch.object(pin_mod, "get_fresh_pinterest_token", new=AsyncMock(return_value="tok")):
            res = asyncio.get_event_loop().run_until_complete(pin_mod.publish_to_pinterest(
                user_id="u1",
                text="A single pin",
                image_url="https://example.com/only.jpg",
                board_id="b1",
            ))
        assert res["ok"] is True
        assert "carousel_slides" not in res or res["carousel_slides"] is None
        body = captured["body"]
        assert body["media_source"]["source_type"] == "image_url"
        assert body["media_source"]["url"] == "https://example.com/only.jpg"

    def test_carousel_caps_at_five_images(self):
        """If the caller passes 8 images, only the first 5 should be sent."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_pinterest as pin_mod

        captured = {}

        class FakeResp:
            status_code = 201
            text = ""
            def json(self): return {"id": "p"}

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None):
                captured["body"] = json
                return FakeResp()

        with patch.object(pin_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})), \
             patch.object(pin_mod, "get_fresh_pinterest_token", new=AsyncMock(return_value="tok")):
            asyncio.get_event_loop().run_until_complete(pin_mod.publish_to_pinterest(
                user_id="u1",
                text="big carousel",
                images=[f"https://x/{i}.jpg" for i in range(8)],
                board_id="b1",
            ))
        assert len(captured["body"]["media_source"]["items"]) == 5


class TestAgentFollowUps:
    """Verify the inline `<<FUPS>>` parser strips the sentinel from the
    answer and returns the chip array."""

    def test_parser_extracts_chips(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_chat import _extract_followups

        raw = 'Here is the answer.\n\n<<FUPS>>["What about TikTok?","Cost per post?","Best time to post?"]<<END>>'
        clean, chips = _extract_followups(raw)
        assert clean == "Here is the answer."
        assert chips == ["What about TikTok?", "Cost per post?", "Best time to post?"]

    def test_parser_tolerates_missing_end_marker(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_chat import _extract_followups

        raw = 'Answer body.\n<<FUPS>>["q1","q2","q3"]'
        clean, chips = _extract_followups(raw)
        assert clean == "Answer body."
        assert len(chips) == 3

    def test_parser_returns_original_on_malformed_block(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_chat import _extract_followups

        raw = "Answer with no follow-ups."
        clean, chips = _extract_followups(raw)
        assert clean == raw
        assert chips == []

    def test_parser_caps_at_3_chips(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_chat import _extract_followups

        raw = 'Body.\n<<FUPS>>["a","b","c","d","e"]<<END>>'
        clean, chips = _extract_followups(raw)
        assert chips == ["a", "b", "c"]
