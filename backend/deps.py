"""Dependencies: auth, admin, audit logging."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import db, ADMIN_EMAILS
from models import User


async def get_current_user(request: Request) -> User:
    """Returns the current authenticated user or raises 401."""
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")

    user_doc.setdefault("is_admin", user_doc.get("email", "").lower() in ADMIN_EMAILS)
    user_doc.setdefault("status", "active")

    if user_doc.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")

    return User(**user_doc)


async def require_admin(request: Request) -> User:
    user = await get_current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def log_admin_action(
    admin: User,
    action: str,
    target_user_id: Optional[str] = None,
    target_email: Optional[str] = None,
    details: Optional[dict] = None,
):
    await db.audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "admin_id": admin.user_id,
        "admin_email": admin.email,
        "admin_name": admin.name,
        "action": action,
        "target_user_id": target_user_id,
        "target_email": target_email,
        "details": details or {},
        "created_at": datetime.now(timezone.utc),
    })
