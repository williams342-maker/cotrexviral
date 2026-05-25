"""Admin system settings: signups toggle + per-platform disable."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
H_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _reset_settings():
    """Reset to defaults via the admin API so the server's in-process cache
    is also invalidated (calling Mongo directly from pytest doesn't reach the
    running backend's cache)."""
    httpx.patch(
        f"{API_URL}/api/admin/settings",
        headers=H_ADMIN,
        json={"signups_enabled": True, "disabled_platforms": []},
        timeout=10,
    )


def _cleanup_test_channels():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.channels.delete_many({
            "user_id": "user_test1779636592168",
            "platform": {"$in": ["pinterest", "facebook"]},
        })
    asyncio.get_event_loop().run_until_complete(go())


class TestPublicSettingsEndpoint:
    def setup_method(self):
        _reset_settings()

    def teardown_method(self):
        _reset_settings()

    def test_public_endpoint_returns_defaults(self):
        r = httpx.get(f"{API_URL}/api/system/settings", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["signups_enabled"] is True
        assert body["disabled_platforms"] == []


class TestAdminSettingsEndpoint:
    def setup_method(self):
        _reset_settings()

    def teardown_method(self):
        _reset_settings()

    def test_admin_required(self):
        r = httpx.get(f"{API_URL}/api/admin/settings", timeout=10)
        assert r.status_code == 401

    def test_get_returns_current_settings(self):
        r = httpx.get(f"{API_URL}/api/admin/settings", headers=H_ADMIN, timeout=10)
        assert r.status_code == 200
        assert r.json()["signups_enabled"] is True

    def test_patch_signups_toggle_persists(self):
        r = httpx.patch(
            f"{API_URL}/api/admin/settings",
            headers=H_ADMIN,
            json={"signups_enabled": False},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["signups_enabled"] is False

        # Re-fetch via public endpoint to confirm it's visible
        pub = httpx.get(f"{API_URL}/api/system/settings", timeout=10)
        assert pub.json()["signups_enabled"] is False

    def test_patch_platforms_dedupes_and_sorts(self):
        r = httpx.patch(
            f"{API_URL}/api/admin/settings",
            headers=H_ADMIN,
            json={"disabled_platforms": ["pinterest", "facebook", "pinterest", "  ", ""]},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["disabled_platforms"] == ["facebook", "pinterest"]

    def test_partial_patch_preserves_other_field(self):
        # First disable a platform
        httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"disabled_platforms": ["facebook"]}, timeout=10,
        )
        # Then patch only signups_enabled — disabled_platforms must persist
        r = httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"signups_enabled": False}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["signups_enabled"] is False
        assert r.json()["disabled_platforms"] == ["facebook"]


class TestPlatformDisableEnforcement:
    def setup_method(self):
        _reset_settings()
        _cleanup_test_channels()

    def teardown_method(self):
        _reset_settings()
        _cleanup_test_channels()

    def test_connect_blocked_when_platform_disabled(self):
        # Disable pinterest
        httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"disabled_platforms": ["pinterest"]}, timeout=10,
        )

        r = httpx.post(
            f"{API_URL}/api/channels/connect",
            headers=H_ADMIN,
            json={"platform": "pinterest"},
            timeout=10,
        )
        assert r.status_code == 403
        assert "pinterest" in r.text.lower()

    def test_connect_works_for_non_disabled_platform(self):
        # Disable pinterest but try facebook — should work
        httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"disabled_platforms": ["pinterest"]}, timeout=10,
        )

        r = httpx.post(
            f"{API_URL}/api/channels/connect",
            headers=H_ADMIN,
            json={"platform": "facebook"},
            timeout=10,
        )
        assert r.status_code == 200, r.text

    def test_reconnect_blocked_by_admin_disable(self):
        """Even a reconnect of a previously-connected channel is blocked when
        the admin disables that platform (reconnect logic only bypasses the
        plan-tier cap, not the global kill-switch)."""
        # Connect first
        c1 = httpx.post(
            f"{API_URL}/api/channels/connect", headers=H_ADMIN,
            json={"platform": "pinterest"}, timeout=10,
        )
        assert c1.status_code == 200

        # Admin disables pinterest globally
        httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"disabled_platforms": ["pinterest"]}, timeout=10,
        )

        # Reconnect attempt → blocked
        c2 = httpx.post(
            f"{API_URL}/api/channels/connect", headers=H_ADMIN,
            json={"platform": "pinterest"}, timeout=10,
        )
        assert c2.status_code == 403


class TestSignupsToggleEnforcement:
    def setup_method(self):
        _reset_settings()

    def teardown_method(self):
        _reset_settings()

    def test_admin_create_works_even_with_signups_disabled(self):
        """Admin-create path bypasses the signup pause (otherwise an admin who
        pauses signups also locks themselves out of onboarding warm leads)."""
        import secrets
        email = f"adminbypass_{secrets.token_hex(4)}@signup-test.dev"

        # Disable signups
        httpx.patch(
            f"{API_URL}/api/admin/settings", headers=H_ADMIN,
            json={"signups_enabled": False}, timeout=10,
        )

        try:
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "Bypass", "send_email": False},
                timeout=15,
            )
            assert r.status_code == 200
            assert r.json()["new_user"] is True
        finally:
            import sys
            sys.path.insert(0, "/app/backend")
            from core import db

            async def cleanup():
                await db.users.delete_many({"email": email.lower()})
                await db.magic_links.delete_many({"email": email.lower()})
            asyncio.get_event_loop().run_until_complete(cleanup())
