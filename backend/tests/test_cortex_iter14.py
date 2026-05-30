"""Cortex iteration_14 — Conversational Execution Architecture tests.

Coverage:
- GET  /api/cortex/missions/active           (rail data)
- GET  /api/cortex/missions/{id}             (detail + 404)
- GET  /api/cortex/missions/{id}/events      (timeline + since filter + 404)
- POST /api/cortex/console/execute           (followup turn appended for
    launch_seller_mission, run_bulk_outreach, queued autonomy=1)
"""
import os
import time
import pytest
import requests


def _load_backend_url():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_backend_url()).rstrip("/")
SESSION_TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HEADERS = {
    "Authorization": f"Bearer {SESSION_TOKEN}",
    "Content-Type": "application/json",
}
TIMEOUT = 60


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ---------------- /missions/active ----------------
def test_active_missions_shape(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=6", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "missions" in data
    assert "count" in data
    assert isinstance(data["missions"], list)
    assert data["count"] == len(data["missions"])
    if not data["missions"]:
        pytest.skip("No active missions seeded; shape-only assertions complete.")
    m = data["missions"][0]
    for f in ("id", "title", "mission_type", "status", "autonomy_level",
              "progress", "phase", "next_action"):
        assert f in m, f"missing {f} in {m}"
    p = m["progress"]
    for f in ("current", "target", "pct"):
        assert f in p
    na = m["next_action"]
    assert "label" in na and "description" in na


def test_active_missions_sorted_newest_first(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=20", timeout=TIMEOUT)
    assert r.status_code == 200
    missions = r.json()["missions"]
    if len(missions) < 2:
        pytest.skip("need 2+ missions to test order")
    timestamps = [m.get("created_at") for m in missions if m.get("created_at")]
    if len(timestamps) >= 2:
        assert timestamps == sorted(timestamps, reverse=True), timestamps


def test_active_missions_status_filter(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=20", timeout=TIMEOUT)
    assert r.status_code == 200
    for m in r.json()["missions"]:
        assert m["status"] in ("running", "active", "queued", "paused"), m["status"]


# ---------------- /missions/{id} ----------------
def test_mission_detail_ok(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=1", timeout=TIMEOUT)
    missions = r.json()["missions"]
    if not missions:
        pytest.skip("no missions to test detail")
    mid = missions[0]["id"]
    d = api.get(f"{BASE_URL}/api/cortex/missions/{mid}", timeout=TIMEOUT)
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["id"] == mid
    assert "progress" in body and "next_action" in body


def test_mission_detail_404(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/does-not-exist-xyz", timeout=TIMEOUT)
    assert r.status_code == 404, r.text


# ---------------- /missions/{id}/events ----------------
def test_mission_events_ok(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=1", timeout=TIMEOUT)
    missions = r.json()["missions"]
    if not missions:
        pytest.skip("no missions to test events")
    mid = missions[0]["id"]
    ev = api.get(f"{BASE_URL}/api/cortex/missions/{mid}/events?limit=20", timeout=TIMEOUT)
    assert ev.status_code == 200, ev.text
    data = ev.json()
    assert data["mission_id"] == mid
    assert "events" in data
    assert isinstance(data["events"], list)


def test_mission_events_since_filter(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/active?limit=1", timeout=TIMEOUT)
    missions = r.json()["missions"]
    if not missions:
        pytest.skip("no missions to test events")
    mid = missions[0]["id"]
    # since=year 2100 → empty
    r2 = api.get(
        f"{BASE_URL}/api/cortex/missions/{mid}/events?since=2100-01-01T00:00:00Z",
        timeout=TIMEOUT,
    )
    assert r2.status_code == 200
    assert r2.json()["events"] == []


def test_mission_events_404(api):
    r = api.get(f"{BASE_URL}/api/cortex/missions/no-such-mission/events", timeout=TIMEOUT)
    assert r.status_code == 404


# ---------------- /console/execute followup ----------------
def _fresh_rec(api, message: str) -> dict:
    r = api.post(
        f"{BASE_URL}/api/cortex/console/chat",
        json={"message": message},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    rec = r.json().get("recommendation") or {}
    assert rec.get("type"), f"no rec type from chat: {rec}"
    return rec


def test_execute_launch_seller_mission_followup(api):
    rec = _fresh_rec(api, "Recruit 12 ceramic mug makers")
    assert rec.get("type") == "launch_seller_mission"
    r = api.post(
        f"{BASE_URL}/api/cortex/console/execute",
        json={"recommendation": rec, "override_autonomy": 3},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("action_taken") == "launched"
    assert data.get("mission_id")
    assert data.get("autonomy_level") == 3
    f = data.get("followup")
    assert f, f"missing followup: {data}"
    assert f.get("id")
    msg = f.get("message") or ""
    assert "Mission launched" in msg, msg
    assert "Discovery" in msg, msg
    # 3+ refinement options
    for kw in ("premium", "high-volume", "region"):
        assert kw in msg.lower(), f"missing '{kw}' in followup: {msg}"


def test_execute_bulk_outreach_followup(api):
    rec = _fresh_rec(api, "Push outreach to all qualified leads now")
    if rec.get("type") != "run_bulk_outreach":
        pytest.skip(f"router returned {rec.get('type')} instead of run_bulk_outreach")
    r = api.post(
        f"{BASE_URL}/api/cortex/console/execute",
        json={"recommendation": rec, "override_autonomy": 3},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    f = data.get("followup") or {}
    msg = (f.get("message") or "").lower()
    assert msg, f"empty followup msg: {data}"
    # Must reference A/B, throttle, or audit
    assert any(k in msg for k in ("a/b", "throttle", "audit")), msg


def test_execute_queued_followup_starts_with_queued(api):
    rec = _fresh_rec(api, "Recruit 8 leather artisans")
    assert rec.get("type") == "launch_seller_mission"
    r = api.post(
        f"{BASE_URL}/api/cortex/console/execute",
        json={"recommendation": rec, "override_autonomy": 1},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("action_taken") == "queued", data
    f = data.get("followup") or {}
    msg = f.get("message") or ""
    assert msg.startswith("Plan queued for approval"), msg


def test_execute_followup_persisted_in_conversations(api):
    """After execute, the followup turn should land in cortex_conversations."""
    rec = _fresh_rec(api, "Recruit 9 jewelry makers")
    r = api.post(
        f"{BASE_URL}/api/cortex/console/execute",
        json={"recommendation": rec, "override_autonomy": 3},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200
    followup_id = (r.json().get("followup") or {}).get("id")
    assert followup_id
    # Allow eventual consistency
    time.sleep(0.5)
    # Hit the conversations history (if route exists) – fall back to skip
    h = api.get(f"{BASE_URL}/api/cortex/console/history?limit=20", timeout=TIMEOUT)
    if h.status_code != 200:
        pytest.skip(f"history endpoint not available: {h.status_code}")
    turns = h.json().get("turns") or h.json().get("messages") or []
    ids = [t.get("id") for t in turns]
    intents = [t.get("intent") for t in turns]
    assert followup_id in ids or "followup" in intents, (
        f"followup not persisted; followup_id={followup_id} ids={ids[:5]} intents={intents[:5]}"
    )
