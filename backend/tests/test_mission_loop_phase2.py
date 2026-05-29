"""Phase 2 — Mission event-loop regression suite.

Verifies the scout→creator→operator→intelligence relay graph:
  1. Drain processes queued dispatches one-by-one.
  2. Each processed scout/creator/operator dispatch writes the next-team
     dispatch automatically.
  3. Intelligence dispatch writes a Creator variant ONLY when confidence
     is below threshold; otherwise the loop terminates AND the mission
     auto-completes when target reached.
  4. Autonomy gate — a low-autonomy mission's Operator/Intelligence
     dispatches go to `awaiting_approval` instead of being processed.
  5. Daily cap — > 25 dispatches/day for a single mission get blocked.
  6. Paused missions are skipped.
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


def _uid() -> str:
    return requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10).json()["user_id"]


@pytest.fixture
def user_id():
    return _uid()


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        await db.missions.delete_many({"user_id": user_id})
        await db.team_dispatches.delete_many({"user_id": user_id})
        await db.agent_messages.delete_many({"user_id": user_id, "from_agent": "cortex"})
    _run(go())
    yield
    _run(go())


def _start_mission(level: int = 3) -> str:
    """Helper: create a mission via Cortex at the given autonomy level.
    Returns mission id."""
    # Stub the LLM parse so the test is fast + deterministic.
    import sys
    sys.path.insert(0, "/app/backend")
    from routes import cortex as C
    original = C._llm_parse_goal

    async def fake(goal, uid):
        return C._regex_parse_goal(goal)
    C._llm_parse_goal = fake
    try:
        r = requests.post(
            f"{API_URL}/api/cortex/missions",
            json={"goal": f"Loop test {uuid.uuid4().hex[:6]}",
                  "autonomy_level": level, "deadline_days": 14},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        return r.json()["mission"]["id"]
    finally:
        C._llm_parse_goal = original


def _run_loop() -> dict:
    r = requests.post(f"{API_URL}/api/missions/loop/run-once",
                      headers=HEADERS, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestLoopDrain:
    def test_full_relay_at_level_3(self, user_id):
        """At L3, every team is auto-processed. One drain should advance
        each of the 4 initial dispatches once and write 3 next-step
        dispatches (scout→creator, creator→operator, operator→intel).
        Intelligence's next-step depends on confidence (likely <60 with no
        published variants → kicks Creator variant once)."""
        mid = _start_mission(level=3)

        # Cortex wrote 4 queued dispatches initially.
        async def initial():
            db = _mongo()
            return await db.team_dispatches.count_documents(
                {"mission_id": mid, "status": "queued"})
        assert _run(initial()) == 4

        res = _run_loop()
        assert res["processed"] == 4

        # After drain: each of the 4 should be `done`.
        async def post_drain():
            db = _mongo()
            done = await db.team_dispatches.count_documents(
                {"mission_id": mid, "status": "done"})
            queued = await db.team_dispatches.count_documents(
                {"mission_id": mid, "status": "queued"})
            total = await db.team_dispatches.count_documents({"mission_id": mid})
            return done, queued, total
        done, queued, total = _run(post_drain())
        assert done == 4
        # Relay should have written 3 new queued dispatches (scout→creator,
        # creator→operator, operator→intel). Intel→creator variant only
        # fires if confidence < threshold — with no real published variants
        # the confidence is 0 so we get the variant dispatch too = 4 new.
        assert queued == 4
        assert total  == 8

        # Verify the relay chain is correct: each new dispatch references
        # the prior team in its `context.prev_team`.
        async def chain():
            db = _mongo()
            cursor = db.team_dispatches.find(
                {"mission_id": mid, "status": "queued"},
                {"_id": 0},
            )
            rows = await cursor.to_list(length=20)
            teams_after_relay = {r["team"] for r in rows}
            # Expected new teams from relay
            assert teams_after_relay == {"creator", "operator", "intelligence"}
            # Creator appears twice (scout→creator + intelligence→creator variant)
            creator_rows = [r for r in rows if r["team"] == "creator"]
            assert len(creator_rows) == 2
        _run(chain())

    def test_paused_mission_skips_processing(self, user_id):
        mid = _start_mission(level=3)
        # Pause
        requests.post(f"{API_URL}/api/missions/{mid}/pause", headers=HEADERS, timeout=10)
        res = _run_loop()
        # All 4 dispatches should still be queued (loop saw mission paused,
        # left them alone). processed count is the # of records iterated,
        # but their status didn't change.
        async def still_queued():
            db = _mongo()
            return await db.team_dispatches.count_documents(
                {"mission_id": mid, "status": "queued"})
        assert _run(still_queued()) == 4


class TestAutonomyGate:
    def test_level_1_blocks_operator_and_intelligence(self, user_id):
        """At L1, Scout and Creator auto-process, but Operator and
        Intelligence should land in `awaiting_approval`."""
        mid = _start_mission(level=1)
        _run_loop()

        async def by_status():
            db = _mongo()
            cursor = db.team_dispatches.find({"mission_id": mid}, {"_id": 0})
            rows = await cursor.to_list(length=50)
            grouped = {}
            for r in rows:
                grouped.setdefault((r["team"], r["status"]), 0)
                grouped[(r["team"], r["status"])] += 1
            return grouped
        g = _run(by_status())

        # Scout → done (level 1 >= min 1)
        assert g.get(("scout", "done"), 0) == 1
        # Creator → done (level 1 >= min 1)  + relay-added scout→creator queued
        # so 1 done + 1 queued
        assert g.get(("creator", "done"), 0) >= 1
        # Operator → awaiting_approval (level 1 < min 2)
        assert g.get(("operator", "awaiting_approval"), 0) >= 1
        # Intelligence → awaiting_approval (level 1 < min 3)
        assert g.get(("intelligence", "awaiting_approval"), 0) >= 1


class TestDailyCap:
    def test_cap_blocks_excess_dispatches(self, user_id):
        """Pre-populate a mission with > MAX_DISPATCHES_PER_MISSION_PER_DAY
        dispatches and verify the next one gets blocked_cap."""
        mid = _start_mission(level=3)

        async def stuff():
            db = _mongo()
            now = datetime.now(timezone.utc)
            extra = []
            for i in range(30):
                extra.append({
                    "id":         uuid.uuid4().hex,
                    "user_id":    user_id,
                    "mission_id": mid,
                    "team":       "scout",
                    "from_agent": "cortex",
                    "to_agent":   "rae",
                    "task":       f"cap test {i}",
                    "status":     "queued",
                    "created_at": now,
                    "updated_at": now,
                })
            await db.team_dispatches.insert_many(extra)
        _run(stuff())

        _run_loop()
        # At least one row should be marked blocked_cap.
        async def count_capped():
            db = _mongo()
            return await db.team_dispatches.count_documents(
                {"mission_id": mid, "status": "blocked_cap"})
        assert _run(count_capped()) > 0


class TestListDispatches:
    def test_endpoint_returns_chronological(self, user_id):
        mid = _start_mission(level=3)
        _run_loop()
        r = requests.get(f"{API_URL}/api/missions/{mid}/dispatches",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        rows = r.json()["dispatches"]
        assert len(rows) >= 4
        # Sorted ascending by created_at
        for i in range(1, len(rows)):
            assert rows[i - 1]["created_at"] <= rows[i]["created_at"]

    def test_endpoint_404_for_unknown_mission(self):
        r = requests.get(f"{API_URL}/api/missions/nope/dispatches",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 404
