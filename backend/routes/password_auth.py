"""Email + password authentication.

Adapts the standard bcrypt + login flow to issue the SAME `session_token`
cookie shape Emergent Google Auth produces — so the rest of the app
(deps.get_current_user, ProtectedRoute, etc.) treats password users
indistinguishably from Google users.

Key endpoints:
  POST /api/auth/password/login           — email + password → session cookie
  POST /api/auth/password/request-reset   — anonymous, sends a fresh temp pw
  POST /api/auth/password/set-initial     — authenticated, first-login forced change
  POST /api/auth/password/change          — authenticated, old + new

Generated temp passwords:
  • 12 chars, alphanumeric (no ambiguous 0/O/1/l)
  • Stored as bcrypt hash on the user doc
  • `must_change_password=True` so the SPA forces a change on first login

Brute-force protection:
  • Mongo `login_attempts` collection keyed by `"ip:email"`
  • 5 failed attempts → 15-min lockout
  • Cleared on successful login
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core import db, api, logger
from deps import get_current_user


# --- helpers ----------------------------------------------------------------

# Unambiguous alphanumeric (no 0/O, 1/l/I).
_TEMP_PW_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


def generate_temp_password(length: int = 12) -> str:
    """12-char temp password the user can read off a screen or email."""
    return "".join(secrets.choice(_TEMP_PW_ALPHABET) for _ in range(length))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keying."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _is_locked_out(ip: str, email: str) -> bool:
    """Returns True if this ip:email pair has too many recent failed attempts."""
    cutoff = datetime.now(timezone.utc) - LOCKOUT_WINDOW
    count = await db.login_attempts.count_documents({
        "identifier": f"{ip}:{email}",
        "ts": {"$gte": cutoff},
    })
    return count >= LOCKOUT_THRESHOLD


async def _record_failed_attempt(ip: str, email: str):
    await db.login_attempts.insert_one({
        "identifier": f"{ip}:{email}",
        "ts": datetime.now(timezone.utc),
    })


async def _clear_attempts(ip: str, email: str):
    await db.login_attempts.delete_many({"identifier": f"{ip}:{email}"})


async def _set_user_password(user_id: str, new_plain: str, *,
                             require_change_on_next_login: bool = False):
    """Sets the user's password hash + clears any pending must_change flag
    (unless explicitly requested)."""
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "password_hash": hash_password(new_plain),
            "must_change_password": bool(require_change_on_next_login),
            "password_updated_at": datetime.now(timezone.utc),
        }},
    )


async def issue_password_session(user_id: str, response: Response) -> str:
    """Mint a session_token + set the cookie. Mirrors what
    routes.magic_link.exchange_magic_link does so the rest of the app
    doesn't care which auth path the user came from."""
    session_token = uuid.uuid4().hex + uuid.uuid4().hex  # 64 char
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    return session_token


# --- public endpoints --------------------------------------------------------

class _LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@api.post("/auth/password/login")
async def password_login(payload: _LoginRequest, request: Request, response: Response):
    email = payload.email.lower().strip()
    ip = _client_ip(request)

    if await _is_locked_out(ip, email):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again in 15 minutes.",
        )

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        # We deliberately return the same generic 401 whether the email exists
        # or not — prevents enumeration of registered users.
        await _record_failed_attempt(ip, email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account is suspended")

    if not verify_password(payload.password, user["password_hash"]):
        await _record_failed_attempt(ip, email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Success
    await _clear_attempts(ip, email)
    await issue_password_session(user["user_id"], response)
    return {
        "ok": True,
        "user_id": user["user_id"],
        "email": email,
        "name": user.get("name"),
        "must_change_password": bool(user.get("must_change_password")),
    }


class _RequestResetPayload(BaseModel):
    email: EmailStr


@api.post("/auth/password/request-reset")
async def password_request_reset(payload: _RequestResetPayload, request: Request):
    """Anonymous password-reset request. Always returns 200 to prevent email
    enumeration. If the email exists, we generate a fresh temp password,
    hash + store it, mark `must_change_password=True`, and email the plaintext."""
    email = payload.email.lower().strip()
    ip = _client_ip(request)
    # Light rate limit on the reset endpoint itself (10 / 15 min / IP).
    cutoff = datetime.now(timezone.utc) - LOCKOUT_WINDOW
    reset_attempts = await db.login_attempts.count_documents({
        "identifier": f"reset:{ip}",
        "ts": {"$gte": cutoff},
    })
    if reset_attempts >= 10:
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again later.")
    await db.login_attempts.insert_one({
        "identifier": f"reset:{ip}",
        "ts": datetime.now(timezone.utc),
    })

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user and user.get("status") != "suspended":
        temp_pw = generate_temp_password()
        await _set_user_password(user["user_id"], temp_pw, require_change_on_next_login=True)
        try:
            from routes.email import send_temp_password_email, fire
            fire(send_temp_password_email(
                to=email,
                name=user.get("name") or email.split("@")[0],
                temp_password=temp_pw,
                reason="reset",
            ))
        except Exception:
            logger.exception("Failed to send temp-password email (password still rotated)")
    # Always 200 — no enumeration leak.
    return {"ok": True, "message": "If the email is registered, a temporary password has been sent."}


class _SetInitialPayload(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@api.post("/auth/password/set-initial")
async def password_set_initial(payload: _SetInitialPayload, request: Request):
    """First-login forced password change. Authenticated (the user already
    signed in with their temp password). Clears must_change_password."""
    user = await get_current_user(request)
    full = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not full or not full.get("must_change_password"):
        raise HTTPException(status_code=400, detail="No pending password change required")
    await _set_user_password(user.user_id, payload.new_password,
                             require_change_on_next_login=False)
    return {"ok": True}


class _ChangePayload(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@api.post("/auth/password/change")
async def password_change(payload: _ChangePayload, request: Request):
    """Authenticated change-password from the account-settings page."""
    user = await get_current_user(request)
    full = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not full:
        raise HTTPException(status_code=404, detail="User not found")
    # If they don't have a password yet (Google-only user) we let them set one
    # without a current_password check — same as "add password login".
    if full.get("password_hash"):
        if not verify_password(payload.current_password, full["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
    await _set_user_password(user.user_id, payload.new_password,
                             require_change_on_next_login=False)
    return {"ok": True}


# --- helper used by routes/leads.py + admin_create -------------------------

async def issue_temp_password_for(user_id: str, email: str, name: Optional[str] = None,
                                  *, reason: str = "lead_form") -> Optional[str]:
    """Generates a temp password, persists hash, and emails plaintext.
    Returns the plaintext temp password (so admin flows can show it once)
    or None if the user couldn't be found / email failed.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return None
    temp = generate_temp_password()
    await _set_user_password(user_id, temp, require_change_on_next_login=True)
    try:
        from routes.email import send_temp_password_email, fire
        fire(send_temp_password_email(
            to=email,
            name=name or user.get("name") or email.split("@")[0],
            temp_password=temp,
            reason=reason,
        ))
    except Exception:
        logger.exception("Temp password email failed (password still set)")
    return temp
