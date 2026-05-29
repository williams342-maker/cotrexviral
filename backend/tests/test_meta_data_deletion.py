"""Meta data-deletion-callback tests.

Verifies the webhook + status endpoint behave per Meta's spec:
  • HMAC verification (rejects forged + malformed signed_requests).
  • Best-effort deletion of facebook_connections / instagram_connections
    / channels rows on a match.
  • Returns the spec-shaped {url, confirmation_code} JSON.
  • Status page renders the right summary for a valid code, 404 otherwise.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
# Pull the DB-stored secret since it may not be in env anymore (Phase 5 moved
# meta credentials into app_config). Falls back to env for backward compat.
def _load_meta_secret():
    import asyncio
    from routes.app_config import get_config
    async def go():
        return await get_config("META_APP_SECRET")
    return asyncio.get_event_loop().run_until_complete(go())

META_APP_SECRET = _load_meta_secret() or os.environ.get("META_APP_SECRET", "")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def _make_signed_request(payload: dict, secret: str) -> str:
    """Build a Meta-style signed_request — base64url(sig).base64url(payload)."""
    payload_str = json.dumps(payload, separators=(",", ":"))
    payload_b64 = _b64url(payload_str.encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return f"{_b64url(sig)}.{payload_b64}"


SKIP_REASON = "META_APP_SECRET not set — set it in /app/backend/.env to run these"
needs_secret = pytest.mark.skipif(not META_APP_SECRET, reason=SKIP_REASON)


class TestSignedRequestParsing:

    @needs_secret
    def test_rejects_missing_signed_request(self):
        r = requests.post(f"{API_URL}/api/meta/data-deletion-callback", timeout=10)
        # FastAPI returns 422 for the missing required Form field
        assert r.status_code in (400, 422), r.text

    @needs_secret
    def test_rejects_malformed(self):
        r = requests.post(
            f"{API_URL}/api/meta/data-deletion-callback",
            data={"signed_request": "no-dot-here"}, timeout=10,
        )
        assert r.status_code == 400, r.text

    @needs_secret
    def test_rejects_forged_hmac(self):
        """A signed_request HMAC'd with the WRONG secret must be rejected."""
        signed = _make_signed_request(
            {"algorithm": "HMAC-SHA256", "user_id": "fb_user_test_forged"},
            "totally-not-the-real-secret",
        )
        r = requests.post(
            f"{API_URL}/api/meta/data-deletion-callback",
            data={"signed_request": signed}, timeout=10,
        )
        assert r.status_code == 400, r.text

    @needs_secret
    def test_rejects_missing_user_id(self):
        signed = _make_signed_request(
            {"algorithm": "HMAC-SHA256"}, META_APP_SECRET,
        )
        r = requests.post(
            f"{API_URL}/api/meta/data-deletion-callback",
            data={"signed_request": signed}, timeout=10,
        )
        assert r.status_code == 400, r.text


class TestHappyPath:

    @needs_secret
    def test_callback_returns_spec_shape_and_cleans_up(self):
        """A valid signed_request returns {url, confirmation_code} per Meta
        spec AND deletes matching connection rows."""
        fb_user_id = f"fb_test_{uuid.uuid4().hex[:10]}"
        internal_user_id = f"u_test_{uuid.uuid4().hex[:10]}"

        async def seed():
            db = _mongo()
            await db.facebook_connections.insert_one({
                "id": uuid.uuid4().hex,
                "user_id": internal_user_id,
                "fb_user_id": fb_user_id,
                "user_access_token": "test_token",
            })
            await db.channels.insert_one({
                "id": uuid.uuid4().hex,
                "user_id": internal_user_id,
                "platform": "facebook",
                "connected": True,
            })
        _run(seed())

        try:
            signed = _make_signed_request(
                {"algorithm": "HMAC-SHA256", "user_id": fb_user_id,
                 "issued_at": 1700000000},
                META_APP_SECRET,
            )
            r = requests.post(
                f"{API_URL}/api/meta/data-deletion-callback",
                data={"signed_request": signed}, timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert "url" in body
            assert "confirmation_code" in body
            assert body["url"].endswith(f"/{body['confirmation_code']}")
            assert "/api/meta/data-deletion-status/" in body["url"]

            # Cleanup actually happened
            async def check():
                db = _mongo()
                fb = await db.facebook_connections.count_documents({"fb_user_id": fb_user_id})
                ch = await db.channels.count_documents({"user_id": internal_user_id, "platform": "facebook"})
                rec = await db.meta_deletion_requests.find_one(
                    {"confirmation_code": body["confirmation_code"]}, {"_id": 0},
                )
                return fb, ch, rec
            fb_count, ch_count, rec = _run(check())
            assert fb_count == 0, "facebook_connections should be deleted"
            assert ch_count == 0, "channels row should be deleted"
            assert rec is not None
            assert rec["fb_user_id"] == fb_user_id
            assert rec["matched_user_id"] == internal_user_id
            assert rec["status"] == "completed"

            # Status page renders. Note: body["url"] points to PUBLIC_SITE_URL
            # (cortexviral.com); the route is the same on this preview API.
            status_path = body["url"].split("/api/meta/", 1)[1]
            r2 = requests.get(f"{API_URL}/api/meta/{status_path}", timeout=10)
            assert r2.status_code == 200, r2.text
            assert "Status: completed" in r2.text
            assert body["confirmation_code"] in r2.text
        finally:
            async def cleanup():
                db = _mongo()
                await db.facebook_connections.delete_many({"fb_user_id": fb_user_id})
                await db.channels.delete_many({"user_id": internal_user_id})
                await db.meta_deletion_requests.delete_many({"fb_user_id": fb_user_id})
            _run(cleanup())

    @needs_secret
    def test_callback_succeeds_even_with_no_match(self):
        """Meta sends the webhook for users who may not even be in our DB
        (e.g. they tested then revoked before we recorded anything). We
        still must return 200 with spec shape."""
        signed = _make_signed_request(
            {"algorithm": "HMAC-SHA256",
             "user_id": f"fb_unknown_{uuid.uuid4().hex[:10]}",
             "issued_at": 1700000000},
            META_APP_SECRET,
        )
        r = requests.post(
            f"{API_URL}/api/meta/data-deletion-callback",
            data={"signed_request": signed}, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "confirmation_code" in body
        # Cleanup the stub record we just created
        async def cleanup():
            db = _mongo()
            await db.meta_deletion_requests.delete_many({"confirmation_code": body["confirmation_code"]})
        _run(cleanup())


class TestStatusEndpoint:

    def test_unknown_code_returns_404(self):
        r = requests.get(
            f"{API_URL}/api/meta/data-deletion-status/this_code_does_not_exist",
            timeout=10,
        )
        assert r.status_code == 404
