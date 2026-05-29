"""Phase 2 writer migration — content_layer tests.

Verifies that every writer path (compose, scheduler, approvals, auto-draft)
mirrors into `content_items` + `content_variants` and propagates status
transitions correctly. Also covers idempotency and cascade-delete.

These run against the live dev Mongo. Test rows are cleaned up via UUID
prefixes — every row inserted by a test carries a known suffix so cleanup
is precise.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import content_layer as CL  # noqa: E402
from routes import brands as B          # noqa: E402


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_post(*, user_id: str, platforms: list, content: str = "Test post body", status: str = "scheduled", post_id: str | None = None) -> dict:
    """Helper — build a post dict the way channels.py would write it."""
    return {
        "id":          post_id or uuid.uuid4().hex,
        "user_id":     user_id,
        "content":     content,
        "platforms":   platforms,
        "media_url":   None,
        "status":      status,
        "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
        "campaign_id": None,
        "created_at":  datetime.now(timezone.utc),
    }


@pytest.fixture(scope="module")
def user_id() -> str:
    """A throwaway user_id we can attribute all writes to. Cleanup at module teardown."""
    return f"phase2_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True, scope="module")
def _cleanup(user_id):
    yield
    db = _mongo()
    async def go():
        await db.posts.delete_many({"user_id": user_id})
        await db.content_items.delete_many({"user_id": user_id})
        await db.content_variants.delete_many({"user_id": user_id})
        await db.brands.delete_many({"user_id": user_id})
    _run(go())


class TestMirror:

    def test_mirror_creates_content_item_and_variants(self, user_id):
        """A new post → 1 content_item + N variants (one per platform). Cross-ref
        triple stamped on the legacy post row."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin", "twitter", "instagram"])
            await db.posts.insert_one(dict(post))
            ref = await CL.mirror_post_to_normalized(post)

            assert ref is not None
            assert ref["content_item_id"]
            assert len(ref["variant_ids"]) == 3
            assert ref["brand_id"]

            # content_item exists with right shape
            ci = await db.content_items.find_one({"id": ref["content_item_id"]}, {"_id": 0})
            assert ci["user_id"] == user_id
            assert ci["status"] == "scheduled"
            assert ci["intent"] == "Test post body"

            # 3 variants, one per platform
            variants = await db.content_variants.find(
                {"content_item_id": ref["content_item_id"]}, {"_id": 0}
            ).to_list(10)
            assert len(variants) == 3
            platforms = sorted(v["platform"] for v in variants)
            assert platforms == ["instagram", "linkedin", "twitter"]
            assert all(v["post_id"] == post["id"] for v in variants)
            assert all(v["status"] == "scheduled" for v in variants)

            # Legacy post got stamped with the triple
            stamped = await db.posts.find_one({"id": post["id"]}, {"_id": 0})
            assert stamped["brand_id"] == ref["brand_id"]
            assert stamped["content_item_id"] == ref["content_item_id"]
            assert sorted(stamped["variant_ids"]) == sorted(ref["variant_ids"])
        _run(go())

    def test_mirror_is_idempotent(self, user_id):
        """Calling twice on the same post → same reference, no duplicate variants."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin"])
            await db.posts.insert_one(dict(post))

            ref1 = await CL.mirror_post_to_normalized(post)
            ref2 = await CL.mirror_post_to_normalized(post)

            assert ref1["content_item_id"] == ref2["content_item_id"]
            assert ref1["variant_ids"] == ref2["variant_ids"]

            # Exactly one item, one variant
            n_items = await db.content_items.count_documents({"id": ref1["content_item_id"]})
            n_variants = await db.content_variants.count_documents({"post_id": post["id"]})
            assert n_items == 1
            assert n_variants == 1
        _run(go())

    def test_mirror_handles_missing_platforms(self, user_id):
        """A post with no platforms gets one 'unknown' variant rather than zero —
        we'd lose attribution otherwise."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=[])
            await db.posts.insert_one(dict(post))
            ref = await CL.mirror_post_to_normalized(post)
            assert ref is not None
            variants = await db.content_variants.find(
                {"post_id": post["id"]}, {"_id": 0, "platform": 1}
            ).to_list(10)
            assert len(variants) == 1
            assert variants[0]["platform"] == "unknown"
        _run(go())


