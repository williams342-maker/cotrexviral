"""Iter22 — AI-guided onboarding mission endpoints.

Validates:
- Eligibility gate (1a + 2a): unset onboarded_at + zero missions + zero
  conversations. Existing users with data are NOT eligible.
- /start (replay=true) bypasses the gate.
- /advance walks the state machine: welcome → set_goal → cc_intro →
  sample_mission_proposal → mission_lifecycle → autonomous_execution →
  autonomy_explain → complete.
- set_goal step captures user_input into the row's `goal` field and
  personalizes subsequent messages.
- sample_mission_proposal inserts a `demo:true` row in `missions`.
- /demo-tick advances the demo phase index.
- /complete (via final advance) hard-deletes the demo mission and
  stamps users.onboarded_at.
- /skip also hard-deletes the demo mission and stamps onboarded_at.
"""
import os
import time
import uuid
import asyncio

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
COOKIES = {"session_token": TOKEN}


def _run(coro):
    """Use asyncio.run for each call so motor doesn't end up bound to
    a stale closed loop after earlier test modules in the full suite
    have done the same. asyncio.run() always creates a fresh loop AND
    closes it cleanly at the end — motor rebinds on the next call."""
    return asyncio.run(coro)


def _get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES, timeout=45, **kw)


def _post(path, json=None, **kw):
    return requests.post(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES,
                          json=json or {}, timeout=45, **kw)


@pytest.fixture(autouse=True)
def _clean():
    """Reset onboarding state between tests via the public API so we
    don't have to share motor's event-loop binding with earlier test
    modules in the suite (avoids 'Event loop is closed' cross-suite)."""
    # Skip any in-progress onboarding (idempotent — no-op if none).
    try:
        requests.post(f"{BASE_URL}/api/cortex/onboarding/skip",
                       headers=HDRS, cookies=COOKIES, timeout=10)
    except Exception:
        pass
    # Clear user.onboarded_at + nuke the row + delete demo missions via
    # a tiny one-shot subprocess (own python interpreter, own loop).
    # ALSO wipe cortex_conversations for the test user so the
    # eligibility gate (zero conversations) is honest across tests.
    import subprocess
    subprocess.run([
        "python3", "-c",
        f"""
import asyncio, os, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.cortex_onboarding.delete_many({{'user_id': '{USER_ID}'}})
    await db.missions.delete_many({{'user_id': '{USER_ID}', 'demo': True}})
    await db.cortex_conversations.delete_many({{'user_id': '{USER_ID}'}})
    await db.users.update_one({{'user_id': '{USER_ID}'}},
                                 {{'$unset': {{'onboarded_at': ''}}}})
asyncio.run(go())
"""
    ], check=False, timeout=15)
    yield


class TestState:
    def test_initial_state_returns_eligibility(self):
        r = _get("/api/cortex/onboarding/state")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["step"] is None
        assert "eligible" in d
        assert "spotlight" in d
        # User has existing missions → not eligible by default.
        assert d["eligible"] is False


