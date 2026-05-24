"""Admin plan-tier override + comped-flag tests."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
ADMIN_USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _reset():
    """Reset admin test user to plain free, no comp, no subscription_status."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.users.update_one(
            {"user_id": ADMIN_USER_ID},
            {"$set": {"plan": "free", "comped": False},
             "$unset": {"comped_by": 1, "comped_reason": 1, "comped_at": 1, "subscription_status": 1}},
        )
    asyncio.get_event_loop().run_until_complete(go())


class TestAdminSetPlan:
    def test_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            json={"plan": "growth", "comped": True},
            timeout=10,
        )
        assert r.status_code == 401

    def test_rejects_unknown_plan(self):
        _reset()
        r = httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            headers=H,
            json={"plan": "platinum", "comped": True},
            timeout=10,
        )
        assert r.status_code == 422  # Pydantic Literal rejects

    def test_404_on_unknown_user(self):
        r = httpx.post(
            f"{API_URL}/api/admin/users/does_not_exist/plan",
            headers=H,
            json={"plan": "growth", "comped": True},
            timeout=10,
        )
        assert r.status_code == 404

    def test_set_plan_updates_user_and_persists_comp_metadata(self):
        _reset()
        r = httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            headers=H,
            json={"plan": "growth", "comped": True, "reason": "VIP creator"},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        assert body["plan"] == "growth"
        assert body["comped"] is True

        # Verify via admin/users listing
        users = httpx.get(f"{API_URL}/api/admin/users", headers=H, timeout=10).json()
        me = [u for u in users if u["user_id"] == ADMIN_USER_ID][0]
        assert me["plan"] == "growth"
        assert me["comped"] is True
        assert me.get("comped_reason") == "VIP creator"

        # Verify via billing/usage that the plan + entitlements flipped
        u = httpx.get(f"{API_URL}/api/billing/usage", headers=H, timeout=10).json()
        assert u["plan"] == "growth"
        assert u["comped"] is True
        assert u["ai_generations_limit"] is None  # Growth = unlimited
        assert u["features"]["trend_engine"] is True
        _reset()

    def test_uncomped_clears_metadata(self):
        _reset()
        # First comp
        httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            headers=H, json={"plan": "starter", "comped": True, "reason": "x"}, timeout=10,
        ).raise_for_status()
        # Then un-comp
        httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            headers=H, json={"plan": "free", "comped": False}, timeout=10,
        ).raise_for_status()

        users = httpx.get(f"{API_URL}/api/admin/users", headers=H, timeout=10).json()
        me = [u for u in users if u["user_id"] == ADMIN_USER_ID][0]
        assert me["plan"] == "free"
        assert me["comped"] is False
        assert not me.get("comped_reason")
        _reset()

    def test_audit_log_records_plan_change(self):
        _reset()
        httpx.post(
            f"{API_URL}/api/admin/users/{ADMIN_USER_ID}/plan",
            headers=H, json={"plan": "agency", "comped": True, "reason": "audit-log-test"}, timeout=10,
        ).raise_for_status()
        log = httpx.get(f"{API_URL}/api/admin/audit-log?limit=20", headers=H, timeout=10).json()
        recent = [e for e in log if e.get("action") == "set_user_plan"]
        assert recent, "set_user_plan should be in audit log"
        latest = recent[0]
        assert latest["details"]["to"] == "agency"
        assert latest["details"]["comped"] is True
        assert latest["details"]["reason"] == "audit-log-test"
        _reset()


class TestCompedImmunity:
    def test_comped_user_keeps_plan_when_past_due(self):
        """Direct DB sim: mark a user comped=true with past_due status, then
        verify billing/usage still reports the paid plan (not downgraded)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def setup():
            await db.users.update_one(
                {"user_id": ADMIN_USER_ID},
                {"$set": {"plan": "growth", "comped": True, "subscription_status": "past_due"}},
            )
        asyncio.get_event_loop().run_until_complete(setup())

        u = httpx.get(f"{API_URL}/api/billing/usage", headers=H, timeout=10).json()
        assert u["plan"] == "growth", "Comped users must keep their plan even when past_due"
        assert u["features"]["trend_engine"] is True
        _reset()

    def test_uncomped_user_falls_back_to_free_when_past_due(self):
        """Same setup but comped=false → past_due forces fallback to free."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def setup():
            await db.users.update_one(
                {"user_id": ADMIN_USER_ID},
                {"$set": {"plan": "growth", "comped": False, "subscription_status": "past_due"}},
            )
        asyncio.get_event_loop().run_until_complete(setup())

        u = httpx.get(f"{API_URL}/api/billing/usage", headers=H, timeout=10).json()
        assert u["plan"] == "free", "Non-comped past_due users must fall back to free"
        _reset()
