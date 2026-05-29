"""Phase 3 — Goal-seeking (L4+) auto-extension regression.

When the Intelligence dispatch processes a mission whose:
  • autonomy_level >= 4
  • confidence < INTELLIGENCE_RETRY_THRESHOLD (60)
  • >=50% of the timeline elapsed
  • <2 extensions already used

…the mission_loop must auto-extend the deadline by 7 days and bump
`deadline_extensions`.

We bypass the HTTP layer here and call `_process_dispatch()` directly so
we can plant exact `started_at` / `deadline` times.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from routes import mission_loop as ML  # noqa: E402


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def user_id():
    return "user_test_phase3_" + uuid.uuid4().hex[:8]


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        await db.missions.delete_many({"user_id": user_id})
        await db.team_dispatches.delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


def _make_mission(user_id, *, autonomy: int, deadline_offset_days: float,
                  started_offset_days: float, extensions: int = 0) -> str:
    """Insert a Mission directly so we control all timing fields."""
    now = datetime.now(timezone.utc)
    started = now - timedelta(days=started_offset_days)
    deadline = now + timedelta(days=deadline_offset_days)
    mid = uuid.uuid4().hex
    doc = {
        "id":                  mid,
        "user_id":             user_id,
        "title":               "Goal-seeking test mission",
        "target":              100,
        "metric":              "leads",
        "autonomy_level":      autonomy,
        "team_autonomy":       {},
        "teams_assigned":      ["scout", "creator", "operator", "intelligence"],
        "deadline":            deadline,
        "deadline_extensions": extensions,
        "status":              "running",
        "started_at":          started,
        "created_at":          started,
        "updated_at":          now,
    }
    _run(_mongo().missions.insert_one(doc))
    return mid


def _make_intel_dispatch(user_id, mid) -> dict:
    """Insert an intelligence dispatch directly so we don't have to drain
    earlier scout/creator/operator rows."""
    now = datetime.now(timezone.utc)
    d = {
        "id":         uuid.uuid4().hex,
        "user_id":    user_id,
        "mission_id": mid,
        "team":       "intelligence",
        "from_agent": "cortex",
        "to_agent":   "ori",
        "task":       "measure",
        "status":     "queued",
        "created_at": now,
        "updated_at": now,
    }
    _run(_mongo().team_dispatches.insert_one(d))
    return d


class TestGoalSeeking:
    def test_level_4_past_halftime_extends_deadline(self, user_id):
        # Mission halfway through timeline (started 5d ago, deadline 5d out)
        mid = _make_mission(user_id, autonomy=4,
                            deadline_offset_days=5, started_offset_days=5)
        d = _make_intel_dispatch(user_id, mid)

        _run(ML._process_dispatch(d))

        fresh = _run(_mongo().missions.find_one({"id": mid}))
        assert fresh["deadline_extensions"] == 1
        # Mission timeline was 10 days total (started 5d ago, deadline 5d out).
        # After 7-day extension → total span = 17 days.
        delta_days = (fresh["deadline"] - fresh["started_at"]).days
        assert 16 <= delta_days <= 18
        assert fresh["goal_seeking"]["extension_1_reason"]

    def test_level_3_does_not_extend(self, user_id):
        mid = _make_mission(user_id, autonomy=3,
                            deadline_offset_days=5, started_offset_days=5)
        d = _make_intel_dispatch(user_id, mid)
        _run(ML._process_dispatch(d))

        fresh = _run(_mongo().missions.find_one({"id": mid}))
        assert fresh.get("deadline_extensions", 0) == 0
        assert "goal_seeking" not in fresh

    def test_under_halftime_does_not_extend(self, user_id):
        # 1d elapsed, 9d left — only 10% through
        mid = _make_mission(user_id, autonomy=5,
                            deadline_offset_days=9, started_offset_days=1)
        d = _make_intel_dispatch(user_id, mid)
        _run(ML._process_dispatch(d))

        fresh = _run(_mongo().missions.find_one({"id": mid}))
        assert fresh.get("deadline_extensions", 0) == 0

    def test_extension_cap_at_two(self, user_id):
        # Already extended twice — no further extension.
        mid = _make_mission(user_id, autonomy=4,
                            deadline_offset_days=5, started_offset_days=5,
                            extensions=2)
        d = _make_intel_dispatch(user_id, mid)
        _run(ML._process_dispatch(d))

        fresh = _run(_mongo().missions.find_one({"id": mid}))
        assert fresh["deadline_extensions"] == 2  # unchanged

    def test_intelligence_terminates_loop_when_at_target(self, user_id):
        """When current >= target AND confidence is high enough, the
        Intelligence dispatch should flip the mission to 'succeeded'."""
        mid = _make_mission(user_id, autonomy=3,
                            deadline_offset_days=10, started_offset_days=2)
        # Seed enough variants to push current ≥ target = 100. (100+ rows
        # of published variants for this mission.)
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            rows = []
            for _ in range(110):
                rows.append({
                    "id":           uuid.uuid4().hex,
                    "user_id":      user_id,
                    "mission_id":   mid,
                    "status":       "published",
                    "platform":     "instagram",
                    "performance": {"engagements": 5},
                    "published_at": now,
                    "created_at":   now,
                })
            await db.content_variants.insert_many(rows)
        _run(seed())
        try:
            d = _make_intel_dispatch(user_id, mid)
            _run(ML._process_dispatch(d))

            fresh = _run(_mongo().missions.find_one({"id": mid}))
            assert fresh["status"] == "succeeded"
            assert fresh["completed_at"]
        finally:
            _run(_mongo().content_variants.delete_many({"mission_id": mid}))
