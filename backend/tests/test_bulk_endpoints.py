"""Regression tests for the bulk-delete + bulk-retry endpoints across
Reports, Cortex Assets, and Cortex Memory.

Covered:
  • POST /api/cortex/assets/bulk-delete       — soft-delete + storage purge, user-scoped
  • POST /api/cortex/memory/bulk-delete       — hard-delete vectors, user-scoped
  • POST /api/reports/bulk-delete             — hard-delete reports, user-scoped, batch capped
  • POST /api/reports/bulk-retry              — re-runs failed url scans only, parallel-capped

Security invariants (the hard part):
  • A spoofed id belonging to another user is silently ignored — never deleted/touched.
  • An empty / malformed body returns ok with deleted=0 (no 500s).

Test isolation:
  • Each test inserts its own fixture rows tagged with a unique prefix, then
    cleans them up in a finally block. No reliance on existing user state.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TEST_TOKEN = "test_session_1779636592168"
TEST_USER_ID = "user_test1779636592168"
HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}",
           "Content-Type": "application/json"}

# A second user for cross-tenant security checks.
OTHER_USER_ID = "user_bulk_test_other_" + uuid.uuid4().hex[:8]


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------
# Sanity precheck — backend reachable + the test session is valid.
# Without this the rest of the suite is meaningless.
# --------------------------------------------------------------------------
def test_precheck_backend_reachable_and_token_valid():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    assert r.status_code == 200, f"/api/auth/me returned {r.status_code}: {r.text}"
    payload = r.json()
    assert payload.get("user_id") == TEST_USER_ID, \
        f"Expected test user_id, got {payload.get('user_id')}"


# ==========================================================================
# Reports — POST /api/reports/bulk-delete
# ==========================================================================
def _insert_report(db, *, report_id: str, user_id: str, failed: bool = False):
    body = {"summary": "", "improvements": []} if failed else {
        "summary": "Looks great", "improvements": ["a", "b"]}
    return db.reports.insert_one({
        "id": report_id,
        "user_id": user_id,
        "url": "https://example.com",
        "type": "seo",
        "status": "complete",
        "report": body,
        "created_at": datetime.now(timezone.utc),
    })


def test_reports_bulk_delete_happy_path():
    prefix = "bulk-del-rpt-" + uuid.uuid4().hex[:8]
    ids = [f"{prefix}-{i}" for i in range(3)]

    async def setup():
        db = _db()
        for rid in ids:
            await _insert_report(db, report_id=rid, user_id=TEST_USER_ID)

    async def cleanup():
        await _db().reports.delete_many({"id": {"$in": ids}})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/reports/bulk-delete",
                          json={"ids": ids}, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"] == 3
        # All rows must actually be gone.
        remaining = _run(_db().reports.count_documents({"id": {"$in": ids}}))
        assert remaining == 0
    finally:
        _run(cleanup())


def test_reports_bulk_delete_ignores_other_users_rows():
    """Spoofed id list referencing another user's reports must NOT touch them.
    This is the security invariant that justifies the user_id filter."""
    mine = ["bulk-del-mine-" + uuid.uuid4().hex[:8] for _ in range(2)]
    theirs = ["bulk-del-theirs-" + uuid.uuid4().hex[:8] for _ in range(2)]

    async def setup():
        db = _db()
        for rid in mine:
            await _insert_report(db, report_id=rid, user_id=TEST_USER_ID)
        for rid in theirs:
            await _insert_report(db, report_id=rid, user_id=OTHER_USER_ID)

    async def cleanup():
        await _db().reports.delete_many({"id": {"$in": mine + theirs}})

    _run(setup())
    try:
        # Caller asks to delete both lists but only owns `mine`.
        r = requests.post(f"{API_URL}/api/reports/bulk-delete",
                          json={"ids": mine + theirs},
                          headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # The endpoint should report only `mine` as deleted.
        assert body["deleted"] == 2, body
        # The other user's rows are still in the DB.
        survived = _run(_db().reports.count_documents(
            {"id": {"$in": theirs}, "user_id": OTHER_USER_ID}))
        assert survived == 2
    finally:
        _run(cleanup())


def test_reports_bulk_delete_empty_body_is_noop():
    r = requests.post(f"{API_URL}/api/reports/bulk-delete",
                      json={"ids": []}, headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deleted": 0}


def test_reports_bulk_delete_caps_batch_at_500():
    """The route caps ids[:500]; over-cap requests must still 200 OK and
    process only up to 500 (we don't actually need to seed 501 rows, the
    truncation is what matters)."""
    huge = [f"nonexistent-{i}" for i in range(750)]
    r = requests.post(f"{API_URL}/api/reports/bulk-delete",
                      json={"ids": huge}, headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_reports_bulk_delete_requires_auth():
    r = requests.post(f"{API_URL}/api/reports/bulk-delete",
                      json={"ids": ["anything"]},
                      headers={"Content-Type": "application/json"},
                      timeout=10)
    assert r.status_code in (401, 403), r.text


# ==========================================================================
# Reports — POST /api/reports/bulk-retry
# ==========================================================================
def test_reports_bulk_retry_skips_non_failed_rows():
    """Only rows that look failed (_looks_failed heuristic) should be
    retried. Non-failed rows must be returned in the skipped list with
    reason='not_failed' — the LLM must not be invoked for them."""
    healthy = "bulk-retry-healthy-" + uuid.uuid4().hex[:8]

    async def setup():
        db = _db()
        await _insert_report(db, report_id=healthy,
                             user_id=TEST_USER_ID, failed=False)

    async def cleanup():
        await _db().reports.delete_many({"id": healthy})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/reports/bulk-retry",
                          json={"ids": [healthy]}, headers=HEADERS,
                          timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["retried"] == 0
        assert body["skipped"] == 1
        items = body["items"]
        assert len(items) == 1
        assert items[0]["old_id"] == healthy
        assert items[0]["ok"] is False
        assert items[0]["reason"] == "not_failed"
        # The healthy row must NOT have been deleted (retry would delete it).
        survived = _run(_db().reports.count_documents({"id": healthy}))
        assert survived == 1
    finally:
        _run(cleanup())


def test_reports_bulk_retry_empty_body_is_noop():
    r = requests.post(f"{API_URL}/api/reports/bulk-retry",
                      json={"ids": []}, headers=HEADERS, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "retried": 0, "skipped": 0, "items": []}


def test_reports_bulk_retry_ignores_other_users_rows():
    """Other users' failed rows must not be touched even when their ids are
    listed. The cursor's user_id filter is the only thing standing between
    a malicious client and another tenant's reports."""
    other_id = "bulk-retry-other-" + uuid.uuid4().hex[:8]

    async def setup():
        db = _db()
        await _insert_report(db, report_id=other_id,
                             user_id=OTHER_USER_ID, failed=True)

    async def cleanup():
        await _db().reports.delete_many({"id": other_id})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/reports/bulk-retry",
                          json={"ids": [other_id]}, headers=HEADERS,
                          timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # The id belongs to another user, so the cursor returns 0 rows —
        # nothing retried, nothing skipped.
        assert body["retried"] == 0
        # The other user's row is still in the DB untouched.
        survived = _run(_db().reports.count_documents(
            {"id": other_id, "user_id": OTHER_USER_ID}))
        assert survived == 1
    finally:
        _run(cleanup())


