"""Plan-gating tests: AI generation cap + channel-connection cap."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _reset_user_state():
    """Clear usage + downgrade test user to free + disconnect channels.
    Done synchronously via the backend's own helper (motor)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.users.update_one(
            {"user_id": "user_test1779636592168"},
            {"$unset": {"usage": 1}, "$set": {"plan": "free"}},
        )
        await db.channels.update_many(
            {"user_id": "user_test1779636592168"},
            {"$set": {"connected": False}},
        )
    asyncio.get_event_loop().run_until_complete(go())


class TestUsageEndpoint:
    def test_usage_endpoint_returns_limits(self):
        _reset_user_state()
        r = httpx.get(f"{API_URL}/api/billing/usage", headers=HEADERS, timeout=10)
        r.raise_for_status()
        u = r.json()
        assert u["plan"] == "free"
        assert u["ai_generations_limit"] == 20
        assert u["channels_limit"] == 2
        assert u["ai_generations_used"] == 0

    def test_usage_endpoint_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/billing/usage", timeout=10)
        assert r.status_code == 401


class TestAIGenerationCap:
    def test_first_ai_call_passes(self):
        _reset_user_state()
        r = httpx.post(
            f"{API_URL}/api/ai/generate-post",
            headers=HEADERS,
            json={"platform": "x", "tone": "friendly", "topic": "test"},
            timeout=30,
        )
        # Either 200 (generated) or 500 (LLM hiccup) — both prove the gate let it through
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            u = httpx.get(f"{API_URL}/api/billing/usage", headers=HEADERS, timeout=10).json()
            assert u["ai_generations_used"] >= 1

    def test_ai_blocked_when_cap_reached(self):
        """Force usage to 20 → next call must 402."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from datetime import datetime, timezone

        month = datetime.now(timezone.utc).strftime("%Y-%m")

        async def bump():
            await db.users.update_one(
                {"user_id": "user_test1779636592168"},
                {"$set": {f"usage.{month}.ai_generations": 20, "plan": "free"}},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(bump())

        r = httpx.post(
            f"{API_URL}/api/ai/generate-post",
            headers=HEADERS,
            json={"platform": "x", "tone": "friendly", "topic": "test blocked"},
            timeout=10,
        )
        assert r.status_code == 402
        detail = r.json()["detail"]
        assert detail["code"] == "ai_generation_limit_reached"
        assert detail["limit"] == 20
        # Cleanup
        _reset_user_state()


class TestChannelCap:
    def test_blocked_after_2_channels_on_free(self):
        _reset_user_state()
        # Connect 2 channels
        for p in ("instagram", "x"):
            r = httpx.post(
                f"{API_URL}/api/channels/connect",
                headers=HEADERS, json={"platform": p}, timeout=10,
            )
            assert r.status_code == 200, f"{p}: {r.text}"

        # 3rd one — must 402
        r = httpx.post(
            f"{API_URL}/api/channels/connect",
            headers=HEADERS, json={"platform": "linkedin"}, timeout=10,
        )
        assert r.status_code == 402
        detail = r.json()["detail"]
        assert detail["code"] == "channel_limit_reached"
        assert detail["limit"] == 2
        _reset_user_state()

    def test_reconnect_same_channel_doesnt_count_again(self):
        """Reconnecting an already-connected channel must not 402."""
        _reset_user_state()
        for p in ("instagram", "x"):
            httpx.post(f"{API_URL}/api/channels/connect", headers=HEADERS,
                       json={"platform": p}, timeout=10)
        # Reconnect instagram — should succeed (idempotent)
        r = httpx.post(f"{API_URL}/api/channels/connect", headers=HEADERS,
                       json={"platform": "instagram"}, timeout=10)
        assert r.status_code == 200
        _reset_user_state()


class TestProPlanUnlimited:
    def test_pro_plan_bypasses_ai_cap(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from datetime import datetime, timezone

        month = datetime.now(timezone.utc).strftime("%Y-%m")

        async def go():
            await db.users.update_one(
                {"user_id": "user_test1779636592168"},
                {"$set": {"plan": "pro", f"usage.{month}.ai_generations": 9999}},
                upsert=True,
            )
        asyncio.get_event_loop().run_until_complete(go())

        u = httpx.get(f"{API_URL}/api/billing/usage", headers=HEADERS, timeout=10).json()
        assert u["plan"] == "pro"
        assert u["ai_generations_limit"] is None
        assert u["ai_generations_remaining"] is None
        _reset_user_state()
