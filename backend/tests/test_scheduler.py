"""Regression tests for the background scheduler (publish-due scheduled posts).

Runs against the live FastAPI server in this preview pod.
Requires test_session_1779636592168 / user_test1779636592168 with is_admin=true
in `test_database` (see /app/memory/test_credentials.md).
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

API_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _schedule(seconds_offset: int) -> str:
    """Create a scheduled post N seconds from now and return its id."""
    at = (datetime.now(timezone.utc) + timedelta(seconds=seconds_offset)).isoformat()
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={
            "content": f"sched-test-{uuid.uuid4().hex[:6]}",
            "platforms": ["instagram"],
            "scheduled_at": at,
        },
        timeout=10,
    )
    r.raise_for_status()
    body = r.json()
    assert body["status"] == "scheduled", body
    return body["id"]


def _get_post(post_id: str) -> dict | None:
    r = httpx.get(f"{API_URL}/api/posts", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return next((p for p in r.json() if p["id"] == post_id), None)


def test_past_scheduled_at_publishes_immediately():
    """If scheduled_at is in the past at publish-time, the API publishes immediately
    (no need to wait for the scheduler). Documents existing behavior."""
    at = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=HEADERS,
        json={
            "content": f"sched-test-immediate-{uuid.uuid4().hex[:6]}",
            "platforms": ["instagram"],
            "scheduled_at": at,
        },
        timeout=10,
    )
    r.raise_for_status()
    assert r.json()["status"] == "published"


def test_scheduler_publishes_future_due_post():
    pid = _schedule(seconds_offset=2)
    p = _get_post(pid)
    assert p["status"] == "scheduled"

    # Wait until the post is due, then trigger the scheduler manually
    time.sleep(3)
    r = httpx.post(f"{API_URL}/api/admin/scheduler/run-once", headers=HEADERS, timeout=10)
    r.raise_for_status()
    body = r.json()
    assert body["ok"] is True
    assert body["published_now"] >= 1
    assert pid in body["ids"]

    p = _get_post(pid)
    assert p["status"] == "published"
    assert p.get("publish_mode") == "scheduler"
    assert p.get("published_at")


def test_scheduler_does_not_publish_future_post():
    pid = _schedule(seconds_offset=300)  # 5 minutes from now
    r = httpx.post(f"{API_URL}/api/admin/scheduler/run-once", headers=HEADERS, timeout=10)
    r.raise_for_status()
    p = _get_post(pid)
    assert p["status"] == "scheduled", "future post must NOT be published yet"

    # Cleanup: cancel it
    httpx.delete(f"{API_URL}/api/posts/scheduled/{pid}", headers=HEADERS, timeout=10)


def test_run_once_requires_admin():
    # Hit with no auth → 401
    r = httpx.post(f"{API_URL}/api/admin/scheduler/run-once", timeout=10)
    assert r.status_code == 401


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    # Best-effort cleanup of any orphaned sched-test-* posts left behind.
    try:
        r = httpx.get(f"{API_URL}/api/posts", headers=HEADERS, timeout=10)
        for p in r.json():
            if p["content"].startswith("sched-test-"):
                if p["status"] == "scheduled":
                    httpx.delete(f"{API_URL}/api/posts/scheduled/{p['id']}", headers=HEADERS, timeout=10)
    except Exception:
        pass
