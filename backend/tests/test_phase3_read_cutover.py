"""Phase 3 — read-side cutover tests.

Verifies that `/api/posts/scheduled` and `/api/approvals` now resolve
matching posts via the normalized `content_variants` index rather than
querying `db.posts` directly — while still returning the legacy
post-shaped JSON the frontend expects.

Also covers:
  • Lenient fallback for un-mirrored posts (a post lacking content_item_id
    still surfaces in the reads).
  • Admin drift/health endpoint.
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
from core import STRICT_NORMALIZED_READS  # noqa: E402

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TEST_TOKEN = "test_session_1779636592168"
TEST_USER_ID = "user_test1779636592168"
HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def cleanup():
    """Track created post_ids + content_item_ids for cleanup after each test."""
    created = {"post_ids": [], "content_item_ids": []}
    yield created
    async def go():
        db = _mongo()
        if created["post_ids"]:
            await db.posts.delete_many({"id": {"$in": created["post_ids"]}})
            await db.content_variants.delete_many({"post_id": {"$in": created["post_ids"]}})
        if created["content_item_ids"]:
            await db.content_items.delete_many({"id": {"$in": created["content_item_ids"]}})
    _run(go())


async def _insert_mirrored(post: dict):
    """Helper: insert a post + mirror it into the normalized layer."""
    db = _mongo()
    await db.posts.insert_one(dict(post))
    await CL.mirror_post_to_normalized(post)


async def _insert_unmirrored(post: dict):
    """Helper: insert a post WITHOUT mirroring it — simulates a Phase 2
    mirror failure or a pre-migration straggler."""
    db = _mongo()
    await db.posts.insert_one(dict(post))


class TestScheduledReads:

    def test_list_scheduled_resolves_via_normalized(self, cleanup):
        """A mirrored scheduled post shows up via the normalized read path."""
        async def go():
            post = {
                "id":            uuid.uuid4().hex,
                "user_id":       TEST_USER_ID,
                "content":       "phase3 scheduled read test " + uuid.uuid4().hex[:6],
                "platforms":     ["linkedin", "twitter"],
                "status":        "scheduled",
                "scheduled_at":  datetime.now(timezone.utc) + timedelta(hours=2),
                "created_at":    datetime.now(timezone.utc),
            }
            await _insert_mirrored(post)
            cleanup["post_ids"].append(post["id"])

            r = requests.get(f"{API_URL}/api/posts/scheduled", headers=HEADERS, timeout=20)
            assert r.status_code == 200, r.text
            ids = [p["id"] for p in r.json()]
            assert post["id"] in ids
        _run(go())

    def test_list_scheduled_falls_back_for_unmirrored(self, cleanup):
        """In lenient mode, a scheduled post that escaped the mirror (no
        content_item_id) still appears via the lenient fallback to the
        legacy posts query. In strict mode it should NOT appear."""
        async def go():
            post = {
                "id":            uuid.uuid4().hex,
                "user_id":       TEST_USER_ID,
                "content":       "phase3 unmirrored straggler " + uuid.uuid4().hex[:6],
                "platforms":     ["linkedin"],
                "status":        "scheduled",
                "scheduled_at":  datetime.now(timezone.utc) + timedelta(hours=2),
                "created_at":    datetime.now(timezone.utc),
            }
            await _insert_unmirrored(post)
            cleanup["post_ids"].append(post["id"])

            r = requests.get(f"{API_URL}/api/posts/scheduled", headers=HEADERS, timeout=20)
            assert r.status_code == 200, r.text
            ids = [p["id"] for p in r.json()]
            if STRICT_NORMALIZED_READS:
                assert post["id"] not in ids, "Strict mode must hide un-mirrored posts"
            else:
                assert post["id"] in ids, "Lenient mode should surface un-mirrored posts"
        _run(go())

    def test_list_scheduled_filters_by_time_range(self, cleanup):
        """The start/end filter still works after the normalized cutover."""
        async def go():
            # A post 2 hours from now and another 5 days from now
            now = datetime.now(timezone.utc)
            soon = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 range-soon",
                "platforms":    ["linkedin"],
                "status":       "scheduled",
                "scheduled_at": now + timedelta(hours=2),
                "created_at":   now,
            }
            far = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 range-far",
                "platforms":    ["linkedin"],
                "status":       "scheduled",
                "scheduled_at": now + timedelta(days=5),
                "created_at":   now,
            }
            await _insert_mirrored(soon)
            await _insert_mirrored(far)
            cleanup["post_ids"].extend([soon["id"], far["id"]])

            # Window covers only the next 24h
            start = now.isoformat().replace("+00:00", "Z")
            end = (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
            r = requests.get(
                f"{API_URL}/api/posts/scheduled",
                params={"start": start, "end": end},
                headers=HEADERS, timeout=20,
            )
            assert r.status_code == 200, r.text
            ids = [p["id"] for p in r.json()]
            assert soon["id"] in ids
            assert far["id"] not in ids
        _run(go())


class TestApprovalsReads:

    def test_list_pending_resolves_via_normalized(self, cleanup):
        """A mirrored pending_approval post shows up via the normalized read path."""
        async def go():
            post = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 approval read " + uuid.uuid4().hex[:6],
                "platforms":    ["linkedin"],
                "status":       "pending_approval",
                "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
                "created_at":   datetime.now(timezone.utc),
            }
            await _insert_mirrored(post)
            cleanup["post_ids"].append(post["id"])

            r = requests.get(f"{API_URL}/api/approvals", headers=HEADERS, timeout=20)
            assert r.status_code == 200, r.text
            body = r.json()
            assert "pending" in body
            ids = [p["id"] for p in body["pending"]]
            assert post["id"] in ids
        _run(go())

    def test_list_pending_falls_back_for_unmirrored(self, cleanup):
        """An un-mirrored pending_approval still surfaces in lenient mode;
        is hidden in strict mode."""
        async def go():
            post = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 approval straggler " + uuid.uuid4().hex[:6],
                "platforms":    ["linkedin"],
                "status":       "pending_approval",
                "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
                "created_at":   datetime.now(timezone.utc),
            }
            await _insert_unmirrored(post)
            cleanup["post_ids"].append(post["id"])

            r = requests.get(f"{API_URL}/api/approvals", headers=HEADERS, timeout=20)
            assert r.status_code == 200, r.text
            ids = [p["id"] for p in r.json()["pending"]]
            if STRICT_NORMALIZED_READS:
                assert post["id"] not in ids
            else:
                assert post["id"] in ids
        _run(go())


class TestDriftHealthEndpoint:

    def test_requires_admin(self):
        # No bearer = 401
        r = requests.get(f"{API_URL}/api/admin/content-layer/health", timeout=10)
        assert r.status_code == 401

    def test_health_shape(self):
        """Returns the expected counters + drift flag."""
        r = requests.get(f"{API_URL}/api/admin/content-layer/health",
                          headers=HEADERS, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in [
            "total_posts", "mirrored_posts", "unmirrored_posts",
            "mirror_coverage_pct", "total_content_items",
            "total_content_variants", "unmirrored_by_status",
            "drift_threshold", "drift_triggered",
        ]:
            assert k in body, f"Missing field {k} in {body}"
        # Coverage is a float in [0, 100]
        assert isinstance(body["mirror_coverage_pct"], (int, float))
        assert 0 <= body["mirror_coverage_pct"] <= 100
        # Consistency: mirrored + unmirrored == total
        assert body["mirrored_posts"] + body["unmirrored_posts"] == body["total_posts"]
        # drift_triggered is a deterministic function of the count
        assert body["drift_triggered"] is (body["unmirrored_posts"] >= body["drift_threshold"])


class TestResolveHelper:

    def test_resolver_finds_mirrored_and_unmirrored(self, cleanup):
        """`resolve_post_ids_for_status` returns the UNION of normalized
        + un-mirrored posts (when called with strict=False) and reports
        the un-mirrored count regardless of strictness."""
        async def go():
            now = datetime.now(timezone.utc)
            mirrored = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 resolver mirrored",
                "platforms":    ["linkedin"],
                "status":       "scheduled",
                "scheduled_at": now + timedelta(hours=2),
                "created_at":   now,
            }
            unmirrored = {
                "id":           uuid.uuid4().hex,
                "user_id":      TEST_USER_ID,
                "content":      "phase3 resolver unmirrored",
                "platforms":    ["linkedin"],
                "status":       "scheduled",
                "scheduled_at": now + timedelta(hours=2),
                "created_at":   now,
            }
            await _insert_mirrored(mirrored)
            await _insert_unmirrored(unmirrored)
            cleanup["post_ids"].extend([mirrored["id"], unmirrored["id"]])

            # Explicitly request lenient mode for this test (independent of env flag).
            post_ids, n_unmirrored = await CL.resolve_post_ids_for_status(
                TEST_USER_ID, status="scheduled", strict=False,
            )
            assert mirrored["id"] in post_ids
            assert unmirrored["id"] in post_ids
            assert n_unmirrored >= 1
        _run(go())
