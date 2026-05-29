"""Execution-layer key rotation — P1 wrap-up.

LinkedIn, TikTok, and Pinterest publishing helpers used to read their
client_id / client_secret from module-level env vars imported at process
start. After P1 we routed them through `app_config.get_config()` so the
admin can rotate them live via /admin/integrations — same UX as Meta
and YouTube.

This file locks down:
  1. All 8 new keys (3 LinkedIn-ish, 3 TikTok-ish, 3 Pinterest-ish; minus
     the LinkedIn redirect override which we intentionally don't expose
     because LinkedIn requires an exact-match registered redirect URI)
     show up in /api/admin/app-config.
  2. They're grouped under linkedin / tiktok / pinterest so the
     AdminIntegrations UI clusters them in their own sections.
  3. Secret keys are flagged secret (UI masks them).
  4. set → /status reflects configured=true. clear → configured=false.
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

ROTATABLE_KEYS = {
    "linkedin":  ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
    "tiktok":    ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI"],
    "pinterest": ["PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_REDIRECT_URI"],
}
ALL_KEYS = [k for ks in ROTATABLE_KEYS.values() for k in ks]
SECRET_KEYS = {"LINKEDIN_CLIENT_SECRET", "TIKTOK_CLIENT_SECRET", "PINTEREST_APP_SECRET"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _cleanup():
    """Wipe any test-injected app_config rows + cache around each test."""
    async def go():
        db = _mongo()
        await db.app_config.delete_many({"key": {"$in": ALL_KEYS}})
        AC.invalidate_cache()
    _run(go())
    yield
    _run(go())


class TestRegistry:
    """All execution-layer keys must surface in /admin/app-config."""

    def test_all_keys_present_and_grouped(self):
        r = requests.get(f"{API_URL}/api/admin/app-config",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        items = {it["key"]: it for it in r.json()["items"]}
        for group, keys in ROTATABLE_KEYS.items():
            for k in keys:
                assert k in items, f"{k} missing from registry"
                assert items[k]["group"] == group, \
                    f"{k} should be in group '{group}', got '{items[k]['group']}'"

    def test_secret_flag_correct(self):
        r = requests.get(f"{API_URL}/api/admin/app-config",
                         headers=HEADERS, timeout=10)
        items = {it["key"]: it for it in r.json()["items"]}
        for k in ALL_KEYS:
            expected_secret = k in SECRET_KEYS
            assert items[k]["secret"] is expected_secret, \
                f"{k}.secret should be {expected_secret}"


class TestRotationFlow:
    """Set a DB value → /status reflects configured=true. Clear → false."""

    @pytest.mark.parametrize("platform,id_key,secret_key,status_path", [
        ("linkedin",  "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "/api/oauth/linkedin/status"),
        ("tiktok",    "TIKTOK_CLIENT_KEY",  "TIKTOK_CLIENT_SECRET",   "/api/oauth/tiktok/status"),
        ("pinterest", "PINTEREST_APP_ID",   "PINTEREST_APP_SECRET",   "/api/oauth/pinterest/status"),
    ])
    def test_set_then_status_reflects(self, platform, id_key, secret_key, status_path):
        # Set both via admin endpoint
        fake_id     = f"fake-{platform}-id-{uuid.uuid4().hex[:6]}"
        fake_secret = f"fake-{platform}-secret-{uuid.uuid4().hex[:6]}"
        r1 = requests.put(f"{API_URL}/api/admin/app-config",
                          json={"key": id_key,     "value": fake_id},
                          headers=HEADERS, timeout=10)
        r2 = requests.put(f"{API_URL}/api/admin/app-config",
                          json={"key": secret_key, "value": fake_secret},
                          headers=HEADERS, timeout=10)
        assert r1.status_code == 200 and r2.status_code == 200

        # Cache TTL is 60s; force-invalidate so we see the new state immediately.
        AC.invalidate_cache()

        # /status should now report configured=true (no connection though).
        r = requests.get(f"{API_URL}{status_path}", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] is True, \
            f"{platform} configured should be true after admin-set, got {body}"
        assert body["connected"] is False

        # Now clear via empty value
        requests.put(f"{API_URL}/api/admin/app-config",
                     json={"key": id_key, "value": ""},
                     headers=HEADERS, timeout=10)
        requests.put(f"{API_URL}/api/admin/app-config",
                     json={"key": secret_key, "value": ""},
                     headers=HEADERS, timeout=10)
        AC.invalidate_cache()

        # If the .env file also has no creds, /status should now report
        # configured=false. If env has creds, the env value is the fallback
        # so configured remains true — only assert the truthy → false path
        # in environments where env doesn't already set the keys.
        env_has = bool(os.environ.get(id_key) and os.environ.get(secret_key))
        r = requests.get(f"{API_URL}{status_path}", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["configured"] is env_has


class TestStartGatesOnConfig:
    """`POST /oauth/<platform>/start` must 503 when neither DB nor env
    has credentials — preventing a half-configured connect attempt."""

    @pytest.mark.parametrize("start_path,id_key,secret_key", [
        ("/api/oauth/linkedin/start",  "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"),
        ("/api/oauth/tiktok/start",    "TIKTOK_CLIENT_KEY",  "TIKTOK_CLIENT_SECRET"),
        ("/api/oauth/pinterest/start", "PINTEREST_APP_ID",   "PINTEREST_APP_SECRET"),
    ])
    def test_503_when_no_creds(self, start_path, id_key, secret_key):
        # Skip the test if env already has creds — we can't simulate an
        # unconfigured state in that pod without touching the env file.
        if os.environ.get(id_key) or os.environ.get(secret_key):
            pytest.skip(f"{id_key}/{secret_key} present in env; cannot test unconfigured branch")
        r = requests.get(f"{API_URL}{start_path}", headers=HEADERS, timeout=10)
        assert r.status_code == 503, r.text
        assert "not configured" in r.text.lower()
