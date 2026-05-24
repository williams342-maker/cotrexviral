"""Health endpoints."""
from fastapi import Request

from core import db, api
from deps import require_admin
from routes.scheduler import _publish_due_posts_now, WORKER_ID


@api.get("/")
async def root():
    return {"app": "Automatex", "status": "ok"}


@api.post("/admin/scheduler/run-once")
async def admin_scheduler_run_once(request: Request):
    """Admin debug: manually trigger the publish-due job once (bypasses scheduler lock)."""
    await require_admin(request)
    before = await db.posts.count_documents({"status": "scheduled"})
    result = await _publish_due_posts_now()
    after_scheduled = await db.posts.count_documents({"status": "scheduled"})
    return {
        "ok": True,
        "worker": WORKER_ID,
        "scheduled_before": before,
        "due_at_run": result["due"],
        "published_now": result["published"],
        "scheduled_after": after_scheduled,
        "ids": result["ids"][:20],
    }
