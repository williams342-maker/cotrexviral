"""Phase 1 — Autonomous Marketing OS regression suite.

Covers:
  1. Missions CRUD + lifecycle (draft → running → paused → succeeded).
  2. compute_progress correctness (current, confidence, ETA math).
  3. Team façade — 4 teams returned, persona membership matches spec,
     dispatch flow writes agent_messages + team_dispatches rows.
  4. Cortex orchestrator end-to-end — natural-language goal in →
     parsed Mission + 4 team dispatches out.
  5. Autonomy validation (0-5 inclusive).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

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


# ----------------------------------------------------------------------
# Teams façade
# ----------------------------------------------------------------------
class TestTeams:
    def test_list_returns_four_teams(self):
        r = requests.get(f"{API_URL}/api/teams", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        ids = [t["id"] for t in r.json()["teams"]]
        assert ids == ["scout", "creator", "operator", "intelligence"]

    def test_personas_match_spec(self):
        r = requests.get(f"{API_URL}/api/teams", headers=HEADERS, timeout=10)
        by_id = {t["id"]: t for t in r.json()["teams"]}
        # Spec from the user's brief
        assert set(by_id["scout"]["personas"])        == {"rae", "lyra", "atlas"}
        assert set(by_id["creator"]["personas"])      == {"nova", "atlas"}
        assert set(by_id["operator"]["personas"])     == {"echo", "jules"}
        assert set(by_id["intelligence"]["personas"]) == {"ori", "pico"}

    def test_team_detail_has_kpis_personas_activity(self):
        r = requests.get(f"{API_URL}/api/teams/scout", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "kpis" in body and isinstance(body["kpis"], dict)
        assert "personas" in body and isinstance(body["personas"], list)
        assert "recent_activity" in body

    def test_unknown_team_404(self):
        r = requests.get(f"{API_URL}/api/teams/marketing", headers=HEADERS, timeout=10)
        assert r.status_code == 404

    def test_dispatch_writes_messages_and_dispatch_log(self, user_id):
        r = requests.post(
            f"{API_URL}/api/teams/creator/dispatch",
            json={"task": "draft 3 instagram hooks for maker signups"},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["team"] == "creator"
        assert body["lead_persona"] == "nova"

        async def check():
            db = _mongo()
            msg = await db.agent_messages.find_one({"id": body["dispatch_id"]})
            assert msg is not None
            assert msg["from_agent"] == "cortex"
            assert msg["to_agent"]   == "nova"
            assert msg["team"]       == "creator"
            log = await db.team_dispatches.find_one({"id": body["dispatch_id"]})
            assert log is not None
        _run(check())


# ----------------------------------------------------------------------
# Missions CRUD + lifecycle
# ----------------------------------------------------------------------
class TestMissions:
    def test_requires_auth(self):
        # Valid payload — checks the route hits the auth dep, not pydantic
        r = requests.post(f"{API_URL}/api/missions",
                          json={"title": "Anonymous attempt", "target": 1},
                          timeout=10)
        assert r.status_code == 401

    def test_create_then_list_then_get(self):
        c = requests.post(
            f"{API_URL}/api/missions",
            json={"title": "Test mission", "target": 10, "metric": "leads",
                  "autonomy_level": 2},
            headers=HEADERS, timeout=10,
        )
        assert c.status_code == 200, c.text
        mid = c.json()["id"]
        assert c.json()["status"] == "draft"

        lst = requests.get(f"{API_URL}/api/missions", headers=HEADERS, timeout=10).json()
        assert any(m["id"] == mid for m in lst["missions"])

        one = requests.get(f"{API_URL}/api/missions/{mid}", headers=HEADERS, timeout=10).json()
        assert one["id"] == mid
        assert one["progress"]["target"] == 10
        assert one["progress"]["progress_pct"] == 0

    def test_start_and_pause(self):
        c = requests.post(f"{API_URL}/api/missions",
                          json={"title": "Lifecycle test", "target": 5, "autonomy_level": 1},
                          headers=HEADERS, timeout=10).json()
        mid = c["id"]
        s = requests.post(f"{API_URL}/api/missions/{mid}/start", headers=HEADERS, timeout=10)
        assert s.status_code == 200
        assert s.json()["status"] == "running"
        assert s.json()["started_at"]

        p = requests.post(f"{API_URL}/api/missions/{mid}/pause", headers=HEADERS, timeout=10)
        assert p.status_code == 200
        assert p.json()["status"] == "paused"

        # Resume = start
        s2 = requests.post(f"{API_URL}/api/missions/{mid}/start", headers=HEADERS, timeout=10)
        assert s2.json()["status"] == "running"

    def test_pause_only_from_running(self):
        c = requests.post(f"{API_URL}/api/missions",
                          json={"title": "Bad pause", "target": 5},
                          headers=HEADERS, timeout=10).json()
        # Status is draft — pause should 400
        r = requests.post(f"{API_URL}/api/missions/{c['id']}/pause", headers=HEADERS, timeout=10)
        assert r.status_code == 400

    def test_autonomy_validation(self):
        r = requests.post(f"{API_URL}/api/missions",
                          json={"title": "Bad autonomy", "autonomy_level": 9},
                          headers=HEADERS, timeout=10)
        assert r.status_code == 400

    def test_patch_status_update_writes_completed_at(self):
        c = requests.post(f"{API_URL}/api/missions",
                          json={"title": "complete me", "target": 3},
                          headers=HEADERS, timeout=10).json()
        mid = c["id"]
        u = requests.patch(f"{API_URL}/api/missions/{mid}",
                           json={"status": "succeeded"},
                           headers=HEADERS, timeout=10)
        assert u.status_code == 200
        assert u.json()["status"] == "succeeded"
        assert u.json()["completed_at"]

    def test_delete(self):
        c = requests.post(f"{API_URL}/api/missions",
                          json={"title": "kill me", "target": 1},
                          headers=HEADERS, timeout=10).json()
        d = requests.delete(f"{API_URL}/api/missions/{c['id']}", headers=HEADERS, timeout=10)
        assert d.status_code == 200
        assert requests.get(f"{API_URL}/api/missions/{c['id']}",
                            headers=HEADERS, timeout=10).status_code == 404


# ----------------------------------------------------------------------
# compute_progress math
# ----------------------------------------------------------------------
class TestComputeProgress:
    """We call compute_progress directly via in-process import for
    deterministic math testing — no HTTP."""

    def test_zero_when_no_data(self, user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.missions import compute_progress
        m = {
            "id":             "fake",
            "user_id":        user_id,
            "target":         100,
            "started_at":     datetime.now(timezone.utc) - timedelta(days=1),
            "deadline":       datetime.now(timezone.utc) + timedelta(days=9),
            "growth_goal_id": None,
        }
        out = _run(compute_progress(m))
        assert out["current"] == 0
        assert out["progress_pct"] == 0
        assert out["confidence"] == 0
        assert out["eta_days"] is None

    def test_confidence_drops_when_behind_pace(self, user_id):
        """50% of the time has elapsed but only 10% progress → confidence
        should be heavily discounted (10% * (10/50 pace ratio) ≈ 2%)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.missions import compute_progress

        # Insert 10 variants attributed to a fake mission to drive current=10
        mid = uuid.uuid4().hex
        async def seed():
            db = _mongo()
            for _ in range(10):
                await db.content_variants.insert_one({
                    "id":          uuid.uuid4().hex,
                    "user_id":     user_id,
                    "mission_id":  mid,
                    "status":      "published",
                    "platform":    "instagram",
                    "published_at": datetime.now(timezone.utc),
                    "created_at":  datetime.now(timezone.utc),
                })
        _run(seed())
        try:
            m = {
                "id":             mid,
                "user_id":        user_id,
                "target":         100,
                # 5 days elapsed, 10 days total → 50% through deadline
                "started_at":     datetime.now(timezone.utc) - timedelta(days=5),
                "deadline":       datetime.now(timezone.utc) + timedelta(days=5),
                "growth_goal_id": None,
            }
            out = _run(compute_progress(m))
            assert out["current"] == 10
            assert out["progress_pct"] == 10
            # Behind pace: confidence < raw pct
            assert out["confidence"] < 10
            assert out["top_channel"] == "instagram"
        finally:
            # Cleanup the seeded variants
            async def clean():
                db = _mongo()
                await db.content_variants.delete_many({"mission_id": mid})
            _run(clean())


