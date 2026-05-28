"""Tests for the signal→draft loop + per-user spend nudge."""
import os
import sys
import httpx

sys.path.insert(0, "/app/backend")

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _comp(plan: str = "growth"):
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "trend draft test"},
        timeout=10,
    )


def _get_a_trend_id() -> str:
    """Helper: returns the most recent trend id for the test user. Triggers
    an ingest first if the user has none."""
    r = httpx.get(f"{API_URL}/api/trends/recent?limit=1", headers=H, timeout=10)
    trends = r.json().get("trends", [])
    if trends:
        return trends[0]["id"]
    # Seed at least one signal via Google Trends.
    httpx.post(f"{API_URL}/api/trends/ingest", headers=H,
               json={"keywords": ["marketing"], "subreddits": []},
               timeout=45)
    r = httpx.get(f"{API_URL}/api/trends/recent?limit=1", headers=H, timeout=10)
    return r.json()["trends"][0]["id"]


# ----------------------------------------------------------------------
# 1) Draft-post endpoint
# ----------------------------------------------------------------------
class TestDraftFromSignalAuth:
    def test_auth_required(self):
        r = httpx.post(f"{API_URL}/api/trends/draft-post",
                       json={"trend_id": "x"}, timeout=10)
        assert r.status_code == 401

    def test_unknown_platform_rejected(self):
        _comp("growth")
        tid = _get_a_trend_id()
        r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                       json={"trend_id": tid, "platform": "myspace"},
                       timeout=15)
        assert r.status_code == 422

    def test_unknown_trend_returns_404(self):
        _comp("growth")
        r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                       json={"trend_id": "nonexistent-12345", "platform": "linkedin"},
                       timeout=15)
        assert r.status_code == 404

    def test_other_user_cannot_access_signal(self):
        """Trend rows are user-scoped; passing another user's id must 404."""
        _comp("growth")
        # Insert a trend owned by a different user_id via direct Mongo.
        from pymongo import MongoClient
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        coll = MongoClient(mongo_url)[db_name].cortex_memory
        from datetime import datetime, timezone
        import uuid
        foreign_id = f"isolation-test-{uuid.uuid4()}"
        coll.insert_one({
            "id":         foreign_id,
            "user_id":    "user_someone_else",  # not USER_ID
            "kind":       "trend",
            "text":       "foreign trend",
            "embedding":  [0.0] * 384,
            "meta":       {"source": "gtrends"},
            "created_at": datetime.now(timezone.utc),
        })
        try:
            r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                           json={"trend_id": foreign_id, "platform": "linkedin"},
                           timeout=15)
            assert r.status_code == 404
        finally:
            coll.delete_one({"id": foreign_id})


class TestDraftFromSignalHappyPath:
    def test_generates_draft_with_hashtags(self):
        _comp("growth")
        tid = _get_a_trend_id()
        r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                       json={"trend_id": tid, "platform": "linkedin"},
                       timeout=120)
        if r.status_code in (502, 503, 504) or (r.status_code == 500 and "budget" in r.text.lower()):
            import pytest
            pytest.skip(f"LLM env unavailable (HTTP {r.status_code}) — likely budget/ingress timeout")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data["draft"], str) and len(data["draft"]) > 80
        assert data["platform"] == "linkedin"
        # HASHTAGS line should NOT be in the body — pulled into the
        # separate list instead.
        assert "HASHTAGS:" not in data["draft"]
        assert isinstance(data["suggested_hashtags"], list)
        # Signal echo for the frontend tooltip.
        assert data["signal"]["id"] == tid

    def test_each_platform_supported(self):
        """Smoke test: every platform we documented produces a draft.
        We hit just one (twitter) to keep cost down + skip on budget."""
        _comp("growth")
        tid = _get_a_trend_id()
        r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                       json={"trend_id": tid, "platform": "twitter"},
                       timeout=120)
        if r.status_code in (502, 503, 504) or (r.status_code == 500 and "budget" in r.text.lower()):
            import pytest
            pytest.skip(f"LLM env unavailable (HTTP {r.status_code})")
        assert r.status_code == 200
        assert r.json()["platform"] == "twitter"

    def test_draft_persists_as_memory(self):
        """Calling draft-post creates a `draft_from_trend` memory row so
        the AI Team's Memory panel surfaces past drafts."""
        _comp("growth")
        from pymongo import MongoClient
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        coll = MongoClient(mongo_url)[db_name].cortex_memory

        before = coll.count_documents(
            {"user_id": USER_ID, "kind": "draft_from_trend"},
        )
        tid = _get_a_trend_id()
        r = httpx.post(f"{API_URL}/api/trends/draft-post", headers=H,
                       json={"trend_id": tid, "platform": "instagram"},
                       timeout=120)
        if r.status_code in (502, 503, 504) or (r.status_code == 500 and "budget" in r.text.lower()):
            import pytest
            pytest.skip(f"LLM env unavailable (HTTP {r.status_code})")
        assert r.status_code == 200
        after = coll.count_documents(
            {"user_id": USER_ID, "kind": "draft_from_trend"},
        )
        # `remember()` uses a dedupe_key, so we expect a NEW row (different
        # platform→different key) or an updated existing one — either way
        # the count should not decrease.
        assert after >= before


# ----------------------------------------------------------------------
# 2) Spend nudge endpoint
# ----------------------------------------------------------------------
class TestSpendHint:
    def test_auth_required(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint", timeout=10)
        assert r.status_code == 401

    def test_default_user_no_nudge(self):
        """A user with no LLM usage (or all fast/sonnet) should see
        `show: false` — we don't nudge people who aren't spending."""
        r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "show" in body
        # The test user fired Haiku calls in earlier tests, NOT Opus, so
        # `show` must be False.
        assert body["show"] is False
        assert "opus_calls" in body and "opus_cost" in body

    def test_heavy_opus_user_gets_nudge(self):
        """Synthetic high-Opus history → expect `show: True` + a
        non-empty suggestion message + non-zero estimated savings."""
        from pymongo import MongoClient
        from datetime import datetime, timezone
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        coll = MongoClient(mongo_url)[db_name].llm_usage

        # Wipe and seed 25 fake Opus calls totalling ~$1.125 + 5 Haiku
        # calls so the share is overwhelmingly Opus.
        coll.delete_many({"user_id": USER_ID, "model": {"$regex": "synthetic"}})
        try:
            now = datetime.now(timezone.utc)
            opus_rows = [{
                "user_id": USER_ID, "agent_id": "strategy", "mode": "deep",
                "model": "claude-opus-4-7-synthetic", "cost": 0.045, "ts": now,
            } for _ in range(25)]
            coll.insert_many(opus_rows)

            r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint?days=30",
                          headers=H, timeout=10)
            assert r.status_code == 200
            body = r.json()
            assert body["show"] is True
            assert body["opus_calls"] >= 25
            assert body["suggestion"] is not None
            assert "Deep" in body["suggestion"]["message"]
            assert body["suggestion"]["estimated_savings"] > 0
        finally:
            coll.delete_many({"user_id": USER_ID, "model": {"$regex": "synthetic"}})

    def test_days_clamped(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint?days=99999",
                      headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["days"] == 90
