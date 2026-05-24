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
    # TODO once OAuth lands: dispatch to live platform APIs for each post in `due`.
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
    scheduler.start()
    logger.info("scheduler: started (worker=%s, every 60s)", WORKER_ID)


@app.on_event("shutdown")
async def stop_scheduler():
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
