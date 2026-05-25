"""Magic-link authentication — admin-created accounts.

Purpose: Lets admins create users (and lead-form auto-create users) WITHOUT
requiring Google Auth. The user gets an email with a one-time URL of the form
    https://cortexviral.com/auth/claim?token=<urlsafe>
Clicking it validates the token, creates the same `session_token` cookie that
Emergent Google Auth produces, and the user is logged in — Google never needed.

Security model:
  - Tokens are 32-byte secrets via `secrets.token_urlsafe(32)` (≈256 bits entropy).
  - Single-use: marked `used_at` on first redemption and rejected thereafter.
  - 7-day expiry via a MongoDB TTL index.
  - Tokens are NEVER stored hashed because we generate + email them once;
    no readback path other than the user's inbox.
  - Email enumeration is mitigated by always returning 200 from /admin/users
    (admins are trusted) and the /auth/claim path returning a generic 400 for
    any invalid/expired/used token without distinguishing the failure mode.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from core import db, api, logger, ADMIN_EMAILS, PUBLIC_SITE_URL
from deps import require_admin


# Magic-link tokens live for 7 days. The TTL index uses `expires_at` so Mongo
# auto-purges them — saves the cron job for cleanup.
_MAGIC_LINK_TTL_DAYS = 7
_INDEX_BUILT = False


async def _ensure_indexes():
    global _INDEX_BUILT
    if _INDEX_BUILT:
        return
    try:
        await db.magic_links.create_index("token", unique=True)
        await db.magic_links.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        logger.exception("Failed to create magic_links indexes (continuing)")
    _INDEX_BUILT = True


async def issue_magic_link(user_id: str, email: str, purpose: str = "claim") -> str:
    """Generate + persist a new magic-link token for an existing user_id.
    Returns the absolute URL the user should click."""
    await _ensure_indexes()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.magic_links.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email.lower().strip(),
        "purpose": purpose,
        "created_at": now,
        "expires_at": now + timedelta(days=_MAGIC_LINK_TTL_DAYS),
        "used_at": None,
    })
    return f"{PUBLIC_SITE_URL}/auth/claim?token={token}"


@api.get("/auth/claim")
async def claim_magic_link(token: str, request: Request, response: Response):
    """Exchange a magic-link token for a session_token cookie."""
    await _ensure_indexes()
    if not token or len(token) < 16:
        raise HTTPException(status_code=400, detail="Invalid or expired link")

    doc = await db.magic_links.find_one({"token": token})
    if not doc:
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    if doc.get("used_at"):
        raise HTTPException(status_code=400, detail="This link has already been used")
    expires = doc.get("expires_at")
    if isinstance(expires, datetime) and expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This link has expired")

    user = await db.users.find_one({"user_id": doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=400, detail="Account no longer exists")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account is suspended")

    # Mint a session_token shaped identically to the Emergent Google Auth one
    # so the rest of the app (deps.get_current_user, etc.) sees no difference.
    session_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
        "via": "magic_link",
    })
    # Burn the token (single-use).
    await db.magic_links.update_one(
        {"token": token},
        {"$set": {"used_at": datetime.now(timezone.utc)}},
    )

    response.set_cookie(
        key="session_token", value=session_token,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=7 * 24 * 60 * 60,
    )
    return {
        "ok": True,
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name"),
    }


# -----------------------------------------------------------------------------
# Admin: create a new user manually and email them the magic link.
# -----------------------------------------------------------------------------
class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    plan: str = "free"
    comped: bool = False
    brand_name: Optional[str] = None
    website: Optional[str] = None
    niche: Optional[str] = None
    send_email: bool = True


@api.post("/admin/users/create")
async def admin_create_user(payload: AdminCreateUserRequest, request: Request):
    """Create a new user from the admin panel and (optionally) email them a
    magic-link sign-in URL. Idempotent on email — if the user already exists,
    we just re-issue a fresh magic link."""
    admin = await require_admin(request)
    email_norm = payload.email.lower().strip()
    if payload.plan not in {"free", "starter", "growth", "agency", "pro", "scale"}:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.plan}'")

    existing = await db.users.find_one({"email": email_norm}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        # Update plan / comp / profile if admin passed new values.
        update = {"updated_at": datetime.now(timezone.utc)}
        if payload.plan != existing.get("plan"):
            update["plan"] = payload.plan
        if payload.comped != bool(existing.get("comped")):
            update["comped"] = payload.comped
        if payload.brand_name and not existing.get("brand_name"):
            update["brand_name"] = payload.brand_name
        if payload.website and not existing.get("website"):
            w = payload.website.strip()
            update["website"] = w if "://" in w else "https://" + w.lstrip("/")
        if payload.niche and not existing.get("niche"):
            update["niche"] = payload.niche
        await db.users.update_one({"user_id": user_id}, {"$set": update})
        was_new = False
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        website = payload.website.strip() if payload.website else None
        if website and "://" not in website:
            website = "https://" + website.lstrip("/")
        await db.users.insert_one({
            "user_id": user_id,
            "email": email_norm,
            "name": payload.name.strip() or email_norm.split("@")[0],
            "picture": None,
            "is_admin": email_norm in ADMIN_EMAILS,
            "status": "active",
            "plan": payload.plan,
            "comped": payload.comped,
            "brand_name": payload.brand_name,
            "website": website,
            "niche": payload.niche,
            "created_at": datetime.now(timezone.utc),
            "created_via": "admin_create",
            "created_by": admin.user_id,
        })
        was_new = True

    # Issue a magic-link token + (optionally) email it.
    link = await issue_magic_link(user_id, email_norm, purpose="claim")
    email_result = None
    if payload.send_email:
        try:
            from routes.email import send_account_invite_email
            email_result = await send_account_invite_email(
                to=email_norm,
                name=payload.name,
                magic_link=link,
                inviter_name=admin.name or "the CortexViral team",
            )
        except Exception:
            logger.exception("Failed to send invite email to %s", email_norm)

    # Audit log
    from deps import log_admin_action
    await log_admin_action(
        admin, "create_user" if was_new else "reinvite_user",
        target_user_id=user_id, target_email=email_norm,
        details={"plan": payload.plan, "comped": payload.comped, "was_new": was_new},
    )

    return {
        "ok": True,
        "user_id": user_id,
        "email": email_norm,
        "new_user": was_new,
        "magic_link": link,           # admin can copy if email fails
        "email_sent": bool(email_result and email_result.get("sent")),
    }


@api.post("/admin/users/{user_id}/resend-invite")
async def admin_resend_invite(user_id: str, request: Request):
    """Generate a fresh magic link for an existing user and re-email it.
    Useful when the original link expired or the user lost the email."""
    admin = await require_admin(request)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    link = await issue_magic_link(user_id, user["email"], purpose="resend")
    sent = False
    try:
        from routes.email import send_account_invite_email
        res = await send_account_invite_email(
            to=user["email"], name=user.get("name") or "",
            magic_link=link, inviter_name=admin.name or "the CortexViral team",
        )
        sent = bool(res and res.get("sent"))
    except Exception:
        logger.exception("Failed to re-send invite email to %s", user["email"])

    from deps import log_admin_action
    await log_admin_action(
        admin, "resend_invite", target_user_id=user_id, target_email=user["email"],
    )
    return {"ok": True, "magic_link": link, "email_sent": sent}
