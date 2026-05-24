"""Regression tests for the LinkedIn OAuth scaffold.

These run WITHOUT LinkedIn credentials configured (default in this preview pod)
and verify the unconfigured-state contracts. End-to-end OAuth testing requires
real LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET — covered manually once the
user provides credentials.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_oauth_status_when_unconfigured():
    r = httpx.get(f"{API_URL}/api/oauth/linkedin/status", headers=HEADERS, timeout=10)
    r.raise_for_status()
    body = r.json()
    assert "configured" in body
    assert body["connected"] is False
    assert body["connection"] is None


def test_oauth_start_returns_503_when_unconfigured():
    """If LINKEDIN_CLIENT_ID is empty in .env, /start should 503 with a clear message."""
    r = httpx.get(f"{API_URL}/api/oauth/linkedin/start", headers=HEADERS, timeout=10)
    # If user has configured credentials in their pod, this will be 200 instead — that's OK.
    if r.status_code == 503:
        assert "LINKEDIN_CLIENT_ID" in r.text
    else:
        assert r.status_code == 200
        assert "linkedin.com/oauth/v2/authorization" in r.json()["authorize_url"]


def test_oauth_start_requires_auth():
    """The OAuth start endpoint must require a logged-in user."""
    r = httpx.get(f"{API_URL}/api/oauth/linkedin/start", timeout=10)
    assert r.status_code == 401


def test_oauth_callback_rejects_missing_code():
    r = httpx.get(f"{API_URL}/api/oauth/linkedin/callback", timeout=10)
    assert r.status_code == 400


def test_oauth_callback_rejects_bad_state():
    r = httpx.get(
        f"{API_URL}/api/oauth/linkedin/callback?code=abc&state=garbage",
        timeout=10,
    )
    # Either 400 (bad state) OR 503 (creds not configured) — both prove the
    # endpoint is wired correctly without leaking 500s.
    assert r.status_code in (400, 503)


def test_publish_to_non_linkedin_platform_unaffected():
    """Publishing to a non-LinkedIn platform should still work even when LinkedIn is unconfigured."""
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={"content": "li-test", "platforms": ["instagram"]},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "published"
    # No LinkedIn dispatch attempted since instagram only
    assert body.get("dispatch", {}).get("linkedin") is None
