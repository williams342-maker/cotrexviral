"""API-level tests for the WordPress self-hosted connector.

Exercises the live FastAPI endpoints through REACT_APP_BACKEND_URL — no
mocks — using the persistent test session from /app/memory/test_credentials.md.

Covered scenarios (from iteration_35 review request):
  - /wordpress/test with a bogus (unreachable) URL returns 400 (not 500)
  - /wordpress/test without auth returns 401
  - /wordpress/connect without auth returns 401
  - /wordpress/connect with http:// site_url returns 400 with https:// hint
  - /wordpress/status returns {connected: false} when no channel exists
  - /channels response includes site_url field on the WordPress row
"""
from __future__ import annotations

import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to reading from the frontend/.env file (system prompt guarantee).
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

TEST_SESSION = "test_session_1779636592168"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def auth_client():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TEST_SESSION}",
    })
    # Sanity check: make sure the test session is still valid.
    r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Test session invalid: /auth/me returned {r.status_code}")
    return s


@pytest.fixture(autouse=True)
def _cleanup_wp_channel(auth_client):
    """Ensure the WordPress channel row is absent before + after each test
    so /status returns {connected: false} for the empty-state tests and no
    residual state leaks between iterations."""
    try:
        auth_client.post(
            f"{BASE_URL}/api/channels/disconnect",
            json={"platform": "wordpress_selfhosted"},
            timeout=15,
        )
    except Exception:
        pass
    yield
    try:
        auth_client.post(
            f"{BASE_URL}/api/channels/disconnect",
            json={"platform": "wordpress_selfhosted"},
            timeout=15,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestWordPressAuth:
    def test_test_endpoint_requires_auth(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/wordpress/test", json={
            "site_url": "https://example.com",
            "username": "u",
            "application_password": "p",
        }, timeout=15)
        assert r.status_code == 401, f"expected 401 without auth, got {r.status_code}: {r.text[:200]}"

    def test_connect_endpoint_requires_auth(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/wordpress/connect", json={
            "site_url": "https://example.com",
            "username": "u",
            "application_password": "p",
        }, timeout=15)
        assert r.status_code == 401

    def test_status_endpoint_requires_auth(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/wordpress/status", timeout=15)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Validation paths
# ---------------------------------------------------------------------------

class TestWordPressValidation:
    def test_test_bogus_domain_returns_400_not_500(self, auth_client):
        """DNS/connect failure must surface as a friendly 400, never a 500."""
        r = auth_client.post(f"{BASE_URL}/api/wordpress/test", json={
            "site_url": "https://this-domain-does-not-exist-9876.com",
            "username": "u",
            "application_password": "p",
        }, timeout=30)
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:300]}"
        detail = (r.json().get("detail") or "").lower()
        assert "could not reach" in detail or "timed out" in detail or "wordpress" in detail

    def test_connect_http_site_url_returns_400(self, auth_client):
        r = auth_client.post(f"{BASE_URL}/api/wordpress/connect", json={
            "site_url": "http://example.com",
            "username": "u",
            "application_password": "p",
        }, timeout=15)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "https://" in detail, f"expected https:// hint in error, got: {detail!r}"

    def test_test_http_site_url_returns_400(self, auth_client):
        """Same https-only rule should apply to /test."""
        r = auth_client.post(f"{BASE_URL}/api/wordpress/test", json={
            "site_url": "http://example.com",
            "username": "u",
            "application_password": "p",
        }, timeout=15)
        assert r.status_code == 400
        assert "https://" in r.json().get("detail", "")


# ---------------------------------------------------------------------------
# Status / channels listing
# ---------------------------------------------------------------------------

class TestWordPressStatusAndChannels:
    def test_status_without_channel_returns_disconnected(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/wordpress/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("connected") is False, f"expected connected:false, got {data!r}"

    def test_channels_list_includes_site_url_field_on_wp_row(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/channels", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        wp_rows = [row for row in rows if row.get("platform") == "wordpress_selfhosted"]
        assert wp_rows, "wordpress_selfhosted row missing from GET /api/channels"
        wp = wp_rows[0]
        # Field must be present (schema contract). null is fine when not connected.
        assert "site_url" in wp, f"'site_url' key missing from WP channel row: {wp}"
        assert wp.get("connected") is False
        assert wp.get("site_url") is None
