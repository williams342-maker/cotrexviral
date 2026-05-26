"""Pinterest publishing tests (boards endpoint + dispatch helper)."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _cleanup_test_posts():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.posts.delete_many({"content": {"$regex": "^PIN_PUB_TEST"}})
    asyncio.get_event_loop().run_until_complete(go())


class TestBoardsEndpoint:
    def test_anon_401(self):
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/boards", timeout=10)
        assert r.status_code == 401

    def test_400_when_not_connected(self):
        # No active Pinterest connection for the test user → 400 (not 500)
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/boards", headers=H, timeout=10)
        assert r.status_code == 400
        assert "not connected" in r.text.lower()


class TestPublishValidation:
    """The publish endpoint should record clear, actionable failures rather
    than silently dropping Pinterest posts."""

    def setup_method(self):
        _cleanup_test_posts()

    def teardown_method(self):
        _cleanup_test_posts()

    def test_publish_pinterest_without_image_records_failure(self):
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={"content": "PIN_PUB_TEST no image",
                  "platforms": ["pinterest"]},
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "published"
        # Dispatch result should clearly say WHY it failed.
        pin = body["dispatch"]["pinterest"]
        assert pin["ok"] is False
        assert pin["reason"] == "pinterest_requires_image_url"

    def test_publish_pinterest_without_board_records_failure(self):
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={"content": "PIN_PUB_TEST no board",
                  "platforms": ["pinterest"],
                  "media_url": "https://example.com/test.jpg"},
            timeout=15,
        )
        assert r.status_code == 200
        pin = r.json()["dispatch"]["pinterest"]
        assert pin["ok"] is False
        assert pin["reason"] == "pinterest_requires_board_id"

    def test_publish_pinterest_not_connected_records_failure(self):
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={"content": "PIN_PUB_TEST not connected",
                  "platforms": ["pinterest"],
                  "media_url": "https://example.com/test.jpg",
                  "pinterest_board_id": "fake_board_id_123"},
            timeout=15,
        )
        assert r.status_code == 200
        pin = r.json()["dispatch"]["pinterest"]
        assert pin["ok"] is False
        # No Pinterest connection exists for the test user.
        assert pin["reason"] == "not_connected"

    def test_publish_pinterest_fields_persisted_on_post(self):
        """The Pinterest-specific fields must be saved on the post doc so the
        background scheduler can use them when it dispatches later."""
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "PIN_PUB_TEST persists fields",
                "platforms": ["pinterest"],
                "media_url": "https://example.com/persistence.jpg",
                "pinterest_board_id": "board_xyz",
                "pinterest_link": "https://shop.example.com/abc",
                "pinterest_title": "My Pin",
            },
            timeout=15,
        )
        assert r.status_code == 200
        post_id = r.json()["id"]

        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def check():
            p = await db.posts.find_one({"id": post_id})
            assert p["pinterest_board_id"] == "board_xyz"
            assert p["pinterest_link"] == "https://shop.example.com/abc"
            assert p["pinterest_title"] == "My Pin"
        asyncio.get_event_loop().run_until_complete(check())


class TestPublishHelperShape:
    """The publish_to_pinterest helper must return the same {ok, reason,
    pin_id?, permalink?} shape the other publish_to_* helpers do — the
    scheduler dispatcher relies on this contract."""

    def test_helper_validates_image_url(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_pinterest import publish_to_pinterest
        result = asyncio.get_event_loop().run_until_complete(
            publish_to_pinterest("any_user", "caption", image_url=None, board_id="b")
        )
        assert result == {"ok": False, "reason": "pinterest_requires_image_url"}

    def test_helper_validates_board_id(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_pinterest import publish_to_pinterest
        result = asyncio.get_event_loop().run_until_complete(
            publish_to_pinterest("any_user", "caption",
                                 image_url="https://example.com/i.jpg",
                                 board_id=None)
        )
        assert result == {"ok": False, "reason": "pinterest_requires_board_id"}

    def test_helper_truncates_description_to_500(self):
        """Pinterest's hard cap is 500 chars. The helper must truncate to
        avoid a 400 from the API; check the helper's PIN_DESCRIPTION_LIMIT
        constant rather than mocking httpx."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_pinterest import PIN_DESCRIPTION_LIMIT
        assert PIN_DESCRIPTION_LIMIT == 500
