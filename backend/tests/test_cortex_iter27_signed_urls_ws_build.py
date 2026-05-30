"""Iter-27: Signed asset URLs (HMAC) + WS tickets + DELETE-cancel
pipeline + Whisper cost surfacing + PPTX hero slide + build-campaign.

Read-mostly; reuses existing fixture assets to avoid LLM credit burn.
"""
import os
import asyncio
import hmac
import hashlib
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SESSION = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
PPTX_ASSET_ID = "52a3b704722d4138b9e92a056a630dbb"
VIDEO_ASSET_ID = "3b8e06e6c7cf4500a3a9783e64b15587"
PPTX_KEY = f"{USER_ID}/{PPTX_ASSET_ID}.pptx"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.cookies.set("session_token", SESSION)
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def signing_secret():
    from dotenv import dotenv_values
    env = dotenv_values("/app/backend/.env")
    return (env.get("ASSET_SIGNING_SECRET")
            or env.get("EMERGENT_LLM_KEY")
            or "cortex-default-signing")


def _mint(key: str, secret: str, ttl: int = 3600):
    exp = int(time.time()) + ttl
    sig = hmac.new(secret.encode(), f"{key}|{exp}".encode(),
                   hashlib.sha256).hexdigest()
    return sig, exp


# ---------- Signed Asset URL ----------
class TestSignedAssetURL:
    def test_valid_signed_token_returns_200_no_cookie(self, signing_secret):
        sig, exp = _mint(PPTX_KEY, signing_secret, ttl=3600)
        r = requests.get(
            f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}",
            params={"token": sig, "exp": exp})
        assert r.status_code == 200, r.text[:200]
        assert len(r.content) > 100

    def test_tampered_token_returns_403(self, signing_secret):
        sig, exp = _mint(PPTX_KEY, signing_secret, ttl=3600)
        bad = ("0" * 64) if not sig.startswith("0") else ("f" * 64)
        r = requests.get(
            f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}",
            params={"token": bad, "exp": exp})
        assert r.status_code == 403

    def test_expired_token_returns_403(self, signing_secret):
        exp = int(time.time()) - 60
        sig = hmac.new(signing_secret.encode(),
                       f"{PPTX_KEY}|{exp}".encode(),
                       hashlib.sha256).hexdigest()
        r = requests.get(
            f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}",
            params={"token": sig, "exp": exp})
        assert r.status_code == 403

    def test_token_for_different_key_returns_403(self, signing_secret):
        other_key = f"{USER_ID}/nonexistent.pptx"
        sig, exp = _mint(other_key, signing_secret, ttl=3600)
        r = requests.get(
            f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}",
            params={"token": sig, "exp": exp})
        assert r.status_code == 403

    def test_cookie_auth_still_works(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}")
        assert r.status_code == 200
        assert len(r.content) > 100

    def test_cookie_auth_wrong_user_prefix_403(self, client):
        wrong_key = "someone_else/file.pptx"
        r = client.get(f"{BASE_URL}/api/cortex/assets/file/{wrong_key}")
        assert r.status_code == 403

    def test_no_auth_no_token_fails(self):
        r = requests.get(f"{BASE_URL}/api/cortex/assets/file/{PPTX_KEY}")
        assert r.status_code in (401, 403)


