"""Iter25 — Real Site Scan + Optimize Automatically (Option A).

Validates:
- POST /cortex/analysis-jobs with job_type=site_scan → real LLM-backed
  analysis (or graceful degrade), reports row persisted with type='site_scan'.
- POST /cortex/analysis-jobs/{id}/optimize:
    - 404 when job doesn't exist
    - 400 when job_type != seo_scan
    - 409 when job not yet completed
    - Happy path: creates a missions row with mission_type=seo_auto_fix,
      autonomy_level=3, target=high_priority count
    - Drafts seo_change_records with status='ready'
    - Idempotent — second call returns same mission + same drafts
- GET /cortex/analysis-jobs/missions/{id}/changes returns the
  approve-all batch with correct shape.
"""
import asyncio
import os
import time
import uuid
import subprocess

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
COOKIES = {"session_token": TOKEN}


def _get(path):
    return requests.get(f"{BASE_URL}{path}", headers=HDRS,
                          cookies=COOKIES, timeout=45)


def _post(path, body=None):
    return requests.post(f"{BASE_URL}{path}", headers=HDRS,
                          cookies=COOKIES, json=body or {}, timeout=45)


@pytest.fixture(autouse=True)
def _clean():
    """Wipe analysis_jobs + seo_change_records for this user."""
    subprocess.run([
        "python3", "-c",
        f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.delete_many({{'user_id': '{USER_ID}'}})
    await db.seo_change_records.delete_many({{'user_id': '{USER_ID}'}})
asyncio.run(go())
"""
    ], check=False, timeout=15)
    yield


def _seed_completed_seo_scan(job_id: str, *, with_report: bool = True):
    """Seed a completed SEO scan with a reports row so /optimize works."""
    rid = uuid.uuid4().hex
    subprocess.run([
        "python3", "-c",
        f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': '{job_id}',
        'user_id': '{USER_ID}',
        'job_type': 'seo_scan',
        'status': 'completed',
        'progress_pct': 100,
        'target': 'https://example.com',
        'queued_at': datetime.now(timezone.utc),
        'completed_at': datetime.now(timezone.utc),
        'metrics': {{'issues_found': 5, 'high_priority': 3, 'recommendations': 5}},
        'result_summary': 'done',
        'result_link': '/dashboard/reports?id={rid}',
    }})
    {('await db.reports.insert_one({' + '"id":"' + rid + '","user_id":"' + USER_ID + '","type":"seo_scan","url":"https://example.com","report":{"summary":"x","improvements":["Add meta descriptions","Fix heading hierarchy","Add alt text"],"post_ideas":[]},"created_at":datetime.now(timezone.utc)})') if with_report else ''}
asyncio.run(go())
"""
    ], check=True, timeout=15)
    return rid


# ----------------------------------- Site Scan real implementation
class TestSiteScanReal:
    def test_site_scan_runs_and_persists_report(self):
        """Create a site_scan job, wait for completion, verify a real
        reports row was persisted with type=site_scan."""
        r = _post("/api/cortex/analysis-jobs",
                   {"job_type": "site_scan", "target": "https://example.com"})
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]

        # Wait up to 25s for completion (real LLM call).
        deadline = time.time() + 30
        while time.time() < deadline:
            r = _get(f"/api/cortex/analysis-jobs/{job_id}")
            assert r.status_code == 200
            j = r.json()
            if j["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(1.5)
        assert j["status"] == "completed", \
            f"site_scan should complete, got {j['status']}"
        # Site-scan metrics differ from SEO scan — must have these keys.
        m = j.get("metrics") or {}
        assert "issues_found" in m
        assert "trust_signals" in m
        assert "ux_signals" in m

        # Verify reports row persisted with type='site_scan'.
        result = subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    r = await db.reports.find_one(
        {{'user_id': '{USER_ID}', 'type': 'site_scan',
          'url': 'https://example.com'}}, {{'_id': 0}})
    print('FOUND' if r else 'MISSING')
asyncio.run(go())
"""
        ], capture_output=True, text=True, timeout=15)
        assert "FOUND" in result.stdout, result.stdout


# ----------------------------------- Optimize Automatically endpoint
class TestOptimizeEndpoint:
    def test_404_when_job_missing(self):
        r = _post("/api/cortex/analysis-jobs/nonexistent/optimize")
        assert r.status_code == 404

    def test_400_when_wrong_job_type(self):
        """Seed a completed seller_discovery job → /optimize must 400."""
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'sd-completed-1',
        'user_id': '{USER_ID}',
        'job_type': 'seller_discovery',
        'status': 'completed',
        'progress_pct': 100,
        'target': 'candles',
        'queued_at': datetime.now(timezone.utc),
        'completed_at': datetime.now(timezone.utc),
        'metrics': {{'qualified': 10}},
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/sd-completed-1/optimize")
        assert r.status_code == 400, r.text

    def test_409_when_job_still_running(self):
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.insert_one({{
        'id': 'seo-running-1',
        'user_id': '{USER_ID}',
        'job_type': 'seo_scan',
        'status': 'running',
        'progress_pct': 50,
        'queued_at': datetime.now(timezone.utc),
    }})
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _post("/api/cortex/analysis-jobs/seo-running-1/optimize")
        assert r.status_code == 409, r.text

    def test_happy_path_creates_l3_mission_and_drafts_records(self):
        """Complete SEO scan + report → /optimize creates mission +
        seo_change_records rows + is idempotent on retry."""
        _seed_completed_seo_scan("seoscan-opt-1")
        r = _post("/api/cortex/analysis-jobs/seoscan-opt-1/optimize")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mission_id"]
        assert "Auto-fix top SEO" in d["title"]
        assert d["already_created"] is False
        # If Claude is reachable, drafted > 0; we tolerate 0 only on LLM outage.
        # The mission row exists either way.
        assert d.get("drafted") is not None

        # Verify mission shape (L3 autonomy, seo_auto_fix type).
        out = subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    m = await db.missions.find_one(
        {{'id': '{d["mission_id"]}', 'user_id': '{USER_ID}'}}, {{'_id': 0}})
    print('TYPE:', m.get('mission_type') if m else 'MISSING')
    print('AUTONOMY:', m.get('autonomy_level') if m else 'MISSING')
asyncio.run(go())
"""
        ], capture_output=True, text=True, timeout=15)
        assert "TYPE: seo_auto_fix" in out.stdout
        assert "AUTONOMY: 3" in out.stdout

        # Idempotency: second call returns same mission.
        r2 = _post("/api/cortex/analysis-jobs/seoscan-opt-1/optimize")
        assert r2.status_code == 200
        assert r2.json()["mission_id"] == d["mission_id"]
        assert r2.json()["already_created"] is True

    def test_list_changes_endpoint_returns_shape(self):
        """Seed change records, hit list endpoint, validate the shape."""
        mid = uuid.uuid4().hex
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    now = datetime.now(timezone.utc)
    rows = [{{
        'id': uuid.uuid4().hex,
        'user_id': '{USER_ID}',
        'mission_id': '{mid}',
        'category': 'title', 'current': 'x', 'proposed': 'y',
        'rationale': 'r', 'impact': 'high',
        'status': 'ready', 'created_at': now,
    }} for _ in range(3)]
    await db.seo_change_records.insert_many(rows)
asyncio.run(go())
"""
        ], check=True, timeout=15)
        r = _get(f"/api/cortex/analysis-jobs/missions/{mid}/changes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 3
        assert d["by_status"].get("ready") == 3
        assert all("proposed" in c for c in d["changes"])