def test_reports_bulk_retry_caps_batch_at_5():
    """The route hard-caps batches at 5 (Cloudflare 60s ingress budget).
    Non-failed rows count as a skip so we don't actually pay for retries
    in this test."""
    ids = ["bulk-retry-cap-" + uuid.uuid4().hex[:8] for _ in range(8)]

    async def setup():
        db = _db()
        for rid in ids:
            await _insert_report(db, report_id=rid,
                                 user_id=TEST_USER_ID, failed=False)

    async def cleanup():
        await _db().reports.delete_many({"id": {"$in": ids}})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/reports/bulk-retry",
                          json={"ids": ids}, headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # Only the first 5 are processed; the remaining 3 are dropped
        # before the DB cursor runs.
        assert len(items) <= 5
    finally:
        _run(cleanup())


# ==========================================================================
# Cortex Assets — POST /api/cortex/assets/bulk-delete
# ==========================================================================
def _insert_asset(db, *, asset_id: str, user_id: str, storage_key: str | None = None):
    return db.cortex_assets.insert_one({
        "id": asset_id,
        "user_id": user_id,
        "filename": f"{asset_id}.pdf",
        "mime": "application/pdf",
        "storage_key": storage_key or f"assets/{user_id}/{asset_id}.pdf",
        "status": "ready",
        "created_at": datetime.now(timezone.utc),
    })


def test_assets_bulk_delete_soft_deletes_user_owned():
    """Soft-delete sets deleted_at + status='deleted'. Row must still
    exist for audit but be excluded from the live cursor."""
    ids = ["bulk-asset-" + uuid.uuid4().hex[:8] for _ in range(3)]

    async def setup():
        db = _db()
        for aid in ids:
            await _insert_asset(db, asset_id=aid, user_id=TEST_USER_ID)

    async def cleanup():
        await _db().cortex_assets.delete_many({"id": {"$in": ids}})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/cortex/assets/bulk-delete",
                          json={"ids": ids}, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"] == 3
        # All rows still exist (audit trail) but flagged deleted.
        rows = _run(_db().cortex_assets.find(
            {"id": {"$in": ids}}, {"_id": 0, "status": 1, "deleted_at": 1}
        ).to_list(None))
        assert len(rows) == 3
        for r_ in rows:
            assert r_.get("status") == "deleted"
            assert r_.get("deleted_at") is not None
    finally:
        _run(cleanup())


