"""Pinterest OAuth 2.0 (API v5).

Same four-endpoint shape as the other social integrations:

  GET    /api/oauth/pinterest/start
  GET    /api/oauth/pinterest/callback
  GET    /api/oauth/pinterest/status
  DELETE /api/oauth/pinterest

Pinterest API v5 quirks worth knowing:
  • Authorize URL is hosted on pinterest.com (not the API host).
  • Token exchange uses HTTP Basic auth (client_id:client_secret, base64),
    POST body is x-www-form-urlencoded — NOT JSON. Easy to get wrong.
  • Access tokens last ~30 days. Refresh tokens are continuous (replace the
    legacy 365-day refresh model deprecated late 2024).
  • Trial-tier apps may have POST /v5/pins rate-limited until you graduate
    to Standard access (free, requires a video demo).

Required env (/app/backend/.env):
  PINTEREST_APP_ID=...
  PINTEREST_APP_SECRET=...

Optional:
  PINTEREST_REDIRECT_URI=https://...    # if you need a non-standard URI
  PINTEREST_API_BASE=https://api-sandbox.pinterest.com   # for sandbox testing
"""
import base64
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from core import (
    db, api, logger,
    PUBLIC_SITE_URL,
    PINTEREST_APP_ID, PINTEREST_APP_SECRET,
    PINTEREST_REDIRECT_URI_OVERRIDE, PINTEREST_API_BASE,
)
from deps import get_current_user


AUTHORIZE_URL = "https://www.pinterest.com/oauth/"

# Minimum scopes for our use case (publish Pins). If you later need analytics
# or audience insights, add `user_accounts:read` + `pins:read` here AND
# request them during App Review.
SCOPES = ["boards:read", "pins:write", "pins:read"]


def _token_url() -> str:
    return f"{PINTEREST_API_BASE}/v5/oauth/token"


def _redirect_uri() -> str:
    return PINTEREST_REDIRECT_URI_OVERRIDE or f"{PUBLIC_SITE_URL}/api/oauth/pinterest/callback"


def _post_oauth_redirect(query: str) -> str:
    base = _redirect_uri().split("/api/oauth/pinterest/callback")[0]
    return f"{base}/dashboard/channels?{query}"


def _basic_auth_header() -> str:
    raw = f"{PINTEREST_APP_ID}:{PINTEREST_APP_SECRET}".encode()
    return f"Basic {base64.b64encode(raw).decode()}"


def _check_configured():
    if not PINTEREST_APP_ID or not PINTEREST_APP_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Pinterest OAuth not configured. Set PINTEREST_APP_ID and "
                "PINTEREST_APP_SECRET in /app/backend/.env."
            ),
        )


# --- /start ------------------------------------------------------------------

@api.get("/oauth/pinterest/start")
async def pinterest_start(request: Request):
    user = await get_current_user(request)
    _check_configured()
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": "pinterest",
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    params = {
        "client_id": PINTEREST_APP_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": ",".join(SCOPES),  # Pinterest accepts comma OR space separated
        "state": state,
    }
    return {"authorize_url": f"{AUTHORIZE_URL}?{urlencode(params)}"}


# --- /callback ---------------------------------------------------------------

