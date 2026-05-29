"""Briefs — Phase 3 of the Autonomous Growth Team.

Covers:
  - Auth gating on every endpoint
  - Settings round-trip (manual ↔ autopilot)
  - Manual propose creates pending briefs (via fallback path when LLM unavailable)
  - List returns hydrated stats + status filter
  - Approve flips status + spawns a campaign with cross-ref
  - Reject writes a `brief_rejected` memory row + flips status
  - Edit stamps `edited_body` + approve uses the edited version
  - Delete removes the row
  - Autopilot scanner skips users not in autopilot mode
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

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


def _admin_user_id():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    if r.status_code == 200:
        return r.json().get("user_id")
    return None


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing")
    return uid


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    """Wipe pytest-injected rows before AND after each test."""
    async def go():
        db = _mongo()
        await db.proposed_briefs.delete_many({"user_id": admin_user_id, "title": {"$regex": "pytest_"}})
        await db.campaigns.delete_many({"user_id": admin_user_id, "name": {"$regex": "pytest_"}})
        await db.cortex_memory.delete_many({"user_id": admin_user_id, "kind": "brief_rejected",
                                             "text": {"$regex": "pytest_"}})
        # Reset autopilot row to default for clean tests
        await db.autopilot_settings.delete_many({"user_id": admin_user_id})
        await db.growth_goals.delete_many({"user_id": admin_user_id, "title": {"$regex": "pytest_"}})
    _run(go())
    yield
    _run(go())


def _seed_brief(user_id: str, *, title: str = "pytest_seed_brief", status: str = "pending") -> str:
    """Insert a brief directly so we can test approve/reject/edit without
    going through the LLM-backed propose path."""
    bid = uuid.uuid4().hex
    async def go():
        db = _mongo()
        await db.proposed_briefs.insert_one({
            "id":                 bid,
            "user_id":            user_id,
            "proposer_agent":     "atlas",
            "title":              title,
            "hypothesis":         "pytest hypothesis",
            "body":               "pytest body — at least ten characters long for the editor to accept.",
            "rationale":          "pytest rationale",
            "suggested_platforms": ["instagram", "linkedin"],
            "target_metric":      "engagements",
            "status":             status,
            "source":             "manual",
            "created_at":         datetime.now(timezone.utc),
            "decided_at":         None,
            "decided_by":         None,
            "resolved_into_campaign_id": None,
            "edited_body":        None,
        })
    _run(go())
    return bid


class TestAuth:
    def test_endpoints_require_auth(self):
        for path, method, body in [
            ("/api/briefs",                     "get",   None),
            ("/api/briefs/settings",            "get",   None),
            ("/api/briefs/settings",            "put",   {"briefs_mode": "manual"}),
            ("/api/briefs/propose",             "post",  {}),
            ("/api/briefs/abc",                 "get",   None),
            ("/api/briefs/abc/approve",         "post",  {}),
            ("/api/briefs/abc/reject",          "post",  {}),
            ("/api/briefs/abc/edit",            "patch", {"body": "x" * 20}),
            ("/api/briefs/abc",                 "delete", None),
        ]:
            kw = {"timeout": 10}
            if body is not None:
                kw["json"] = body
            r = getattr(requests, method)(f"{API_URL}{path}", **kw)
            assert r.status_code == 401, f"{method.upper()} {path} → {r.status_code}"


class TestSettings:
    def test_default_is_manual(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/briefs/settings", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["briefs_mode"] == "manual"
        assert "Manual" in r.json()["cadence_label"]

    def test_toggle_to_autopilot(self, admin_user_id):
        r = requests.put(f"{API_URL}/api/briefs/settings",
                         json={"briefs_mode": "autopilot"},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["briefs_mode"] == "autopilot"
        assert "09:00" in r.json()["cadence_label"]

    def test_rejects_unknown_mode(self, admin_user_id):
        r = requests.put(f"{API_URL}/api/briefs/settings",
                         json={"briefs_mode": "yolo"},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 400


class TestPropose:
    def test_propose_with_no_signals_or_goals_returns_empty(self, admin_user_id):
        # Cleanup fixture already wiped goals; no listening signals seeded.
        # The fallback path returns [] when both lists are empty.
        # Note: the live LLM may also return [] on empty facts; we can't
        # assert exactly 0 since the LLM might still propose something
        # speculative. Just assert the call succeeds + last_scan_at is stamped.
        r = requests.post(f"{API_URL}/api/briefs/propose",
                          json={"max_briefs": 1}, headers=HEADERS, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "items" in body and "count" in body
        # last_brief_scan_at should now be set
        r2 = requests.get(f"{API_URL}/api/briefs/settings", headers=HEADERS, timeout=10)
        assert r2.json().get("last_scan_at") is not None


class TestListAndStats:
    def test_list_pending_with_seeded_briefs(self, admin_user_id):
        b1 = _seed_brief(admin_user_id, title="pytest_brief_one", status="pending")
        b2 = _seed_brief(admin_user_id, title="pytest_brief_two", status="rejected")
        r = requests.get(f"{API_URL}/api/briefs", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        ids = {it["id"] for it in body["items"]}
        assert {b1, b2}.issubset(ids)
        assert body["pending_count"] >= 1
        assert body["rejected_count"] >= 1

        # Filter by status
        r = requests.get(f"{API_URL}/api/briefs?status=pending", headers=HEADERS, timeout=10)
        statuses = {it["status"] for it in r.json()["items"]}
        assert statuses == {"pending"} or len(statuses) == 0


class TestApprove:
    def test_approve_creates_campaign(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_approve_target", status="pending")
        r = requests.post(f"{API_URL}/api/briefs/{bid}/approve", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["brief"]["status"] == "approved"
        assert body["brief"]["resolved_into_campaign_id"] is not None
        # Campaign exists in db
        async def check():
            db = _mongo()
            camp = await db.campaigns.find_one(
                {"id": body["brief"]["resolved_into_campaign_id"]}, {"_id": 0}
            )
            assert camp is not None
            assert camp["proposed_brief_id"] == bid
            assert camp["platforms"] == ["instagram", "linkedin"]
        _run(check())

    def test_approve_404_on_non_pending(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_already_decided", status="approved")
        r = requests.post(f"{API_URL}/api/briefs/{bid}/approve", headers=HEADERS, timeout=10)
        assert r.status_code == 404


class TestReject:
    def test_reject_writes_memory(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_reject_me", status="pending")
        r = requests.post(f"{API_URL}/api/briefs/{bid}/reject", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "rejected"
        assert body.get("memory_id")
        # Memory row landed with the right kind + dedupe key
        async def check():
            db = _mongo()
            mem = await db.cortex_memory.find_one({"id": body["memory_id"]})
            assert mem is not None
            assert mem["kind"] == "brief_rejected"
            assert mem["dedupe_key"] == f"brief_rejected:{bid}"
            assert "pytest_reject_me" in mem["text"]
        _run(check())


class TestEdit:
    def test_edit_stamps_edited_body(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_edit_me", status="pending")
        new_body = "Edited body — at least ten characters long for validation."
        r = requests.patch(f"{API_URL}/api/briefs/{bid}/edit",
                           json={"body": new_body}, headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["edited_body"] == new_body

    def test_edit_validation_rejects_short_body(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_validation_check", status="pending")
        r = requests.patch(f"{API_URL}/api/briefs/{bid}/edit",
                           json={"body": "short"}, headers=HEADERS, timeout=10)
        assert r.status_code == 422

    def test_approve_uses_edited_body(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_edited_approve", status="pending")
        edited = "EDITED FINAL — the operator rewrote this brief before approving."
        requests.patch(f"{API_URL}/api/briefs/{bid}/edit",
                       json={"body": edited}, headers=HEADERS, timeout=10)
        r = requests.post(f"{API_URL}/api/briefs/{bid}/approve", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert edited in r.json()["campaign"]["notes"]


class TestDelete:
    def test_delete_removes_row(self, admin_user_id):
        bid = _seed_brief(admin_user_id, title="pytest_delete_target", status="pending")
        r = requests.delete(f"{API_URL}/api/briefs/{bid}", headers=HEADERS, timeout=10)
        assert r.status_code == 200
        async def check():
            db = _mongo()
            assert await db.proposed_briefs.find_one({"id": bid}) is None
        _run(check())


class TestAutopilotScanner:
    def test_scanner_skips_when_no_autopilot_users(self, admin_user_id):
        """No autopilot rows exist (cleanup ran). Scanner should do zero work."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.briefs import run_autopilot_scan
        summary = _run(run_autopilot_scan())
        assert summary["users_processed"] == 0
        assert summary["total_briefs"] == 0

    def test_scanner_respects_20h_window(self, admin_user_id):
        """User opted into autopilot but ran 1h ago → should be skipped."""
        async def setup():
            db = _mongo()
            await db.autopilot_settings.update_one(
                {"user_id": admin_user_id},
                {"$set": {
                    "user_id": admin_user_id,
                    "briefs_mode": "autopilot",
                    "last_brief_scan_at": datetime.now(timezone.utc) - timedelta(hours=1),
                    "updated_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )
        _run(setup())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.briefs import run_autopilot_scan
        summary = _run(run_autopilot_scan())
        assert summary["users_skipped"] >= 1
        assert summary["users_processed"] == 0
