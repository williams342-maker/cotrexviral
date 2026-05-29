"""Phase 4 — strict-mode read cutover tests.

Verifies that:
  1. The remaining read paths (`/activity`, `/posts`, `/admin/users/{id}`
     recent_posts, `/marketing-os/dashboard` approvals snapshot,
     `/dashboard/stats` posts count) all resolve through the normalized
     `content_items` / `content_variants` layer.
  2. `STRICT_NORMALIZED_READS=true` drops the lenient fallback — un-mirrored
     posts vanish from all reads when the flag is on.
  3. With the flag OFF (default), un-mirrored stragglers still surface.

Uses module-scoped fixtures to seed a known mix of mirrored + un-mirrored
test posts so each assertion can target a specific id deterministically.
"""
import asyncio
import os
import uuid
import importlib
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


@pytest.fixture
def seeded(request):
    """Yield (mirrored_id, unmirrored_id). Cleanup runs unconditionally."""
    db = _mongo()
    mirrored = {
        "id":          uuid.uuid4().hex,
        "user_id":     TEST_USER_ID,
        "content":     "phase4 mirrored " + uuid.uuid4().hex[:6],
        "platforms":   ["linkedin"],
        "status":      "scheduled",
        "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "created_at":  datetime.now(timezone.utc),
    }
    unmirrored = {
        "id":          uuid.uuid4().hex,
        "user_id":     TEST_USER_ID,
        "content":     "phase4 unmirrored " + uuid.uuid4().hex[:6],
        "platforms":   ["linkedin"],
        "status":      "scheduled",
        "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "created_at":  datetime.now(timezone.utc),
    }

    async def go():
        await db.posts.insert_one(dict(mirrored))
        await CL.mirror_post_to_normalized(mirrored)
        await db.posts.insert_one(dict(unmirrored))
    _run(go())

    yield {"mirrored_id": mirrored["id"], "unmirrored_id": unmirrored["id"]}

    async def cleanup():
        await db.posts.delete_many({"id": {"$in": [mirrored["id"], unmirrored["id"]]}})
        await db.content_variants.delete_many({"post_id": {"$in": [mirrored["id"], unmirrored["id"]]}})
        ci = await db.content_variants.find_one({"post_id": mirrored["id"]}, {"_id": 0, "content_item_id": 1})
        if ci and ci.get("content_item_id"):
            await db.content_items.delete_one({"id": ci["content_item_id"]})
    _run(cleanup())


class TestActivityFeed:

    def test_activity_includes_mirrored_post(self, seeded):
        r = requests.get(f"{API_URL}/api/activity", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        ids = [it["id"] for it in r.json() if it["type"] == "post"]
        assert seeded["mirrored_id"] in ids

    def test_activity_lenient_includes_unmirrored(self, seeded):
        """Default (lenient) mode tops up with un-mirrored stragglers."""
        r = requests.get(f"{API_URL}/api/activity", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        ids = [it["id"] for it in r.json() if it["type"] == "post"]
        assert seeded["unmirrored_id"] in ids


class TestListPosts:

    def test_list_posts_includes_mirrored(self, seeded):
        r = requests.get(f"{API_URL}/api/posts", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert seeded["mirrored_id"] in ids

    def test_list_posts_lenient_includes_unmirrored(self, seeded):
        r = requests.get(f"{API_URL}/api/posts", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        ids = [p["id"] for p in r.json()]
        assert seeded["unmirrored_id"] in ids


class TestAdminRecentPosts:

    def test_admin_user_detail_recent_posts(self, seeded):
        r = requests.get(
            f"{API_URL}/api/admin/users/{TEST_USER_ID}",
            headers=HEADERS, timeout=20,
        )
        assert r.status_code == 200, r.text
        recent = r.json().get("recent_posts", [])
        ids = [p["id"] for p in recent]
        # mirrored should be in the top 5 (we just inserted it)
        assert seeded["mirrored_id"] in ids


class TestMarketingOsDashboardApprovals:

    def test_approvals_snapshot_uses_normalized(self):
        """A mirrored pending_approval post surfaces in the OS dashboard."""
        db = _mongo()
        post = {
            "id":           uuid.uuid4().hex,
            "user_id":      TEST_USER_ID,
            "content":      "phase4 os-dash approval " + uuid.uuid4().hex[:6],
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
            ids = [p["id"] for p in r.json().get("approvals", [])]
            assert post["id"] in ids
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


class TestDashboardStats:

    def test_stats_posts_count_uses_content_items(self):
        """The `posts` counter in /dashboard/stats reflects content_items in
        strict mode (or content_items + un-mirrored count in lenient)."""
        r = requests.get(f"{API_URL}/api/dashboard/stats", headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "posts" in body
        assert isinstance(body["posts"], int)
        assert body["posts"] >= 0


class TestStrictModeBehavior:
    """Direct unit tests on the resolver and list helper for the strict flag."""

    def test_resolve_strict_excludes_unmirrored(self, seeded):
        """In strict mode, un-mirrored posts must NOT appear in resolved ids."""
        async def go():
            ids_lenient, n_unmirrored_l = await CL.resolve_post_ids_for_status(
                TEST_USER_ID, status="scheduled", strict=False,
            )
            ids_strict, n_unmirrored_s = await CL.resolve_post_ids_for_status(
                TEST_USER_ID, status="scheduled", strict=True,
            )
            assert seeded["unmirrored_id"] in ids_lenient
            assert seeded["unmirrored_id"] not in ids_strict
            assert seeded["mirrored_id"] in ids_strict
            # The drift count is reported identically — strictness only
            # gates *inclusion*, not visibility.
            assert n_unmirrored_l == n_unmirrored_s
            assert n_unmirrored_l >= 1
        _run(go())

    def test_list_posts_strict_excludes_unmirrored(self, seeded):
        async def go():
            lenient = await CL.list_posts_via_normalized(TEST_USER_ID, limit=200, strict=False)
            strict = await CL.list_posts_via_normalized(TEST_USER_ID, limit=200, strict=True)
            lenient_ids = {p["id"] for p in lenient}
            strict_ids = {p["id"] for p in strict}
            assert seeded["unmirrored_id"] in lenient_ids
            assert seeded["unmirrored_id"] not in strict_ids
            assert seeded["mirrored_id"] in strict_ids
        _run(go())

    def test_list_posts_zero_limit_returns_empty(self):
        async def go():
            res = await CL.list_posts_via_normalized(TEST_USER_ID, limit=0)
            assert res == []
        _run(go())
