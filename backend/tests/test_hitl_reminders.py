"""HITL paused-run reminder job — branch coverage.

The reminder code path is gnarly enough that an actual end-to-end test
with the scheduler isn't worth the cost; instead we test the pure
`_remind_paused_runs()` function with a stubbed `send_email` against a
real Mongo (which the testing harness already uses). Each branch:

  1. Happy path — paused run >24h, user has email → email sent + stamped.
  2. Skip — user deleted or no email → no send, row still stamped.
  3. Idempotency — already-stamped row is NOT re-sent on the next tick.
  4. Send failure — provider returns sent=False → row still stamped to
     prevent retry-storms.

These tests run directly against the dev Mongo so we use disposable
ids prefixed with `test_hitl_reminder_` and clean up at the end.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import hitl_reminders as hr   # noqa: E402


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _seed_user(email: str | None, *, deleted=False) -> str:
    uid = f"test_hitl_user_{uuid.uuid4().hex[:8]}"
    doc = {
        "user_id": uid,
        "name":    "Test Reviewer",
        "status":  "deleted" if deleted else "active",
    }
    if email is not None:
        doc["email"] = email
    await _mongo().users.insert_one(doc)
    return uid


async def _seed_paused_run(user_id: str, *, hours_old: int, already_stamped=False) -> str:
    rid = f"test_hitl_run_{uuid.uuid4().hex[:8]}"
    doc = {
        "id":                rid,
        "user_id":           user_id,
        "status":            "awaiting_approval",
        "requires_approval": True,
        "brief":             "Launch a tiny indie SaaS for makers",
        "created_at":        datetime.now(timezone.utc) - timedelta(hours=hours_old),
        "framework":         "langgraph",
    }
    if already_stamped:
        doc["reminder_sent_at"] = datetime.now(timezone.utc) - timedelta(hours=1)
    await _mongo().marketing_os_runs.insert_one(doc)
    return rid


@pytest.fixture(autouse=True)
def _cleanup():
    """Wipe disposable test rows before AND after each test so cross-
    test contamination is impossible."""
    async def _wipe():
        m = _mongo()
        await m.users.delete_many({"user_id": {"$regex": "^test_hitl_"}})
        await m.marketing_os_runs.delete_many({"id": {"$regex": "^test_hitl_"}})
    asyncio.get_event_loop().run_until_complete(_wipe())
    yield
    asyncio.get_event_loop().run_until_complete(_wipe())


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------
class TestHitlReminders:

    def test_happy_path_sends_and_stamps(self, monkeypatch):
        captured = {}

        async def fake_send_email(to, subject, html, text=None, **kw):
            captured["to"] = to
            captured["subject"] = subject
            captured["tags"] = kw.get("tags")
            return {"sent": True, "id": "fake-msg-1", "provider": "fake"}

        import routes.email
        monkeypatch.setattr(routes.email, "send_email", fake_send_email)

        async def _go():
            uid = await _seed_user("reviewer@example.com")
            rid = await _seed_paused_run(uid, hours_old=30)
            res = await hr._remind_paused_runs()
            assert res == {"sent": 1, "failed": 0, "skipped": 0}, res
            doc = await _mongo().marketing_os_runs.find_one({"id": rid})
            assert doc["reminder_status"] == "sent"
            assert doc["reminder_sent_at"] is not None
            assert captured["to"] == "reviewer@example.com"
            assert "Marketing OS run" in captured["subject"]
            assert "hitl-reminder" in (captured["tags"] or [])

        asyncio.get_event_loop().run_until_complete(_go())

    def test_idempotent_already_stamped_row_is_not_resent(self, monkeypatch):
        send_calls = {"n": 0}

        async def fake_send_email(*a, **kw):
            send_calls["n"] += 1
            return {"sent": True, "id": "fake", "provider": "fake"}

        import routes.email
        monkeypatch.setattr(routes.email, "send_email", fake_send_email)

        async def _go():
            uid = await _seed_user("reviewer@example.com")
            await _seed_paused_run(uid, hours_old=30, already_stamped=True)
            res = await hr._remind_paused_runs()
            assert res == {"sent": 0, "failed": 0, "skipped": 0}
            assert send_calls["n"] == 0, "already-stamped row must NOT trigger send"

        asyncio.get_event_loop().run_until_complete(_go())

    def test_skips_deleted_user_but_stamps_to_prevent_retry(self, monkeypatch):
        send_calls = {"n": 0}

        async def fake_send_email(*a, **kw):
            send_calls["n"] += 1
            return {"sent": True}

        import routes.email
        monkeypatch.setattr(routes.email, "send_email", fake_send_email)

        async def _go():
            uid = await _seed_user("gone@example.com", deleted=True)
            rid = await _seed_paused_run(uid, hours_old=48)
            res = await hr._remind_paused_runs()
            assert res["skipped"] == 1
            assert send_calls["n"] == 0
            # Still stamped so we don't reconsider on the next tick.
            doc = await _mongo().marketing_os_runs.find_one({"id": rid})
            assert doc.get("reminder_sent_at") is not None
            assert doc.get("reminder_skipped_reason") == "no_email_or_deleted_user"

        asyncio.get_event_loop().run_until_complete(_go())

    def test_send_failure_still_stamps_row(self, monkeypatch):
        async def fake_send_email(*a, **kw):
            return {"sent": False, "error": "provider 500"}

        import routes.email
        monkeypatch.setattr(routes.email, "send_email", fake_send_email)

        async def _go():
            uid = await _seed_user("rev@example.com")
            rid = await _seed_paused_run(uid, hours_old=30)
            res = await hr._remind_paused_runs()
            assert res["failed"] == 1
            doc = await _mongo().marketing_os_runs.find_one({"id": rid})
            assert doc["reminder_status"] == "failed"
            assert doc.get("reminder_sent_at") is not None  # stamped → no retry loop

        asyncio.get_event_loop().run_until_complete(_go())

    def test_fresh_run_under_threshold_is_not_touched(self, monkeypatch):
        send_calls = {"n": 0}

        async def fake_send_email(*a, **kw):
            send_calls["n"] += 1
            return {"sent": True}

        import routes.email
        monkeypatch.setattr(routes.email, "send_email", fake_send_email)

        async def _go():
            uid = await _seed_user("rev@example.com")
            rid = await _seed_paused_run(uid, hours_old=2)   # well under 24h
            res = await hr._remind_paused_runs()
            assert res == {"sent": 0, "failed": 0, "skipped": 0}
            assert send_calls["n"] == 0
            doc = await _mongo().marketing_os_runs.find_one({"id": rid})
            assert "reminder_sent_at" not in doc, "fresh run must NOT be stamped yet"

        asyncio.get_event_loop().run_until_complete(_go())
