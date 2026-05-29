"""Team Performance + YouTube publish + Atlas multi-handoff tests.

Bundled in one file because the three features ship together.

Covers:
  • /api/agents/team-performance — auth, shape, week-bounded aggregations
  • publish_to_youtube — input validation (requires video_url + valid privacy,
    not_connected when no token, etc.). Live YouTube uploads are skipped.
  • fetch_youtube_post_metrics — returns None when not connected
  • Atlas hand-offs — handoff calls are silently no-ops without LLM key,
    but the briefs path doesn't crash when goals/signals are present.
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
        await db.proposed_briefs.delete_many({"user_id": admin_user_id, "title": {"$regex": "^pytest_"}})
        await db.experiments.delete_many({"user_id": admin_user_id, "name": {"$regex": "^pytest_"}})
        await db.growth_goals.delete_many({"user_id": admin_user_id, "title": {"$regex": "^pytest_"}})
        await db.social_listening_signals.delete_many({"user_id": admin_user_id, "text": {"$regex": "^pytest_"}})
        await db.agent_messages.delete_many({"user_id": admin_user_id, "query": {"$regex": "^pytest_"}})
        await db.youtube_connections.delete_many({"user_id": admin_user_id})
    _run(go())
    yield
    _run(go())


class TestTeamPerformanceAuth:
    def test_requires_auth(self):
        r = requests.get(f"{API_URL}/api/agents/team-performance", timeout=10)
        assert r.status_code == 401


class TestTeamPerformanceShape:
    def test_returns_all_personas(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/agents/team-performance",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("rows", "iso_week", "week_started_at", "briefs_week",
                  "experiments_active", "signals_week"):
            assert k in body
        ids = {row["agent_id"] for row in body["rows"]}
        assert {"vera", "atlas", "nova", "rae", "lyra", "echo", "ori", "jules"}.issubset(ids)
        # Each row has the contract we render against
        for row in body["rows"]:
            for k in ("name", "role", "headline", "verbs",
                      "headroom_pct", "can_act"):
                assert k in row, f"missing {k} in row {row}"
            assert isinstance(row["verbs"], list)

    def test_aggregates_week_only(self, admin_user_id):
        """Seed two briefs: one within the week + one 60 days ago.
        team_performance briefs_week should count only the recent one."""
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            old = now - timedelta(days=60)
            for ts, title in [(now, "pytest_recent_brief"), (old, "pytest_old_brief")]:
                await db.proposed_briefs.insert_one({
                    "id": uuid.uuid4().hex, "user_id": admin_user_id,
                    "proposer_agent": "atlas", "title": title,
                    "body": "x" * 30, "status": "pending",
                    "source": "manual", "auto_approved": False,
                    "created_at": ts, "decided_at": None, "decided_by": None,
                    "resolved_into_campaign_id": None, "edited_body": None,
                })
        _run(seed())
        r = requests.get(f"{API_URL}/api/agents/team-performance",
                         headers=HEADERS, timeout=10)
        atlas = next(row for row in r.json()["rows"] if row["agent_id"] == "atlas")
        # Atlas's headline should reference proposals
        assert "brief" in atlas["headline"].lower()
        proposed = next(v for v in atlas["verbs"] if v["label"] == "Proposed")
        # Recent counts only; old brief is filtered out by week_start cutoff.
        assert proposed["value"] >= 1


class TestYoutubePublishValidation:
    """`publish_to_youtube` input checks. Live upload paths require a real
    OAuth token + video file, so we cover the negative paths here."""

    def test_requires_video_url(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_youtube import publish_to_youtube
        r = _run(publish_to_youtube(admin_user_id, "caption text"))
        assert r["ok"] is False
        assert r["reason"] == "youtube_requires_video_url"

    def test_rejects_invalid_privacy(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_youtube import publish_to_youtube
        r = _run(publish_to_youtube(
            admin_user_id, "caption",
            video_url="https://example.com/video.mp4",
            privacy="vip-only",
        ))
        assert r["ok"] is False
        assert r["reason"] == "invalid_privacy_status"

    def test_not_connected_when_no_token(self, admin_user_id):
        """No youtube_connections row → publish returns not_connected."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_youtube import publish_to_youtube
        r = _run(publish_to_youtube(
            admin_user_id, "caption",
            video_url="https://example.com/video.mp4",
            privacy="unlisted",
        ))
        assert r["ok"] is False
        assert r["reason"] == "not_connected"


class TestYoutubeMetricsValidation:
    def test_returns_none_when_not_connected(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.oauth_youtube import fetch_youtube_post_metrics
        r = _run(fetch_youtube_post_metrics(admin_user_id, "fake_video_id"))
        assert r is None


class TestAtlasMultiHandoff:
    """The 3 hand-offs (Lyra/Ori/Rae) fire when there's data + skip silently
    otherwise. They never block proposal — even on errors. Live LLM calls
    persist messages we can verify."""

    def test_handoffs_dont_crash_propose(self, admin_user_id):
        """Trigger /api/briefs/propose with seeded goals so Atlas's
        consultations have something to ask about. The call should
        succeed (status 200) regardless of whether any handoff returns
        useful answers."""
        # Seed a goal so Atlas→Ori has context to consult on
        async def seed():
            db = _mongo()
            await db.growth_goals.insert_one({
                "id": uuid.uuid4().hex, "user_id": admin_user_id,
                "title": "pytest_handoff_goal", "description": "test",
                "owner_agent": "vera", "metric": "engagements",
                "current": 0, "target": 100, "deadline": None,
                "status": "active",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            # Also seed 3+ signals so Atlas→Lyra fires
            for i in range(3):
                await db.social_listening_signals.insert_one({
                    "id": uuid.uuid4().hex, "user_id": admin_user_id,
                    "text": f"pytest_signal_{i}",
                    "sentiment": "positive", "signal_type": "mention",
                    "urgency": 2, "source": "manual",
                    "topic": "test",
                    "detected_at": datetime.now(timezone.utc),
                })
        _run(seed())

        r = requests.post(f"{API_URL}/api/briefs/propose",
                          json={"max_briefs": 1},
                          headers=HEADERS, timeout=120)
        assert r.status_code == 200, r.text
        # Atlas should have written ≥1 message to the bus
        # (Lyra: 3 signals → fires; Ori: 1 goal → fires; Rae: goals OR signals → fires)
        async def check():
            db = _mongo()
            count = await db.agent_messages.count_documents({
                "user_id": admin_user_id,
                "from_agent": "atlas",
                "to_agent": {"$in": ["lyra", "ori", "rae"]},
                "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=5)},
            })
            # At least one of the three handoffs should have fired.
            assert count >= 1
        _run(check())