class TestPropagateStatus:

    def test_propagate_status_flips_variants_and_item(self, user_id):
        """scheduler -> published should flip every variant + the umbrella item."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin", "tiktok"])
            await db.posts.insert_one(dict(post))
            ref = await CL.mirror_post_to_normalized(post)

            published_at = datetime.now(timezone.utc)
            ok = await CL.propagate_status_to_variants(
                post["id"], status="published", published_at=published_at,
            )
            assert ok is True

            variants = await db.content_variants.find(
                {"post_id": post["id"]}, {"_id": 0}
            ).to_list(10)
            assert all(v["status"] == "published" for v in variants)
            assert all(v["published_at"] is not None for v in variants)

            ci = await db.content_items.find_one({"id": ref["content_item_id"]}, {"_id": 0})
            assert ci["status"] == "published"
        _run(go())

    def test_propagate_external_dispatch_per_platform(self, user_id):
        """Per-platform dispatch metadata (external_post_id/url) lands on the
        matching variant — not bled across to others."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin", "tiktok"])
            await db.posts.insert_one(dict(post))
            await CL.mirror_post_to_normalized(post)

            await CL.propagate_status_to_variants(
                post["id"],
                external_dispatch={
                    "linkedin": {"ok": True, "external_id": "li_123", "permalink": "https://linkedin.com/p/li_123"},
                    "tiktok":   {"ok": False, "reason": "rate limited"},
                },
            )

            li = await db.content_variants.find_one(
                {"post_id": post["id"], "platform": "linkedin"}, {"_id": 0},
            )
            tt = await db.content_variants.find_one(
                {"post_id": post["id"], "platform": "tiktok"}, {"_id": 0},
            )
            assert li["external_post_id"] == "li_123"
            assert li["external_url"] == "https://linkedin.com/p/li_123"
            assert li.get("error") in (None, "")
            # TikTok carries the error, NOT linkedin's id
            assert tt.get("external_post_id") in (None, "")
            assert tt["error"] == "rate limited"
        _run(go())

    def test_propagate_body_edit_updates_intent_and_title(self, user_id):
        """PATCH /posts/scheduled body edits should propagate into the
        normalized layer too — the agent should see the latest text."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin"])
            await db.posts.insert_one(dict(post))
            ref = await CL.mirror_post_to_normalized(post)

            new_body = "Edited body — this is now what gets read by the agent layer"
            await CL.propagate_status_to_variants(post["id"], body=new_body)

            v = await db.content_variants.find_one({"post_id": post["id"]}, {"_id": 0})
            assert v["body"] == new_body
            ci = await db.content_items.find_one({"id": ref["content_item_id"]}, {"_id": 0})
            assert ci["intent"] == new_body
            assert ci["title"].startswith("Edited body")
        _run(go())

    def test_unknown_status_is_rejected(self, user_id):
        """A typo'd status should be ignored — we don't want junk values
        leaking into the normalized layer."""
        async def go():
            ok = await CL.propagate_status_to_variants(
                "nonexistent_post_id_for_test", status="not_a_real_status",
            )
            assert ok is False
        _run(go())


class TestBulkAndCascade:

    def test_propagate_status_for_many(self, user_id):
        """Bulk scheduler flip should hit every variant of every input post."""
        async def go():
            db = _mongo()
            posts = []
            for _ in range(3):
                p = _make_post(user_id=user_id, platforms=["linkedin", "x"])
                await db.posts.insert_one(dict(p))
                await CL.mirror_post_to_normalized(p)
                posts.append(p)

            ids = [p["id"] for p in posts]
            await CL.propagate_status_for_many(ids, status="published",
                                                published_at=datetime.now(timezone.utc))
            n_published = await db.content_variants.count_documents(
                {"post_id": {"$in": ids}, "status": "published"},
            )
            # 3 posts × 2 platforms = 6 variants
            assert n_published == 6
        _run(go())

    def test_cascade_delete_archives_rather_than_deletes(self, user_id):
        """Cancel of a scheduled post should mark variants as archived,
        not physically delete them — keeps attribution / metrics intact."""
        async def go():
            db = _mongo()
            post = _make_post(user_id=user_id, platforms=["linkedin"])
            await db.posts.insert_one(dict(post))
            await CL.mirror_post_to_normalized(post)

            # Pretend the user cancelled — the route already did delete_one.
            await db.posts.delete_one({"id": post["id"]})
            await CL.cascade_delete_for_posts([post["id"]])

            # Variant still exists, just archived
            v = await db.content_variants.find_one({"post_id": post["id"]}, {"_id": 0})
            assert v is not None
            assert v["status"] == "archived"
        _run(go())