# ---------- WS ticket ----------
class TestWsTicket:
    def test_ws_ticket_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/auth/ws-ticket")
        assert r.status_code == 401

    def test_ws_ticket_shape(self, client):
        r = client.post(f"{BASE_URL}/api/auth/ws-ticket")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "ticket" in body and "expires_at" in body
        assert body["ticket"].startswith("wst_")
        assert len(body["ticket"]) >= 30
        from datetime import datetime, timezone
        exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        delta = (exp - datetime.now(timezone.utc)).total_seconds()
        assert 60 <= delta <= 120, f"expires_at delta = {delta}s"

    def test_ws_ticket_single_use(self, client):
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets lib not installed")

        r = client.post(f"{BASE_URL}/api/auth/ws-ticket")
        assert r.status_code == 200
        ticket = r.json()["ticket"]

        ws_base = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{ws_base}/api/ws/hitl-inbox?token={ticket}"

        async def _connect_and_recv():
            async with websockets.connect(url, open_timeout=15,
                                          close_timeout=5) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                return msg

        loop = asyncio.new_event_loop()
        try:
            msg = loop.run_until_complete(_connect_and_recv())
            assert msg
        finally:
            loop.close()

        # Replay same ticket → should fail (single-use consumed)
        async def _replay():
            try:
                async with websockets.connect(url, open_timeout=10,
                                              close_timeout=5) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=3)
                    return "accepted"
            except Exception as e:
                return f"rejected:{type(e).__name__}"

        loop2 = asyncio.new_event_loop()
        try:
            result = loop2.run_until_complete(_replay())
        finally:
            loop2.close()
        assert "rejected" in result, f"single-use NOT enforced: {result}"


# ---------- Whisper cost on video asset ----------
class TestWhisperCost:
    def test_video_extraction_meta_has_cost(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/assets/{VIDEO_ASSET_ID}")
        assert r.status_code == 200
        meta = r.json().get("extraction_meta", {})
        assert "transcription_cost_usd" in meta
        cost = meta["transcription_cost_usd"]
        assert isinstance(cost, (int, float))
        if cost > 0:
            assert meta.get("transcription_provider") == "whisper-1"
            assert 0.0001 <= cost <= 0.01, f"unexpected cost {cost}"
        else:
            assert meta.get("transcription_provider") in (None, "")


# ---------- PPTX hero slide ----------
class TestPPTXHeroSlide:
    def test_pptx_meta_has_hero_fields(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/assets/{PPTX_ASSET_ID}")
        assert r.status_code == 200
        body = r.json()
        meta = body.get("extraction_meta", {})
        for k in ("hero_slide_index", "hero_slide_score",
                  "hero_image_count", "thumb_format"):
            assert k in meta, f"missing {k}"
        assert meta["thumb_format"] in ("png", "jpeg", "jpg")
        assert meta["hero_slide_index"] == 0
        assert meta["hero_slide_score"] >= 3.0
        assert body.get("thumb_b64") and len(body["thumb_b64"]) > 500


# ---------- Build campaign endpoint (shape only — no costly full build) ----------
class TestBuildCampaignFromAsset:
    def test_404_for_unknown_asset(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/assets/does_not_exist_xyz/build-campaign")
        assert r.status_code == 404


# ---------- DELETE pipeline cancel ----------
class TestDeleteCampaignCancel:
    def test_delete_unknown_404(self, client):
        r = client.delete(
            f"{BASE_URL}/api/cortex/campaigns/does_not_exist_xyz")
        assert r.status_code == 404


# ---------- Signed URLs in campaign creatives ----------
class TestSignedUrlsInCampaignCreatives:
    def test_campaign_creative_media_url_is_signed(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/campaigns")
        assert r.status_code == 200
        data = r.json()
        campaigns = data.get("campaigns") if isinstance(data, dict) else data
        if not campaigns:
            pytest.skip("no campaigns")
        found_signed = False
        for c in campaigns[:8]:
            cid = c.get("id")
            if not cid:
                continue
            rr = client.get(f"{BASE_URL}/api/cortex/campaigns/{cid}")
            if rr.status_code != 200:
                continue
            detail = rr.json()
            posts = detail.get("posts") or detail.get("social_posts") or []
            for p in posts:
                url = p.get("media_url")
                if url and "token=" in url and "exp=" in url:
                    found_signed = True
                    rrr = requests.get(url)
                    assert rrr.status_code in (200, 404)
                    return
        if not found_signed:
            pytest.skip("no campaign creative with signed media_url found")
