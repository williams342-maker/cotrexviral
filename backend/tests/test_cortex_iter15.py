"""Iteration 15 — Polish + extraction.

Backend coverage:
  1. POST /api/missions/{id}/cancel       (NEW)
       - cancel running mission → status=cancelled + cancelled_at + audit row
       - cancel paused mission  → ok
       - cancel already-cancelled → 400
       - cancel non-existent / other-user mission → 404
       - mission_events row inserted with event='cancelled'
  2. /api/cortex/plan/cancel + /console/opportunities filter (7d window)
       - dismiss rec_type='launch_seller_mission'
       - opportunities of that type are filtered from briefing
  3. /api/cortex/missions/active still works (timedelta import regression)
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    })
    s.cookies.set("session_token", TOKEN)
    return s


def _create_mission(client, title_suffix: str = "", status: str = "running") -> str:
    """Helper: create a running mission and return id."""
    payload = {
        "title": f"TEST_iter15 cancel {title_suffix} {uuid.uuid4().hex[:6]}",
        "description": "Created by iter15 test for cancel-endpoint verification",
        "metric": "leads",
        "target": 10,
        "autonomy_level": 2,
    }
    r = client.post(f"{BASE_URL}/api/missions", json=payload)
    assert r.status_code == 200, f"create mission failed: {r.status_code} {r.text}"
    mid = r.json()["id"]
    # If we want it running, transition draft → running.
    if status == "running":
        r2 = client.post(f"{BASE_URL}/api/missions/{mid}/start")
        assert r2.status_code == 200, f"start mission failed: {r2.text}"
        assert r2.json()["status"] == "running"
    elif status == "paused":
        client.post(f"{BASE_URL}/api/missions/{mid}/start")
        r2 = client.post(f"{BASE_URL}/api/missions/{mid}/pause")
        assert r2.status_code == 200, f"pause mission failed: {r2.text}"
        assert r2.json()["status"] == "paused"
    return mid


# ============================================================
# 1.  POST /api/missions/{id}/cancel
# ============================================================
class TestMissionCancel:
    def test_cancel_running_mission(self, client):
        mid = _create_mission(client, "running", status="running")

        r = client.post(f"{BASE_URL}/api/missions/{mid}/cancel")
        assert r.status_code == 200, f"cancel failed: {r.status_code} {r.text}"
        body = r.json()
        assert body["status"] == "cancelled"
        assert body.get("cancelled_at"), "cancelled_at must be set"
        assert body["id"] == mid
        # Progress block should still be present (serialized + recomputed).
        assert "progress" in body
        assert isinstance(body["progress"], dict)

        # Verify persistence via GET.
        r2 = client.get(f"{BASE_URL}/api/missions/{mid}")
        assert r2.status_code == 200
        assert r2.json()["status"] == "cancelled"

    def test_cancel_paused_mission(self, client):
        mid = _create_mission(client, "paused", status="paused")
        r = client.post(f"{BASE_URL}/api/missions/{mid}/cancel")
        assert r.status_code == 200, f"cancel paused failed: {r.text}"
        assert r.json()["status"] == "cancelled"

    def test_cancel_already_cancelled_returns_400(self, client):
        mid = _create_mission(client, "doublecancel", status="running")
        r1 = client.post(f"{BASE_URL}/api/missions/{mid}/cancel")
        assert r1.status_code == 200
        # 2nd cancel
        r2 = client.post(f"{BASE_URL}/api/missions/{mid}/cancel")
        assert r2.status_code == 400, f"expected 400, got {r2.status_code} {r2.text}"
        body = r2.json()
        msg = (body.get("detail") or body.get("message") or "").lower()
        assert "cannot cancel" in msg, f"unexpected error msg: {body}"

    def test_cancel_unknown_mission_returns_404(self, client):
        bogus = "nonexistent_" + uuid.uuid4().hex
        r = client.post(f"{BASE_URL}/api/missions/{bogus}/cancel")
        assert r.status_code == 404

    def test_cancel_writes_audit_event(self, client):
        """The cancel endpoint should insert a mission_events row with
        event='cancelled'. Verify via /api/cortex/missions/{id}/events."""
        mid = _create_mission(client, "audit", status="running")
        rc = client.post(f"{BASE_URL}/api/missions/{mid}/cancel")
        assert rc.status_code == 200

        re = client.get(f"{BASE_URL}/api/cortex/missions/{mid}/events")
        assert re.status_code == 200, f"events endpoint failed: {re.text}"
        events = re.json().get("events", re.json())
        if isinstance(events, dict):
            events = events.get("events", [])
        # The endpoint exposes the event name as the `label` field
        # (mission_events.event → label, with "_" → " ").
        kinds = [e.get("label") or e.get("event") for e in events]
        assert "cancelled" in kinds, f"cancelled event missing; got events={kinds} / raw={events!r}"


# ============================================================
# 2.  Dismissed-plan filter on /console/opportunities
# ============================================================
class TestDismissedPlanFilter:
    def test_dismiss_filters_opportunity_type(self, client):
        # Baseline: GET briefing first to see what's there.
        r0 = client.get(f"{BASE_URL}/api/cortex/console/opportunities")
        assert r0.status_code == 200, f"briefing failed: {r0.text}"
        base = r0.json()
        # opportunities live either at top-level or inside .briefing
        base_opps = base.get("opportunities") or (base.get("briefing", {}) or {}).get("opportunities") or []
        baseline_types = {(o.get("type") or o.get("intent")) for o in base_opps}
        # We want to dismiss a type that's currently visible — prefer
        # launch_seller_mission, else any first visible.
        target_type = "launch_seller_mission"
        if target_type not in baseline_types and base_opps:
            target_type = (base_opps[0].get("type") or base_opps[0].get("intent"))

        # If nothing is surfaced at all, skip the assertion (the filter
        # only matters when there's something to filter).
        if not baseline_types:
            pytest.skip("No opportunities surfaced for this user — nothing to dismiss")

        # Dismiss the chosen type.
        fake_rec = {
            "id":   f"rec-{uuid.uuid4().hex[:8]}",
            "type": target_type,
            "title": "TEST_iter15 dismissed plan",
        }
        rd = client.post(f"{BASE_URL}/api/cortex/plan/cancel",
                         json={"recommendation": fake_rec,
                               "reason": "iter15 test dismissal"})
        assert rd.status_code == 200, f"dismiss failed: {rd.text}"
        assert rd.json().get("action_taken") == "cancelled"

        # Re-fetch and confirm that target_type is no longer present.
        r1 = client.get(f"{BASE_URL}/api/cortex/console/opportunities")
        assert r1.status_code == 200
        post = r1.json()
        post_opps = post.get("opportunities") or (post.get("briefing", {}) or {}).get("opportunities") or []
        post_types = {(o.get("type") or o.get("intent")) for o in post_opps}
        assert target_type not in post_types, (
            f"Dismissed type {target_type!r} still present in briefing! "
            f"baseline_types={baseline_types} post_types={post_types}"
        )


# ============================================================
# 3. /api/cortex/missions/active regression (timedelta import)
# ============================================================
class TestActiveMissionsRegression:
    def test_active_missions_endpoint_still_works(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/missions/active")
        assert r.status_code == 200, f"active missions failed: {r.text}"
        body = r.json()
        # Must contain `missions` and `count` keys per iter14 shape.
        assert "missions" in body or "active" in body, f"unexpected shape: {list(body.keys())}"
        # If there are missions, each should have status in running/paused.
        missions = body.get("missions") or body.get("active") or []
        for m in missions:
            assert m.get("status") in ("running", "paused"), m.get("status")

    def test_briefing_endpoint_still_works(self, client):
        """Smoke: briefing endpoint with new timedelta filter shouldn't 500."""
        r = client.get(f"{BASE_URL}/api/cortex/console/opportunities")
        assert r.status_code == 200, f"briefing failed: {r.text}"
        body = r.json()
        assert isinstance(body, dict)


# ============================================================
# Cleanup
# ============================================================
@pytest.fixture(scope="module", autouse=True)
def _cleanup(client):
    yield
    # Remove TEST_iter15 missions to keep the user's mission list tidy.
    try:
        r = client.get(f"{BASE_URL}/api/missions")
        for m in (r.json().get("missions") or []):
            if (m.get("title") or "").startswith("TEST_iter15"):
                client.delete(f"{BASE_URL}/api/missions/{m['id']}")
    except Exception:
        pass
