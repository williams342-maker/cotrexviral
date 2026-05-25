"""Recurring weekly posts + lead-form auto-create with magic-link tests."""
import os
import asyncio
import httpx
import secrets
from datetime import datetime, timedelta, timezone

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _cleanup_user(email: str):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        u = await db.users.find_one({"email": email.lower()}, {"_id": 0})
        if u:
            uid = u["user_id"]
            await db.users.delete_one({"user_id": uid})
            await db.user_sessions.delete_many({"user_id": uid})
            await db.magic_links.delete_many({"user_id": uid})
            await db.leads.delete_many({"email": email.lower()})

    asyncio.get_event_loop().run_until_complete(go())


def _cleanup_test_user_posts():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.posts.delete_many({
            "user_id": USER_ID,
            "content": {"$regex": "^WEEKLY_RECUR_TEST"},
        })
    asyncio.get_event_loop().run_until_complete(go())


class TestRepeatWeekly:
    def setup_method(self):
        _cleanup_test_user_posts()

    def teardown_method(self):
        _cleanup_test_user_posts()

    def test_creates_N_recurring_posts_when_scheduled(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "WEEKLY_RECUR_TEST one",
                "platforms": ["instagram"],
                "scheduled_at": future.isoformat(),
                "repeat_weeks": 4,
            },
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "scheduled"
        assert body["repeat_weeks"] == 4
        assert len(body["ids"]) == 4
        assert body["recurrence_group_id"]

        # Verify each post is exactly +7 days from the previous, same content,
        # all share the same recurrence_group_id.
        sched = httpx.get(
            f"{API_URL}/api/posts/scheduled",
            headers=H,
            params={
                "start": future.isoformat(),
                "end": (future + timedelta(weeks=5)).isoformat(),
            },
            timeout=10,
        )
        assert sched.status_code == 200
        series = [p for p in sched.json()
                  if p.get("recurrence_group_id") == body["recurrence_group_id"]]
        assert len(series) == 4
        # All share same group_id
        gid = series[0]["recurrence_group_id"]
        assert all(p["recurrence_group_id"] == gid for p in series)
        # Each has a unique index 0..3
        indices = sorted(p["recurrence_index"] for p in series)
        assert indices == [0, 1, 2, 3]
        # All have the same content
        assert all(p["content"] == "WEEKLY_RECUR_TEST one" for p in series)

    def test_repeat_weeks_ignored_when_not_scheduled(self):
        # No scheduled_at → should NOT create a series, just one immediate post.
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "WEEKLY_RECUR_TEST immediate",
                "platforms": ["instagram"],
                "repeat_weeks": 4,
            },
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        # Single-post response shape, not a series.
        assert "ids" not in body
        assert body["status"] == "published"
        assert body["id"]

    def test_rejects_repeat_weeks_below_2(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "WEEKLY_RECUR_TEST bad",
                "platforms": ["instagram"],
                "scheduled_at": future.isoformat(),
                "repeat_weeks": 1,
            },
            timeout=10,
        )
        assert r.status_code == 422

    def test_rejects_repeat_weeks_above_12(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "WEEKLY_RECUR_TEST too many",
                "platforms": ["instagram"],
                "scheduled_at": future.isoformat(),
                "repeat_weeks": 13,
            },
            timeout=10,
        )
        assert r.status_code == 422

    def test_max_12_weeks_accepted(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        r = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "WEEKLY_RECUR_TEST max",
                "platforms": ["tiktok"],
                "scheduled_at": future.isoformat(),
                "repeat_weeks": 12,
            },
            timeout=15,
        )
        assert r.status_code == 200
        assert len(r.json()["ids"]) == 12


class TestLeadAutoCreate:
    """Verify the lead form auto-creates a user account + issues a magic link."""

    def test_lead_creates_user_and_magic_link(self):
        email = f"leadtest_{secrets.token_hex(4)}@magic-test.dev"
        try:
            r = httpx.post(
                f"{API_URL}/api/leads",
                json={
                    "agent_id": "nova",
                    "name": "Lead Test",
                    "email": email,
                    "pain_points": "Need more SEO traffic",
                },
                timeout=15,
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True

            # Wait a moment for fire-and-forget DB writes to settle.
            import time
            time.sleep(0.5)

            # Verify a user with this email was auto-created.
            import sys
            sys.path.insert(0, "/app/backend")
            from core import db

            async def check():
                user = await db.users.find_one({"email": email.lower()})
                assert user is not None, "User was not auto-created from lead"
                assert user.get("created_via") == "lead_form"
                # Verify a magic link was issued for that user.
                ml = await db.magic_links.find_one({"user_id": user["user_id"]})
                assert ml is not None, "Magic link was not issued"
                assert ml.get("purpose") == "lead_claim"

            asyncio.get_event_loop().run_until_complete(check())
        finally:
            _cleanup_user(email)

    def test_lead_idempotent_when_user_already_exists(self):
        """If the lead's email matches an existing user, we reuse it (no
        duplicate user creation) but still issue a fresh magic link."""
        email = f"leaddupe_{secrets.token_hex(4)}@magic-test.dev"
        try:
            # First lead → creates the user
            r1 = httpx.post(
                f"{API_URL}/api/leads",
                json={"agent_id": "kai", "name": "Dupe", "email": email},
                timeout=15,
            )
            assert r1.status_code == 200

            import time
            time.sleep(0.4)

            # Second lead with same email → should NOT create a second user
            r2 = httpx.post(
                f"{API_URL}/api/leads",
                json={"agent_id": "kai", "name": "Dupe again", "email": email},
                timeout=15,
            )
            assert r2.status_code == 200

            time.sleep(0.4)

            import sys
            sys.path.insert(0, "/app/backend")
            from core import db

            async def check():
                count = await db.users.count_documents({"email": email.lower()})
                assert count == 1, f"Expected 1 user, found {count}"
                # And both leads were persisted.
                lead_count = await db.leads.count_documents({"email": email.lower()})
                assert lead_count == 2

            asyncio.get_event_loop().run_until_complete(check())
        finally:
            _cleanup_user(email)
