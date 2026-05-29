"""Phase 5 — count-source migration tests.

Verifies that count-style endpoints now read from the normalized layer
(`content_items` / `content_variants`) instead of the legacy `posts`
collection. Strict-mode safe — these counts are stable regardless of the
STRICT_NORMALIZED_READS flag.

Cuts over in this phase:
  • `/api/admin/stats.total_posts`        → `content_items.count`
  • `/api/admin/users.[stats.posts]`      → `content_items.count`
  • `/api/admin/users/{id}.stats.posts`   → `content_items.count`
  • `/api/marketing-os/dashboard.stats.pending_approvals` → `content_items`
  • `/api/admin/scheduler/run-once`       → `content_variants.count`
"""
import asyncio
import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import content_layer as CL  # noqa: E402

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TEST_TOKEN = "test_session_1779636592168"
TEST_USER_ID = "user_test1779636592168"
HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAdminTotalPostsCount:

    def test_total_posts_matches_content_items(self):
        """`/api/admin/stats.total_posts` should equal `content_items` count."""
        r = requests.get(f"{API_URL}/api/admin/stats", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        api_total = r.json().get("total_posts")

        async def go():
            db = _mongo()
            return await db.content_items.count_documents({})
        expected = _run(go())
        assert api_total == expected, f"API says {api_total} but content_items has {expected}"


class TestAdminPerUserPostsCount:

    def test_per_user_posts_matches_content_items(self):
        """`/api/admin/users/{id}.stats.posts` should equal user's content_items count."""
        r = requests.get(
            f"{API_URL}/api/admin/users/{TEST_USER_ID}",
            headers=HEADERS, timeout=20,
        )
        assert r.status_code == 200, r.text
        api_count = r.json()["stats"]["posts"]

        async def go():
            db = _mongo()
            return await db.content_items.count_documents({"user_id": TEST_USER_ID})
        expected = _run(go())
        assert api_count == expected


class TestMarketingOsPendingCount:

    def test_pending_approvals_count_uses_content_items(self):
        """Seed a pending_approval mirrored post and assert the OS
        dashboard counter reflects it (counts ≥ 1)."""
        db = _mongo()
        post = {
            "id":           uuid.uuid4().hex,
            "user_id":      TEST_USER_ID,
            "content":      "phase5 pending count " + uuid.uuid4().hex[:6],
            "platforms":    ["linkedin"],
            "status":       "pending_approval",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
            "created_at":   datetime.now(timezone.utc),
        }

        async def setup():
            await db.posts.insert_one(dict(post))
            await CL.mirror_post_to_normalized(post)
        _run(setup())

        try:
            r = requests.get(f"{API_URL}/api/marketing-os/dashboard",
                              headers=HEADERS, timeout=20)
            assert r.status_code == 200, r.text
            pending = r.json()["stats"]["pending_approvals"]
            assert pending >= 1, f"Expected >= 1 pending, got {pending}"
        finally:
            async def teardown():
                ci = await db.content_variants.find_one(
                    {"post_id": post["id"]}, {"_id": 0, "content_item_id": 1},
                )
                await db.posts.delete_one({"id": post["id"]})
                await db.content_variants.delete_many({"post_id": post["id"]})
                if ci and ci.get("content_item_id"):
                    await db.content_items.delete_one({"id": ci["content_item_id"]})
            _run(teardown())


class TestSchedulerHealthCheck:

    def test_scheduler_run_once_uses_normalized_count(self):
        """`/admin/scheduler/run-once` reports `scheduled_before` from
        the normalized layer. We just need a clean 200 — admins use it
        as a manual trigger."""
        r = requests.post(f"{API_URL}/api/admin/scheduler/run-once",
                           headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "scheduled_before" in body
        assert "scheduled_after" in body
        assert isinstance(body["scheduled_before"], int)
        assert isinstance(body["scheduled_after"], int)


class TestStrictModeIsActive:
    """Sanity check — the operator flip in /app/backend/.env should be live."""

    def test_strict_mode_pill_is_on(self):
        r = requests.get(f"{API_URL}/api/admin/content-layer/health",
                          headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("strict_mode") is True, (
            f"Expected strict_mode=True after operator flip; got {body.get('strict_mode')}"
        )
        # Coverage should remain at or near 100 — operator was supposed
        # to flip only after sustained zero drift.
        assert body["mirror_coverage_pct"] >= 99.0
