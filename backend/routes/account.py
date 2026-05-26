"""User self-serve account deletion, session management, and pause.

Privacy / GDPR / Meta-app-review requirement: a clear, one-click way for a
user to permanently delete their account and all associated data. This route
performs the same cascade as `admin_delete_user` but is callable by the
authenticated user against THEIR OWN account only.

We require a confirmation phrase in the request body to prevent accidental
self-deletes (e.g. a misclick or CSRF replay).

Also exposes:
  • GET  /account/sessions          — list active sessions for the user
  • POST /account/sessions/revoke-others — sign out everywhere except current
  • POST /account/sessions/revoke-all    — sign out everywhere including current
  • POST /account/pause             — soft-delete (status=paused, sessions cleared)
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


# ---------------------------------------------------------------------------
# Session management (sign out everywhere)
# ---------------------------------------------------------------------------
@api.get("/account/sessions")
async def list_my_sessions(request: Request):
    """Returns the count of active sessions for the calling user, plus the
    current session's created/expires timestamps so the UI can show the user
    when they last signed in."""
    user = await get_current_user(request)
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    total = await db.user_sessions.count_documents({"user_id": user.user_id})
    current = None
    if token:
        doc = await db.user_sessions.find_one(
            {"session_token": token, "user_id": user.user_id},
            {"_id": 0, "created_at": 1, "expires_at": 1},
        )
        if doc:
            current = {
                "created_at": doc.get("created_at"),
                "expires_at": doc.get("expires_at"),
            }
    return {"total": total, "others": max(0, total - 1), "current": current}


@api.post("/account/sessions/revoke-others")
async def revoke_other_sessions(request: Request):
    """Sign the user out of every device EXCEPT the one making this call.
    Useful after a stolen-laptop scare or after a password change."""
    user = await get_current_user(request)
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    query = {"user_id": user.user_id}
    if token:
        query["session_token"] = {"$ne": token}
    result = await db.user_sessions.delete_many(query)
    logger.info("Revoke-others: user=%s deleted=%s", user.user_id, result.deleted_count)
    return {"ok": True, "revoked": result.deleted_count}


@api.post("/account/sessions/revoke-all")
async def revoke_all_sessions(request: Request, response: Response):
    """Sign the user out everywhere INCLUDING the current device. The SPA
    should redirect to the marketing page after this returns."""
    user = await get_current_user(request)
    result = await db.user_sessions.delete_many({"user_id": user.user_id})
    response.delete_cookie(key="session_token", path="/")
    logger.info("Revoke-all: user=%s deleted=%s", user.user_id, result.deleted_count)
    return {"ok": True, "revoked": result.deleted_count}


# ---------------------------------------------------------------------------
# Pause account (soft-delete) — preserves all data, blocks access until the
# user signs in again. The act of signing in is what reactivates the account.
# ---------------------------------------------------------------------------
class _PauseRequest(BaseModel):
    reason: str | None = None


@api.post("/account/pause")
async def pause_my_account(
    payload: _PauseRequest, request: Request, response: Response,
):
    """Soft-delete: mark the user `status=paused`, clear every session.

    The user's data (posts, scheduled content, channels, OAuth tokens) is
    fully preserved. On their next sign-in (Google or password), the auth
    routes detect the paused status and auto-reactivate the account.
    """
    user = await get_current_user(request)
    uid = user.user_id

    await db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "status": "paused",
            "paused_at": datetime.now(timezone.utc),
            "pause_reason": (payload.reason or "")[:500],
        }},
    )
    await db.user_sessions.delete_many({"user_id": uid})

    logger.info("Account paused: %s (%s) reason=%r",
                user.email, uid, (payload.reason or "")[:120])

    # Notify the user how to come back — fire-and-forget.
    try:
        from routes.email import send_account_paused_email, fire
        fire(send_account_paused_email(to=user.email, name=user.name or ""))
    except Exception:
        logger.exception("Failed to schedule account-paused email")

    response.delete_cookie(key="session_token", path="/")
    return {"ok": True, "paused_user_id": uid}
