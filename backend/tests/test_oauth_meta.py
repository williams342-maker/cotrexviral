"""Facebook + Instagram OAuth (shared Meta app) tests.

These tests exercise the parts that DON'T need a live Meta credential: the
auth flow, the /start endpoint generating a valid authorize URL, the
configuration error path (503), and the HEAD probe Meta uses to verify the
redirect URI before approving the app.
"""
import os
import asyncio
import importlib
import httpx
from urllib.parse import urlparse, parse_qs

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}"}


def _set_meta_creds_in_process(app_id="test_app_id", app_secret="test_app_secret"):
    """Patch the running backend's core constants for tests that need to
    pretend the env vars are configured. NOTE: this only affects the in-test
    imports — the actual live backend stays unconfigured (which is what we
    want for the 503 path)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from routes import oauth_meta
    oauth_meta.META_APP_ID = app_id
    oauth_meta.META_APP_SECRET = app_secret
    return oauth_meta


def _restore_meta_creds():
    import sys
    sys.path.insert(0, "/app/backend")
    from routes import oauth_meta
    oauth_meta.META_APP_ID = ""
    oauth_meta.META_APP_SECRET = ""


# -----------------------------------------------------------------------------
# Auth + 503-when-unconfigured tests run against the LIVE backend over HTTP.
# These match what Meta and your users will actually experience.
# -----------------------------------------------------------------------------
class TestStatusEndpoints:
    def test_facebook_status_anon(self):
        r = httpx.get(f"{API_URL}/api/oauth/facebook/status", timeout=10)
        assert r.status_code == 401

    def test_instagram_status_anon(self):
        r = httpx.get(f"{API_URL}/api/oauth/instagram/status", timeout=10)
        assert r.status_code == 401

    def test_facebook_status_authed(self):
        r = httpx.get(f"{API_URL}/api/oauth/facebook/status", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "configured" in body
        assert "connected" in body
        assert body["connected"] is False

    def test_instagram_status_authed(self):
        r = httpx.get(f"{API_URL}/api/oauth/instagram/status", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["connected"] is False


class TestStartReturnsAuthorizeUrl:
    """When Meta creds are NOT configured, /start should fail loudly (503),
    not silently return a broken URL. This protects the user from clicking
    Connect and seeing a Meta "invalid app id" error."""

    def test_facebook_start_503_when_unconfigured(self):
        r = httpx.get(f"{API_URL}/api/oauth/facebook/start", headers=H, timeout=10)
        # When the live backend has no META_APP_ID, /start MUST 503.
        # If it's actually configured (e.g. you've set the env), this test is
        # skipped via the body check.
        if r.status_code == 200:
            # User has provided real creds — verify URL shape instead.
            url = r.json()["authorize_url"]
            assert "facebook.com" in url
            assert "/dialog/oauth" in url
            qs = parse_qs(urlparse(url).query)
            assert "client_id" in qs
            assert "state" in qs
            assert "redirect_uri" in qs
            assert qs["response_type"] == ["code"]
            assert "pages_manage_posts" in qs["scope"][0]
        else:
            assert r.status_code == 503
            assert "META_APP_ID" in r.text

    def test_instagram_start_503_when_unconfigured(self):
        r = httpx.get(f"{API_URL}/api/oauth/instagram/start", headers=H, timeout=10)
        if r.status_code == 200:
            url = r.json()["authorize_url"]
            assert "facebook.com" in url  # IG Business Login uses the FB dialog
            qs = parse_qs(urlparse(url).query)
            assert "instagram_basic" in qs["scope"][0]
            assert "instagram_content_publish" in qs["scope"][0]
        else:
            assert r.status_code == 503


class TestCallbackProbe:
    """Meta sends a HEAD or empty GET to verify the redirect URI is reachable
    BEFORE approving the app. Our callback must return 200 in that case
    (not 405, not 400) — otherwise the app review fails before a human even
    looks at it."""

    def test_facebook_callback_head_returns_200(self):
        r = httpx.head(f"{API_URL}/api/oauth/facebook/callback", timeout=10)
        assert r.status_code == 200

    def test_instagram_callback_head_returns_200(self):
        r = httpx.head(f"{API_URL}/api/oauth/instagram/callback", timeout=10)
        assert r.status_code == 200

    def test_callback_with_error_redirects_not_500(self):
        # Meta sends `error=access_denied` when the user clicks "Cancel" on
        # the consent dialog. We must redirect them to /dashboard/channels
        # with a friendly query, NOT return a 500.
        r = httpx.get(
            f"{API_URL}/api/oauth/facebook/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            timeout=10,
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "facebook=denied" in r.headers.get("location", "")

    def test_callback_without_code_or_state_400(self):
        r = httpx.get(f"{API_URL}/api/oauth/facebook/callback", timeout=10)
        # No code, no error, GET (not HEAD) → invalid
        assert r.status_code == 400

    def test_callback_invalid_state_400(self):
        r = httpx.get(
            f"{API_URL}/api/oauth/facebook/callback",
            params={"code": "fake_code", "state": "definitely_not_a_real_state"},
            timeout=10,
        )
        assert r.status_code == 400


class TestDisconnectIdempotent:
    """Disconnect should always succeed (200), even if there's no existing
    connection — this lets the frontend safely call it on every "Disconnect"
    click without worrying about state."""

    def test_facebook_disconnect_when_not_connected(self):
        r = httpx.delete(f"{API_URL}/api/oauth/facebook", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_instagram_disconnect_when_not_connected(self):
        r = httpx.delete(f"{API_URL}/api/oauth/instagram", headers=H, timeout=10)
        assert r.status_code == 200


class TestScopeMinimality:
    """We must request the minimum scopes — Meta App Review reviewers reject
    apps asking for permissions they don't use."""

    def test_facebook_scope_minimal(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta
        # No excess permissions that we don't have a use case for.
        forbidden = {"user_friends", "user_birthday", "user_photos",
                     "publish_to_groups", "ads_management", "business_management"}
        assert not (set(oauth_meta.FACEBOOK_SCOPES) & forbidden)
        # Must include the publishing scope.
        assert "pages_manage_posts" in oauth_meta.FACEBOOK_SCOPES

    def test_instagram_scope_minimal(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta
        forbidden = {"instagram_manage_messages", "instagram_manage_comments",
                     "instagram_manage_insights"}
        assert not (set(oauth_meta.INSTAGRAM_SCOPES) & forbidden)
        assert "instagram_content_publish" in oauth_meta.INSTAGRAM_SCOPES
        # IG Business publishing requires both the basic + the Pages list.
        assert "instagram_basic" in oauth_meta.INSTAGRAM_SCOPES
        assert "pages_show_list" in oauth_meta.INSTAGRAM_SCOPES


class TestRedirectUriShape:
    """The redirect URI must match EXACTLY what the user pastes in the Meta
    developer portal. Validate the shape so regressions don't silently break
    app review."""

    def test_default_redirect_uri_uses_public_site(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import oauth_meta
        # Save and clear override
        prev = oauth_meta.META_REDIRECT_URI_OVERRIDE
        oauth_meta.META_REDIRECT_URI_OVERRIDE = ""
        try:
            assert oauth_meta._redirect_uri("facebook").endswith("/api/oauth/facebook/callback")
            assert oauth_meta._redirect_uri("instagram").endswith("/api/oauth/instagram/callback")
        finally:
            oauth_meta.META_REDIRECT_URI_OVERRIDE = prev
