"""Tests for weekly auto-draft toggle + user-side spend chip surface."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _coll(name: str):
    mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
    db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
    return MongoClient(mongo_url)[db_name][name]


def _comp(plan: str = "growth"):
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "auto-draft test"},
        timeout=10,
    )


# ----------------------------------------------------------------------
# 1) Settings round-trip + validation
# ----------------------------------------------------------------------
class TestAutoDraftSettings:
    def test_auth_required(self):
        r = httpx.get(f"{API_URL}/api/trends/auto-draft/settings", timeout=10)
        assert r.status_code == 401

    def test_default_settings_shape(self):
        """New user without any saved config gets sensible defaults."""
        _coll("users").update_one(
            {"user_id": USER_ID},
            {"$unset": {"auto_draft_trends": ""}},
        )
        r = httpx.get(f"{API_URL}/api/trends/auto-draft/settings", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["platform"] == "linkedin"
        assert body["count"] == 3
        assert body["max_count"] == 5
        assert "last_run_at" in body

    def test_set_and_read_round_trip(self):
        # turn it on with custom platform + count
        r = httpx.put(
            f"{API_URL}/api/trends/auto-draft/settings", headers=H,
            json={"enabled": True, "platform": "twitter", "count": 4}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is True
        assert r.json()["platform"] == "twitter"
        assert r.json()["count"] == 4
        # partial update — only flip enabled, others stay
        r = httpx.put(
            f"{API_URL}/api/trends/auto-draft/settings", headers=H,
            json={"enabled": False}, timeout=10,
        )
        assert r.json()["enabled"] is False
        assert r.json()["platform"] == "twitter"
        assert r.json()["count"] == 4

    def test_rejects_unsupported_platform(self):
        r = httpx.put(
            f"{API_URL}/api/trends/auto-draft/settings", headers=H,
            json={"platform": "myspace"}, timeout=10,
        )
        assert r.status_code == 422

    def test_rejects_count_out_of_range(self):
        r = httpx.put(
            f"{API_URL}/api/trends/auto-draft/settings", headers=H,
            json={"count": 99}, timeout=10,
        )
        assert r.status_code == 422
        r = httpx.put(
            f"{API_URL}/api/trends/auto-draft/settings", headers=H,
            json={"count": 0}, timeout=10,
        )
        assert r.status_code == 422


# ----------------------------------------------------------------------
# 2) run_now: cooldown + opt-in gate
# ----------------------------------------------------------------------
class TestRunNowGuards:
    def test_run_now_blocked_when_disabled(self):
        """Manually triggering the auto-drafter must fail with 422 if
        the user hasn't actually enabled the feature."""
        httpx.put(f"{API_URL}/api/trends/auto-draft/settings", headers=H,
                  json={"enabled": False}, timeout=10)
        r = httpx.post(f"{API_URL}/api/trends/auto-draft/run-now",
                       headers=H, json={}, timeout=10)
        assert r.status_code == 422

    def test_run_now_respects_cooldown(self):
        """If last_run_at is within the 6-day cooldown, return 429."""
        _coll("users").update_one(
            {"user_id": USER_ID},
            {"$set": {
                "auto_draft_trends": {
                    "enabled": True, "platform": "linkedin", "count": 2,
                    "last_run_at": datetime.now(timezone.utc) - timedelta(hours=2),
                },
            }},
        )
        r = httpx.post(f"{API_URL}/api/trends/auto-draft/run-now",
                       headers=H, json={}, timeout=10)
        assert r.status_code == 429
        assert "Cooldown" in r.json().get("detail", "")


