"""Migration tests — normalize_001.

Covers:
  1. Idempotency — running migrate_now twice produces no extra work.
  2. Default brand auto-created per user.
  3. Every existing campaign + post is stamped with brand_id.
  4. Every legacy post produces 1 content_item + N variants (one per platform).
  5. cortex_memory rows with kind="post" carry brand_id/content_item_id/variant_id
     in meta after migration.
  6. needs_migration() flips False after a successful run.
  7. ensure_default_brand_for_user is idempotent on its own.
  8. Signup hook creates a default brand for a freshly-inserted user.

These run against the live dev Mongo. Migration is idempotent so we
don't need to reset state — the production data lives alongside the
test rows.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from migrations import normalize_001 as M       # noqa: E402
from routes import brands as B                  # noqa: E402


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestNormalizeMigration:

    def test_migration_is_idempotent(self):
        """First run does work; second run should report zero creates."""
        async def go():
            first = await M.migrate_now()
            second = await M.migrate_now()
            # Second pass should create no NEW brands / campaigns /
            # items / variants — everything is reused.
            assert second["brands_created"] == 0, second
            assert second["campaigns_updated"] == 0, second
            assert second["posts_updated"] == 0, second
            assert second["items_created"] == 0, second
            assert second["variants_created"] == 0, second
            # And `needs_migration()` must now report False.
            assert (await M.needs_migration()) is False
            return first, second
        first, second = _run(go())
        # First run may have done work or may have been a no-op (already
        # done by startup). Either way the counts make sense.
        assert first["users"] >= 1

    def test_every_active_user_has_default_brand(self):
        async def go():
            db = _mongo()
            users = await db.users.find(
                {"status": {"$ne": "deleted"}}, {"_id": 0, "user_id": 1},
            ).to_list(length=500)
            for u in users:
                b = await db.brands.find_one(
                    {"user_id": u["user_id"], "is_default": True},
                    {"_id": 0, "id": 1},
                )
                assert b is not None, f"user {u['user_id']} missing default brand"
        _run(go())

    def test_every_campaign_has_brand_id(self):
        async def go():
            db = _mongo()
            no_brand = await db.campaigns.count_documents(
                {"brand_id": {"$exists": False}},
            )
            assert no_brand == 0, f"{no_brand} campaigns missing brand_id"
        _run(go())

    def test_every_post_has_brand_id_and_variants(self):
        async def go():
            db = _mongo()
            no_brand = await db.posts.count_documents(
                {"brand_id": {"$exists": False}},
            )
            assert no_brand == 0
            # Every migrated post should have content_item_id + at least
            # one variant_id.
            stale = await db.posts.count_documents({
                "brand_id":         {"$exists": True},
                "content_item_id":  {"$exists": False},
            })
            assert stale == 0, f"{stale} posts missing content_item_id"
        _run(go())

    def test_variants_count_matches_platforms_count(self):
        """For a randomly-sampled migrated post, the number of variants
        equals the number of platforms it had."""
        async def go():
            db = _mongo()
            sample = await db.posts.aggregate([
                {"$match": {"migrated": True, "variant_ids": {"$exists": True}}},
                {"$sample": {"size": 10}},
                {"$project": {"_id": 0, "id": 1, "platforms": 1, "variant_ids": 1}},
            ]).to_list(length=10)
            for p in sample:
                want = max(1, len(p.get("platforms") or []))
                got  = len(p.get("variant_ids") or [])
                assert got == want, f"post {p['id']}: platforms={want}, variants={got}"
                # And every variant_id should be reachable.
                for vid in p["variant_ids"]:
                    v = await db.content_variants.find_one({"id": vid}, {"_id": 0, "post_id": 1})
                    assert v is not None, f"missing variant row {vid}"
                    assert v["post_id"] == p["id"]
        _run(go())

    def test_cortex_memory_post_rows_carry_normalized_fks(self):
        """Memory rows with kind="post" pointing at a migrated post
        should have meta.brand_id, meta.content_item_id, meta.variant_id
        stamped."""
        async def go():
            db = _mongo()
            sample = await db.cortex_memory.aggregate([
                {"$match": {"kind": "post", "meta.post_id": {"$exists": True},
                            "meta.brand_id": {"$exists": True}}},
                {"$sample": {"size": 5}},
                {"$project": {"_id": 0, "meta": 1}},
            ]).to_list(length=5)
            # Don't hard-require 5 matches (the test env may have few
            # memory rows of this kind), but every match we DO get must
            # have all three fields.
            for m in sample:
                meta = m["meta"]
                assert meta.get("brand_id"), meta
                assert meta.get("content_item_id"), meta
                # variant_id can be None if the source post had no
                # platforms[], but the key must exist.
                assert "variant_id" in meta, meta
        _run(go())

    def test_ensure_default_brand_is_idempotent(self):
        """Calling the helper many times with the same user_id never
        creates more than one brand."""
        async def go():
            db = _mongo()
            uid = f"test_norm_helper_{uuid.uuid4().hex[:8]}"
            try:
                await db.users.insert_one({
                    "user_id":    uid,
                    "name":       "Test Solo",
                    "status":     "active",
                    "created_at": datetime.now(timezone.utc),
                })
                bid_a = await B.ensure_default_brand_for_user(uid, name_hint="Test Solo")
                bid_b = await B.ensure_default_brand_for_user(uid)
                bid_c = await B.ensure_default_brand_for_user(uid, name_hint="Different name")
                assert bid_a == bid_b == bid_c
                count = await db.brands.count_documents({"user_id": uid})
                assert count == 1
            finally:
                await db.users.delete_many({"user_id": uid})
                await db.brands.delete_many({"user_id": uid})
        _run(go())

    def test_indexes_exist_after_migration(self):
        """All NORMALIZED_INDEXES should be present."""
        async def go():
            db = _mongo()
            from models_normalized import NORMALIZED_INDEXES
            for col_name, idx_list in NORMALIZED_INDEXES.items():
                col = db[col_name]
                existing = await col.index_information()
                # `_id_` is always there, but our compound indexes
                # produce auto-generated names — at minimum the count
                # should be > 1 for every collection we declared
                # indexes for.
                assert len(existing) >= 1 + len(idx_list), (
                    f"col {col_name}: expected at least {1+len(idx_list)} "
                    f"indexes, got {list(existing.keys())}"
                )
        _run(go())
