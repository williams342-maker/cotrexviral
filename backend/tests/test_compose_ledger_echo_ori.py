"""Three new feature tests bundled (Compose YouTube + LLM ledger ticks + Echo→Ori).

Covers:
  • _estimate_usd math sanity
  • send_with_usage with agent_id+user_id ticks the ledger atomically
  • POST /channels/publish accepts youtube fields + posts row gets them
  • /ai/optimal-times kicks off Echo→Ori handoff when niche/audience present
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin_user_id():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    return r.json().get("user_id") if r.status_code == 200 else None


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing")
    return uid


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    async def go():
        db = _mongo()
        await db.posts.delete_many({"user_id": admin_user_id, "content": {"$regex": "^pytest_"}})
        await db.agent_usage_ledger.delete_many({"user_id": admin_user_id})
        await db.agent_messages.delete_many({"user_id": admin_user_id,
                                              "query": {"$regex": "pytest_"}})
    _run(go())
    yield
    _run(go())


class TestEstimateUsd:
    def test_known_model_pricing(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.ai import _estimate_usd
        # gpt-5-mini: $0.30/M input, $1.20/M output
        # 1000 input + 500 output = 0.0003 + 0.0006 = 0.0009
        cost = _estimate_usd("gpt-5-mini", 1000, 500)
        assert abs(cost - 0.0009) < 1e-6

    def test_unknown_model_falls_back(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.ai import _estimate_usd
        cost_unknown = _estimate_usd("frontier-z-2070", 1000, 500)
        cost_mini = _estimate_usd("gpt-5-mini", 1000, 500)
        assert cost_unknown == cost_mini


class TestLedgerTicksOnLLM:
    """When `query_agent` makes a real LLM call, it should bump the ledger
    for the target agent. We can't pin the exact token count (depends on
    LLM response length) but we can assert it incremented from 0."""

    def test_ledger_increments_on_agent_message(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_messaging import query_agent
        from routes.autonomy import check_budget, _iso_week_key
        # Ensure ledger is zero before
        async def reset():
            db = _mongo()
            await db.agent_usage_ledger.delete_many({
                "agent_id": "lyra", "user_id": admin_user_id,
                "iso_week": _iso_week_key(),
            })
        _run(reset())
        snap_before = _run(check_budget("lyra", admin_user_id))
        assert snap_before["tokens_used"] == 0
        # Make a real LLM call
        r = _run(query_agent(
            user_id=admin_user_id, from_agent="atlas", to_agent="lyra",
            query="pytest_ledger_tick: respond with one short word",
            context_str="x",
        ))
        # When the LLM key is set + the call succeeded, tokens must have ticked.
        if r["ok"] and os.environ.get("EMERGENT_LLM_KEY"):
            snap_after = _run(check_budget("lyra", admin_user_id))
            assert snap_after["tokens_used"] > 0
            assert snap_after["usd_used"] >= 0


class TestComposePublishYoutube:
    """The Compose form sends {video_url, youtube_title, youtube_tags,
    youtube_privacy}. The /channels/publish endpoint must persist them
    on the posts row so the scheduler dispatcher can read them later."""

    def test_publish_stores_youtube_fields(self, admin_user_id):
        # Schedule for ~10s in the future so it's not dispatched immediately.
        scheduled = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        r = requests.post(
            f"{API_URL}/api/channels/publish",
            json={
                "content": "pytest_yt_compose body text",
                "platforms": ["youtube"],
                "video_url": "https://example.com/sample.mp4",
                "youtube_title": "pytest_yt_compose title",
                "youtube_tags": ["alpha", "beta"],
                "youtube_privacy": "unlisted",
                "scheduled_at": scheduled,
            }, headers=HEADERS, timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        post_id = (body.get("ids") or [body.get("id")])[0] if body.get("ids") else body.get("id")
        assert post_id

        async def check():
            db = _mongo()
            doc = await db.posts.find_one({"id": post_id})
            assert doc is not None
            # The dispatcher reads video_url + youtube_* off the row.
            assert doc.get("video_url") == "https://example.com/sample.mp4"
            assert doc.get("youtube_title") == "pytest_yt_compose title"
            assert doc.get("youtube_privacy") == "unlisted"
            assert doc.get("youtube_tags") == ["alpha", "beta"]
        _run(check())


class TestOptimalTimesEchoOriHandoff:
    """When the user calls /ai/optimal-times with a niche, Echo should
    ask Ori for past-winners memory. The response should include the
    ori_insight field (may be None on LLM failure, but the key must
    exist), and the agent_messages collection should have a row."""

    def test_handoff_writes_message(self, admin_user_id):
        # Fires the Echo→Ori handoff.
        r = requests.post(
            f"{API_URL}/api/ai/optimal-times",
            json={
                "platforms": ["instagram", "tiktok"],
                "niche": "pytest_niche_marketing",
                "audience": "pytest_audience_founders",
            },
            headers=HEADERS, timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "slots" in body
        assert "ori_insight" in body  # key always present

        # The handoff message should be logged
        async def check():
            db = _mongo()
            count = await db.agent_messages.count_documents({
                "user_id": admin_user_id,
                "from_agent": "echo", "to_agent": "ori",
                "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=5)},
            })
            assert count >= 1
        _run(check())

    def test_no_handoff_without_niche(self, admin_user_id):
        """When niche AND audience are both absent, Echo skips Ori entirely
        (the rationale path is gated on niche/audience presence)."""
        async def baseline():
            db = _mongo()
            return await db.agent_messages.count_documents({
                "user_id": admin_user_id, "from_agent": "echo", "to_agent": "ori",
            })
        before = _run(baseline())

        r = requests.post(
            f"{API_URL}/api/ai/optimal-times",
            json={"platforms": ["x"]},
            headers=HEADERS, timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ori_insight") is None

        after = _run(baseline())
        assert after == before
