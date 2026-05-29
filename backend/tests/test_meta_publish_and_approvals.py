"""Tests for the approval workflow + Meta (Facebook/Instagram) publish helpers."""
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


def _insert_pending(content: str = "Pending test post"):
    """Drop a status=pending_approval post into the DB for the admin user.
    Phase 5: also mirrors into the normalized layer so strict-mode reads
    (`STRICT_NORMALIZED_READS=true`) still surface it."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db
    from routes.content_layer import mirror_post_to_normalized

    user_id = _admin_user_id()
    post_id = f"appr_{secrets.token_hex(6)}"
    doc = {
        "id": post_id,
        "user_id": user_id,
        "content": content,
        "platforms": ["facebook"],
        "status": "pending_approval",
        "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "created_at": datetime.now(timezone.utc),
    }

    async def go():
        await db.posts.insert_one(doc)
        await mirror_post_to_normalized(doc)
    asyncio.get_event_loop().run_until_complete(go())
    return post_id


def _cleanup_post(post_id: str):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        # Cascade: variants + content_item too (Phase 2 mirrored these).
        ci = await db.content_variants.find_one(
            {"post_id": post_id}, {"_id": 0, "content_item_id": 1},
        )
        await db.posts.delete_one({"id": post_id})
        await db.content_variants.delete_many({"post_id": post_id})
        if ci and ci.get("content_item_id"):
            await db.content_items.delete_one({"id": ci["content_item_id"]})
    asyncio.get_event_loop().run_until_complete(go())


def _reset_user_approval():
    """Best-effort reset of the require_post_approval flag back to False."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    uid = _admin_user_id()

    async def go():
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"require_post_approval": False}},
        )
    asyncio.get_event_loop().run_until_complete(go())


