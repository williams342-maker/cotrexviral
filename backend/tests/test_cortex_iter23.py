"""Iter23 — Analysis Jobs system: durable queue + runner + chat integration.

Validates:
- /cortex/analysis-jobs POST creates a queued job + returns job_id.
- Unknown job_type → 400.
- >5 concurrent jobs → 429.
- Runner advances a seller_discovery job (safe mock) through phases →
  completed. Cortex chat message gets appended with kind="analysis_complete".
- /retry resets failed/cancelled jobs and re-fires the runner.
- /cancel marks queued/running jobs cancelled.
- /mark-reviewed transitions completed → reviewed.
"""
import asyncio
import os
import time
import uuid
import subprocess

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
COOKIES = {"session_token": TOKEN}


def _get(path):
    return requests.get(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES, timeout=20)


def _post(path, body=None):
    return requests.post(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES,
                          json=body or {}, timeout=20)


@pytest.fixture(autouse=True)
def _clean():
    """Wipe analysis_jobs for this user via subprocess (own loop)."""
    subprocess.run([
        "python3", "-c",
        f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.delete_many({{'user_id': '{USER_ID}'}})
asyncio.run(go())
"""
    ], check=False, timeout=15)
    yield


class TestCreateJob:
    def test_creates_queued_job(self):
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "seller_discovery", "target": "woodworking"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["job_type"] == "seller_discovery"
        assert d["status"] == "queued"
        assert d["progress_pct"] == 0
        assert len(d["id"]) == 32, "job_id must be a uuid hex"
        assert d["view_label"] == "View Discovered Sellers"

    def test_unknown_job_type_rejected(self):
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "shibboleth", "target": "x"})
        assert r.status_code == 400

    def test_too_many_active_jobs(self):
        """Cap is 5 simultaneous queued+running."""
        for _ in range(5):
            r = _post("/api/cortex/analysis-jobs",
                       {"job_type": "seller_discovery", "target": "x"})
            assert r.status_code == 200
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "seller_discovery", "target": "x"})
        assert r.status_code == 429


class TestRunner:
    def test_seller_discovery_completes_with_chat_message(self):
        """Mock runner advances through all phases and posts a Cortex
        chat message with kind='analysis_complete'."""
        # Get/create a conversation first so the chat message lands somewhere
        # readable. /history just reads the legacy bucket — easier path.
        r = _post("/api/cortex/console/conversations/new")
        if r.status_code == 200:
            conv_id = r.json().get("id")
        else:
            conv_id = None

        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "seller_discovery", "target": "woodworking",
                    "conversation_id": conv_id})
        assert r.status_code == 200
        job_id = r.json()["id"]

        # Wait up to 15s for completion (seller_discovery mock takes ~9s).
        deadline = time.time() + 18
        final_status = None
        while time.time() < deadline:
            r = _get(f"/api/cortex/analysis-jobs/{job_id}")
            assert r.status_code == 200
            j = r.json()
            final_status = j["status"]
            if final_status in ("completed", "failed", "cancelled"):
                break
            time.sleep(1.0)
        assert final_status == "completed", \
            f"Expected completed, got {final_status} (job={j})"
        assert j["progress_pct"] == 100
        assert j["result_summary"]
        assert "qualified" in (j["metrics"] or {})

        # Chat message persisted with kind='analysis_complete'.
        result = subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    r = await db.cortex_conversations.find_one(
        {{'user_id': '{USER_ID}', 'kind': 'analysis_complete', 'job_id': '{job_id}'}},
        {{'_id': 0}})
    print('FOUND' if r else 'MISSING', '|', (r or {{}}).get('message', '')[:80])
asyncio.run(go())
"""
        ], capture_output=True, text=True, timeout=15)
        assert "FOUND" in result.stdout, \
            f"Chat message missing for completed job (out={result.stdout!r})"


class TestRetryAndCancel:
    def test_cancel_queued_job(self):
        # Saturate the runner so subsequent jobs sit queued briefly.
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "seller_discovery", "target": "x"})
        job_id = r.json()["id"]
        # Cancel immediately while still queued/running.
        r = _post(f"/api/cortex/analysis-jobs/{job_id}/cancel")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"

    def test_retry_resets_cancelled_job(self):
        # Create + cancel.
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "seller_discovery", "target": "x"})
        job_id = r.json()["id"]
        _post(f"/api/cortex/analysis-jobs/{job_id}/cancel")
        # Retry → must transition back to queued or running.
        r = _post(f"/api/cortex/analysis-jobs/{job_id}/retry")
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("queued", "running")
        assert r.json()["error_message"] is None


