"""Tests for scheduling endpoints + AI optimal times + performance overview."""
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://social-sync-ai-1.preview.emergentagent.com").rstrip("/")
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def test_auth_me(session):
    r = session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "user_test1779636592168"


# ---- Scheduling ----
def test_publish_scheduled(session):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
    body = {
        "content": "TEST scheduled post for lasso testing",
        "platforms": ["instagram"],
        "scheduled_at": future,
    }
    r = session.post(f"{BASE_URL}/api/channels/publish", json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "scheduled"
    assert "id" in data
    pytest.scheduled_id = data["id"]


def test_list_scheduled_in_range(session):
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = session.get(f"{BASE_URL}/api/posts/scheduled", params={"start": start, "end": end}, timeout=15)
    assert r.status_code == 200, r.text
    posts = r.json()
    assert isinstance(posts, list)
    ids = [p["id"] for p in posts]
    assert pytest.scheduled_id in ids
    p0 = [p for p in posts if p["id"] == pytest.scheduled_id][0]
    assert p0["status"] == "scheduled"
    assert "instagram" in p0["platforms"]


def test_patch_scheduled(session):
    new_date = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0).isoformat()
    r = session.patch(
        f"{BASE_URL}/api/posts/scheduled/{pytest.scheduled_id}",
        json={"scheduled_at": new_date, "platforms": ["instagram", "x"]},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    # Verify persistence via GET
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    rg = session.get(f"{BASE_URL}/api/posts/scheduled", params={"start": start, "end": end}, timeout=15)
    posts = rg.json()
    p0 = [p for p in posts if p["id"] == pytest.scheduled_id][0]
    assert "x" in p0["platforms"]


def test_delete_scheduled(session):
    r = session.delete(f"{BASE_URL}/api/posts/scheduled/{pytest.scheduled_id}", timeout=15)
    assert r.status_code == 200, r.text
    # Verify removal
    r2 = session.delete(f"{BASE_URL}/api/posts/scheduled/{pytest.scheduled_id}", timeout=15)
    assert r2.status_code == 404


def test_delete_scheduled_not_found(session):
    r = session.delete(f"{BASE_URL}/api/posts/scheduled/nonexistent-id", timeout=15)
    assert r.status_code == 404


# ---- AI optimal times ----
def test_optimal_times_no_niche(session):
    r = session.post(
        f"{BASE_URL}/api/ai/optimal-times",
        json={"platforms": ["instagram"]},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "slots" in data
    assert "instagram" in data["slots"]
    slots = data["slots"]["instagram"]
    assert len(slots) >= 1
    first = slots[0]
    for k in ("datetime", "day", "hour", "score"):
        assert k in first, f"missing key {k}"
    assert data.get("rationale") in (None, "")


def test_optimal_times_with_niche(session):
    r = session.post(
        f"{BASE_URL}/api/ai/optimal-times",
        json={"platforms": ["instagram"], "niche": "fitness coaches", "audience": "women 25-40"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("rationale"), "rationale should be non-empty when niche provided"
    assert isinstance(data["rationale"], str)


# ---- Performance ----
def test_performance_overview_24h(session):
    r = session.get(f"{BASE_URL}/api/performance/overview", params={"range": "24h"}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["range"] == "24h"
    keys = [m["key"] for m in data["metrics"]]
    assert "sessions" in keys and "revenue" in keys
    series_keys = [s["key"] for s in data["series"]]
    assert "sessions" in series_keys
    assert len(data["labels"]) == 24