# ----------------------------------------------------------------------
# 3) _process_user core pipeline (no HTTP, calls Nova live)
# ----------------------------------------------------------------------
class TestProcessUserPipeline:
    def test_queues_drafts_in_approvals(self):
        """Running the pipeline must:
          1. Create N pending_approval posts (where N = count, capped by
             how many trends the user actually has).
          2. Each post tagged `source: auto_draft` + a `dedupe_key`.
          3. Each post scheduled ~24h in the future (editing window).
        """
        _comp("growth")
        # Make sure the user has at least one trend signal.
        httpx.post(f"{API_URL}/api/trends/ingest", headers=H,
                   json={"keywords": ["marketing"], "subreddits": []},
                   timeout=45)
        # Enable + reset cooldown for a clean fire.
        _coll("users").update_one(
            {"user_id": USER_ID},
            {"$set": {"auto_draft_trends": {
                "enabled": True, "platform": "linkedin", "count": 1,
                "last_run_at": None,
            }}},
        )
        posts = _coll("posts")
        posts.delete_many({"user_id": USER_ID, "source": "auto_draft"})

        r = httpx.post(f"{API_URL}/api/trends/auto-draft/run-now",
                       headers=H, json={}, timeout=120)
        if r.status_code in (500, 502, 503) and "budget" in r.text.lower():
            import pytest
            pytest.skip("LLM budget exceeded")
        assert r.status_code == 200, r.text
        if r.json().get("drafts_queued", 0) == 0:
            import pytest
            pytest.skip("Nova produced no drafts (transient)")

        rows = list(posts.find({"user_id": USER_ID, "source": "auto_draft"}))
        assert len(rows) >= 1
        row = rows[0]
        assert row["status"] == "pending_approval"
        assert row["platforms"] == ["linkedin"]
        assert row["dedupe_key"].startswith("auto_draft:")
        # Scheduled ~24h out (allow 23-25h window for clock drift).
        delta = row["scheduled_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        assert timedelta(hours=23) < delta < timedelta(hours=25)
        posts.delete_many({"user_id": USER_ID, "source": "auto_draft"})

    def test_dedupe_key_prevents_duplicate_drafts(self):
        """Calling the auto-drafter twice for the same signal+platform
        must upsert (not duplicate) the post row. We use the HTTP
        `/run-now` endpoint twice (resetting cooldown between calls) so
        we don't fight Motor's per-loop binding from inside pytest."""
        _comp("growth")
        httpx.post(f"{API_URL}/api/trends/ingest", headers=H,
                   json={"keywords": ["marketing"], "subreddits": []},
                   timeout=45)
        # Enable + reset last_run_at so the first /run-now isn't blocked.
        _coll("users").update_one(
            {"user_id": USER_ID},
            {"$set": {"auto_draft_trends": {
                "enabled": True, "platform": "linkedin", "count": 1,
                "last_run_at": None,
            }}},
        )
        posts = _coll("posts")
        posts.delete_many({"user_id": USER_ID, "source": "auto_draft"})

        def fire():
            return httpx.post(f"{API_URL}/api/trends/auto-draft/run-now",
                              headers=H, json={}, timeout=120)

        r1 = fire()
        if r1.status_code in (500, 502, 503) and "budget" in r1.text.lower():
            import pytest
            pytest.skip("LLM budget exceeded")
        assert r1.status_code == 200, r1.text
        if r1.json().get("drafts_queued", 0) == 0:
            import pytest
            pytest.skip("Nova produced no drafts (transient)")

        # Reset cooldown so the second call goes through.
        _coll("users").update_one(
            {"user_id": USER_ID},
            {"$set": {"auto_draft_trends.last_run_at": None}},
        )
        r2 = fire()
        if r2.status_code in (500, 502, 503) and "budget" in r2.text.lower():
            import pytest
            pytest.skip("LLM budget exceeded")
        assert r2.status_code == 200

        rows = list(posts.find({"user_id": USER_ID, "source": "auto_draft"}))
        # Both runs hit the same (top recent) signal → still ONE post row.
        dedupe_keys = {r["dedupe_key"] for r in rows}
        assert len(rows) == len(dedupe_keys), \
            f"duplicate rows for same dedupe_key: {rows}"
        posts.delete_many({"user_id": USER_ID, "source": "auto_draft"})


# ----------------------------------------------------------------------
# 4) Spend hint endpoint surfaces the chip-friendly fields
# ----------------------------------------------------------------------
class TestSpendChipFields:
    def test_endpoint_returns_total_tokens_and_calls(self):
        """The AgentWorkspace sidebar chip needs `total_cost`,
        `total_tokens`, `total_calls`, `days`. Confirm shape regardless
        of whether `show` is true."""
        r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        for k in ("total_cost", "total_tokens", "total_calls", "days", "show"):
            assert k in body, f"missing {k}"
        assert isinstance(body["total_tokens"], int)
        assert isinstance(body["total_calls"], int)
        assert isinstance(body["total_cost"], (int, float))

    def test_zero_state_for_clean_user(self):
        """A user with no llm_usage rows in the window returns all zeros
        + `show: false`, not a 404 or null."""
        _coll("llm_usage").delete_many({"user_id": USER_ID})
        r = httpx.get(f"{API_URL}/api/ai/agent/spend-hint?days=30",
                      headers=H, timeout=10)
        body = r.json()
        assert body["show"] is False
        assert body["total_cost"] == 0
        assert body["total_tokens"] == 0
        assert body["total_calls"] == 0
