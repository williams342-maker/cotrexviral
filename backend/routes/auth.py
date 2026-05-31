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

    # Block brand-new signups when admin has paused them. Existing users +
    # email-allowlisted admins always get through (so admins can still log in
    # to flip the switch back).
    if is_new_user and not is_admin_flag:
        from routes.admin_settings import are_signups_enabled
        if not await are_signups_enabled():
            raise HTTPException(
                status_code=503,
                detail="Signups are temporarily paused. Please check back soon.",
            )

    if existing:
        user_id = existing["user_id"]
        was_paused = existing.get("status") == "paused"
        update_set = {"name": name, "picture": picture,
                      "is_admin": is_admin_flag or existing.get("is_admin", False)}
        update_doc = {"$set": update_set}
        if was_paused:
            update_set["status"] = "active"
            update_set["reactivated_at"] = datetime.now(timezone.utc)
            update_doc["$unset"] = {"paused_at": "", "pause_reason": ""}
        await db.users.update_one({"user_id": user_id}, update_doc)
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

    # Auto-create a default brand for every signup. Idempotent so
    # re-runs (e.g. after a reactivation) are safe. This is the
    # `brand_id` every downstream collection FKs on (decision 1c).
    try:
        from routes.brands import ensure_default_brand_for_user
        await ensure_default_brand_for_user(user_id, name_hint=name)
    except Exception:
        # Brand auto-create failure must NEVER block login — the
        # migration cron will pick the user up on the next run.
        import logging
        logging.getLogger(__name__).exception(
            "ensure_default_brand_for_user failed for %s", user_id,
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
    payload["has_password"] = bool(doc.get("password_hash"))
    payload["must_change_password"] = bool(doc.get("must_change_password"))
    return payload


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie(key="session_token", path="/")
    return {"ok": True}


@api.post("/auth/ws-ticket")
async def ws_ticket(request: Request):
    """Mint a short-lived (90 s) one-time ticket the frontend can pass
    as `?token=` on a WebSocket URL. Solves the HttpOnly-cookie problem:
    `document.cookie` can't read session_token, so the frontend asks for
    a ticket via a normal HTTP POST (which sends the cookie), and uses
    that ticket as the WS query param. The WS auth treats it like a
    regular session token. Tickets are stored in user_sessions with a
    90-second TTL and are deleted on first use."""
    user = await get_current_user(request)
    import secrets
    from datetime import datetime, timezone, timedelta
    ticket = "wst_" + secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=90)
    await db.user_sessions.insert_one({
        "session_token": ticket,
        "user_id":       user.user_id,
        "expires_at":    expires_at,
        "kind":          "ws_ticket",
        "single_use":    True,
        "created_at":    datetime.now(timezone.utc),
    })
    return {"ticket": ticket, "expires_at": expires_at.isoformat()}


# ---------------------------------------------------------------------
# Generic per-user preferences. The shape is intentionally open-ended
# (a plain dict on `users.preferences`) so we can add new toggles
# without schema migrations. Validate known keys at the route boundary.
# ---------------------------------------------------------------------
_CONVERSATION_MODES = {"fresh_every_visit", "resume_last"}

_PREF_VALIDATORS: dict[str, callable] = {
    "conversation_mode": lambda v: isinstance(v, str) and v in _CONVERSATION_MODES,
}

_PREF_DEFAULTS = {
    "conversation_mode": "fresh_every_visit",
}


@api.get("/user/preferences")
async def get_user_preferences(request: Request):
    """Return the user's preference dict merged with defaults so the
    frontend doesn't need to know which keys are unset."""
    user = await get_current_user(request)
    doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "preferences": 1}) or {}
    prefs = {**_PREF_DEFAULTS, **(doc.get("preferences") or {})}
    return {"preferences": prefs}


@api.put("/user/preferences")
async def update_user_preferences(request: Request):
    """Patch one or more preference keys. Body shape: a flat dict of
    `{key: value}`. Unknown keys → 422. Bad values → 422."""
    user = await get_current_user(request)
    payload = await request.json()
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(400, "Body must be a non-empty {key: value} dict.")
    update: dict = {}
    for k, v in payload.items():
        validator = _PREF_VALIDATORS.get(k)
        if validator is None:
            raise HTTPException(422, f"Unknown preference key: {k}")
        if not validator(v):
            raise HTTPException(422, f"Invalid value for {k}: {v!r}")
        update[f"preferences.{k}"] = v
    await db.users.update_one(
        {"user_id": user.user_id}, {"$set": update}, upsert=True)
    doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "preferences": 1}) or {}
    prefs = {**_PREF_DEFAULTS, **(doc.get("preferences") or {})}
    return {"preferences": prefs}
