"""Trend Engine + A/B Hook Lab integration tests."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _set_plan(plan: str, comped: bool = True):
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": comped, "reason": "test"}, timeout=10,
    ).raise_for_status()


def _reset():
    """Reset user to free + clear trend cache."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.users.update_one(
            {"user_id": USER_ID},
            {"$set": {"plan": "free", "comped": False},
             "$unset": {"comped_by": 1, "comped_reason": 1, "comped_at": 1, "subscription_status": 1}},
        )
        await db.trend_cache.delete_many({})

    asyncio.get_event_loop().run_until_complete(go())


class TestTrendEngineGating:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/ai/trends", timeout=15)
        assert r.status_code == 401

    def test_free_plan_blocked_with_402(self):
        _reset()
        r = httpx.get(f"{API_URL}/api/ai/trends", headers=H, timeout=15)
        assert r.status_code == 402
        body = r.json()
        assert body["detail"]["code"] == "feature_locked"

    def test_starter_plan_blocked(self):
        _reset()
        _set_plan("starter", comped=True)
        r = httpx.get(f"{API_URL}/api/ai/trends", headers=H, timeout=15)
        assert r.status_code == 402
        _reset()

    def test_growth_plan_succeeds_returns_trends(self):
        _reset()
        _set_plan("growth", comped=True)
        r = httpx.get(f"{API_URL}/api/ai/trends", headers=H, timeout=45)
        r.raise_for_status()
        body = r.json()
        assert "trends" in body
        assert isinstance(body["trends"], list)
        assert len(body["trends"]) >= 4
        first = body["trends"][0]
        assert first["hashtag"].startswith("#")
        assert isinstance(first["velocity"], int)
        assert 50 <= first["velocity"] <= 99
        assert first["sample"]
        assert first.get("source") in {"tiktok_creative_center", "ai_synthesised", "fallback"}
        _reset()


class TestTrendEngineCache:
    def test_cache_persists_between_requests(self):
        _reset()
        _set_plan("growth", comped=True)
        r1 = httpx.get(f"{API_URL}/api/ai/trends", headers=H, timeout=45)
        r1.raise_for_status()
        r2 = httpx.get(f"{API_URL}/api/ai/trends", headers=H, timeout=15)
        r2.raise_for_status()
        # Second call should be much faster (served from cache) and identical.
        assert r2.json()["cached_at"] == r1.json()["cached_at"]
        _reset()


class TestABLabGating:
    def test_requires_auth(self):
        r = httpx.post(f"{API_URL}/api/ai/ab-variations", json={"seed": "x"}, timeout=15)
        assert r.status_code == 401

    def test_free_plan_blocked_with_402(self):
        _reset()
        r = httpx.post(
            f"{API_URL}/api/ai/ab-variations", headers=H,
            json={"seed": "why most TikToks fail"}, timeout=15,
        )
        assert r.status_code == 402
        body = r.json()
        assert body["detail"]["code"] == "feature_not_in_plan"
        assert body["detail"]["feature"] == "ab_variations"

    def test_growth_plan_returns_scored_variants(self):
        _reset()
        _set_plan("growth", comped=True)
        r = httpx.post(
            f"{API_URL}/api/ai/ab-variations", headers=H,
            json={"seed": "why most TikToks fail in 2 seconds", "count": 5}, timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        assert body["seed"] == "why most TikToks fail in 2 seconds"
        assert body["platform"] == "tiktok"
        assert len(body["variants"]) == 5

        # Each variant has full structure
        for v in body["variants"]:
            assert v["text"]
            assert 0 <= v["score"] <= 100
            for axis in ("curiosity_gap", "specificity", "pattern_interrupt", "emotional_charge", "brevity"):
                assert axis in v["breakdown"]
                assert 0 <= v["breakdown"][axis] <= 20

        # Variants are sorted by score desc
        scores = [v["score"] for v in body["variants"]]
        assert scores == sorted(scores, reverse=True)
        _reset()

    def test_rejects_empty_seed(self):
        _reset()
        _set_plan("growth", comped=True)
        r = httpx.post(
            f"{API_URL}/api/ai/ab-variations", headers=H,
            json={"seed": "   "}, timeout=15,
        )
        assert r.status_code == 400
        _reset()

    def test_counts_against_ai_quota(self):
        """A/B Lab call should increment the user's monthly ai_generations counter."""
        _reset()
        _set_plan("starter", comped=True)
        # First, comp them to growth so they can call. Then check counter delta.
        _set_plan("growth", comped=True)
        before = httpx.get(f"{API_URL}/api/billing/usage", headers=H, timeout=10).json()
        before_count = before.get("ai_generations_used", 0)
        httpx.post(
            f"{API_URL}/api/ai/ab-variations", headers=H,
            json={"seed": "stop scrolling — here's the truth", "count": 3}, timeout=60,
        ).raise_for_status()
        after = httpx.get(f"{API_URL}/api/billing/usage", headers=H, timeout=10).json()
        after_count = after.get("ai_generations_used", 0)
        assert after_count == before_count + 1, (
            f"Expected ai_generations_used to increase by 1; was {before_count}, now {after_count}"
        )
        _reset()
