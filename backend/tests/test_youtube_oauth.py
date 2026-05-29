"""YouTube OAuth integration tests.

Live live-token tests are skipped automatically when YOUTUBE_CLIENT_ID is
unset (the common case during CI / before the admin pastes credentials
in /admin/integrations). The auth-gating + endpoint-shape coverage runs
unconditionally so we catch regressions in the wiring even before real
Google credentials exist.
"""
import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import app_config as AC  # noqa: E402

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _cleanup():
    """Wipe any test-injected youtube_connections / app_config rows + cache."""
    yield
    async def go():
        db = _mongo()
        await db.youtube_connections.delete_many({"user_id": {"$regex": "^test_yt_"}})
        await db.channels.delete_many({"user_id": {"$regex": "^test_yt_"}, "platform": "youtube"})
        await db.app_config.delete_many({"key": {"$in": [
            "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI",
        ]}})
        AC.invalidate_cache()
    _run(go())


class TestYouTubeAuth:
    """Auth-gating on every endpoint (401 without a session cookie/token)."""

    def test_start_requires_auth(self):
        r = requests.get(f"{API_URL}/api/oauth/youtube/start", timeout=10)
        assert r.status_code == 401

    def test_status_requires_auth(self):
        r = requests.get(f"{API_URL}/api/oauth/youtube/status", timeout=10)
        assert r.status_code == 401

    def test_disconnect_requires_auth(self):
        r = requests.delete(f"{API_URL}/api/oauth/youtube", timeout=10)
        assert r.status_code == 401


class TestAppConfigRegistry:
    """The three YouTube keys must be exposed in /admin/integrations."""

    def test_youtube_keys_registered(self):
        r = requests.get(f"{API_URL}/api/admin/app-config",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        keys = {it["key"]: it for it in r.json()["items"]}
        assert "YOUTUBE_CLIENT_ID" in keys
        assert "YOUTUBE_CLIENT_SECRET" in keys
        assert "YOUTUBE_REDIRECT_URI" in keys
        # Client Secret must be flagged secret (UI masks it).
        assert keys["YOUTUBE_CLIENT_SECRET"]["secret"] is True
        # Client ID is non-secret (numeric/string visible).
        assert keys["YOUTUBE_CLIENT_ID"]["secret"] is False
        # All three share the "youtube" group so the admin UI clusters them.
        for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI"):
            assert keys[k]["group"] == "youtube"

    def test_set_and_clear_client_id_roundtrip(self):
        fake_id = f"fake-client-{uuid.uuid4().hex[:8]}.apps.googleusercontent.com"
        r = requests.put(f"{API_URL}/api/admin/app-config",
                         json={"key": "YOUTUBE_CLIENT_ID", "value": fake_id},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200 and r.json()["cleared"] is False

        r = requests.get(f"{API_URL}/api/admin/app-config",
                         headers=HEADERS, timeout=10)
        items = {it["key"]: it for it in r.json()["items"]}
        # Non-secret keys preview in cleartext.
        assert items["YOUTUBE_CLIENT_ID"]["preview"] == fake_id
        assert items["YOUTUBE_CLIENT_ID"]["source"] == "database"

        # Clear it via empty value.
        r = requests.put(f"{API_URL}/api/admin/app-config",
                         json={"key": "YOUTUBE_CLIENT_ID", "value": ""},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200 and r.json()["cleared"] is True


class TestStatusShape:
    """When YOUTUBE_CLIENT_ID is unset, /status reports configured=false +
    connected=false. Admin can use this to render an inert connect button."""

    def test_status_unconfigured(self):
        # Wipe any test creds and the cache to force the unconfigured state.
        async def go():
            db = _mongo()
            await db.app_config.delete_many({"key": {"$in": [
                "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
            ]}})
            AC.invalidate_cache()
        _run(go())

        r = requests.get(f"{API_URL}/api/oauth/youtube/status",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # When env vars are also unset, configured = false.
        env_has_creds = bool(os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_CLIENT_SECRET"))
        assert body["configured"] is env_has_creds
        assert body["connected"] is False
        assert body["channel"] is None