@api.api_route("/oauth/pinterest/callback", methods=["GET", "HEAD"])
async def pinterest_callback(request: Request, code: str = "", state: str = "",
                             error: str = "", error_description: str = ""):
    # Pinterest's "verify redirect URI" check during app review sends HEAD/empty GET.
    if not code and not error and request.method == "HEAD":
        return {"ok": True}
    if error:
        logger.info("Pinterest callback denied: %s — %s", error, error_description)
        return RedirectResponse(_post_oauth_redirect("pinterest=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "pinterest"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    _check_configured()

    # Exchange code → access + refresh token. Pinterest requires Basic auth +
    # form-encoded body (NOT JSON). This is the #1 thing devs get wrong.
    async with httpx.AsyncClient(timeout=20) as cli:
        tok = await cli.post(
            _token_url(),
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
            },
        )
        if tok.status_code != 200:
            logger.error("Pinterest token exchange failed: %s %s",
                         tok.status_code, tok.text[:300])
            raise HTTPException(status_code=502, detail="Pinterest token exchange failed")
        body = tok.json()
        access_token = body["access_token"]
        refresh_token = body.get("refresh_token")
        expires_in = int(body.get("expires_in", 30 * 24 * 3600))
        scope = body.get("scope", "")

        # Fetch the user's username for the "handle" badge in our UI.
        handle = "Pinterest"
        me = await cli.get(
            f"{PINTEREST_API_BASE}/v5/user_account",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code == 200:
            username = me.json().get("username")
            if username:
                handle = f"@{username}"

    now = datetime.now(timezone.utc)
    await db.pinterest_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "scope": scope,
                "expires_at": now + timedelta(seconds=expires_in),
                "username": handle.lstrip("@"),
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    await db.channels.update_one(
        {"user_id": user_id, "platform": "pinterest"},
        {
            "$set": {
                "user_id": user_id, "platform": "pinterest",
                "connected": True, "handle": handle,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    return RedirectResponse(_post_oauth_redirect("pinterest=connected"), 302)


# --- /status -----------------------------------------------------------------

@api.get("/oauth/pinterest/status")
async def pinterest_status(request: Request):
    user = await get_current_user(request)
    conn = await db.pinterest_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "access_token": 0, "refresh_token": 0},
    )
    return {
        "configured": bool(PINTEREST_APP_ID and PINTEREST_APP_SECRET),
        "connected": bool(conn),
        "username": (conn or {}).get("username"),
        "expires_at": (conn or {}).get("expires_at"),
    }


# --- /disconnect -------------------------------------------------------------

@api.delete("/oauth/pinterest")
async def pinterest_disconnect(request: Request):
    user = await get_current_user(request)
    await db.pinterest_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "pinterest"},
        {"$set": {"connected": False, "handle": None,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


# --- Internal helper: refresh tokens before they expire ----------------------
# Used by future publishing code; not directly exposed as a route.

async def get_fresh_pinterest_token(user_id: str) -> str | None:
    """Return a valid access token for the user, refreshing if within 3 days
    of expiry. Returns None if the user isn't connected or refresh failed."""
    conn = await db.pinterest_connections.find_one({"user_id": user_id})
    if not conn:
        return None
    now = datetime.now(timezone.utc)
    expires = conn.get("expires_at")
    if isinstance(expires, datetime):
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires - now > timedelta(days=3):
            return conn["access_token"]
    refresh_token = conn.get("refresh_token")
    if not refresh_token:
        return conn.get("access_token")  # best effort

    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(
            _token_url(),
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
    if r.status_code != 200:
        logger.warning("Pinterest refresh failed for %s: %s", user_id, r.text[:200])
        return conn.get("access_token")
    body = r.json()
    new_token = body["access_token"]
    await db.pinterest_connections.update_one(
        {"user_id": user_id},
        {"$set": {
            "access_token": new_token,
            "refresh_token": body.get("refresh_token", refresh_token),
            "expires_at": now + timedelta(seconds=int(body.get("expires_in", 30 * 24 * 3600))),
            "updated_at": now,
        }},
    )
    return new_token


# --- /boards: list the connected user's boards (for the Compose picker) ------

@api.get("/oauth/pinterest/boards")
async def pinterest_boards(request: Request):
    """Return the connected user's boards. Used by the Compose page to let
    the user pick a destination when publishing a Pin."""
    user = await get_current_user(request)
    token = await get_fresh_pinterest_token(user.user_id)
    if not token:
        raise HTTPException(status_code=400, detail="Pinterest not connected")
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(
            f"{PINTEREST_API_BASE}/v5/boards",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_size": 100},
        )
    if r.status_code != 200:
        logger.warning("Pinterest /boards failed for %s: %s %s",
                       user.user_id, r.status_code, r.text[:200])
        raise HTTPException(status_code=502, detail="Could not fetch boards")
    items = r.json().get("items", []) or []
    # Slim shape — the frontend only needs id + name + privacy.
    return {
        "boards": [
            {"id": b.get("id"), "name": b.get("name"), "privacy": b.get("privacy")}
            for b in items if b.get("id") and b.get("name")
        ],
    }


# --- Publish helper: create a Pin -------------------------------------------

# Pinterest's POST /v5/pins requires an image. We accept image_url (URL we
# pass through to Pinterest, who fetches it server-side). The post body needs
# to include a `board_id` — which the user picked in Compose and we stored
# on the post doc as `pinterest_board_id`.
PIN_DESCRIPTION_LIMIT = 500


async def publish_to_pinterest(user_id: str, text: str, *,
                               image_url: str | None = None,
                               board_id: str | None = None,
                               link: str | None = None,
                               title: str | None = None) -> dict:
    """Create a Pin on the user's behalf. Returns {ok, ...} shape matching
    the other publish_to_* helpers so the scheduler dispatcher can record the
    outcome uniformly."""
    if not image_url:
        return {"ok": False, "reason": "pinterest_requires_image_url"}
    if not board_id:
        return {"ok": False, "reason": "pinterest_requires_board_id"}

    token = await get_fresh_pinterest_token(user_id)
    if not token:
        return {"ok": False, "reason": "not_connected"}

    # Pinterest's description cap is 500 chars — truncate gracefully so a
    # long AI-generated caption doesn't 400 the whole publish.
    description = (text or "")[:PIN_DESCRIPTION_LIMIT]
    pin_title = (title or text or "Pin")[:100] if text else "Pin"

    body = {
        "board_id": board_id,
        "title": pin_title,
        "description": description,
        "media_source": {"source_type": "image_url", "url": image_url},
    }
    if link:
        body["link"] = link

    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(
            f"{PINTEREST_API_BASE}/v5/pins",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if r.status_code not in (200, 201):
        logger.warning("Pinterest publish failed for %s: %s %s",
                       user_id, r.status_code, r.text[:300])
        return {
            "ok": False,
            "reason": "api_error",
            "status": r.status_code,
            "body": r.text[:400],
        }
    pin = r.json() or {}
    return {
        "ok": True,
        "pin_id": pin.get("id"),
        "permalink": pin.get("link") or f"https://www.pinterest.com/pin/{pin.get('id')}",
    }