class TestStartFlow:
    def test_first_time_gate_blocks_start_without_replay(self):
        # User isn't eligible (has real missions). /start without replay must 409.
        r = _post("/api/cortex/onboarding/start", json={"replay": False})
        assert r.status_code == 409, r.text

    def test_replay_bypasses_gate(self):
        r = _post("/api/cortex/onboarding/start", json={"replay": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["step"] == "welcome"
        assert d["replay"] is True
        # Welcome message is personalized.
        assert "Cortex" in d["message"]


class TestAdvanceStateMachine:
    def _start_replay(self):
        r = _post("/api/cortex/onboarding/start", json={"replay": True})
        assert r.status_code == 200, r.text

    def test_walks_full_machine_to_complete(self):
        self._start_replay()
        # welcome → set_goal
        r = _post("/api/cortex/onboarding/advance", json={"from_step": "welcome"})
        assert r.json()["step"] == "set_goal"
        assert r.json()["expects_user_reply"] is True
        assert r.json()["spotlight"] == "composer"

        # set_goal: submit goal text
        goal = "Recruit 50 woodworking sellers on Etsy."
        r = _post("/api/cortex/onboarding/advance",
                   json={"from_step": "set_goal", "user_input": goal})
        d = r.json()
        assert d["step"] == "cc_intro"
        assert d["goal"] == goal
        # Personalized message includes goal text.
        assert "Recruit 50 woodworking sellers" in d["message"]

        # cc_intro → sample_mission_proposal (demo mission minted)
        r = _post("/api/cortex/onboarding/advance", json={"from_step": "cc_intro"})
        d = r.json()
        assert d["step"] == "sample_mission_proposal"
        assert d["demo_mission_id"], "Demo mission must be created"
        demo_mid = d["demo_mission_id"]

        # Demo mission visible in active missions rail with demo flag.
        r = _get("/api/cortex/missions/active")
        ms = r.json()["missions"]
        demo = next((m for m in ms if m["id"] == demo_mid), None)
        assert demo is not None, "Demo mission missing from rail"
        assert demo["demo"] is True
        assert "Demo:" in demo["title"]

        # sample_mission_proposal → mission_lifecycle
        r = _post("/api/cortex/onboarding/advance",
                   json={"from_step": "sample_mission_proposal"})
        assert r.json()["step"] == "mission_lifecycle"
        assert r.json()["spotlight"] == "mission_rail"

        # demo-tick advances the demo phase
        r = _post("/api/cortex/onboarding/demo-tick")
        d = r.json()
        assert d["ticked"] is True
        assert d["phase_idx"] >= 1
        assert d["phase"]["key"] in ("qualification", "outreach", "conversations")

        # mission_lifecycle → autonomous_execution → autonomy_explain → complete
        for from_step in ("mission_lifecycle", "autonomous_execution", "autonomy_explain"):
            r = _post("/api/cortex/onboarding/advance",
                       json={"from_step": from_step})
            assert r.status_code == 200, r.text

        d = r.json()
        assert d["step"] == "complete"
        assert d["is_terminal"] is True
        assert d["completed_at"] is not None
        # Demo mission must be hard-deleted on complete.
        assert d["demo_mission_id"] is None
        r = _get("/api/cortex/missions/active")
        ms = r.json()["missions"]
        assert not any(m["id"] == demo_mid for m in ms), \
            "Demo mission should be hard-deleted on complete"

    def test_complete_stamps_onboarded_at(self):
        self._start_replay()
        for from_step in ONBOARDING_STEPS[:-1]:
            ui = "test goal" if from_step == "set_goal" else None
            _post("/api/cortex/onboarding/advance",
                   json={"from_step": from_step, "user_input": ui})

        # Verify via subprocess (own event loop) to avoid motor's stale
        # loop binding when this test module runs alongside others.
        import subprocess
        result = subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    u = await db.users.find_one({{'user_id': '{USER_ID}'}}, {{'_id': 0}})
    print('STAMPED' if u and u.get('onboarded_at') else 'MISSING')
asyncio.run(go())
"""
        ], capture_output=True, text=True, timeout=15)
        assert "STAMPED" in result.stdout, \
            f"users.onboarded_at must be stamped on complete (stdout: {result.stdout!r})"


class TestSkipFlow:
    def test_skip_hard_deletes_demo_mission_and_stamps_onboarded(self):
        # Get into sample_mission_proposal so a demo mission exists.
        _post("/api/cortex/onboarding/start", json={"replay": True})
        _post("/api/cortex/onboarding/advance", json={"from_step": "welcome"})
        _post("/api/cortex/onboarding/advance",
               json={"from_step": "set_goal", "user_input": "test goal"})
        r = _post("/api/cortex/onboarding/advance", json={"from_step": "cc_intro"})
        demo_mid = r.json()["demo_mission_id"]
        assert demo_mid

        # Skip
        r = _post("/api/cortex/onboarding/skip")
        assert r.status_code == 200, r.text
        assert r.json()["skipped"] is True

        # Demo mission gone
        r = _get("/api/cortex/missions/active")
        ms = r.json()["missions"]
        assert not any(m["id"] == demo_mid for m in ms)

        # State returns terminal
        r = _get("/api/cortex/onboarding/state")
        d = r.json()
        assert d["step"] == "complete"
        assert d["skipped_at"] is not None


# Import the constant for the second walk test.
import sys  # noqa: E402
sys.path.insert(0, "/app/backend")
from routes.cortex_onboarding import ONBOARDING_STEPS  # noqa: E402
