"""Iter17 — Cortex Autonomous OODA Optimization Loop tests.

Covers:
  * POST /api/cortex/optimization/run-now → triggers one iteration
  * GET  /api/cortex/optimization/log → recent findings (newest first)
  * GET  /api/cortex/optimization/status → headline (active, latest, counts)
  * De-dupe: 2nd call within 12h for same kind returns fired=false
  * Detector rules: discovery_stall for the test user with 5 running missions + 0 leads
  * Stage classifier discovery-ack normalization (appends '?' when missing)
  * Scheduler: cortex_optimization_loop job is registered (30min interval)
"""
from __future__ import annotations

import os
import sys
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://social-sync-ai-1.preview.emergentagent.com").rstrip("/")
USER_ID = "user_test1779636592168"
SESSION_TOKEN = "test_session_1779636592168"
HEADERS = {
    "Authorization": f"Bearer {SESSION_TOKEN}",
    "Content-Type": "application/json",
}
COOKIES = {"session_token": SESSION_TOKEN}

# Ensure backend modules are importable for the unit test.
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.cookies.update(COOKIES)
    return s


# ------------------------------------------------------- helpers
def _clear_log_for_user():
    """Wipe cortex_optimization_log for the test user so dedupe tests are clean."""
    async def _go():
        from core import db
        await db.cortex_optimization_log.delete_many({"user_id": USER_ID})
    asyncio.run(_go())


# ============================================================== STATUS
class TestOptimizationStatus:
    def test_status_endpoint_shape(self, api):
        r = api.get(f"{BASE_URL}/api/cortex/optimization/status")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("active", "latest", "detections_24h",
                  "detections_7d", "improved_7d", "monitoring_since"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["detections_24h"], int)
        assert isinstance(d["detections_7d"], int)
        assert isinstance(d["improved_7d"], int)


