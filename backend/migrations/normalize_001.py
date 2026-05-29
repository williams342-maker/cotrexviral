"""Migration 001 — Normalize the data model.

Idempotent. Safe to run many times. Backfills:

  1. **brands** — one default brand per existing user.
  2. **content_items + content_variants** — one item per existing
     `posts` row, one variant per platform in that post's
     `platforms[]` list.
  3. **campaigns.brand_id** — every existing campaign gets stamped.
  4. **posts.brand_id** — every existing post gets stamped (FK for
     legacy reads).
  5. **cortex_memory.meta** — for `kind="post"` rows that link to a
     migrated post via `meta.post_id`, stamp `brand_id`,
     `content_item_id`, and `variant_id` so the agent can
     cross-reference the normalized layer without latency (decision 4a).

Strategy
--------
- Each row carries a `migrated: true` flag the first time we touch it,
  so subsequent runs skip the work.
- The script processes rows in batches of 500 to keep memory bounded.
- Logs aggregate counts at the end. Returns the same dict so callers
  (admin endpoint, pytest, startup hook) can assert.

Wired to:
- `migrate_now()` is exposed as a one-shot admin POST so a deploy can
  trigger it without an SSH window.
- It also auto-runs on backend startup the FIRST time, gated by a
  `_migration_state` doc — so a fresh deploy is self-healing.
"""
import logging
import uuid
from datetime import datetime, timezone

from core import db
from models_normalized import NORMALIZED_INDEXES
from routes.brands import ensure_default_brand_for_user

logger = logging.getLogger(__name__)

MIGRATION_ID = "normalize_001"
BATCH_SIZE = 500


async def _ensure_indexes() -> None:
    """Idempotent index creation across the new collections."""
    for col, idx_list in NORMALIZED_INDEXES.items():
        for keys, opts in idx_list:
            try:
                await db[col].create_index(keys, **opts)
            except Exception:
                logger.exception("create_index failed: col=%s keys=%s opts=%s", col, keys, opts)


async def _backfill_brands_for_users() -> dict:
    """One default brand per user. Returns user_id → brand_id."""
    mapping: dict = {}
    created = 0
    reused = 0
    cursor = db.users.find({"status": {"$ne": "deleted"}}, {"_id": 0, "user_id": 1, "name": 1})
    async for u in cursor:
        existing = await db.brands.find_one(
            {"user_id": u["user_id"], "is_default": True}, {"_id": 0, "id": 1},
        )
        if existing:
            mapping[u["user_id"]] = existing["id"]
            reused += 1
        else:
            bid = await ensure_default_brand_for_user(u["user_id"], name_hint=u.get("name"))
            mapping[u["user_id"]] = bid
            created += 1
    return {"users": len(mapping), "brands_created": created, "brands_reused": reused, "mapping": mapping}


async def _backfill_campaigns_brand_id(brand_map: dict) -> dict:
    """Stamp `brand_id` on every campaign row. Idempotent."""
    updated = 0
    skipped_no_brand = 0
    cursor = db.campaigns.find(
        {"brand_id": {"$exists": False}}, {"_id": 0, "id": 1, "user_id": 1},
    ).batch_size(BATCH_SIZE)
    async for c in cursor:
        bid = brand_map.get(c.get("user_id"))
        if not bid:
            skipped_no_brand += 1
            continue
        res = await db.campaigns.update_one(
            {"id": c["id"]},
            {"$set": {"brand_id": bid, "migrated": True,
                      "migrated_at": datetime.now(timezone.utc)}},
        )
        if res.modified_count:
            updated += 1
    return {"campaigns_updated": updated, "skipped_no_brand": skipped_no_brand}


async def _split_post_into_items_and_variants(post: dict, brand_id: str) -> tuple[str, list[str]]:
    """Create a content_item + N variants (one per platform). Returns
    (content_item_id, [variant_ids])."""
    now = datetime.now(timezone.utc)
    content_item_id = uuid.uuid4().hex
    body = post.get("content") or ""
    title = (body[:80] + "…") if len(body) > 80 else (body or "(no content)")

    await db.content_items.insert_one({
        "id":            content_item_id,
        "brand_id":      brand_id,
        "user_id":       post["user_id"],
        "campaign_id":   post.get("campaign_id"),
        "title":         title,
        "intent":        body,
        "status":        post.get("status") or "draft",
        "source":        "migrated",
        "source_run_id": None,
        "created_at":    post.get("created_at") or now,
        "updated_at":    now,
    })

    platforms = post.get("platforms") or []
    if not platforms:
        # Defensive: every legacy post should have at least one
        # platform, but if it doesn't, treat it as a single
        # "unknown"-platform variant so we don't lose it.
        platforms = ["unknown"]

    variant_ids: list[str] = []
    media_urls: list[str] = []
    if post.get("media_url"):
        media_urls.append(post["media_url"])

    for platform in platforms:
        vid = uuid.uuid4().hex
        await db.content_variants.insert_one({
            "id":               vid,
            "content_item_id":  content_item_id,
            "brand_id":         brand_id,
            "user_id":          post["user_id"],
            "platform":         platform,
            "body":             body,
            "media_urls":       list(media_urls),
            "status":           post.get("status") or "draft",
            "post_id":          post["id"],   # link back to the legacy row
            "scheduled_at":     post.get("scheduled_at"),
            "published_at":     post.get("published_at"),
            "external_post_id": None,
            "external_url":     None,
            "error":            None,
            "created_at":       post.get("created_at") or now,
            "updated_at":       now,
        })
        variant_ids.append(vid)

    return content_item_id, variant_ids


