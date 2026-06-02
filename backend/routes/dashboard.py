"""Dashboard summary endpoint (stats + recent activity for /dashboard overview)."""

from typing import List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import db, api, STRICT_NORMALIZED_READS
from deps import get_current_user


@api.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    """Headline counters for the dashboard overview. Phase 4 reads `posts`
    via the normalized `content_items` layer (one row per platform-agnostic
    intent — the agent-readable source-of-truth). In lenient mode we top
    up with any un-mirrored straggler posts so the number stays
    semantically equivalent to the pre-Phase-4 count during the
    migration window."""
    user = await get_current_user(request)

    posts_count = await db.content_items.count_documents({"user_id": user.user_id})
    if not STRICT_NORMALIZED_READS:
        unmirrored = await db.posts.count_documents({
            "user_id": user.user_id,
            "$or": [{"content_item_id": {"$exists": False}}, {"content_item_id": None}],
        })
        posts_count += unmirrored

    reports_count = await db.reports.count_documents({"user_id": user.user_id})
    channels_count = await db.channels.count_documents({"user_id": user.user_id})
    leads_count = await db.leads.count_documents({"user_id": user.user_id})
    return {
        "posts": posts_count,
        "reports": reports_count,
        "channels": channels_count,
        "leads": leads_count,
    }


@api.get("/reports")
async def list_reports(request: Request):
    user = await get_current_user(request)
    cursor = db.reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(50)


@api.delete("/reports/{report_id}")
async def delete_report(report_id: str, request: Request):
    """Hard-delete a report owned by the current user. Used by the
    Reports page card close (X) button so users can dismiss noisy or
    failed scans from their list."""
    user = await get_current_user(request)
    result = await db.reports.delete_one(
        {"id": report_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Report not found.")
    return {"ok": True, "id": report_id}


class BulkDeleteReportsPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)


@api.post("/reports/bulk-delete")
async def bulk_delete_reports(payload: BulkDeleteReportsPayload, request: Request):
    """Bulk-delete reports owned by the current user. Always scoped to
    the caller's user_id so a malicious client can't wipe other users'
    rows even with a spoofed id list."""
    user = await get_current_user(request)
    ids = [i for i in (payload.ids or []) if isinstance(i, str) and i.strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    # Cap the batch so a runaway client can't issue a huge delete in one shot.
    ids = ids[:500]
    result = await db.reports.delete_many(
        {"id": {"$in": ids}, "user_id": user.user_id})
    return {"ok": True, "deleted": int(result.deleted_count), "requested": len(ids)}