class TestMarkReviewed:
    def test_completed_job_can_be_marked_reviewed(self):
        # Insert a completed job directly to skip the 10s wait.
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'completed-test-job-fixed',
        'user_id': '{USER_ID}',
        'job_type': 'seller_discovery',
        'status': 'completed',
        'progress_pct': 100,
        'queued_at': datetime.now(timezone.utc),
        'completed_at': datetime.now(timezone.utc),
        'metrics': {{'qualified': 10}},
        'result_summary': 'done',
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/completed-test-job-fixed/mark-reviewed")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "reviewed"


class TestCreateMissionFromJob:
    def test_seo_scan_completed_creates_seo_fix_mission(self):
        """Seed a completed SEO job, hit /create-mission, verify a real
        mission row exists in the missions collection with seo_fix type."""
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'seoscan-finished-1',
        'user_id': '{USER_ID}',
        'job_type': 'seo_scan',
        'status': 'completed',
        'progress_pct': 100,
        'target': 'https://example.com',
        'queued_at': datetime.now(timezone.utc),
        'completed_at': datetime.now(timezone.utc),
        'metrics': {{'issues_found': 14, 'high_priority': 3, 'recommendations': 9}},
        'result_summary': 'done',
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/seoscan-finished-1/create-mission")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mission_id"]
        assert "Fix SEO findings" in d["title"]
        assert d["already_created"] is False

        # Idempotency: second call returns same mission.
        r2 = _post("/api/cortex/analysis-jobs/seoscan-finished-1/create-mission")
        assert r2.status_code == 200
        assert r2.json()["mission_id"] == d["mission_id"]
        assert r2.json()["already_created"] is True

        # Mission row exists in `missions` with correct shape.
        result = subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    m = await db.missions.find_one({{'id': '{d["mission_id"]}',
                                       'user_id': '{USER_ID}'}}, {{'_id': 0}})
    print('TYPE:', m.get('mission_type') if m else 'MISSING')
    print('TARGET:', m.get('target') if m else 'MISSING')
    print('AUTONOMY:', m.get('autonomy_level') if m else 'MISSING')
asyncio.run(go())
"""
        ], capture_output=True, text=True, timeout=15)
        assert "TYPE: seo_fix" in result.stdout, result.stdout
        assert "TARGET: 14" in result.stdout
        assert "AUTONOMY: 2" in result.stdout

    def test_seller_discovery_creates_seller_acquisition_mission(self):
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'sd-finished-1',
        'user_id': '{USER_ID}',
        'job_type': 'seller_discovery',
        'status': 'completed',
        'progress_pct': 100,
        'target': 'candles',
        'queued_at': datetime.now(timezone.utc),
        'completed_at': datetime.now(timezone.utc),
        'metrics': {{'qualified': 32, 'tier_1': 8}},
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/sd-finished-1/create-mission")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mission_id"]
        assert "Recruit qualified sellers" in d["title"]

    def test_non_completed_job_rejected(self):
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'running-1',
        'user_id': '{USER_ID}',
        'job_type': 'seo_scan',
        'status': 'running',
        'progress_pct': 50,
        'queued_at': datetime.now(timezone.utc),
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/running-1/create-mission")
        assert r.status_code == 409, r.text


class TestListGrouping:
    def test_list_groups_by_status(self):
        # Insert one of each status via subprocess.
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    now = datetime.now(timezone.utc)
    rows = [
        {{'id': 'rj1', 'user_id': '{USER_ID}', 'job_type': 'seller_discovery',
          'status': 'running', 'progress_pct': 50, 'queued_at': now,
          'current_step': 'x', 'next_step': 'y'}},
        {{'id': 'cj1', 'user_id': '{USER_ID}', 'job_type': 'seller_discovery',
          'status': 'completed', 'progress_pct': 100, 'queued_at': now,
          'metrics': {{'qualified': 5}}, 'result_summary': 'ok'}},
    ]
    await db.analysis_jobs.insert_many(rows)
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _get("/api/cortex/analysis-jobs")
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("grouped"), dict)
        assert any(j["id"] == "rj1" for j in d["grouped"].get("running", []))
        assert any(j["id"] == "cj1" for j in d["grouped"].get("completed", []))