async def _backfill_posts_and_split(brand_map: dict) -> dict:
    """For each legacy post that doesn't have `brand_id` yet:
      • Stamp `brand_id`, `content_item_id`, `variant_ids` on the post row.
      • Create the new content_item + variants.
    """
    items_created = 0
    variants_created = 0
    posts_updated = 0
    skipped_no_brand = 0

    cursor = db.posts.find(
        {"brand_id": {"$exists": False}},
        {"_id": 0, "id": 1, "user_id": 1, "content": 1, "platforms": 1,
         "media_url": 1, "status": 1, "scheduled_at": 1,
         "published_at": 1, "created_at": 1, "campaign_id": 1},
    ).batch_size(BATCH_SIZE)

    async for p in cursor:
        bid = brand_map.get(p.get("user_id"))
        if not bid:
            skipped_no_brand += 1
            continue
        try:
            content_item_id, variant_ids = await _split_post_into_items_and_variants(p, bid)
        except Exception:
            logger.exception("split failed for post %s", p.get("id"))
            continue
        items_created += 1
        variants_created += len(variant_ids)
        await db.posts.update_one(
            {"id": p["id"]},
            {"$set": {
                "brand_id":        bid,
                "content_item_id": content_item_id,
                "variant_ids":     variant_ids,
                "migrated":        True,
                "migrated_at":     datetime.now(timezone.utc),
            }},
        )
        posts_updated += 1

    return {
        "posts_updated":     posts_updated,
        "items_created":     items_created,
        "variants_created":  variants_created,
        "skipped_no_brand":  skipped_no_brand,
    }


async def _backfill_cortex_memory_meta() -> dict:
    """For each `kind="post"` memory row whose `meta.post_id` points at
    a now-migrated post, stamp `brand_id`, `content_item_id`, and
    `variant_id` into the meta block. Variant choice = first variant
    (memory is platform-agnostic; the agent can hop to other variants
    via content_item_id if it cares about a specific platform)."""
    updated = 0
    skipped_no_post = 0
    cursor = db.cortex_memory.find(
        {"kind": "post", "meta.brand_id": {"$exists": False}},
        {"_id": 0, "id": 1, "meta": 1},
    ).batch_size(BATCH_SIZE)
    async for m in cursor:
        post_id = (m.get("meta") or {}).get("post_id")
        if not post_id:
            skipped_no_post += 1
            continue
        p = await db.posts.find_one(
            {"id": post_id, "brand_id": {"$exists": True}},
            {"_id": 0, "brand_id": 1, "content_item_id": 1, "variant_ids": 1},
        )
        if not p:
            skipped_no_post += 1
            continue
        first_variant = (p.get("variant_ids") or [None])[0]
        await db.cortex_memory.update_one(
            {"id": m["id"]},
            {"$set": {
                "meta.brand_id":        p["brand_id"],
                "meta.content_item_id": p.get("content_item_id"),
                "meta.variant_id":      first_variant,
            }},
        )
        updated += 1
    return {"memory_rows_updated": updated, "memory_rows_skipped": skipped_no_post}


async def migrate_now() -> dict:
    """Public entrypoint. Runs all steps in order. Idempotent."""
    await _ensure_indexes()

    brand_step = await _backfill_brands_for_users()
    brand_map = brand_step.pop("mapping")
    campaign_step = await _backfill_campaigns_brand_id(brand_map)
    post_step = await _backfill_posts_and_split(brand_map)
    memory_step = await _backfill_cortex_memory_meta()

    # Stamp a high-watermark doc so a future startup hook can skip when
    # there's nothing to do. Motor blocks `db.<name>` for collection
    # names that start with `_`, so we use the dict accessor.
    await db["_migration_state"].update_one(
        {"_id": MIGRATION_ID},
        {"$set": {
            "completed_at": datetime.now(timezone.utc),
            "result":       {**brand_step, **campaign_step, **post_step, **memory_step},
        }},
        upsert=True,
    )

    result = {
        **brand_step,
        **campaign_step,
        **post_step,
        **memory_step,
    }
    logger.info("migration %s done: %s", MIGRATION_ID, result)
    return result


async def needs_migration() -> bool:
    """Cheap check used by the startup hook — if there are users
    without a default brand, OR campaigns/posts without brand_id, we
    need to run."""
    if await db.users.count_documents({"status": {"$ne": "deleted"}}) == 0:
        return False
    if await db.brands.count_documents({"is_default": True}) == 0:
        return True
    if await db.campaigns.count_documents({"brand_id": {"$exists": False}}) > 0:
        return True
    if await db.posts.count_documents({"brand_id": {"$exists": False}}) > 0:
        return True
    return False
