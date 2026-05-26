"""Background scheduler: promotes scheduled posts to published every 60s."""
import os
import socket
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core import db, app, logger

# Mongo-backed TTL lock so multiple uvicorn workers don't double-publish.
SCHEDULER_LOCK_NAME = "publish_scheduled_posts"
SCHEDULER_LOCK_TTL_SECONDS = 55  # job runs every 60s
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
scheduler: Optional[AsyncIOScheduler] = None


async def _acquire_scheduler_lock() -> bool:
    """Try to acquire a TTL-style mongo lock. Returns True if this worker holds it."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=SCHEDULER_LOCK_TTL_SECONDS)
    res = await db.scheduler_locks.find_one_and_update(
        {
            "_id": SCHEDULER_LOCK_NAME,
            "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}],
        },
        {"$set": {"worker": WORKER_ID, "expires_at": expires_at, "updated_at": now}},
        upsert=False,
    )
    if res:
        return True
    try:
        await db.scheduler_locks.insert_one(
            {"_id": SCHEDULER_LOCK_NAME, "worker": WORKER_ID, "expires_at": expires_at, "updated_at": now}
        )
        return True
    except Exception:
        return False


async def _publish_due_posts_now() -> dict:
    """Promote due scheduled posts to 'published'. Returns counts."""
    now = datetime.now(timezone.utc)
    due_cursor = db.posts.find({"status": "scheduled", "scheduled_at": {"$lte": now}})
    due = await due_cursor.to_list(length=200)
    if not due:
        return {"due": 0, "published": 0, "ids": []}
    ids = [p["id"] for p in due]
    result = await db.posts.update_many(
        {"id": {"$in": ids}, "status": "scheduled"},
        {"$set": {"status": "published", "published_at": now, "publish_mode": "scheduler"}},
    )

    # Dispatch to live platform APIs (currently: LinkedIn + TikTok).
    # Lazy import to avoid a circular dependency with route modules.
    try:
        from routes.oauth_linkedin import publish_to_linkedin
    except Exception:  # pragma: no cover
        publish_to_linkedin = None
    try:
        from routes.oauth_tiktok import publish_to_tiktok
    except Exception:  # pragma: no cover
        publish_to_tiktok = None
    try:
        from routes.oauth_pinterest import publish_to_pinterest
    except Exception:  # pragma: no cover
        publish_to_pinterest = None

    for post in due:
        platforms = post.get("platforms") or []
        if "linkedin" in platforms and publish_to_linkedin:
            res = await publish_to_linkedin(post["user_id"], post["content"])
            await db.posts.update_one(
                {"id": post["id"]},
                {"$set": {"dispatch.linkedin": res}},
            )
            if not res.get("ok"):
                logger.warning("scheduler: linkedin dispatch failed for %s: %s", post["id"], res.get("reason"))
        if "tiktok" in platforms and publish_to_tiktok:
            res = await publish_to_tiktok(post["user_id"], post["content"], post.get("media_url"))
            await db.posts.update_one(
                {"id": post["id"]},
                {"$set": {"dispatch.tiktok": res}},
            )
            if not res.get("ok"):
                logger.warning("scheduler: tiktok dispatch failed for %s: %s", post["id"], res.get("reason"))
        if "pinterest" in platforms and publish_to_pinterest:
            res = await publish_to_pinterest(
                post["user_id"], post["content"],
                image_url=post.get("media_url") or post.get("pinterest_image_url"),
                images=post.get("pinterest_images"),
                board_id=post.get("pinterest_board_id"),
                link=post.get("pinterest_link"),
                title=post.get("pinterest_title"),
            )
            await db.posts.update_one(
                {"id": post["id"]},
                {"$set": {"dispatch.pinterest": res}},
            )
            if not res.get("ok"):
                logger.warning("scheduler: pinterest dispatch failed for %s: %s", post["id"], res.get("reason"))

    return {"due": len(due), "published": result.modified_count, "ids": ids}


async def publish_due_scheduled_posts():
    """Background job: acquire lock and publish due scheduled posts."""
    try:
        if not await _acquire_scheduler_lock():
            return  # another worker is handling this tick
        result = await _publish_due_posts_now()
        if result["published"]:
            logger.info(
                "scheduler: published %s due posts (worker=%s, ids=%s)",
                result["published"], WORKER_ID, result["ids"][:10],
            )
    except Exception:
        logger.exception("scheduler: publish_due_scheduled_posts failed")


@app.on_event("startup")
async def start_scheduler():
    global scheduler
    if os.environ.get("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        logger.info("scheduler: disabled via DISABLE_SCHEDULER env")
        return
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        publish_due_scheduled_posts,
        trigger=IntervalTrigger(seconds=60),
        id="publish_scheduled_posts",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )

    # Per-post analytics refresh — every 6h. Lazy import so the module isn't
    # required at scheduler boot time (and to avoid a circular import).
    try:
        from routes.analytics import refresh_post_metrics
        scheduler.add_job(
            refresh_post_metrics,
            trigger=IntervalTrigger(hours=6),
            id="refresh_post_metrics",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
    except Exception:
        logger.exception("scheduler: failed to register refresh_post_metrics")

    scheduler.start()
    logger.info("scheduler: started (worker=%s, every 60s)", WORKER_ID)


@app.on_event("shutdown")
async def stop_scheduler():
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
