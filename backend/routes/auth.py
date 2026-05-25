"""Authentication: Emergent Google Auth session bootstrap, /auth/me, logout."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from core import db, api, ADMIN_EMAILS
from deps import get_current_user
import httpx


@api.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange Emergent session_id for our session_token cookie."""
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-ID header")

    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")

    data = r.json()
    email = data["email"]
    name = data["name"]
    picture = data.get("picture")
    session_token = data["session_token"]

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    is_admin_flag = email.lower() in ADMIN_EMAILS
    is_new_user = existing is None
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "is_admin": is_admin_flag or existing.get("is_admin", False)}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "is_admin": is_admin_flag,
                "status": "active",
                "created_at": datetime.now(timezone.utc),
            }
        )

    # Fire welcome email for new users (background — never blocks login).
    if is_new_user:
        from routes.email import send_welcome_email, fire
        fire(send_welcome_email(to=email, name=name))

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one(
        {
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    return {"user_id": user_id, "email": email, "name": name, "picture": picture}


@api.get("/auth/me")
async def auth_me(request: Request):
    user = await get_current_user(request)
    # Augment with onboarding status so the frontend can route accordingly.
    from routes.onboarding import _onboarding_required
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    payload = user.model_dump()
    payload["onboarding_required"] = _onboarding_required(doc)
    return payload


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie(key="session_token", path="/")
    return {"ok": True}