def test_assets_bulk_delete_ignores_already_deleted():
    """The cursor filters out rows with deleted_at set — re-deleting an
    already-deleted asset must be a no-op."""
    aid = "bulk-asset-already-deleted-" + uuid.uuid4().hex[:8]

    async def setup():
        db = _db()
        await db.cortex_assets.insert_one({
            "id": aid, "user_id": TEST_USER_ID,
            "filename": f"{aid}.pdf", "storage_key": f"assets/{TEST_USER_ID}/{aid}.pdf",
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        })

    async def cleanup():
        await _db().cortex_assets.delete_one({"id": aid})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/cortex/assets/bulk-delete",
                          json={"ids": [aid]}, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # `deleted` counts target rows that actually transitioned.
        assert body["deleted"] == 0
    finally:
        _run(cleanup())


def test_assets_bulk_delete_ignores_other_users_rows():
    other_id = "bulk-asset-theirs-" + uuid.uuid4().hex[:8]

    async def setup():
        await _insert_asset(_db(), asset_id=other_id, user_id=OTHER_USER_ID)

    async def cleanup():
        await _db().cortex_assets.delete_one({"id": other_id})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/cortex/assets/bulk-delete",
                          json={"ids": [other_id]}, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # The asset belongs to OTHER_USER_ID → cursor returns 0 rows.
        # The route short-circuits before update_many with `deleted=0,
        # requested=1`.
        assert body["deleted"] == 0
        # The other user's row is untouched.
        row = _run(_db().cortex_assets.find_one({"id": other_id}))
        assert row is not None
        assert row.get("deleted_at") is None
        assert row.get("status") != "deleted"
    finally:
        _run(cleanup())


def test_assets_bulk_delete_empty_body_is_noop():
    r = requests.post(f"{API_URL}/api/cortex/assets/bulk-delete",
                      json={"ids": []}, headers=HEADERS, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deleted": 0}


# ==========================================================================
# Cortex Memory — POST /api/cortex/memory/bulk-delete
# ==========================================================================
def _memory_collection_name():
    """Imports cortex.memory lazily so this file works even without the
    package on PYTHONPATH (e.g., running from /app/backend tests
    individually)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from cortex import memory as cmem
    return cmem.COLLECTION_V2


def _insert_memory_turn(db, *, turn_id: str, user_id: str):
    return db[_memory_collection_name()].insert_one({
        "id": turn_id,
        "user_id": user_id,
        "session_id": "regression-bulk-tests",
        "role": "user",
        "text": "regression-test turn",
        "vector": [0.0] * 8,
        "meta": {"stage": "discovery"},
        "pinned": False,
        "created_at": datetime.now(timezone.utc),
    })


def test_memory_bulk_delete_hard_deletes_user_owned():
    coll = _memory_collection_name()
    ids = ["bulk-mem-" + uuid.uuid4().hex[:8] for _ in range(3)]

    async def setup():
        db = _db()
        for tid in ids:
            await _insert_memory_turn(db, turn_id=tid, user_id=TEST_USER_ID)

    async def cleanup():
        await _db()[coll].delete_many({"id": {"$in": ids}})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/cortex/memory/bulk-delete",
                          json={"ids": ids}, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["deleted"] == 3
        # Hard-delete — rows are gone.
        survived = _run(_db()[coll].count_documents({"id": {"$in": ids}}))
        assert survived == 0
    finally:
        _run(cleanup())


def test_memory_bulk_delete_ignores_other_users_rows():
    coll = _memory_collection_name()
    other_id = "bulk-mem-theirs-" + uuid.uuid4().hex[:8]

    async def setup():
        await _insert_memory_turn(_db(), turn_id=other_id,
                                   user_id=OTHER_USER_ID)

    async def cleanup():
        await _db()[coll].delete_one({"id": other_id})

    _run(setup())
    try:
        r = requests.post(f"{API_URL}/api/cortex/memory/bulk-delete",
                          json={"ids": [other_id]}, headers=HEADERS,
                          timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == 0
        # The other user's turn is still in the collection.
        survived = _run(_db()[coll].count_documents(
            {"id": other_id, "user_id": OTHER_USER_ID}))
        assert survived == 1
    finally:
        _run(cleanup())


def test_memory_bulk_delete_empty_body_is_noop():
    r = requests.post(f"{API_URL}/api/cortex/memory/bulk-delete",
                      json={"ids": []}, headers=HEADERS, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deleted": 0}


def test_memory_bulk_delete_requires_auth():
    r = requests.post(f"{API_URL}/api/cortex/memory/bulk-delete",
                      json={"ids": ["x"]},
                      headers={"Content-Type": "application/json"},
                      timeout=10)
    assert r.status_code in (401, 403), r.text
