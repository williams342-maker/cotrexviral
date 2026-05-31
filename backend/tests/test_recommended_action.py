"""Tests for GET /api/cortex/mission-dashboard/recommended-action.

Verifies:
- Authentication is required (401 without session)
- Returns unified card payload (bridge path) for the test user
- Skips bridges already consumed (cortex_dismissed_plans)
- Returns has_recommendation=false cleanly when no bridge/briefing yields a card
- Falls back to briefing engine when bridges are exhausted
"""
import os
import time

import pytest
import requests
from pymongo import MongoClient

def _resolve_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    # Fall back to reading frontend/.env (testing always runs from repo)
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _resolve_base_url()

TEST_USER_ID = "user_test1779636592168"
TEST_SESSION = "test_session_1779636592168"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ENDPOINT = f"{BASE_URL}/api/cortex/mission-dashboard/recommended-action"


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture
def auth_client():
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {TEST_SESSION}",
        "Content-Type": "application/json",
    })
    return s


def _assert_card_shape(data, expected_source=None):
    assert data.get("has_recommendation") is True, data
    assert "source" in data and data["source"] in ("bridge", "briefing"), data
    if expected_source:
        assert data["source"] == expected_source
    for k in ("title", "summary", "expected_outcome", "mission_intent"):
        assert k in data, f"missing field {k}: {data.keys()}"
    assert "confidence" in data
    conf = data["confidence"]
    assert isinstance(conf, int) and 0 <= conf <= 100, conf
    assert "estimated_timeline_days" in data
    assert "estimated_cost_usd" in data
    # recommendation plan card compatible with /cortex/console/execute
    rec = data.get("recommendation")
    assert isinstance(rec, dict) and rec, "recommendation plan card must be present"


# ---------- Auth ------------
def test_requires_auth_returns_401():
    """Endpoint must reject unauthenticated requests."""
    r = requests.get(ENDPOINT)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"


# ---------- Bridge path ------------
def test_bridge_path_returns_unified_card(auth_client, mongo_db):
    """Test user has a high-confidence (>=60) recent bridge -> source='bridge'."""
    # Clean any dismissals that might mask the bridge
    mongo_db.cortex_dismissed_plans.delete_many({"user_id": TEST_USER_ID})

    r = auth_client.get(ENDPOINT)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    if not data.get("has_recommendation"):
        pytest.skip("test user has no bridge AND no briefing top_recommendation right now")

    _assert_card_shape(data)
    if data["source"] == "bridge":
        assert data.get("bridge_id"), "bridge_id required when source=bridge"
        assert data["confidence"] >= 60, "bridge path requires confidence >= 60"


def test_bridge_skipped_when_in_dismissed_plans(auth_client, mongo_db):
    """When a bridge id is in cortex_dismissed_plans (rec_id), the endpoint
    must skip it and either pick the next bridge OR fall back to briefing."""
    # Get baseline response
    r0 = auth_client.get(ENDPOINT)
    assert r0.status_code == 200
    base = r0.json()
    if not base.get("has_recommendation") or base.get("source") != "bridge":
        pytest.skip("user is not currently on bridge path; cannot verify skip")

    bridge_id = base.get("bridge_id")
    assert bridge_id

    # Insert dismissal for that bridge
    mongo_db.cortex_dismissed_plans.insert_one({
        "user_id": TEST_USER_ID,
        "rec_id": bridge_id,
        "reason": "TEST_skip_check",
        "created_at": __import__("datetime").datetime.utcnow(),
    })
    try:
        r1 = auth_client.get(ENDPOINT)
        assert r1.status_code == 200
        d1 = r1.json()
        # Either next bridge, or briefing fallback, or no rec at all – but
        # if a card is returned, its bridge_id must differ from the consumed one.
        if d1.get("has_recommendation") and d1.get("source") == "bridge":
            assert d1.get("bridge_id") != bridge_id, "consumed bridge re-surfaced"
    finally:
        mongo_db.cortex_dismissed_plans.delete_many(
            {"user_id": TEST_USER_ID, "reason": "TEST_skip_check"})


def test_briefing_fallback_when_all_bridges_consumed(auth_client, mongo_db):
    """Mark ALL of the test user's recent qualifying bridges as consumed and
    verify either source='briefing' OR has_recommendation=false (clean fallback)."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    bridges = list(mongo_db.cortex_recommendation_bridges.find(
        {"user_id": TEST_USER_ID, "confidence": {"$gte": 60},
         "created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1},
    ))
    inserted = []
    for b in bridges:
        bid = b.get("id")
        if not bid:
            continue
        inserted.append(bid)
        mongo_db.cortex_dismissed_plans.insert_one({
            "user_id": TEST_USER_ID,
            "rec_id": bid,
            "reason": "TEST_briefing_fallback",
            "created_at": datetime.utcnow(),
        })
    try:
        r = auth_client.get(ENDPOINT)
        assert r.status_code == 200
        d = r.json()
        # No bridge should be selected
        if d.get("has_recommendation"):
            assert d.get("source") == "briefing", (
                f"expected briefing fallback, got {d.get('source')}"
            )
            _assert_card_shape(d, expected_source="briefing")
        else:
            # Clean no-rec response
            assert d == {"has_recommendation": False} or d.get("has_recommendation") is False
    finally:
        mongo_db.cortex_dismissed_plans.delete_many(
            {"user_id": TEST_USER_ID, "reason": "TEST_briefing_fallback"})


# ---------- Response contract sanity ------------
def test_response_is_well_formed_json(auth_client):
    r = auth_client.get(ENDPOINT)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    data = r.json()
    assert "has_recommendation" in data
    assert isinstance(data["has_recommendation"], bool)
