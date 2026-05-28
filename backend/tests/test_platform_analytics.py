"""Tests for LinkedIn / Facebook / Instagram / TikTok per-post analytics
fetchers + the routes/analytics dispatcher that wires them all together,
plus the new `memories_used` payload from agent chat."""
import asyncio
import os
import secrets
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import httpx

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


class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.text = ""

    def json(self):
        return self._body


class _FakeClient:
    """httpx.AsyncClient drop-in. Captures the LAST get/post call args."""

    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        type(self).captured = {"method": "GET", "url": url, "params": params, "headers": headers}
        return self.response

    async def post(self, url, json=None, data=None, params=None, headers=None):
        type(self).captured = {
            "method": "POST", "url": url, "json": json,
            "data": data, "params": params, "headers": headers,
        }
        return self.response


def _make_client(response: _FakeResp):
    return type("h", (), {
        "AsyncClient": type(
            "FakeAC",
            (_FakeClient,),
            {"response": response, "captured": {}},
        ),
    })


# ===========================================================================
# LinkedIn
# ===========================================================================
class TestLinkedInAnalytics:
    def test_returns_none_when_no_connection(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_linkedin import fetch_linkedin_post_metrics

        res = asyncio.get_event_loop().run_until_complete(
            fetch_linkedin_post_metrics(f"ghost-{secrets.token_hex(3)}", "urn:li:share:x"),
        )
        assert res is None

    def test_parses_likes_and_comments(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes import oauth_linkedin as li_mod

        uid = _admin_user_id()

        async def setup():
            await db.linkedin_connections.update_one(
                {"user_id": uid},
                {"$set": {"user_id": uid, "access_token": "tok"}},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(setup())

        try:
            resp = _FakeResp(200, {
                "likesSummary": {"totalLikes": 42},
                "commentsSummary": {"aggregatedTotalComments": 7},
            })
            with patch.object(li_mod, "httpx", new=_make_client(resp)):
                out = asyncio.get_event_loop().run_until_complete(
                    li_mod.fetch_linkedin_post_metrics(uid, "urn:li:share:abc"),
                )
            assert out["likes"] == 42
            assert out["comments"] == 7
            assert out["fetched_at"] is not None
        finally:
            asyncio.get_event_loop().run_until_complete(
                db.linkedin_connections.delete_one({"user_id": uid}),
            )

    def test_returns_none_on_api_failure(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes import oauth_linkedin as li_mod

        uid = _admin_user_id()

        async def setup():
            await db.linkedin_connections.update_one(
                {"user_id": uid},
                {"$set": {"user_id": uid, "access_token": "tok"}},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            resp = _FakeResp(401, {"error": "expired"})
            with patch.object(li_mod, "httpx", new=_make_client(resp)):
                out = asyncio.get_event_loop().run_until_complete(
                    li_mod.fetch_linkedin_post_metrics(uid, "urn:li:share:abc"),
                )
            assert out is None
        finally:
            asyncio.get_event_loop().run_until_complete(
                db.linkedin_connections.delete_one({"user_id": uid}),
            )


# ===========================================================================
# Facebook
# ===========================================================================
class TestFacebookAnalytics:
    def _seed(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid = _admin_user_id()

        async def go():
            await db.facebook_connections.update_one(
                {"user_id": uid},
                {"$set": {
                    "user_id": uid,
                    "pages": [{"id": "page_123", "access_token": "page_tok"}],
                }},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())
        return uid

    def _cleanup(self, uid):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            await db.facebook_connections.delete_one({"user_id": uid})
        asyncio.get_event_loop().run_until_complete(go())

    def test_returns_none_when_no_connection(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_meta import fetch_facebook_post_metrics

        res = asyncio.get_event_loop().run_until_complete(
            fetch_facebook_post_metrics(f"ghost-{secrets.token_hex(3)}", "page_x_post_y"),
        )
        assert res is None

    def test_parses_insights(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta as meta_mod

        uid = self._seed()
        try:
            resp = _FakeResp(200, {"data": [
                {"name": "post_impressions", "values": [{"value": 1000}]},
                {"name": "post_engaged_users", "values": [{"value": 87}]},
                {"name": "post_reactions_by_type_total", "values": [{"value": {"like": 12, "love": 3, "haha": 1}}]},
            ]})
            with patch.object(meta_mod, "httpx", new=_make_client(resp)):
                out = asyncio.get_event_loop().run_until_complete(
                    meta_mod.fetch_facebook_post_metrics(uid, "page_123_post_456"),
                )
            assert out["impressions"] == 1000
            assert out["engaged_users"] == 87
            assert out["reactions"] == 16
        finally:
            self._cleanup(uid)


# ===========================================================================
# Instagram
# ===========================================================================
class TestInstagramAnalytics:
    def _seed(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid = _admin_user_id()

        async def go():
            await db.instagram_connections.update_one(
                {"user_id": uid},
                {"$set": {
                    "user_id": uid,
                    "pages": [{"id": "p1", "access_token": "page_tok"}],
                    "ig_accounts": [{"page_id": "p1", "ig_user_id": "ig1"}],
                }},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())
        return uid

    def _cleanup(self, uid):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            await db.instagram_connections.delete_one({"user_id": uid})
        asyncio.get_event_loop().run_until_complete(go())

    def test_parses_media_insights(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta as meta_mod

        uid = self._seed()
        try:
            resp = _FakeResp(200, {"data": [
                {"name": "impressions", "values": [{"value": 4500}]},
                {"name": "reach", "values": [{"value": 3200}]},
                {"name": "saved", "values": [{"value": 120}]},
                {"name": "likes", "values": [{"value": 250}]},
                {"name": "comments", "values": [{"value": 18}]},
            ]})
            with patch.object(meta_mod, "httpx", new=_make_client(resp)):
                out = asyncio.get_event_loop().run_until_complete(
                    meta_mod.fetch_instagram_post_metrics(uid, "ig_media_42"),
                )
            assert out["impressions"] == 4500
            assert out["reach"] == 3200
            assert out["saved"] == 120
            assert out["likes"] == 250
            assert out["comments"] == 18
        finally:
            self._cleanup(uid)


# ===========================================================================
# TikTok — requires resolving publish_id → video_id (2 API calls)
# ===========================================================================
class TestTikTokAnalytics:
    def _seed(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid = _admin_user_id()

        async def go():
            await db.tiktok_connections.update_one(
                {"user_id": uid},
                {"$set": {"user_id": uid, "access_token": "tt_tok"}},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())
        return uid

    def _cleanup(self, uid):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            await db.tiktok_connections.delete_one({"user_id": uid})
        asyncio.get_event_loop().run_until_complete(go())

    def test_resolves_publish_id_then_fetches_stats(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_tiktok as tt_mod

        uid = self._seed()
        calls = []

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, json=None, data=None, params=None, headers=None):
                calls.append({"url": url, "json": json, "params": params})
                if "/post/publish/status" in url:
                    return _FakeResp(200, {
                        "data": {"publicaly_available_post_id": ["vid_777"]},
                    })
                # /v2/video/query/
                return _FakeResp(200, {
                    "data": {"videos": [{
                        "id": "vid_777",
                        "view_count": 50000,
                        "like_count": 4200,
                        "comment_count": 180,
                        "share_count": 320,
                    }]},
                })

        try:
            with patch.object(tt_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})):
                out = asyncio.get_event_loop().run_until_complete(
                    tt_mod.fetch_tiktok_post_metrics(uid, publish_id="pub_xyz"),
                )
            assert out["views"] == 50000
            assert out["likes"] == 4200
            assert out["comments"] == 180
            assert out["shares"] == 320
            # Two calls were made: status resolve + stats query
            assert len(calls) == 2
        finally:
            self._cleanup(uid)


# ===========================================================================
# routes/analytics dispatcher — picks the right fetcher per platform
# ===========================================================================
class TestAnalyticsDispatcher:
    def test_dispatches_to_linkedin_when_dispatch_has_urn(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import analytics as anal_mod

        post = {
            "id": "p1",
            "user_id": "u1",
            "dispatch": {
                "linkedin": {"ok": True, "linkedin_post_id": "urn:li:share:abc"},
            },
        }
        with patch("routes.oauth_linkedin.fetch_linkedin_post_metrics",
                   new=AsyncMock(return_value={"likes": 10, "comments": 2,
                                              "fetched_at": datetime.now(timezone.utc)})):
            out = asyncio.get_event_loop().run_until_complete(
                anal_mod._fetch_for_post(post),
            )
        assert "linkedin" in out
        assert out["linkedin"]["likes"] == 10

    def test_dispatches_to_facebook_and_instagram(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import analytics as anal_mod

        post = {
            "id": "p2",
            "user_id": "u2",
            "dispatch": {
                "facebook": {"ok": True, "post_id": "page_1_post_1"},
                "instagram": {"ok": True, "post_id": "ig_xx"},
            },
        }
        fb_data = {"impressions": 100, "engaged_users": 10, "reactions": 5, "fetched_at": datetime.now(timezone.utc)}
        ig_data = {"impressions": 500, "reach": 400, "saved": 12, "likes": 80, "comments": 4, "fetched_at": datetime.now(timezone.utc)}
        with patch("routes.oauth_meta.fetch_facebook_post_metrics",
                   new=AsyncMock(return_value=fb_data)), \
             patch("routes.oauth_meta.fetch_instagram_post_metrics",
                   new=AsyncMock(return_value=ig_data)):
            out = asyncio.get_event_loop().run_until_complete(
                anal_mod._fetch_for_post(post),
            )
        assert out["facebook"]["impressions"] == 100
        assert out["instagram"]["likes"] == 80

    def test_skips_platforms_without_successful_dispatch(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import analytics as anal_mod

        # Facebook dispatch failed → no metrics call
        post = {
            "id": "p3",
            "user_id": "u3",
            "dispatch": {"facebook": {"ok": False, "reason": "api_error"}},
        }
        out = asyncio.get_event_loop().run_until_complete(
            anal_mod._fetch_for_post(post),
        )
        assert out == {}


# ===========================================================================
# Agent chat memories_used
# ===========================================================================
class TestAgentMemoriesUsedPayload:
    def test_response_includes_memories_used_array(self):
        """Successful agent chat must include `memories_used` in the
        response, even if empty (consistent shape for the frontend)."""
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "nova", "message": "Say OK in one word."},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "memories_used" in body
        assert isinstance(body["memories_used"], list)
        # Each entry must have the chip-friendly shape
        for m in body["memories_used"]:
            assert {"id", "kind", "preview", "score"} <= set(m.keys())
            assert isinstance(m["preview"], str)
            assert isinstance(m["score"], float) or m["score"] is None
