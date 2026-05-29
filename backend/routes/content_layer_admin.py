"""Phase 3 — content layer drift / health observability.

The Phase 2 writer migration is best-effort: a mirror failure logs but
never blocks the write. To detect drift before it becomes a problem,
this endpoint surfaces the counts of un-mirrored posts (posts that
lack a `content_item_id` cross-ref) alongside the normalized totals.

Admins watch the count trend toward zero before we cut over reads to
strict-normalized in Phase 4 (drops the lenient fallback).

Surfaced on the admin overview next to the memory-perf callout.
"""
from fastapi import Request

from core import api, db, STRICT_NORMALIZED_READS
from deps import require_admin


@api.get("/admin/content-layer/health")
async def content_layer_health(request: Request):
    """Counts un-mirrored posts vs. the total. Lower is better.

    Returned shape:
      {
        "total_posts": int,
        "mirrored_posts": int,
        "unmirrored_posts": int,
        "mirror_coverage_pct": float,       # 0..100
        "total_content_items": int,
        "total_content_variants": int,
        "unmirrored_by_status": {"pending_approval": 2, "scheduled": 1, …},
        "drift_threshold": 5,
        "drift_triggered": bool,
      }
    """
    await require_admin(request)

    total_posts = await db.posts.count_documents({})
    unmirrored_match = {
        "$or": [
            {"content_item_id": {"$exists": False}},
            {"content_item_id": None},
        ],
    }
    unmirrored = await db.posts.count_documents(unmirrored_match)
    mirrored = total_posts - unmirrored
    coverage_pct = round((mirrored / total_posts * 100), 2) if total_posts else 100.0

    total_items = await db.content_items.count_documents({})
    total_variants = await db.content_variants.count_documents({})

    # Break down un-mirrored by status (helps prioritize backfill).
    status_pipeline = [
        {"$match": unmirrored_match},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    by_status_cursor = db.posts.aggregate(status_pipeline)
    by_status = {doc["_id"] or "unknown": doc["n"] async for doc in by_status_cursor}

    DRIFT_THRESHOLD = 5  # un-mirrored posts that should trigger admin attention
    return {
        "total_posts":           total_posts,
        "mirrored_posts":        mirrored,
        "unmirrored_posts":      unmirrored,
        "mirror_coverage_pct":   coverage_pct,
        "total_content_items":   total_items,
        "total_content_variants": total_variants,
        "unmirrored_by_status":  by_status,
        "drift_threshold":       DRIFT_THRESHOLD,
        "drift_triggered":       unmirrored >= DRIFT_THRESHOLD,
        "strict_mode":           STRICT_NORMALIZED_READS,
    }
