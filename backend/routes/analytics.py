"""Per-post analytics — fetch fresh metrics from the platform APIs and
expose them on `/api/posts/metrics`.

Current platform coverage:
  • Pinterest   — LIVE (uses /v5/pins/{pin_id}/analytics)
  • TikTok      — TODO (Content Posting API insights, requires Standard access)
  • LinkedIn    — TODO (/rest/socialActions/{share-urn} endpoint)
  • Meta FB/IG  — TODO (/{post-id}/insights endpoint)

Storage:
  Metrics live INLINE on the post doc under `metrics.{platform}` for fast
  reads, with `metrics.{platform}.fetched_at` for staleness checks. A
  background job (refresh_post_metrics) runs every 6h and refreshes any
  post whose latest snapshot is > 6h old AND whose dispatch happened in
  the last 30 days (Pinterest's analytics horizon).

Endpoints:
  GET  /api/posts/metrics?post_id=...     → metrics for a single post
  POST /api/posts/metrics/refresh         → on-demand refresh for the caller's
                                            recent posts (Pro+ feature gating
                                            handled by plan limits via posts).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from core import db, api
from deps import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-platform fetchers
# ---------------------------------------------------------------------------
async def _fetch_for_post(post: dict) -> dict:
    """Returns a fresh `metrics.{platform}` payload for every platform on
    `post` that has a successful dispatch. Skips platforms we don't yet have
    analytics for. Updates are merged with whatever already exists on the
    post so older snapshots survive failed refreshes."""
    out: dict = {}
    dispatch = post.get("dispatch") or {}

    # Pinterest — LIVE
    pin_dispatch = dispatch.get("pinterest") or {}
    pin_id = pin_dispatch.get("pin_id")
    if pin_id and pin_dispatch.get("ok"):
        try:
            from routes.oauth_pinterest import fetch_pinterest_pin_metrics
            data = await fetch_pinterest_pin_metrics(post["user_id"], pin_id)
            if data:
                out["pinterest"] = data
        except Exception:
            logger.exception("Failed Pinterest analytics fetch for post %s", post.get("id"))

    # LinkedIn — share URN → likes + comments
    li_dispatch = dispatch.get("linkedin") or {}
    li_urn = li_dispatch.get("linkedin_post_id")
    if li_urn and li_dispatch.get("ok"):
        try:
            from routes.oauth_linkedin import fetch_linkedin_post_metrics
            data = await fetch_linkedin_post_metrics(post["user_id"], li_urn)
            if data:
                out["linkedin"] = data
        except Exception:
            logger.exception("Failed LinkedIn analytics fetch for post %s", post.get("id"))

    # Facebook — page-post insights
    fb_dispatch = dispatch.get("facebook") or {}
    fb_post_id = fb_dispatch.get("post_id")
    if fb_post_id and fb_dispatch.get("ok"):
        try:
            from routes.oauth_meta import fetch_facebook_post_metrics
            data = await fetch_facebook_post_metrics(post["user_id"], fb_post_id)
            if data:
                out["facebook"] = data
        except Exception:
            logger.exception("Failed Facebook analytics fetch for post %s", post.get("id"))

    # Instagram — media insights
    ig_dispatch = dispatch.get("instagram") or {}
    ig_media_id = ig_dispatch.get("post_id")
    if ig_media_id and ig_dispatch.get("ok"):
        try:
            from routes.oauth_meta import fetch_instagram_post_metrics
            data = await fetch_instagram_post_metrics(post["user_id"], ig_media_id)
            if data:
                out["instagram"] = data
        except Exception:
            logger.exception("Failed Instagram analytics fetch for post %s", post.get("id"))

    # TikTok — video stats (publish_id may need resolving to video_id)
    tt_dispatch = dispatch.get("tiktok") or {}
    tt_publish_id = tt_dispatch.get("tiktok_publish_id")
    tt_video_id = tt_dispatch.get("tiktok_video_id")
    if (tt_publish_id or tt_video_id) and tt_dispatch.get("ok"):
        try:
            from routes.oauth_tiktok import fetch_tiktok_post_metrics
            data = await fetch_tiktok_post_metrics(
                post["user_id"],
                publish_id=tt_publish_id,
                video_id=tt_video_id,
            )
            if data:
                out["tiktok"] = data
        except Exception:
            logger.exception("Failed TikTok analytics fetch for post %s", post.get("id"))

    return out


async def _refresh_post(post: dict) -> dict | None:
    metrics = await _fetch_for_post(post)
    if not metrics:
        return None
    update = {f"metrics.{plat}": data for plat, data in metrics.items()}
    update["metrics.last_refreshed_at"] = datetime.now(timezone.utc)
    await db.posts.update_one({"id": post["id"]}, {"$set": update})
    return metrics


# ---------------------------------------------------------------------------
# Background job (registered from server.py scheduler bootstrap)
# ---------------------------------------------------------------------------
async def refresh_post_metrics():
    """Scheduled every 6h. Refreshes analytics for posts that:
      • Were successfully dispatched at least once
      • Are < 30 days old (Pinterest/Meta analytics horizon)
      • Haven't been refreshed in the last 6h
    Bounded at 200 posts per tick so a backlog never blocks the loop."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    cursor = db.posts.find(
        {
            "dispatch": {"$exists": True},
            "status": "published",
            "created_at": {"$gte": cutoff},
            "$or": [
                {"metrics.last_refreshed_at": {"$exists": False}},
                {"metrics.last_refreshed_at": {"$lt": stale}},
            ],
        },
        {"_id": 0},
    ).limit(200)
    refreshed = 0
    async for post in cursor:
        res = await _refresh_post(post)
        if res:
            refreshed += 1
    if refreshed:
        logger.info("Analytics refresh: %s post(s) updated", refreshed)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@api.get("/posts/metrics")
async def get_post_metrics(post_id: str, request: Request):
    """Return cached metrics for a single post owned by the caller."""
    user = await get_current_user(request)
    post = await db.posts.find_one(
        {"id": post_id, "user_id": user.user_id},
        {"_id": 0, "metrics": 1, "dispatch": 1, "id": 1, "platforms": 1},
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return {
        "post_id": post_id,
        "metrics": post.get("metrics") or {},
        "platforms": post.get("platforms") or [],
    }


@api.post("/posts/metrics/refresh")
async def refresh_my_post_metrics(request: Request):
    """On-demand refresh for the caller's last 25 published posts. Useful
    for the Posts page "Refresh metrics" button so users don't have to wait
    on the 6h cron tick."""
    user = await get_current_user(request)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    cursor = db.posts.find(
        {
            "user_id": user.user_id,
            "dispatch": {"$exists": True},
            "status": "published",
            "created_at": {"$gte": cutoff},
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(25)
    refreshed = 0
    async for post in cursor:
        res = await _refresh_post(post)
        if res:
            refreshed += 1
    return {"ok": True, "refreshed": refreshed}