# ===========================================================================
# Settings + list endpoints
# ===========================================================================
class TestApprovalSettings:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/approvals/settings", timeout=10)
        assert r.status_code == 401

    def test_get_default_false(self):
        _reset_user_approval()
        r = httpx.get(f"{API_URL}/api/approvals/settings", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["require_post_approval"] is False

    def test_put_persists(self):
        try:
            r = httpx.put(
                f"{API_URL}/api/approvals/settings",
                headers=H, json={"require_post_approval": True}, timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["require_post_approval"] is True

            r2 = httpx.get(f"{API_URL}/api/approvals/settings", headers=H, timeout=10)
            assert r2.status_code == 200
            assert r2.json()["require_post_approval"] is True
        finally:
            _reset_user_approval()


class TestApprovalInbox:
    def test_list_returns_only_pending(self):
        post_id = _insert_pending()
        try:
            r = httpx.get(f"{API_URL}/api/approvals", headers=H, timeout=10)
            assert r.status_code == 200
            ids = [p["id"] for p in r.json()["pending"]]
            assert post_id in ids
            # Every returned row must be pending_approval status
            assert all(p["status"] == "pending_approval" for p in r.json()["pending"])
        finally:
            _cleanup_post(post_id)

    def test_approve_flips_status(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        post_id = _insert_pending("approve me")
        try:
            r = httpx.post(f"{API_URL}/api/approvals/{post_id}/approve", headers=H, timeout=10)
            assert r.status_code == 200, r.text

            async def go():
                return await db.posts.find_one({"id": post_id}, {"_id": 0})
            doc = asyncio.get_event_loop().run_until_complete(go())
            assert doc["status"] == "scheduled"
            assert doc.get("approved_at") is not None
        finally:
            _cleanup_post(post_id)

    def test_reject_records_reason(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        post_id = _insert_pending("reject me")
        try:
            r = httpx.post(
                f"{API_URL}/api/approvals/{post_id}/reject",
                headers=H, json={"reason": "Off brand"}, timeout=10,
            )
            assert r.status_code == 200, r.text

            async def go():
                return await db.posts.find_one({"id": post_id}, {"_id": 0})
            doc = asyncio.get_event_loop().run_until_complete(go())
            assert doc["status"] == "rejected"
            assert doc.get("rejection_reason") == "Off brand"
        finally:
            _cleanup_post(post_id)

    def test_approve_404_when_not_pending(self):
        """Cannot approve a post that's not in pending_approval state."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        user_id = _admin_user_id()
        post_id = f"appr_already_{secrets.token_hex(4)}"

        async def setup():
            await db.posts.insert_one({
                "id": post_id,
                "user_id": user_id,
                "content": "already scheduled",
                "platforms": ["tiktok"],
                "status": "scheduled",
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            r = httpx.post(f"{API_URL}/api/approvals/{post_id}/approve", headers=H, timeout=10)
            assert r.status_code == 404
        finally:
            _cleanup_post(post_id)


# ===========================================================================
# Channels.publish gate — when require_post_approval=True, scheduled posts
# go to pending_approval, not scheduled.
# ===========================================================================
class TestPublishGate:
    def test_scheduled_post_pends_when_setting_on(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        # Turn the flag on
        httpx.put(
            f"{API_URL}/api/approvals/settings",
            headers=H, json={"require_post_approval": True}, timeout=10,
        )
        try:
            future = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
            r = httpx.post(
                f"{API_URL}/api/channels/publish",
                headers=H,
                json={
                    "content": f"GATE-{secrets.token_hex(4)} test scheduled",
                    "platforms": ["tiktok"],
                    "scheduled_at": future,
                },
                timeout=15,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["status"] == "pending_approval"

            # Cleanup
            async def go():
                await db.posts.delete_one({"id": data["id"]})
            asyncio.get_event_loop().run_until_complete(go())
        finally:
            _reset_user_approval()


# ===========================================================================
# Meta publish helpers — unit-tested with monkeypatched httpx
# ===========================================================================
class TestFacebookPublish:
    def _seed_connection(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid = _admin_user_id()

        async def go():
            await db.facebook_connections.update_one(
                {"user_id": uid},
                {"$set": {
                    "user_id": uid,
                    "user_access_token": "fake_user_token",
                    "pages": [{
                        "id": "page_123",
                        "name": "Test Page",
                        "access_token": "fake_page_token",
                    }],
                }},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())
        return uid

    def _cleanup_connection(self, uid: str):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            await db.facebook_connections.delete_one({"user_id": uid})
        asyncio.get_event_loop().run_until_complete(go())

    def test_returns_not_connected_when_no_doc(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_meta import publish_to_facebook

        # Use a random user id that has no FB connection row
        res = asyncio.get_event_loop().run_until_complete(
            publish_to_facebook(f"nope_{secrets.token_hex(3)}", "hi"),
        )
        assert res["ok"] is False
        assert res["reason"] == "not_connected"

    def test_text_post_uses_feed_endpoint(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta as meta_mod

        uid = self._seed_connection()
        captured = {}

        class FakeResp:
            status_code = 200
            text = ""
            def json(self): return {"id": "page_123_post_456"}

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, data=None):
                captured["url"] = url
                captured["data"] = data
                return FakeResp()
            async def get(self, *a, **k): return FakeResp()

        try:
            with patch.object(meta_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})):
                res = asyncio.get_event_loop().run_until_complete(
                    meta_mod.publish_to_facebook(uid, "Hello FB"),
                )
            assert res["ok"] is True
            assert "/page_123/feed" in captured["url"]
            assert captured["data"]["message"] == "Hello FB"
        finally:
            self._cleanup_connection(uid)

    def test_photo_post_uses_photos_endpoint(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta as meta_mod

        uid = self._seed_connection()
        captured = {}

        class FakeResp:
            status_code = 200
            text = ""
            def json(self): return {"post_id": "page_123_photo_789"}

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, data=None):
                captured["url"] = url
                captured["data"] = data
                return FakeResp()

        try:
            with patch.object(meta_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})):
                res = asyncio.get_event_loop().run_until_complete(
                    meta_mod.publish_to_facebook(uid, "Caption text", image_url="https://x/a.jpg"),
                )
            assert res["ok"] is True
            assert "/page_123/photos" in captured["url"]
            assert captured["data"]["url"] == "https://x/a.jpg"
            assert captured["data"]["caption"] == "Caption text"
        finally:
            self._cleanup_connection(uid)


class TestInstagramPublish:
    def _seed_connection(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid = _admin_user_id()

        async def go():
            await db.instagram_connections.update_one(
                {"user_id": uid},
                {"$set": {
                    "user_id": uid,
                    "user_access_token": "fake_user_token",
                    "pages": [{
                        "id": "page_777",
                        "access_token": "fake_page_token",
                    }],
                    "ig_accounts": [{
                        "page_id": "page_777",
                        "ig_user_id": "ig_user_111",
                        "ig_username": "testuser",
                    }],
                }},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())
        return uid

    def _cleanup_connection(self, uid: str):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            await db.instagram_connections.delete_one({"user_id": uid})
        asyncio.get_event_loop().run_until_complete(go())

    def test_requires_image_url(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_meta import publish_to_instagram

        res = asyncio.get_event_loop().run_until_complete(
            publish_to_instagram("any-user", "text only"),
        )
        assert res["ok"] is False
        assert res["reason"] == "instagram_requires_image_url"

    def test_two_step_publish_flow(self):
        """Container create → media_publish."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta as meta_mod

        uid = self._seed_connection()
        calls = []

        class ContainerResp:
            status_code = 200
            text = ""
            def json(self): return {"id": "creation_id_42"}

        class PublishResp:
            status_code = 200
            text = ""
            def json(self): return {"id": "ig_post_42"}

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, data=None):
                calls.append({"url": url, "data": data})
                if "/media_publish" in url:
                    return PublishResp()
                return ContainerResp()

        try:
            with patch.object(meta_mod, "httpx", new=type("h", (), {"AsyncClient": FakeClient})):
                res = asyncio.get_event_loop().run_until_complete(
                    meta_mod.publish_to_instagram(uid, "Caption", image_url="https://x/a.jpg"),
                )
            assert res["ok"] is True
            assert res["post_id"] == "ig_post_42"
            assert len(calls) == 2
            assert "/ig_user_111/media" in calls[0]["url"]
            assert calls[0]["data"]["caption"] == "Caption"
            assert "/ig_user_111/media_publish" in calls[1]["url"]
            assert calls[1]["data"]["creation_id"] == "creation_id_42"
        finally:
            self._cleanup_connection(uid)
