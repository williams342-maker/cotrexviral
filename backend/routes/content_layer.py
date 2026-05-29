"""Phase 2 — Writer mirror into the normalized content layer.

Every code path that creates a `posts` row should also create one
`content_items` row (the platform-agnostic intent) + N `content_variants`
rows (one per platform). Status transitions on `posts` should propagate
to the corresponding variants so the normalized layer stays in lock-step.

This module centralises that logic so the writers (`channels.py`,
`auto_draft.py`, `scheduler.py`, `approvals.py`) don't each duplicate it.

Design notes
------------
- **Idempotent**: `mirror_post_to_normalized` short-circuits if the post
  already carries `content_item_id`. Safe to call from auto-draft upserts
  where the same post may be touched multiple times.
- **Best-effort**: mirroring failures are caught + logged; never raise
  into the caller. The legacy `posts` row remains the read source-of-truth
  during the migration window, so a mirror failure is a degradation,
  never an outage.
- **Brand resolution**: lazy — only resolves the user's default brand_id
  on first call, then reuses it. Falls back to creating one if it doesn't
  exist (matches the signup hook).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

from core import db
from core import STRICT_NORMALIZED_READS
from routes.brands import ensure_default_brand_for_user

logger = logging.getLogger(__name__)


# Statuses the legacy `posts` collection uses. The normalized layer mirrors
# every transition by writing the same string into `content_variants.status`
# (and `content_items.status` for the umbrella).
_MIRRORED_STATUSES = {
    "draft",
    "pending_approval",
    "scheduled",
    "published",
    "failed",
    "rejected",
    "archived",
}


async def mirror_post_to_normalized(post: dict, *, brand_id: Optional[str] = None) -> Optional[dict]:
    """Create one content_item + N content_variants for a freshly-inserted
    `posts` row, and stamp the cross-reference triple
    (`brand_id`, `content_item_id`, `variant_ids`) back on the legacy row.

    Idempotent: returns the existing reference triple if the post was
    already mirrored.

    Returns ``{"content_item_id", "variant_ids", "brand_id"}`` on success,
    or ``None`` on failure (errors are logged, never raised).
    """
    try:
        # Already mirrored — return the existing reference.
        if post.get("content_item_id") and post.get("variant_ids"):
            return {
                "content_item_id": post["content_item_id"],
                "variant_ids":     post["variant_ids"],
                "brand_id":        post.get("brand_id"),
            }

        user_id = post.get("user_id")
        if not user_id:
            logger.warning("mirror_post_to_normalized: post %s has no user_id", post.get("id"))
            return None

        # Resolve brand. Auto-creates if first call for this user.
        bid = brand_id or await ensure_default_brand_for_user(user_id)

        now = datetime.now(timezone.utc)
        body = (post.get("content") or "").strip()
        title = (body[:80] + "…") if len(body) > 80 else (body or "(no content)")

        content_item_id = uuid.uuid4().hex
        await db.content_items.insert_one({
            "id":            content_item_id,
            "brand_id":      bid,
            "user_id":       user_id,
            "campaign_id":   post.get("campaign_id"),
            "title":         title,
            "intent":        body,
            "status":        post.get("status") or "draft",
            "source":        post.get("source") or "compose",
            "source_run_id": post.get("source_run_id"),
            "created_at":    post.get("created_at") or now,
            "updated_at":    now,
        })

        platforms = post.get("platforms") or []
        if not platforms:
            platforms = ["unknown"]

        media_urls: list[str] = []
        if post.get("media_url"):
            media_urls.append(post["media_url"])

        variant_ids: list[str] = []
        for platform in platforms:
            vid = uuid.uuid4().hex
            await db.content_variants.insert_one({
                "id":               vid,
                "content_item_id":  content_item_id,
                "brand_id":         bid,
                "user_id":          user_id,
                "platform":         platform,
                "body":             body,
                "media_urls":       list(media_urls),
                "status":           post.get("status") or "draft",
                "post_id":          post["id"],
                "scheduled_at":     post.get("scheduled_at"),
                "published_at":     post.get("published_at"),
                "external_post_id": None,
                "external_url":     None,
                "error":            None,
                "created_at":       post.get("created_at") or now,
                "updated_at":       now,
            })
            variant_ids.append(vid)

        # Stamp the cross-reference back onto the legacy post so future
        # reads can hop into the normalized layer in O(1).
        await db.posts.update_one(
            {"id": post["id"]},
            {"$set": {
                "brand_id":        bid,
                "content_item_id": content_item_id,
                "variant_ids":     variant_ids,
            }},
        )

        # Mutate the in-memory dict so the caller sees the new fields too
        # (lets callers return the enriched payload without a re-read).
        post["brand_id"] = bid
        post["content_item_id"] = content_item_id
        post["variant_ids"] = variant_ids

        return {
            "content_item_id": content_item_id,
            "variant_ids":     variant_ids,
            "brand_id":        bid,
        }
    except Exception as exc:  # pragma: no cover — never block the writer
        logger.exception("mirror_post_to_normalized failed for post %s: %s", post.get("id"), exc)
        return None


async def propagate_status_to_variants(
    post_id: str,
    *,
    status: Optional[str] = None,
    published_at: Optional[datetime] = None,
    scheduled_at: Optional[datetime] = None,
    body: Optional[str] = None,
    error: Optional[str] = None,
    external_dispatch: Optional[dict] = None,
) -> bool:
    """Propagate a `posts` status / timing / body change into every linked
    `content_variants` row (and the umbrella `content_items.status`).

    Returns True if anything was updated, False otherwise. Failures are
    logged + swallowed — the legacy update already happened in the
    caller, the mirror is best-effort.

    `external_dispatch`: dict keyed by platform (e.g. `{"linkedin": {"ok":
    True, "external_id": "..."}}`) — used by the scheduler to copy each
    platform's published external_post_id/external_url into the matching
    variant.
    """
    if status and status not in _MIRRORED_STATUSES:
        logger.debug("propagate_status_to_variants: unknown status %r — skipping", status)
        return False

    try:
        now = datetime.now(timezone.utc)
        variant_update: dict = {"updated_at": now}
        if status is not None:
            variant_update["status"] = status
        if published_at is not None:
            variant_update["published_at"] = published_at
        if scheduled_at is not None:
            variant_update["scheduled_at"] = scheduled_at
        if body is not None:
            variant_update["body"] = body
        if error is not None:
            variant_update["error"] = error

        # Bulk update every variant tied to this post_id.
        if len(variant_update) > 1:  # at least one real field besides updated_at
            await db.content_variants.update_many(
                {"post_id": post_id},
                {"$set": variant_update},
            )

        # Per-platform dispatch metadata — copy each platform's external
        # id/url into the matching variant row.
        if external_dispatch:
            for platform, payload in external_dispatch.items():
                if not isinstance(payload, dict):
                    continue
                ext_id = payload.get("external_id") or payload.get("post_id") or payload.get("id")
                ext_url = payload.get("permalink") or payload.get("url")
                ext_err = None if payload.get("ok") else (payload.get("reason") or payload.get("error"))
                fields: dict = {"updated_at": now}
                if ext_id:
                    fields["external_post_id"] = ext_id
                if ext_url:
                    fields["external_url"] = ext_url
                if ext_err:
                    fields["error"] = ext_err
                if len(fields) > 1:
                    await db.content_variants.update_one(
                        {"post_id": post_id, "platform": platform},
                        {"$set": fields},
                    )

        # Mirror the umbrella status/body onto content_items too (one item per
        # post in the current schema).
        item_fields: dict = {"updated_at": now}
        if status is not None:
            item_fields["status"] = status
        if body is not None:
            item_fields["intent"] = body
            item_fields["title"] = (body[:80] + "…") if len(body) > 80 else (body or "(no content)")
        if len(item_fields) > 1:
            doc = await db.content_variants.find_one(
                {"post_id": post_id},
                {"_id": 0, "content_item_id": 1},
            )
            if doc and doc.get("content_item_id"):
                await db.content_items.update_one(
                    {"id": doc["content_item_id"]},
                    {"$set": item_fields},
                )

        return True
    except Exception as exc:  # pragma: no cover
        logger.exception("propagate_status_to_variants failed for post %s: %s", post_id, exc)
        return False


async def propagate_status_for_many(
    post_ids: Iterable[str],
    *,
    status: str,
    published_at: Optional[datetime] = None,
) -> None:
    """Bulk version of `propagate_status_to_variants` for the scheduler's
    `update_many` path. No per-platform dispatch metadata here — call the
    single-post helper for that after each dispatch."""
    ids = list(post_ids)
    if not ids:
        return
    try:
        now = datetime.now(timezone.utc)
        v_update: dict = {"status": status, "updated_at": now}
        if published_at is not None:
            v_update["published_at"] = published_at
        await db.content_variants.update_many(
            {"post_id": {"$in": ids}},
            {"$set": v_update},
        )
        # And the content_items umbrella for each.
        items = await db.content_variants.find(
            {"post_id": {"$in": ids}},
            {"_id": 0, "content_item_id": 1},
        ).to_list(length=len(ids) * 6)  # up to 6 variants per post
        item_ids = list({d["content_item_id"] for d in items if d.get("content_item_id")})
        if item_ids:
            await db.content_items.update_many(
                {"id": {"$in": item_ids}},
                {"$set": {"status": status, "updated_at": now}},
            )
    except Exception as exc:  # pragma: no cover
        logger.exception("propagate_status_for_many failed: %s", exc)


async def cascade_delete_for_posts(post_ids: Iterable[str]) -> None:
    """Cancel/archive: when a `posts` row is hard-deleted, mark its mirror
    rows as `archived` (we preserve the rows for historical attribution
    rather than deleting — losing the variant_id breaks any future
    backward-lookup from performance metrics)."""
    ids = list(post_ids)
    if not ids:
        return
    try:
        now = datetime.now(timezone.utc)
        await db.content_variants.update_many(
            {"post_id": {"$in": ids}},
            {"$set": {"status": "archived", "updated_at": now}},
        )
        items = await db.content_variants.find(
            {"post_id": {"$in": ids}},
            {"_id": 0, "content_item_id": 1},
        ).to_list(length=len(ids) * 6)
        item_ids = list({d["content_item_id"] for d in items if d.get("content_item_id")})
        if item_ids:
            await db.content_items.update_many(
                {"id": {"$in": item_ids}},
                {"$set": {"status": "archived", "updated_at": now}},
            )
    except Exception as exc:  # pragma: no cover
        logger.exception("cascade_delete_for_posts failed: %s", exc)



# ---------------------------------------------------------------------
# Phase 3 — read-side cutover helpers.
#
# These let route handlers resolve "all posts matching {status, user, time
# range}" via the normalized layer (the agent-readable source-of-truth)
# instead of querying `db.posts` directly.
#
# The pattern is two-step: (1) get matching post_ids from
# `content_variants` (which is now the index for status + scheduling
# state), (2) fetch full post documents from `db.posts` via those ids.
#
# Step (2) keeps backwards compat — the legacy posts row still carries
# fields like `dispatch`, `recurrence_group_id`, `pinterest_*` that
# haven't been mirrored. Phase 4 will lift those fields into the
# normalized layer and eliminate the second hop entirely.
#
# **Lenient fallback** — if a post somehow lacks a normalized mirror
# (mirror failure, pre-Phase-1 row that escaped backfill), it's still
# included in the result by falling back to a direct `db.posts` query.
# A warning is logged so we can observe the un-mirrored set shrinking
# toward zero before cutting over to a strict read in a future phase.
# ---------------------------------------------------------------------
async def resolve_post_ids_for_status(
    user_id: str,
    *,
    status: str,
    scheduled_after: Optional[datetime] = None,
    scheduled_before: Optional[datetime] = None,
    strict: Optional[bool] = None,
) -> tuple[list[str], int]:
    """Return (post_ids, n_unmirrored) for all posts matching the filter.

    `n_unmirrored` is the count of posts found in the legacy `posts`
    collection that DON'T have a normalized mirror — useful for the
    /admin/content-layer/health endpoint that surfaces migration drift.

    `strict`:
      • None  — use env `STRICT_NORMALIZED_READS` (default behavior).
      • True  — drop the lenient fallback. Only return posts that have
                a normalized mirror. Un-mirrored stragglers are excluded.
      • False — include un-mirrored posts (Phase 3 lenient default).
    """
    strict_mode = strict if strict is not None else STRICT_NORMALIZED_READS

    # --- Step 1: normalized layer ---
    v_match: dict = {"user_id": user_id, "status": status}
    if scheduled_after or scheduled_before:
        sched: dict = {}
        if scheduled_after:
            sched["$gte"] = scheduled_after
        if scheduled_before:
            sched["$lte"] = scheduled_before
        v_match["scheduled_at"] = sched

    variants = await db.content_variants.find(
        v_match, {"_id": 0, "post_id": 1},
    ).to_list(length=2000)
    normalized_ids: set[str] = {v["post_id"] for v in variants if v.get("post_id")}

    # --- Step 2: lenient fallback — catch any un-mirrored stragglers ---
    # Always *count* the un-mirrored set so callers (and the drift health
    # endpoint) have visibility. Only include them in the returned ids when
    # strict mode is off.
    p_match: dict = {
        "user_id": user_id,
        "status": status,
        "$or": [
            {"content_item_id": {"$exists": False}},
            {"content_item_id": None},
        ],
    }
    if "scheduled_at" in v_match:
        p_match["scheduled_at"] = v_match["scheduled_at"]
    unmirrored = await db.posts.find(p_match, {"_id": 0, "id": 1}).to_list(length=2000)
    unmirrored_ids = {p["id"] for p in unmirrored}

    if unmirrored_ids and not strict_mode:
        logger.warning(
            "resolve_post_ids_for_status: %d un-mirrored posts for user=%s status=%s — "
            "lenient mode surfacing them; flip STRICT_NORMALIZED_READS once drift sustains zero",
            len(unmirrored_ids), user_id, status,
        )
    elif unmirrored_ids and strict_mode:
        logger.warning(
            "resolve_post_ids_for_status[STRICT]: HIDING %d un-mirrored posts for user=%s status=%s — "
            "re-run normalize migration to fix",
            len(unmirrored_ids), user_id, status,
        )

    final_ids = list(normalized_ids if strict_mode else (normalized_ids | unmirrored_ids))
    return final_ids, len(unmirrored_ids)


async def list_posts_via_normalized(
    user_id: str,
    *,
    limit: int = 10,
    strict: Optional[bool] = None,
) -> list[dict]:
    """Return the latest N posts for the user, resolved via the normalized
    `content_items` layer (the agent-readable source-of-truth for "what
    content does this brand own?"). Returns full legacy post documents so
    callers can keep their existing JSON shape.

    This is the "all-statuses, latest first" pattern used by the activity
    feed, admin recent_posts, and dashboard recent activity — distinct
    from `resolve_post_ids_for_status` which is filtered by a specific
    status + scheduled-at range.

    Lenient fallback (default) tops up the result with un-mirrored
    stragglers when fewer than `limit` mirrored posts exist. Strict mode
    omits the un-mirrored set entirely.
    """
    strict_mode = strict if strict is not None else STRICT_NORMALIZED_READS
    if limit <= 0:
        return []

    # Step 1: latest content_items for this user. Over-fetch slightly so
    # we still hit the limit when some content_items have been pruned.
    items = await db.content_items.find(
        {"user_id": user_id},
        {"_id": 0, "id": 1},
    ).sort("created_at", -1).limit(limit * 3).to_list(length=limit * 3)
    item_ids = [i["id"] for i in items]

    # Step 2: posts whose content_item_id is in that set. Use the legacy
    # row as the response shape (frontend depends on those fields).
    posts: list[dict] = []
    if item_ids:
        posts = await db.posts.find(
            {"user_id": user_id, "content_item_id": {"$in": item_ids}},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(length=limit)

    # Step 3 (lenient only): merge in un-mirrored stragglers so they aren't
    # silently dropped during the migration window. We re-sort the merged
    # list and truncate to `limit` so a newer un-mirrored post can still
    # bump an older mirrored one out of the result (a strictly-newer
    # straggler shouldn't disappear just because mirrored posts fill the
    # window).
    if not strict_mode:
        unmirrored = await db.posts.find(
            {"user_id": user_id,
             "$or": [{"content_item_id": {"$exists": False}}, {"content_item_id": None}]},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(length=limit)
        if unmirrored:
            logger.warning(
                "list_posts_via_normalized: merging %d un-mirrored posts for user=%s — "
                "flip STRICT_NORMALIZED_READS once drift sustains zero",
                len(unmirrored), user_id,
            )
            posts.extend(unmirrored)
            posts.sort(
                key=lambda p: p.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            posts = posts[:limit]

    return posts
