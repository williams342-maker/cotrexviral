"""TikTok OAuth 2.0 (Login Kit v2) + Content Posting API integration.

Flow:
  1. User clicks "Connect TikTok" in the dashboard → frontend calls
     GET /api/oauth/tiktok/start which returns the TikTok v2 authorize URL.
  2. User authorises on TikTok → TikTok redirects to
     GET /api/oauth/tiktok/callback?code=...&state=...
  3. We exchange the code for access_token + refresh_token + open_id, persist
     a `tiktok_connections` document keyed by our internal user_id, and mirror
     into `channels` so the dashboard reflects "connected".
  4. When a post with platforms=["tiktok"] is published (immediately via
     /channels/publish or by the scheduler), we call publish_to_tiktok which
     uses the Direct Post Content Posting API with PULL_FROM_URL when a
     media_url is present, otherwise returns a not_supported reason (TikTok
     does not allow text-only posts).

Required env vars in /app/backend/.env:
    TIKTOK_CLIENT_KEY=...        # TikTok uses 'client_key' not 'client_id'
    TIKTOK_CLIENT_SECRET=...
    PUBLIC_SITE_URL=https://cortexviral.com   # for the redirect URI

TikTok developer-app checklist:
  • Products: Login Kit + Content Posting API (request video.publish scope)
  • Redirect URI (exact match): https://cortexviral.com/api/oauth/tiktok/callback
  • Verified URL prefix for any host you'll use as `media_url` for PULL_FROM_URL
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from core import (
    db,
    api,
    logger,
    PUBLIC_SITE_URL,
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI_OVERRIDE,
)
from deps import get_current_user


TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
TIKTOK_DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Scopes — comma-separated per TikTok v2 spec (NOT space-separated).
#   user.info.basic → minimal profile info
#   video.publish   → direct-post to user's TikTok profile (Content Posting API)
TIKTOK_SCOPES = ["user.info.basic", "video.publish"]


def _redirect_uri() -> str:
    """Returns the redirect URI registered with TikTok.

    Priority:
      1. TIKTOK_REDIRECT_URI env var (override — useful for preview-pod testing).
      2. PUBLIC_SITE_URL + /api/oauth/tiktok/callback (production default).
    """
    if TIKTOK_REDIRECT_URI_OVERRIDE:
        return TIKTOK_REDIRECT_URI_OVERRIDE
    return f"{PUBLIC_SITE_URL}/api/oauth/tiktok/callback"


def _post_oauth_redirect(query: str) -> str:
    """Where to send the browser after the callback finishes.

    Uses the host of the redirect URI itself so the user lands on the same
    domain they started the OAuth flow from (preview pod or production).
    """
    base = _redirect_uri().split("/api/oauth/tiktok/callback")[0]
    return f"{base}/dashboard/channels?{query}"


def _check_configured():
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "TikTok OAuth not configured. Set TIKTOK_CLIENT_KEY and "
                "TIKTOK_CLIENT_SECRET in /app/backend/.env."
            ),
        )


@api.get("/oauth/tiktok/start")
async def tiktok_oauth_start(request: Request):
    """Returns the TikTok authorize URL the frontend should redirect to."""
    user = await get_current_user(request)
    _check_configured()

    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": "tiktok",
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": ",".join(TIKTOK_SCOPES),
        "redirect_uri": _redirect_uri(),
        "state": state,
    }
    return {"authorize_url": f"{TIKTOK_AUTH_URL}?{urlencode(params)}"}


@api.api_route("/oauth/tiktok/callback", methods=["GET", "HEAD", "POST"])
async def tiktok_oauth_callback(
    request: Request, code: str = "", state: str = "",
    error: str = "", error_description: str = "",
):
    """TikTok redirects here after the user authorises (or denies).

    Accepts HEAD/POST as well so TikTok's "Verify Redirect URI" check
    (which sends a HEAD without query params) returns 200 instead of 405.
    """
    # No code AND no error → this is TikTok's reachability probe. Reply 200.
    if not code and not error and request.method in ("HEAD", "POST"):
        return {"ok": True, "ready": True}
    if error:
        logger.info("TikTok callback denied: %s — %s", error, error_description)
        return RedirectResponse(
            url=_post_oauth_redirect("tiktok=denied"),
            status_code=302,
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "tiktok"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    _check_configured()
    async with httpx.AsyncClient(timeout=20) as cli:
        token_resp = await cli.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _redirect_uri(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.error("TikTok token exchange failed: %s %s",
                         token_resp.status_code, token_resp.text)
            raise HTTPException(status_code=502, detail="TikTok token exchange failed")
        tok = token_resp.json()
        # TikTok wraps errors as {"error": "...", "error_description": "..."}
        if tok.get("error"):
            logger.error("TikTok token error: %s", tok)
            raise HTTPException(status_code=502, detail=f"TikTok: {tok.get('error_description') or tok['error']}")

    access_token = tok["access_token"]
    refresh_token = tok.get("refresh_token", "")
    open_id = tok.get("open_id", "")
    expires_in = int(tok.get("expires_in", 86400))
    refresh_expires_in = int(tok.get("refresh_expires_in", 31536000))
    scope_str = tok.get("scope", "")
    scopes = [s for s in scope_str.split(",") if s]

    now = datetime.now(timezone.utc)
    handle = f"tiktok:{open_id[:10]}" if open_id else "@tiktok"

    await db.tiktok_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "open_id": open_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "scopes": scopes,
                "expires_at": now + timedelta(seconds=expires_in),
                "refresh_expires_at": now + timedelta(seconds=refresh_expires_in),
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )

    await db.channels.update_one(
        {"user_id": user_id, "platform": "tiktok"},
        {
            "$set": {
                "user_id": user_id,
                "platform": "tiktok",
                "connected": True,
                "handle": handle,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )

    return RedirectResponse(
        url=_post_oauth_redirect("tiktok=connected"),
        status_code=302,
    )


@api.delete("/oauth/tiktok")
async def tiktok_disconnect(request: Request):
    """Disconnect — revokes the token with TikTok and clears local state."""
    user = await get_current_user(request)
    conn = await db.tiktok_connections.find_one({"user_id": user.user_id})
    if conn and conn.get("access_token") and TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET:
        # Best-effort revoke; never fail disconnect if TikTok is down.
        try:
            async with httpx.AsyncClient(timeout=10) as cli:
                await cli.post(
                    TIKTOK_REVOKE_URL,
                    data={
                        "client_key": TIKTOK_CLIENT_KEY,
                        "client_secret": TIKTOK_CLIENT_SECRET,
                        "token": conn["access_token"],
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception:
            logger.exception("TikTok revoke failed (continuing with local disconnect)")

    await db.tiktok_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "tiktok"},
        {"$set": {
            "connected": False, "handle": None,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"ok": True}


@api.get("/oauth/tiktok/status")
async def tiktok_status(request: Request):
    user = await get_current_user(request)
    conn = await db.tiktok_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "access_token": 0, "refresh_token": 0},
    )
    return {
        "configured": bool(TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET),
        "connected": bool(conn),
        "connection": conn,
    }


# ==================== Token refresh ====================

async def _refresh_tiktok_token(conn: dict) -> dict | None:
    """Refresh and persist a new access_token. Returns the updated conn (or None)."""
    refresh_token = conn.get("refresh_token")
    if not refresh_token:
        return None
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        logger.error("TikTok refresh failed: %s %s", r.status_code, r.text[:300])
        return None
    tok = r.json()
    if tok.get("error"):
        logger.error("TikTok refresh error: %s", tok)
        return None

    now = datetime.now(timezone.utc)
    expires_in = int(tok.get("expires_in", 86400))
    refresh_expires_in = int(tok.get("refresh_expires_in", 31536000))
    update = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token", refresh_token),
        "expires_at": now + timedelta(seconds=expires_in),
        "refresh_expires_at": now + timedelta(seconds=refresh_expires_in),
        "updated_at": now,
    }
    await db.tiktok_connections.update_one(
        {"user_id": conn["user_id"]}, {"$set": update},
    )
    conn.update(update)
    return conn


# ==================== Publishing ====================

async def publish_to_tiktok(user_id: str, text: str, media_url: str | None = None) -> dict:
    """Post a video to the user's TikTok profile via Content Posting API.

    TikTok does not support text-only posts. When media_url is missing we
    return a graceful `not_supported` reason so the scheduler logs it without
    crashing.
    """
    conn = await db.tiktok_connections.find_one({"user_id": user_id})
    if not conn:
        return {"ok": False, "reason": "not_connected"}

    if not media_url:
        return {"ok": False, "reason": "tiktok_requires_video_media_url"}

    # Refresh token if expiring soon (or already expired).
    expires_at = conn.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not expires_at or expires_at <= datetime.now(timezone.utc) + timedelta(minutes=2):
        refreshed = await _refresh_tiktok_token(conn)
        if not refreshed:
            return {"ok": False, "reason": "token_refresh_failed"}
        conn = refreshed

    # Direct post via PULL_FROM_URL. The media_url host must be a verified
    # URL property on your TikTok developer app, otherwise TikTok rejects the
    # init call. Caption/title is capped at ~2200 chars by TikTok.
    body = {
        "post_info": {
            "title": (text or "")[:2200],
            "privacy_level": "SELF_ONLY",  # safest default; user can change later
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": media_url,
        },
    }
    headers = {
        "Authorization": f"Bearer {conn['access_token']}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(TIKTOK_DIRECT_INIT_URL, json=body, headers=headers)

    if r.status_code != 200:
        logger.error("TikTok publish init failed %s: %s", r.status_code, r.text[:400])
        return {"ok": False, "reason": "api_error", "status": r.status_code, "body": r.text[:400]}

    data = (r.json() or {}).get("data", {})
    publish_id = data.get("publish_id")
    if not publish_id:
        return {"ok": False, "reason": "missing_publish_id", "body": r.text[:400]}
    return {"ok": True, "tiktok_publish_id": publish_id}


@api.get("/oauth/tiktok/publish-status")
async def tiktok_publish_status(request: Request, publish_id: str):
    """Poll TikTok for the status of a previously-initiated publish."""
    user = await get_current_user(request)
    conn = await db.tiktok_connections.find_one({"user_id": user.user_id})
    if not conn:
        raise HTTPException(status_code=404, detail="TikTok not connected")
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(
            TIKTOK_STATUS_URL,
            json={"publish_id": publish_id},
            headers={
                "Authorization": f"Bearer {conn['access_token']}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"TikTok status fetch failed: {r.text[:300]}")
    return r.json()


# ---------------------------------------------------------------------------
# Analytics — per-video stats (likes, comments, shares, views)
# ---------------------------------------------------------------------------
async def fetch_tiktok_post_metrics(
    user_id: str,
    publish_id: str | None = None,
    video_id: str | None = None,
) -> dict | None:
    """Returns {likes, comments, shares, views, fetched_at} for a TikTok
    video. Requires the TikTok video_id — if only the original publish_id
    is known, we first call /v2/post/publish/status/fetch to resolve it.

    Falls back to None on any failure (no permission, expired token,
    rate-limit) — caller renders 'Analytics coming soon' chip.
    """
    if not publish_id and not video_id:
        return None
    conn = await db.tiktok_connections.find_one({"user_id": user_id})
    if not conn or not conn.get("access_token"):
        return None
    token = conn["access_token"]

    # 1. Resolve video_id from publish_id if we don't have it yet.
    if not video_id and publish_id:
        async with httpx.AsyncClient(timeout=15) as cli:
            sr = await cli.post(
                TIKTOK_STATUS_URL,
                json={"publish_id": publish_id},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
            )
        if sr.status_code != 200:
            return None
        sdata = ((sr.json() or {}).get("data") or {})
        # `publicaly_available_post_id` is what TikTok returns once the
        # video is processed and live.
        ids = sdata.get("publicaly_available_post_id") or sdata.get("public_post_id") or []
        if isinstance(ids, list) and ids:
            video_id = ids[0]
        else:
            return None

    # 2. Fetch the stats via /v2/video/query/
    params = {"fields": "id,view_count,like_count,comment_count,share_count"}
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(
            "https://open.tiktokapis.com/v2/video/query/",
            params=params,
            json={"filters": {"video_ids": [video_id]}},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    if r.status_code != 200:
        logger.info("TikTok analytics %s for video %s: %s",
                    r.status_code, video_id, r.text[:200])
        return None
    body = ((r.json() or {}).get("data") or {}).get("videos") or []
    if not body:
        return None
    v = body[0]
    return {
        "views": int(v.get("view_count") or 0),
        "likes": int(v.get("like_count") or 0),
        "comments": int(v.get("comment_count") or 0),
        "shares": int(v.get("share_count") or 0),
        "fetched_at": datetime.now(timezone.utc),
    }
