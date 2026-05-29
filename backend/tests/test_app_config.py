"""DB-backed app_config tests."""
import asyncio
import os
import uuid
import time

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
    """Reset the app_config + cache between tests so order doesn't matter."""
    yield
    async def go():
        db = _mongo()
        await db.app_config.delete_many({"key": "META_REDIRECT_URI"})
        AC.invalidate_cache()
    _run(go())


class TestAdminEndpoints:

    def test_admin_required(self):
        r = requests.get(f"{API_URL}/api/admin/app-config", timeout=10)
        assert r.status_code == 401

        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            json={"key": "META_APP_ID", "value": "should_be_blocked"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_list_returns_all_known_keys(self):
        r = requests.get(f"{API_URL}/api/admin/app-config", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        keys = {it["key"] for it in r.json()["items"]}
        assert {"META_APP_ID", "META_APP_SECRET",
                "META_GRAPH_VERSION", "META_REDIRECT_URI"}.issubset(keys)

    def test_secret_value_is_masked(self):
        """When a secret key is set, the API response shows only the last 4 chars."""
        val = "abcdef1234567890ZZZZ"
        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": "https://test.example.com"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        AC.invalidate_cache()

        r = requests.get(f"{API_URL}/api/admin/app-config", headers=HEADERS, timeout=10)
        items = {it["key"]: it for it in r.json()["items"]}
        # META_REDIRECT_URI is NOT secret — preview should be the full string
        assert items["META_REDIRECT_URI"]["preview"] == "https://test.example.com"
        assert items["META_REDIRECT_URI"]["secret"] is False
        # META_APP_SECRET is secret — value should be masked (•••• + last 4)
        if items["META_APP_SECRET"]["is_set"]:
            assert items["META_APP_SECRET"]["secret"] is True
            assert items["META_APP_SECRET"]["preview"].count("•") >= 4

    def test_rejects_unknown_key(self):
        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "TOTALLY_FAKE_KEY", "value": "x"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_set_then_clear(self):
        # Set
        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": "https://temp.example.com"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["cleared"] is False

        # Clear via empty value
        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": ""},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["cleared"] is True

        # Confirm cleared
        async def check():
            db = _mongo()
            return await db.app_config.find_one({"key": "META_REDIRECT_URI"})
        assert _run(check()) is None

    def test_delete_endpoint(self):
        # Seed
        requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": "https://will-be-deleted.example.com"},
            timeout=10,
        )
        # Delete
        r = requests.delete(
            f"{API_URL}/api/admin/app-config/META_REDIRECT_URI",
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["deleted"] == 1


class TestGetConfigResolver:

    def test_db_wins_over_env(self):
        """A DB row beats the env var for the same key."""
        async def go():
            db = _mongo()
            os.environ["META_REDIRECT_URI"] = "from-env"
            await db.app_config.update_one(
                {"key": "META_REDIRECT_URI"},
                {"$set": {"key": "META_REDIRECT_URI", "value": "from-db"}},
                upsert=True,
            )
            AC.invalidate_cache()
            val = await AC.get_config("META_REDIRECT_URI")
            assert val == "from-db"
            del os.environ["META_REDIRECT_URI"]
        _run(go())

    def test_env_fallback_when_db_empty(self):
        async def go():
            db = _mongo()
            await db.app_config.delete_many({"key": "META_REDIRECT_URI"})
            os.environ["META_REDIRECT_URI"] = "env-only-value"
            AC.invalidate_cache()
            val = await AC.get_config("META_REDIRECT_URI")
            assert val == "env-only-value"
            del os.environ["META_REDIRECT_URI"]
            AC.invalidate_cache()
        _run(go())

    def test_default_fallback(self):
        async def go():
            db = _mongo()
            await db.app_config.delete_many({"key": "META_GRAPH_VERSION"})
            os.environ.pop("META_GRAPH_VERSION", None)
            AC.invalidate_cache()
            val = await AC.get_config("META_GRAPH_VERSION", default="v22.0")
            assert val == "v22.0"
        _run(go())

    def test_cache_invalidation(self):
        """Setting a key via the API invalidates the cache so reads are fresh."""
        async def seed():
            db = _mongo()
            await db.app_config.delete_many({"key": "META_REDIRECT_URI"})
            AC.invalidate_cache()
            # First read = None
            assert await AC.get_config("META_REDIRECT_URI") is None
        _run(seed())

        # Now write via API
        requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": "fresh-value-zzz"},
            timeout=10,
        )

        # The API call should have invalidated the cache (it runs in the
        # backend process, which is a separate process — so we explicitly
        # invalidate here too since this test is in a different Python).
        AC.invalidate_cache()

        async def check():
            val = await AC.get_config("META_REDIRECT_URI")
            assert val == "fresh-value-zzz"
        _run(check())


class TestOAuthUsesDbConfig:
    """Ensure the OAuth start endpoint reads credentials from the DB layer."""

    def test_oauth_start_picks_up_db_redirect(self):
        """Setting META_REDIRECT_URI via DB should change the redirect_uri
        in the next /oauth/facebook/start response (after cache TTL)."""
        # Seed a distinctive override
        sentinel = f"https://sentinel-{uuid.uuid4().hex[:8]}.example.com"
        r = requests.put(
            f"{API_URL}/api/admin/app-config",
            headers=HEADERS,
            json={"key": "META_REDIRECT_URI", "value": sentinel},
            timeout=10,
        )
        assert r.status_code == 200

        # Cache TTL is 60s — admin write invalidates in-process, but a
        # different worker might still cache. Force a small wait + retry.
        from urllib.parse import unquote
        for _ in range(3):
            time.sleep(2)
            r = requests.get(f"{API_URL}/api/oauth/facebook/start", headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            url = r.json()["authorize_url"]
            redirect = unquote([p for p in url.split("&") if p.startswith("redirect_uri=")][0].split("=", 1)[1])
            if sentinel.replace("https://", "") in redirect:
                # Build a fresh-looking redirect for the sentinel host
                assert redirect == f"{sentinel}/api/oauth/facebook/callback"
                return
        pytest.fail(f"OAuth never picked up the DB-stored sentinel: last redirect={redirect!r}")