# ============================================================== RUN-NOW + DETECTOR
class TestRunNowAndDetector:
    @classmethod
    def setup_class(cls):
        _clear_log_for_user()

    def test_run_now_fires_discovery_stall(self, api):
        r = api.post(f"{BASE_URL}/api/cortex/optimization/run-now", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ran"] is True
        assert d["fired"] is True, f"expected fired=true for user with 5 running missions + 0 leads: {d}"
        finding = d["finding"]
        assert finding is not None
        # Validate shape
        for k in ("id", "user_id", "kind", "observations", "bottleneck",
                  "hypothesis", "recommendation", "confidence",
                  "autonomy_level", "autonomy_taken", "created_at"):
            assert k in finding, f"finding missing key {k}: {finding.keys()}"
        assert finding["user_id"] == USER_ID
        assert finding["kind"] == "discovery_stall"
        assert 0.0 <= finding["confidence"] <= 1.0
        assert abs(finding["confidence"] - 0.78) < 0.001
        # Observations snapshot must be embedded
        obs = finding["observations"]
        assert isinstance(obs, dict)
        assert obs.get("user_id") == USER_ID
        assert obs.get("missions", {}).get("running", 0) >= 1
        assert obs.get("funnel_total", 0) == 0

    def test_run_now_dedupes_within_12h(self, api):
        # Calling again immediately for same `kind` (discovery_stall) → fired=false
        r = api.post(f"{BASE_URL}/api/cortex/optimization/run-now", json={})
        assert r.status_code == 200
        d = r.json()
        assert d["ran"] is True
        assert d["fired"] is False, f"dedupe failed — expected fired=false on repeat call: {d}"
        assert d["finding"] is None


# ============================================================== LOG
class TestOptimizationLog:
    def test_log_returns_persisted_finding(self, api):
        r = api.get(f"{BASE_URL}/api/cortex/optimization/log")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "count" in d
        assert d["count"] == len(d["items"])
        assert d["count"] >= 1, "expected at least the discovery_stall finding from previous test"
        top = d["items"][0]
        for k in ("id", "user_id", "kind", "bottleneck", "hypothesis",
                  "recommendation", "confidence", "created_at"):
            assert k in top
        assert top["user_id"] == USER_ID
        # newest-first ordering — created_at should be ISO string, descending
        if len(d["items"]) >= 2:
            assert d["items"][0]["created_at"] >= d["items"][1]["created_at"]

    def test_status_now_active_with_latest(self, api):
        r = api.get(f"{BASE_URL}/api/cortex/optimization/status")
        d = r.json()
        assert d["active"] is True
        assert d["latest"] is not None
        assert d["latest"]["user_id"] == USER_ID
        assert d["latest"]["kind"] == "discovery_stall"
        assert d["detections_24h"] >= 1


# ============================================================== STAGE NORMALIZE
class TestStageNormalize:
    """Unit test the cortex.stages._normalize discovery-ack postprocessing."""
    def test_normalize_appends_question_when_missing(self):
        from cortex.stages import _normalize
        intent_types = ["launch_seller_mission", "generate_content_plan"]
        out = _normalize({
            "stage": "discovery",
            "ack": "You want growth.",
            "clarifying_questions": ["What is your goal?"],
        }, intent_types)
        assert out["stage"] == "discovery"
        assert "?" in out["ack"], f"expected ack to end with '?', got: {out['ack']!r}"
        # The clarifying question should be merged in
        assert "What is your goal?" in out["ack"]

    def test_normalize_preserves_question_already_present(self):
        from cortex.stages import _normalize
        out = _normalize({
            "stage": "discovery",
            "ack": "What's your top priority?",
            "clarifying_questions": ["What is your goal?"],
        }, [])
        # Already has '?', should NOT mangle
        assert out["ack"] == "What's your top priority?"


# ============================================================== SCHEDULER
class TestScheduler:
    def test_cortex_optimization_loop_job_registered(self):
        """Job should be registered with id='cortex_optimization_loop' at 30min interval."""
        from routes import scheduler as sched_mod
        sch = sched_mod.scheduler
        if sch is None:
            pytest.skip("scheduler not started in this process")
        ids = [j.id for j in sch.get_jobs()]
        assert "cortex_optimization_loop" in ids, f"job not registered: {ids}"
        job = next(j for j in sch.get_jobs() if j.id == "cortex_optimization_loop")
        # Trigger interval should be 30 minutes (1800s)
        interval = getattr(job.trigger, "interval", None)
        if interval is not None:
            assert interval.total_seconds() == 1800, f"expected 1800s, got {interval.total_seconds()}"


# ============================================================== DETECTOR UNIT (offline)
class TestDetectorRules:
    """Verify each of the 5 rules fires on synthetic snapshots (no DB)."""
    def test_discovery_stall(self):
        from cortex.optimization_loop import _rules
        snap = {"missions": {"running": 5, "paused": 0}, "funnel_total": 0,
                "funnel": {}, "outreach_24h": {"sent": 0, "opened": 0, "replied": 0}}
        out = _rules(snap)
        kinds = [x["kind"] for x in out]
        assert "discovery_stall" in kinds

    def test_qualification_bottleneck(self):
        from cortex.optimization_loop import _rules
        snap = {"missions": {"running": 0}, "funnel_total": 50,
                "funnel": {"discovered": 50, "qualified": 5},
                "outreach_24h": {"sent": 0, "opened": 0, "replied": 0}}
        out = _rules(snap)
        kinds = [x["kind"] for x in out]
        assert "qualification_bottleneck" in kinds

    def test_deliverability_risk(self):
        from cortex.optimization_loop import _rules
        snap = {"missions": {"running": 0}, "funnel_total": 0, "funnel": {},
                "outreach_24h": {"sent": 30, "opened": 0, "replied": 0},
                "open_rate": 0.0, "reply_rate": 0.0}
        out = _rules(snap)
        kinds = [x["kind"] for x in out]
        assert "deliverability_risk" in kinds

    def test_copy_conversion_gap(self):
        from cortex.optimization_loop import _rules
        snap = {"missions": {"running": 0}, "funnel_total": 0, "funnel": {},
                "outreach_24h": {"sent": 100, "opened": 30, "replied": 0},
                "open_rate": 0.3, "reply_rate": 0.0}
        out = _rules(snap)
        kinds = [x["kind"] for x in out]
        assert "copy_conversion_gap" in kinds

    def test_onboarding_stall(self):
        from cortex.optimization_loop import _rules
        snap = {"missions": {"running": 0}, "funnel_total": 8,
                "funnel": {"interested": 8, "onboarded": 0},
                "outreach_24h": {"sent": 0, "opened": 0, "replied": 0}}
        out = _rules(snap)
        kinds = [x["kind"] for x in out]
        assert "onboarding_stall" in kinds
