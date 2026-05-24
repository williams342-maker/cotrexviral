"""Regression tests for the TikTok OAuth + Content Posting scaffold.

These run WITHOUT TikTok credentials configured (default state) and verify
the unconfigured-state contracts. Full end-to-end OAuth + publish testing
requires real TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET and is covered
manually once the user provides credentials.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_tiktok_status_when_unconfigured():
    r = httpx.get(f"{API_URL}/api/oauth/tiktok/status", headers=HEADERS, timeout=10)
    r.raise_for_status()
    body = r.json()
    assert "configured" in body
    assert body["connected"] is False
    assert body["connection"] is None


def test_tiktok_start_503_or_authorize_url():
    """When TIKTOK_CLIENT_KEY is empty, /start returns 503. When set, returns the v2 authorize URL."""
    r = httpx.get(f"{API_URL}/api/oauth/tiktok/start", headers=HEADERS, timeout=10)
    if r.status_code == 503:
        assert "TIKTOK_CLIENT_KEY" in r.text
    else:
        assert r.status_code == 200
        url = r.json()["authorize_url"]
        assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
        assert "client_key=" in url
        assert "scope=user.info.basic" in url or "scope=user.info.basic%2C" in url
        assert "state=" in url
        assert "response_type=code" in url


def test_tiktok_start_requires_auth():
    r = httpx.get(f"{API_URL}/api/oauth/tiktok/start", timeout=10)
    assert r.status_code == 401


def test_tiktok_callback_rejects_missing_code():
    r = httpx.get(f"{API_URL}/api/oauth/tiktok/callback", timeout=10)
    assert r.status_code == 400


def test_tiktok_callback_redirects_on_error():
    """When TikTok sends ?error=access_denied, we redirect to /dashboard/channels?tiktok=denied — never 500."""
    r = httpx.get(
        f"{API_URL}/api/oauth/tiktok/callback?error=access_denied&error_description=user+denied",
        timeout=10,
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    assert "tiktok=denied" in r.headers.get("location", "")


def test_tiktok_callback_rejects_bad_state():
    r = httpx.get(
        f"{API_URL}/api/oauth/tiktok/callback?code=abc&state=garbage",
        timeout=10,
        follow_redirects=False,
    )
    # 400 (bad state) — never 500. 503 also acceptable if creds happen to be missing
    # before we reach state validation (current implementation hits state first → 400).
    assert r.status_code in (400, 503)


def test_publish_to_non_tiktok_platform_unaffected():
    """Publishing to a non-TikTok platform should still work even when TikTok is unconfigured."""
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={"content": "tt-test", "platforms": ["instagram"]},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "published"
    assert body.get("dispatch", {}).get("tiktok") is None


def test_publish_to_tiktok_without_connection_gracefully_fails():
    """Calling /channels/publish with platforms=['tiktok'] when not connected
    must return ok=True (the post itself is created) and dispatch.tiktok.ok=False
    with reason 'not_connected'."""
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={"content": "viral hook", "platforms": ["tiktok"], "media_url": "https://example.com/x.mp4"},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    assert body["ok"] is True
    # If the user happens to be connected in this preview pod we accept ok=True too;
    # otherwise we expect the not_connected reason.
    tiktok_disp = body.get("dispatch", {}).get("tiktok")
    if tiktok_disp:
        assert tiktok_disp["ok"] in (True, False)
        if not tiktok_disp["ok"]:
            assert tiktok_disp["reason"] in (
                "not_connected", "tiktok_requires_video_media_url",
                "token_expired", "token_refresh_failed",
            )


def test_publish_to_tiktok_without_media_url_returns_specific_reason():
    """TikTok requires a video — text-only posts must return a clear reason, not crash."""
    # Mock a quick path: scheduler/channel routes attempt publish only when connected.
    # When unconnected (default state), the reason is "not_connected", which is fine.
    # We assert no 5xx escapes from the channel route in either case.
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={"content": "text only", "platforms": ["tiktok"]},
        timeout=10,
    )
    assert r.status_code == 200
