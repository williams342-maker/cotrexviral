"""YouTube OAuth 2.0 — Google sign-in flow for channel access.

Lets a user grant our app permission to upload videos and read analytics
on the YouTube channel(s) tied to their Google account. Mirrors the four-
endpoint shape of oauth_linkedin / oauth_meta:

  GET    /api/oauth/youtube/start     →  {authorize_url}
  GET    /api/oauth/youtube/callback  →  exchange code + persist
  GET    /api/oauth/youtube/status    →  {configured, connected, channel}
  DELETE /api/oauth/youtube           →  disconnect

Required runtime config (stored DB-first via /admin/integrations, env fallback):
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REDIRECT_URI   (optional — override the default callback host)
  PUBLIC_SITE_URL        (env only — sets the default callback host)

Google Cloud Console checklist (the admin does this once):
  • Create / select a project at https://console.cloud.google.com
  • APIs & Services → Library → enable **YouTube Data API v3**
  • OAuth consent screen → External → fill brand/contact/privacy/terms URLs
  • Add scopes: youtube.upload + youtube.readonly
  • Add yourself as a Test User while the app is in Testing mode
  • Credentials → Create OAuth Client ID → Web application
  • Authorized redirect URIs (add BOTH so preview + prod both work):
      https://cortexviral.com/api/oauth/youtube/callback
      <your-preview-host>/api/oauth/youtube/callback
  • Copy Client ID + Client Secret → paste into /admin/integrations

Token model:
  • Google OAuth issues short-lived access tokens (~1 h) + a long-lived
    refresh token (only the first time, when prompt=consent + access_type=offline).
  • We store both. The publish/analytics helpers will call
    `refresh_youtube_token(user_id)` to mint a fresh access token whenever
    the current one is within 60 s of expiry.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from core import db, api, logger, PUBLIC_SITE_URL
from deps import get_current_user
from routes.app_config import get_config


# Google OAuth endpoints (stable, well-documented).
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

# Minimum scopes required for "upload videos + read my channel".
# Reviewers reject submissions that ask for more than required, so we
# stick to exactly these two — broader scopes (e.g. youtube) are NOT used.
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


async def _client_id() -> str:
    return (await get_config("YOUTUBE_CLIENT_ID")) or ""


async def _client_secret() -> str:
    return (await get_config("YOUTUBE_CLIENT_SECRET")) or ""


async def _redirect_override() -> str:
    return (await get_config("YOUTUBE_REDIRECT_URI")) or ""


async def _redirect_uri() -> str:
    """Where Google sends the browser after consent.

    Priority:
      1. YOUTUBE_REDIRECT_URI override (DB or env) — treat the value as a
         base host (or any URL with a host) and inject the youtube callback
         path. Lets one value cover both preview + prod testing.
      2. Fall back to PUBLIC_SITE_URL.
    """
    override = await _redirect_override()
    if override:
        parsed = urlparse(override)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/api/oauth/youtube/callback"
    return f"{PUBLIC_SITE_URL}/api/oauth/youtube/callback"


async def _post_oauth_redirect(query: str) -> str:
    base = (await _redirect_uri()).split("/api/oauth/youtube/callback")[0]
    return f"{base}/dashboard/channels?{query}"


async def _check_configured() -> None:
    if not (await _client_id()) or not (await _client_secret()):
        raise HTTPException(
            status_code=503,
            detail=(
                "YouTube OAuth not configured. Set YOUTUBE_CLIENT_ID and "
                "YOUTUBE_CLIENT_SECRET via /admin/integrations."
            ),
        )


# --- /start ------------------------------------------------------------------

@api.get("/oauth/youtube/start")
async def youtube_oauth_start(request: Request):
    """Returns the Google authorize URL the frontend should redirect to."""
    user = await get_current_user(request)
    await _check_configured()

    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": "youtube",
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })

    params = {
        "client_id": await _client_id(),
        "redirect_uri": await _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "state": state,
        # access_type=offline + prompt=consent are the magic words that
        # force Google to issue a refresh_token. Without these, repeat
        # connects (same Google account, same scopes) skip the consent
        # screen and return ONLY a short-lived access token — which dies
        # in an hour and there's no way to renew it.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return {"authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


# --- /callback ---------------------------------------------------------------

async def _exchange_code(code: str) -> dict:
    """Trades the one-shot authorization code for {access_token, refresh_token,
    expires_in, token_type, scope, id_token?}."""
    data = {
        "code": code,
        "client_id": await _client_id(),
        "client_secret": await _client_secret(),
        "redirect_uri": await _redirect_uri(),
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(GOOGLE_TOKEN_URL, data=data)
    if r.status_code != 200:
        logger.error("YouTube token exchange failed: %s %s", r.status_code, r.text[:400])
        raise HTTPException(status_code=502, detail="Google token exchange failed")
    return r.json()


async def _fetch_channel(access_token: str) -> dict | None:
    """Returns the user's primary YouTube channel via /youtube/v3/channels?mine=true.

    Picks the first item in the response (most users have exactly one
    channel attached to their Google account). Returns `None` if the
    account has no YouTube channel yet — common for brand-new Google
    accounts that haven't created a channel.
    """
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(YOUTUBE_CHANNELS_URL, params={
            "part": "snippet,statistics",
            "mine": "true",
        }, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        logger.warning("YouTube /channels?mine=true failed: %s %s",
                       r.status_code, r.text[:300])
        return None
    items = (r.json() or {}).get("items") or []
    if not items:
        return None
    it = items[0]
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    return {
        "channel_id":         it.get("id"),
        "title":              sn.get("title"),
        "description":        sn.get("description"),
        "custom_url":         sn.get("customUrl"),
        "thumbnail_url":      ((sn.get("thumbnails") or {}).get("default") or {}).get("url"),
        "subscriber_count":   int(st.get("subscriberCount") or 0),
        "video_count":        int(st.get("videoCount") or 0),
        "view_count":         int(st.get("viewCount") or 0),
    }


@api.api_route("/oauth/youtube/callback", methods=["GET", "HEAD"])
async def youtube_oauth_callback(request: Request, code: str = "", state: str = "",
                                 error: str = "", error_description: str = ""):
    # HEAD probe (Google sometimes pings the redirect URI during app review).
    if not code and not error and request.method == "HEAD":
        return {"ok": True}
    if error:
        logger.info("YouTube callback denied: %s — %s", error, error_description)
        return RedirectResponse(await _post_oauth_redirect("youtube=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "youtube"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    await _check_configured()
    tok = await _exchange_code(code)
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")  # may be missing on reconnects
    expires_in = int(tok.get("expires_in", 3600))
    scope = tok.get("scope", "")
    if not access_token:
        raise HTTPException(status_code=502, detail="No access_token in Google response")

    channel = await _fetch_channel(access_token)
    now = datetime.now(timezone.utc)

    # If this is a reconnect with no refresh_token in the response (Google
    # silently skipped consent and didn't issue a new one), preserve the
    # one we already had so token refresh keeps working.
    if not refresh_token:
        existing = await db.youtube_connections.find_one(
            {"user_id": user_id}, {"refresh_token": 1, "_id": 0},
        )
        if existing and existing.get("refresh_token"):
            refresh_token = existing["refresh_token"]

    if not channel:
        # No YouTube channel exists on this Google account. We still store
        # the token (the user can create a channel later) but redirect with
        # a clear status so the UI can prompt them.
        logger.info("YouTube OAuth: user %s has no channel on this account", user_id)

    await db.youtube_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id":             user_id,
                "access_token":        access_token,
                "refresh_token":       refresh_token,
                "access_token_expires_at": now + timedelta(seconds=expires_in),
                "scope":               scope,
                "channel":             channel,
                "updated_at":          now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )

    handle = (channel or {}).get("title") or "YouTube"
    await db.channels.update_one(
        {"user_id": user_id, "platform": "youtube"},
        {
            "$set": {
                "user_id": user_id, "platform": "youtube",
                "connected": True, "handle": handle,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )

    qs = "youtube=connected" if channel else "youtube=no_channel"
    return RedirectResponse(await _post_oauth_redirect(qs), 302)


# --- /status -----------------------------------------------------------------

@api.get("/oauth/youtube/status")
async def youtube_status(request: Request):
    user = await get_current_user(request)
    conn = await db.youtube_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "access_token": 0, "refresh_token": 0},  # never leak secrets
    )
    is_configured = bool(await _client_id() and await _client_secret())
    return {
        "configured": is_configured,
        "connected":  bool(conn),
        "channel":    (conn or {}).get("channel"),
        "expires_at": (conn or {}).get("access_token_expires_at"),
        "scope":      (conn or {}).get("scope"),
    }


# --- /disconnect -------------------------------------------------------------

@api.delete("/oauth/youtube")
async def youtube_disconnect(request: Request):
    """Revoke the refresh token at Google + delete our local record. Google's
    /revoke endpoint is best-effort — failure to revoke is logged but doesn't
    block local disconnect (the user explicitly asked to be disconnected)."""
    user = await get_current_user(request)
    conn = await db.youtube_connections.find_one({"user_id": user.user_id}, {"_id": 0})
    if conn and conn.get("refresh_token"):
        try:
            async with httpx.AsyncClient(timeout=10) as cli:
                await cli.post(GOOGLE_REVOKE_URL,
                               data={"token": conn["refresh_token"]},
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
        except Exception as exc:
            logger.warning("YouTube token revoke failed for %s: %s", user.user_id, exc)
    await db.youtube_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "youtube"},
        {"$set": {"connected": False, "handle": None,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


# ===========================================================================
# Token refresh helper — used by future publish/analytics paths.
# ===========================================================================
async def refresh_youtube_token(user_id: str) -> Optional[str]:
    """Returns a valid access_token for `user_id`, refreshing if needed.

    Returns None if:
      - the user has no YouTube connection,
      - the connection has no refresh_token (token expired and can't be
        renewed — user needs to reconnect),
      - Google rejects the refresh (invalid_grant, revoked, etc.).
    """
    conn = await db.youtube_connections.find_one({"user_id": user_id}, {"_id": 0})
    if not conn:
        return None

    # Cheap path: existing token is still valid for > 60 seconds.
    expires_at = conn.get("access_token_expires_at")
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at - timedelta(seconds=60) > datetime.now(timezone.utc):
            return conn.get("access_token")

    refresh_token = conn.get("refresh_token")
    if not refresh_token:
        logger.info("YouTube refresh: user %s has no refresh_token — reconnect needed", user_id)
        return None

    data = {
        "client_id":     await _client_id(),
        "client_secret": await _client_secret(),
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(GOOGLE_TOKEN_URL, data=data)
    if r.status_code != 200:
        logger.warning("YouTube token refresh failed for %s: %s %s",
                       user_id, r.status_code, r.text[:300])
        return None
    payload = r.json() or {}
    new_access = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    if not new_access:
        return None

    now = datetime.now(timezone.utc)
    await db.youtube_connections.update_one(
        {"user_id": user_id},
        {"$set": {
            "access_token":            new_access,
            "access_token_expires_at": now + timedelta(seconds=expires_in),
            "updated_at":              now,
        }},
    )
    return new_access