# ----------------------------------------------------------------------
# Cortex orchestrator end-to-end
# ----------------------------------------------------------------------
class TestCortex:
    """Cortex is the user-facing entry point. We mock the LLM parser so
    these tests are deterministic + fast."""

    @pytest.fixture(autouse=True)
    def _mock_llm(self):
        # Make the parser fall through to the regex parser by patching
        # _llm_parse_goal directly — keeps the test offline.
        from routes import cortex as C
        original = C._llm_parse_goal

        async def fake_parse(goal, user_id):
            return C._regex_parse_goal(goal)

        C._llm_parse_goal = fake_parse
        yield
        C._llm_parse_goal = original

    def test_create_mission_via_cortex(self, user_id):
        r = requests.post(
            f"{API_URL}/api/cortex/missions",
            json={"goal": "Generate 50 new maker signups for CraftersMarket",
                  "autonomy_level": 2, "deadline_days": 14},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        m = body["mission"]
        assert m["status"] == "running"
        assert m["target"] == 50
        assert m["autonomy_level"] == 2
        assert m["raw_goal"].startswith("Generate 50")
        # Deadline ~14 days out (allow slack)
        from datetime import datetime as DT
        deadline = DT.fromisoformat(m["deadline"].replace("Z", "+00:00"))
        delta = (deadline - DT.now(deadline.tzinfo)).days
        assert 12 <= delta <= 14

        # 4 team dispatches written
        assert len(body["dispatches"]) == 4
        teams = [d["team"] for d in body["dispatches"]]
        assert set(teams) == {"scout", "creator", "operator", "intelligence"}

        # Lead personas wired correctly
        leads = {d["team"]: d["lead_persona"] for d in body["dispatches"]}
        assert leads["scout"]        == "rae"
        assert leads["creator"]      == "nova"
        assert leads["operator"]     == "echo"
        assert leads["intelligence"] == "ori"

        # Each dispatch landed in agent_messages
        async def check():
            db = _mongo()
            for d in body["dispatches"]:
                msg = await db.agent_messages.find_one({"id": d["dispatch_id"]})
                assert msg is not None
                assert msg["from_agent"]  == "cortex"
                assert msg["mission_id"]  == m["id"]
        _run(check())

    def test_summary_endpoint(self, user_id):
        # Create one running mission via cortex, verify summary reflects it
        requests.post(f"{API_URL}/api/cortex/missions",
                      json={"goal": "Test mission for summary"},
                      headers=HEADERS, timeout=15)
        r = requests.get(f"{API_URL}/api/cortex/summary", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["running_missions"] >= 1
        assert body["dispatches_24h"] >= 4
