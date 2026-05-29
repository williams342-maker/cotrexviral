"""Human-in-the-loop approval workflow.

AI prepares → human approves → scheduler dispatches. This is the trust
layer that lets users enable autonomous scheduling without worrying
about a runaway post.

User toggle (default OFF): `users.require_post_approval: bool`. When ON:
  • Every NEW scheduled post is created with status="pending_approval"
    instead of "scheduled" — the existing background dispatcher already
    only picks up status=="scheduled", so pending posts simply wait.
  • The user reviews them at /dashboard/approvals.
  • Approve flips status to "scheduled". Reject sets "rejected".

Endpoints:
  GET    /api/approvals               — list pending posts for the user
  POST   /api/approvals/{post_id}/approve
  POST   /api/approvals/{post_id}/reject  body {reason?: str}
  GET    /api/approvals/settings      — {require_post_approval}
  PUT    /api/approvals/settings      body {require_post_approval}
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import db, api, logger
from deps import get_current_user
from routes.content_layer import propagate_status_to_variants


class _SettingsPayload(BaseModel):
    require_post_approval: bool


class _RejectPayload(BaseModel):
    reason: Optional[str] = None


@api.get("/approvals/settings")
async def get_settings(request: Request):
    """Returns the user's approval-workflow preference."""
    user = await get_current_user(request)
    doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "require_post_approval": 1},
    ) or {}
    return {"require_post_approval": bool(doc.get("require_post_approval", False))}


@api.put("/approvals/settings")
async def set_settings(payload: _SettingsPayload, request: Request):
    user = await get_current_user(request)
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "require_post_approval": bool(payload.require_post_approval),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"ok": True, "require_post_approval": payload.require_post_approval}


@api.get("/approvals")
async def list_pending(request: Request):
    """Pending posts for the caller, newest first."""
    user = await get_current_user(request)
    cursor = db.posts.find(
        {"user_id": user.user_id, "status": "pending_approval"},
        {"_id": 0},
    ).sort("scheduled_at", 1).limit(200)
    items = await cursor.to_list(length=200)
    return {"pending": items, "count": len(items)}


@api.post("/approvals/{post_id}/approve")
async def approve_post(post_id: str, request: Request):
    """Flip a pending post to 'scheduled' so the dispatcher picks it up on
    the next tick. The post's existing `scheduled_at` is preserved."""
    user = await get_current_user(request)
    res = await db.posts.update_one(
        {"id": post_id, "user_id": user.user_id, "status": "pending_approval"},
        {"$set": {
            "status": "scheduled",
            "approved_at": datetime.now(timezone.utc),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pending post not found")
    await propagate_status_to_variants(post_id, status="scheduled")
    logger.info("Post %s approved by user %s", post_id, user.user_id)
    return {"ok": True}


@api.post("/approvals/{post_id}/reject")
async def reject_post(post_id: str, payload: _RejectPayload, request: Request):
    """Mark a pending post as rejected. Preserved in the DB so the user can
    review historical decisions; the dispatcher will never touch it again."""
    user = await get_current_user(request)
    res = await db.posts.update_one(
        {"id": post_id, "user_id": user.user_id, "status": "pending_approval"},
        {"$set": {
            "status": "rejected",
            "rejected_at": datetime.now(timezone.utc),
            "rejection_reason": (payload.reason or "")[:500] or None,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pending post not found")
    await propagate_status_to_variants(post_id, status="rejected")
    logger.info("Post %s rejected by user %s", post_id, user.user_id)
    return {"ok": True}
