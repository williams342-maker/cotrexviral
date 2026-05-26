"""Pinterest OAuth (v5) tests — same shape as test_oauth_meta.py."""
import os
import httpx
from urllib.parse import urlparse, parse_qs

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}"}


class TestStatus:
    def test_anon_401(self):
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/status", timeout=10)
        assert r.status_code == 401

    def test_authed_returns_shape(self):
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/status", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        for k in ("configured", "connected", "username", "expires_at"):
            assert k in body
        assert body["connected"] is False


class TestStart:
    def test_start_503_when_unconfigured(self):
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/start", headers=H, timeout=10)
        # Live backend has no PINTEREST_APP_ID configured → 503.
        # If creds are configured, validate the URL shape instead.
        if r.status_code == 200:
            url = r.json()["authorize_url"]
            assert url.startswith("https://www.pinterest.com/oauth/")
            qs = parse_qs(urlparse(url).query)
            assert qs["response_type"] == ["code"]
            assert "pins:write" in qs["scope"][0]
            assert "boards:read" in qs["scope"][0]
            assert "state" in qs
            assert "client_id" in qs
            assert "redirect_uri" in qs
        else:
            assert r.status_code == 503
            assert "PINTEREST_APP_ID" in r.text


class TestCallback:
    def test_head_probe_returns_200(self):
        # Pinterest's app-review redirect-URI verification sends HEAD.
        r = httpx.head(f"{API_URL}/api/oauth/pinterest/callback", timeout=10)
        assert r.status_code == 200

    def test_user_denied_redirects_friendly(self):
        r = httpx.get(
            f"{API_URL}/api/oauth/pinterest/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            timeout=10,
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "pinterest=denied" in r.headers.get("location", "")

    def test_callback_missing_params_400(self):
        r = httpx.get(f"{API_URL}/api/oauth/pinterest/callback", timeout=10)
        assert r.status_code == 400

    def test_callback_invalid_state_400(self):
        r = httpx.get(
            f"{API_URL}/api/oauth/pinterest/callback",
            params={"code": "fake_code", "state": "not_a_real_state"},
            timeout=10,
        )
        assert r.status_code == 400


class TestDisconnect:
    def test_idempotent_when_not_connected(self):
        r = httpx.delete(f"{API_URL}/api/oauth/pinterest", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_anon_blocked(self):
        r = httpx.delete(f"{API_URL}/api/oauth/pinterest", timeout=10)
        assert r.status_code == 401


class TestScopeMinimality:
    """Don't request more than we use — Pinterest reviewers reject apps that
    over-ask for permissions. We currently use boards:read + pins:write +
    pins:read. No analytics, no ads."""

    def test_no_excess_scopes(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_pinterest
        excess = {"ads:read", "ads:write", "user_accounts:read",
                  "catalogs:read", "catalogs:write"}
        assert not (set(oauth_pinterest.SCOPES) & excess)
        assert "pins:write" in oauth_pinterest.SCOPES
        assert "boards:read" in oauth_pinterest.SCOPES


class TestRedirectUriShape:
    def test_default_redirect_uri(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_pinterest
        prev = oauth_pinterest.PINTEREST_REDIRECT_URI_OVERRIDE
        oauth_pinterest.PINTEREST_REDIRECT_URI_OVERRIDE = ""
        try:
            uri = oauth_pinterest._redirect_uri()
            assert uri.endswith("/api/oauth/pinterest/callback")
            assert uri.startswith("http")
        finally:
            oauth_pinterest.PINTEREST_REDIRECT_URI_OVERRIDE = prev
