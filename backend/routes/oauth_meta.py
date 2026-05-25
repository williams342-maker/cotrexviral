"""Meta OAuth (Facebook Pages + Instagram Graph API) — shared OAuth surface.

Both Facebook publishing and Instagram-Business publishing go through the SAME
Meta app via Facebook Login. The only difference is the scope set and the
post-callback work:

  - Facebook: store long-lived user token + the Pages the user manages (each
    has its own non-expiring Page access token) → publish to /{page_id}/feed.

  - Instagram: same long-lived user token + the Pages, then resolve each
    Page's linked `instagram_business_account` → publish via the IG container
    pattern (/{ig_user_id}/media + /media_publish).

We expose the same four-endpoint shape as oauth_tiktok and oauth_linkedin —
one set per provider, sharing the underlying token logic:

  GET    /api/oauth/facebook/start        →  authorize URL
  GET    /api/oauth/facebook/callback     →  exchange + persist
  GET    /api/oauth/facebook/status       →  {configured, connected, pages}
  DELETE /api/oauth/facebook              →  disconnect

  GET    /api/oauth/instagram/start
  GET    /api/oauth/instagram/callback
  GET    /api/oauth/instagram/status      →  {configured, connected, ig_accounts}
  DELETE /api/oauth/instagram

Required env vars (/app/backend/.env):
  META_APP_ID=...
  META_APP_SECRET=...
  PUBLIC_SITE_URL=https://cortexviral.com

Meta developer-portal checklist:
  • Add product: Facebook Login (for both flows)
  • Add product: Instagram (Business Login / Graph API) — same app
  • Valid OAuth redirect URIs (paste BOTH, exact match):
      https://cortexviral.com/api/oauth/facebook/callback
      https://cortexviral.com/api/oauth/instagram/callback
  • App Domains: cortexviral.com
  • Privacy / Terms / Data Deletion URLs: already wired (see /privacy, /terms,
    /data-deletion).
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from core import (
    db, api, logger,
    PUBLIC_SITE_URL,
    META_APP_ID, META_APP_SECRET, META_GRAPH_VERSION,
    META_REDIRECT_URI_OVERRIDE,
)
from deps import get_current_user


# Authorize URL (versioned). Same endpoint for both FB and IG — only scope diff.
def _dialog_url() -> str:
    return f"https://www.facebook.com/{META_GRAPH_VERSION}/dialog/oauth"


def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{META_GRAPH_VERSION}/{path.lstrip('/')}"


# Scope sets — strictly the minimum needed for our publishing use cases.
# Reviewers will reject app review submissions that ask for more than required.
FACEBOOK_SCOPES = [
    "public_profile",
    "email",
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
]
INSTAGRAM_SCOPES = [
    "public_profile",
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
]


def _redirect_uri(provider: str) -> str:
    """Where Meta sends the browser after the user authorises.

    Priority: META_REDIRECT_URI env override → PUBLIC_SITE_URL + provider path.
    The override is per-provider via suffix matching — keep one Meta app per
    deployment to avoid confusion.
    """
    if META_REDIRECT_URI_OVERRIDE and provider in META_REDIRECT_URI_OVERRIDE:
        return META_REDIRECT_URI_OVERRIDE
    return f"{PUBLIC_SITE_URL}/api/oauth/{provider}/callback"


def _post_oauth_redirect(provider: str, query: str) -> str:
    base = _redirect_uri(provider).split(f"/api/oauth/{provider}/callback")[0]
    return f"{base}/dashboard/channels?{query}"


def _check_configured():
    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Meta OAuth not configured. Set META_APP_ID and META_APP_SECRET "
                "in /app/backend/.env."
            ),
        )


# --- /start ------------------------------------------------------------------

async def _start_oauth(request: Request, provider: str, scopes: List[str]) -> dict:
    user = await get_current_user(request)
    _check_configured()
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": provider,
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": _redirect_uri(provider),
        "state": state,
        "response_type": "code",
        "scope": ",".join(scopes),
        # `auth_type=rerequest` lets the user re-grant a previously-declined
        # permission without the consent dialog being silently skipped.
        "auth_type": "rerequest",
    }
    return {"authorize_url": f"{_dialog_url()}?{urlencode(params)}"}


@api.get("/oauth/facebook/start")
async def facebook_start(request: Request):
    return await _start_oauth(request, "facebook", FACEBOOK_SCOPES)


@api.get("/oauth/instagram/start")
async def instagram_start(request: Request):
    return await _start_oauth(request, "instagram", INSTAGRAM_SCOPES)


# --- /callback ---------------------------------------------------------------

async def _exchange_code(code: str, provider: str) -> dict:
    """Exchanges an authorization code for a long-lived user token.

    Returns the long-lived token payload (access_token, expires_in).
    """
    async with httpx.AsyncClient(timeout=20) as cli:
        # 1. Short-lived user token
        short = await cli.get(_graph_url("oauth/access_token"), params={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": _redirect_uri(provider),
            "code": code,
        })
        if short.status_code != 200:
            logger.error("Meta short-token exchange failed (%s): %s %s",
                         provider, short.status_code, short.text[:300])
            raise HTTPException(status_code=502, detail="Meta token exchange failed")
        short_tok = short.json().get("access_token")
        if not short_tok:
            raise HTTPException(status_code=502, detail="No access_token in Meta response")

        # 2. Upgrade to long-lived (~60d expiry).
        lng = await cli.get(_graph_url("oauth/access_token"), params={
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "fb_exchange_token": short_tok,
        })
        if lng.status_code != 200:
            logger.error("Meta long-token exchange failed (%s): %s %s",
                         provider, lng.status_code, lng.text[:300])
            raise HTTPException(status_code=502, detail="Meta long-token exchange failed")
        return lng.json()


async def _fetch_pages(user_token: str) -> list[dict]:
    """Returns the list of Pages the user manages, each with its Page access
    token (which typically never expires) and basic metadata."""
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(_graph_url("me/accounts"), params={
            "access_token": user_token,
            "fields": "id,name,access_token,category,tasks",
        })
        if r.status_code != 200:
            logger.error("Meta /me/accounts failed: %s %s", r.status_code, r.text[:300])
            return []
        return r.json().get("data", []) or []


async def _resolve_instagram_accounts(pages: list[dict]) -> list[dict]:
    """For each Page, ask Graph API for the linked instagram_business_account.
    Returns a list of {page_id, ig_user_id, ig_username} for Pages that have
    a linked IG professional account."""
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=15) as cli:
        for page in pages:
            page_id = page.get("id")
            page_token = page.get("access_token")
            if not page_id or not page_token:
                continue
            r = await cli.get(_graph_url(page_id), params={
                "fields": "instagram_business_account{id,username}",
                "access_token": page_token,
            })
            if r.status_code != 200:
                continue
            ig = (r.json() or {}).get("instagram_business_account")
            if ig and ig.get("id"):
                out.append({
                    "page_id": page_id,
                    "page_name": page.get("name"),
                    "ig_user_id": ig["id"],
                    "ig_username": ig.get("username"),
                })
    return out


@api.api_route("/oauth/facebook/callback", methods=["GET", "HEAD"])
async def facebook_callback(request: Request, code: str = "", state: str = "",
                            error: str = "", error_description: str = ""):
    if not code and not error and request.method == "HEAD":
        return {"ok": True}
    if error:
        logger.info("Facebook callback denied: %s — %s", error, error_description)
        return RedirectResponse(_post_oauth_redirect("facebook", "facebook=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "facebook"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    _check_configured()
    tok = await _exchange_code(code, "facebook")
    user_token = tok["access_token"]
    expires_in = int(tok.get("expires_in", 60 * 24 * 3600))

    pages = await _fetch_pages(user_token)
    now = datetime.now(timezone.utc)
    handle = pages[0]["name"] if pages else "Facebook"

    await db.facebook_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "user_access_token": user_token,
                "user_token_expires_at": now + timedelta(seconds=expires_in),
                "pages": pages,  # each includes its own Page access_token
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    await db.channels.update_one(
        {"user_id": user_id, "platform": "facebook"},
        {
            "$set": {
                "user_id": user_id, "platform": "facebook",
                "connected": True, "handle": handle,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    return RedirectResponse(_post_oauth_redirect("facebook", "facebook=connected"), 302)


@api.api_route("/oauth/instagram/callback", methods=["GET", "HEAD"])
async def instagram_callback(request: Request, code: str = "", state: str = "",
                             error: str = "", error_description: str = ""):
    if not code and not error and request.method == "HEAD":
        return {"ok": True}
    if error:
        logger.info("Instagram callback denied: %s — %s", error, error_description)
        return RedirectResponse(_post_oauth_redirect("instagram", "instagram=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "instagram"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    _check_configured()
    tok = await _exchange_code(code, "instagram")
    user_token = tok["access_token"]
    expires_in = int(tok.get("expires_in", 60 * 24 * 3600))

    pages = await _fetch_pages(user_token)
    ig_accounts = await _resolve_instagram_accounts(pages)

    now = datetime.now(timezone.utc)
    if not ig_accounts:
        # No linked Instagram Business account — friendly error so the user
        # knows what to fix on Meta's side instead of a silent "Connected".
        logger.info("Instagram OAuth: user %s has no IG Business account linked", user_id)
        return RedirectResponse(
            _post_oauth_redirect("instagram", "instagram=no_business_account"), 302,
        )

    handle = f"@{ig_accounts[0]['ig_username']}" if ig_accounts[0].get("ig_username") else "Instagram"

    await db.instagram_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "user_access_token": user_token,
                "user_token_expires_at": now + timedelta(seconds=expires_in),
                "pages": pages,
                "ig_accounts": ig_accounts,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    await db.channels.update_one(
        {"user_id": user_id, "platform": "instagram"},
        {
            "$set": {
                "user_id": user_id, "platform": "instagram",
                "connected": True, "handle": handle,
                "updated_at": now,
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    return RedirectResponse(_post_oauth_redirect("instagram", "instagram=connected"), 302)


# --- /status -----------------------------------------------------------------

@api.get("/oauth/facebook/status")
async def facebook_status(request: Request):
    user = await get_current_user(request)
    conn = await db.facebook_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "user_access_token": 0,
         "pages.access_token": 0},  # strip secrets from the response
    )
    return {
        "configured": bool(META_APP_ID and META_APP_SECRET),
        "connected": bool(conn),
        "pages": (conn or {}).get("pages", []),
        "expires_at": (conn or {}).get("user_token_expires_at"),
    }


@api.get("/oauth/instagram/status")
async def instagram_status(request: Request):
    user = await get_current_user(request)
    conn = await db.instagram_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "user_access_token": 0,
         "pages.access_token": 0},
    )
    return {
        "configured": bool(META_APP_ID and META_APP_SECRET),
        "connected": bool(conn),
        "ig_accounts": (conn or {}).get("ig_accounts", []),
        "expires_at": (conn or {}).get("user_token_expires_at"),
    }


# --- /disconnect -------------------------------------------------------------

@api.delete("/oauth/facebook")
async def facebook_disconnect(request: Request):
    user = await get_current_user(request)
    await db.facebook_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "facebook"},
        {"$set": {"connected": False, "handle": None,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


@api.delete("/oauth/instagram")
async def instagram_disconnect(request: Request):
    user = await get_current_user(request)
    await db.instagram_connections.delete_one({"user_id": user.user_id})
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "instagram"},
        {"$set": {"connected": False, "handle": None,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}
