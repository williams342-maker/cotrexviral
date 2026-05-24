"""LinkedIn OAuth 2.0 + posting integration.

Flow:
  1. User clicks "Connect LinkedIn" in the dashboard → frontend calls
     GET /api/oauth/linkedin/start which returns the LinkedIn authorize URL.
  2. User authorises on LinkedIn → LinkedIn redirects to
     GET /api/oauth/linkedin/callback?code=...&state=...
  3. We exchange the code for an access_token + id_token, fetch the LinkedIn
     userinfo, and persist a `linkedin_connections` document keyed by our
     internal user_id.
  4. When a post with platforms=["linkedin"] is published (either immediately
     via /channels/publish or by the background scheduler), we call
     publish_to_linkedin(user_id, text) which POSTs to /rest/posts.

Required env vars in /app/backend/.env:
    LINKEDIN_CLIENT_ID=...
    LINKEDIN_CLIENT_SECRET=...
    PUBLIC_SITE_URL=https://cortexviral.com   # used for the redirect URI
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
    LINKEDIN_CLIENT_ID,
    LINKEDIN_CLIENT_SECRET,
)
from deps import get_current_user


LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_API_VERSION = "202405"  # increment as LinkedIn publishes new versions

# OAuth scopes:
#   openid + profile + email → required for OIDC userinfo (gets the urn:li:person:xxx id)
#   w_member_social         → posting on behalf of the member ("Share on LinkedIn" product)
LINKEDIN_SCOPES = ["openid", "profile", "email", "w_member_social"]


def _redirect_uri() -> str:
    return f"{PUBLIC_SITE_URL}/api/oauth/linkedin/callback"


def _check_configured():
    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "LinkedIn OAuth not configured. Set LINKEDIN_CLIENT_ID and "
                "LINKEDIN_CLIENT_SECRET in /app/backend/.env."
            ),
        )


@api.get("/oauth/linkedin/start")
async def linkedin_oauth_start(request: Request):
    """Returns the LinkedIn authorize URL the frontend should redirect to."""
    user = await get_current_user(request)
    _check_configured()

    # Random state, stored briefly so we can verify on callback.
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": "linkedin",
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })

    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "state": state,
        "scope": " ".join(LINKEDIN_SCOPES),
    }
    return {"authorize_url": f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"}


@api.get("/oauth/linkedin/callback")
async def linkedin_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """LinkedIn redirects here after the user authorises (or denies)."""
    if error:
        return RedirectResponse(url=f"{PUBLIC_SITE_URL}/dashboard/channels?linkedin=denied", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    # Validate state
    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "linkedin"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    # Consume the state (single-use)
    await db.oauth_states.delete_one({"_id": state})

    _check_configured()
    # Exchange code → access_token
    async with httpx.AsyncClient(timeout=20) as cli:
        token_resp = await cli.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.error("LinkedIn token exchange failed: %s %s", token_resp.status_code, token_resp.text)
            raise HTTPException(status_code=502, detail="LinkedIn token exchange failed")
        tok = token_resp.json()
        access_token = tok["access_token"]
        expires_in = tok.get("expires_in", 3600)

        # Fetch userinfo (OIDC) to get the LinkedIn person URN
        info_resp = await cli.get(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            logger.error("LinkedIn userinfo failed: %s %s", info_resp.status_code, info_resp.text)
            raise HTTPException(status_code=502, detail="LinkedIn userinfo failed")
        info = info_resp.json()

    # Persist (one connection per user — upsert)
    now = datetime.now(timezone.utc)
    handle = info.get("name") or info.get("email") or "@linkedin"
    sub = info.get("sub")  # openid subject — LinkedIn member URN suffix
    person_urn = f"urn:li:person:{sub}" if sub else None

    await db.linkedin_connections.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "access_token": access_token,
            "expires_at": now + timedelta(seconds=int(expires_in)),
            "person_urn": person_urn,
            "name": info.get("name"),
            "email": info.get("email"),
            "picture": info.get("picture"),
            "updated_at": now,
        }, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
        upsert=True,
    )

    # Mirror into the existing `channels` collection so the dashboard reflects "connected"
    await db.channels.update_one(
        {"user_id": user_id, "platform": "linkedin"},
        {"$set": {
            "user_id": user_id,
            "platform": "linkedin",
            "connected": True,
            "handle": handle,
            "updated_at": now,
        }, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
        upsert=True,
    )

    return RedirectResponse(url=f"{PUBLIC_SITE_URL}/dashboard/channels?linkedin=connected", status_code=302)


@api.delete("/oauth/linkedin")
async def linkedin_disconnect(request: Request):
    """Disconnect the user's LinkedIn account."""
    user = await get_current_user(request)
    await db.linkedin_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "linkedin"},
        {"$set": {"connected": False, "handle": None, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


@api.get("/oauth/linkedin/status")
async def linkedin_status(request: Request):
    user = await get_current_user(request)
    conn = await db.linkedin_connections.find_one({"user_id": user.user_id}, {"_id": 0, "access_token": 0})
    return {
        "configured": bool(LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET),
        "connected": bool(conn),
        "connection": conn,
    }


# ==================== Publishing ====================

async def publish_to_linkedin(user_id: str, text: str) -> dict:
    """Post a text update to the user's LinkedIn feed. Returns dict with status."""
    conn = await db.linkedin_connections.find_one({"user_id": user_id})
    if not conn:
        return {"ok": False, "reason": "not_connected"}

    expires_at = conn["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return {"ok": False, "reason": "token_expired"}

    if not conn.get("person_urn"):
        return {"ok": False, "reason": "missing_person_urn"}

    payload = {
        "author": conn["person_urn"],
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {
        "Authorization": f"Bearer {conn['access_token']}",
        "Content-Type": "application/json",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    async with httpx.AsyncClient(timeout=20) as cli:
        r = await cli.post(LINKEDIN_POSTS_URL, json=payload, headers=headers)
    if r.status_code in (200, 201):
        post_id = r.headers.get("x-restli-id") or r.headers.get("X-RestLi-Id")
        return {"ok": True, "linkedin_post_id": post_id}
    logger.error("LinkedIn publish failed %s: %s", r.status_code, r.text[:400])
    return {"ok": False, "reason": "api_error", "status": r.status_code, "body": r.text[:400]}
