"""User self-serve account deletion.

Privacy / GDPR / Meta-app-review requirement: a clear, one-click way for a
user to permanently delete their account and all associated data. This route
performs the same cascade as `admin_delete_user` but is callable by the
authenticated user against THEIR OWN account only.

We require a confirmation phrase in the request body to prevent accidental
self-deletes (e.g. a misclick or CSRF replay).
"""
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from core import db, api, logger
from deps import get_current_user


_REQUIRED_CONFIRMATION = "DELETE MY ACCOUNT"


class _AccountDeleteRequest(BaseModel):
    confirmation: str
    reason: str | None = None  # optional, just for product feedback


@api.post("/account/delete")
async def delete_my_account(
    payload: _AccountDeleteRequest, request: Request, response: Response,
):
    """Permanently delete the calling user's account + all associated data.

    The user MUST pass `confirmation: "DELETE MY ACCOUNT"` exactly (case-
    sensitive) — this is a destructive irreversible operation.
    """
    user = await get_current_user(request)
    if payload.confirmation != _REQUIRED_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=f'Confirmation phrase must be exactly "{_REQUIRED_CONFIRMATION}"',
        )

    uid = user.user_id
    logger.info("Self-serve account delete: %s (%s) reason=%r",
                user.email, uid, (payload.reason or "")[:120])

    # Record the deletion request for compliance audit (kept indefinitely).
    await db.account_deletions.insert_one({
        "user_id": uid,
        "email": user.email,
        "name": user.name,
        "reason": (payload.reason or "")[:500],
        "deleted_at": datetime.now(timezone.utc),
        "via": "self_serve",
    })

    # Cascade: same set as admin_delete_user, plus a few CortexViral-specific
    # collections that the admin path predates.
    await db.users.delete_one({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.leads.delete_many({"user_id": uid})
    await db.posts.delete_many({"user_id": uid})
    await db.reports.delete_many({"user_id": uid})
    await db.channels.delete_many({"user_id": uid})
    await db.tickets.delete_many({"user_id": uid})
    await db.ticket_messages.delete_many({"author_id": uid})
    await db.linkedin_connections.delete_many({"user_id": uid})
    await db.tiktok_connections.delete_many({"user_id": uid})
    await db.magic_links.delete_many({"user_id": uid})
    await db.pageviews.delete_many({"user_id": uid})

    # Clear the session cookie so the SPA sees a clean logged-out state.
    response.delete_cookie(key="session_token", path="/")
    return {"ok": True, "deleted_user_id": uid}
