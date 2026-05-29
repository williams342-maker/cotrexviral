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
)
from deps import get_current_user
from routes.app_config import get_config


# Module-level constants that the OAuth code reads lazily via accessor
# helpers. Direct env imports are deprecated — use `get_config()` so admins
# can rotate keys via /admin/app-config without a redeploy.
async def _meta_app_id() -> str:
    return (await get_config("META_APP_ID")) or ""


async def _meta_app_secret() -> str:
    return (await get_config("META_APP_SECRET")) or ""


async def _ig_app_id() -> str:
    """Instagram-specific App ID. Falls back to META_APP_ID for users who
    haven't created a separate Instagram app."""
    return (await get_config("IG_APP_ID")) or (await get_config("META_APP_ID")) or ""


async def _ig_app_secret() -> str:
    return (await get_config("IG_APP_SECRET")) or (await get_config("META_APP_SECRET")) or ""


async def _app_id_for(provider: str) -> str:
    return await (_ig_app_id() if provider == "instagram" else _meta_app_id())


async def _app_secret_for(provider: str) -> str:
    return await (_ig_app_secret() if provider == "instagram" else _meta_app_secret())


async def _meta_graph_version() -> str:
    return (await get_config("META_GRAPH_VERSION", default="v22.0")) or "v22.0"


async def _meta_redirect_override() -> str:
    return (await get_config("META_REDIRECT_URI")) or ""


# Authorize URL (versioned). Same endpoint for both FB and IG — only scope diff.
async def _dialog_url() -> str:
    return f"https://www.facebook.com/{await _meta_graph_version()}/dialog/oauth"


async def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{await _meta_graph_version()}/{path.lstrip('/')}"


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


async def _redirect_uri(provider: str) -> str:
    """Where Meta sends the browser after the user authorises.

    Priority:
      1. META_REDIRECT_URI override (from DB or env) — treat the value as
         a BASE host (or any URL whose host we should reuse) and inject
         the per-provider path. Lets one value cover both facebook + instagram.
      2. Fall back to PUBLIC_SITE_URL + provider path (production default).
    """
    override = await _meta_redirect_override()
    if override:
        from urllib.parse import urlparse
        parsed = urlparse(override)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}/api/oauth/{provider}/callback"
    return f"{PUBLIC_SITE_URL}/api/oauth/{provider}/callback"


async def _post_oauth_redirect(provider: str, query: str) -> str:
    base = (await _redirect_uri(provider)).split(f"/api/oauth/{provider}/callback")[0]
    return f"{base}/dashboard/channels?{query}"


async def _check_configured(provider: str = "facebook"):
    if not (await _app_id_for(provider)) or not (await _app_secret_for(provider)):
        raise HTTPException(
            status_code=503,
            detail=(
                f"{provider.title()} OAuth not configured. Set credentials "
                "via /admin/integrations or in /app/backend/.env."
            ),
        )


# --- /start ------------------------------------------------------------------

async def _start_oauth(request: Request, provider: str, scopes: List[str]) -> dict:
    user = await get_current_user(request)
    await _check_configured(provider)
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "_id": state,
        "provider": provider,
        "user_id": user.user_id,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    params = {
        "client_id": await _app_id_for(provider),
        "redirect_uri": await _redirect_uri(provider),
        "state": state,
        "response_type": "code",
        "scope": ",".join(scopes),
        # `auth_type=rerequest` lets the user re-grant a previously-declined
        # permission without the consent dialog being silently skipped.
        "auth_type": "rerequest",
    }
    return {"authorize_url": f"{await _dialog_url()}?{urlencode(params)}"}


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
    app_id = await _app_id_for(provider)
    app_secret = await _app_secret_for(provider)
    async with httpx.AsyncClient(timeout=20) as cli:
        # 1. Short-lived user token
        short = await cli.get(await _graph_url("oauth/access_token"), params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": await _redirect_uri(provider),
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
        lng = await cli.get(await _graph_url("oauth/access_token"), params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
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
        r = await cli.get(await _graph_url("me/accounts"), params={
            "access_token": user_token,
            "fields": "id,name,access_token,category,tasks",
        })
        if r.status_code != 200:
            logger.error("Meta /me/accounts failed: %s %s", r.status_code, r.text[:300])
            return []
        return r.json().get("data", []) or []


async def _fetch_fb_user_id(user_token: str) -> str:
    """Returns the user's Facebook **app-scoped** user_id. Same id Meta
    sends in the data-deletion-callback signed_request, so we can map
    a deletion-request payload back to the right `*_connections` row."""
    async with httpx.AsyncClient(timeout=10) as cli:
        r = await cli.get(await _graph_url("me"), params={
            "access_token": user_token,
            "fields": "id",
        })
        if r.status_code != 200:
            logger.warning("Meta /me failed: %s %s", r.status_code, r.text[:300])
            return ""
        return (r.json() or {}).get("id", "") or ""


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
            r = await cli.get(await _graph_url(page_id), params={
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
        return RedirectResponse(await _post_oauth_redirect("facebook", "facebook=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "facebook"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    await _check_configured("facebook")
    tok = await _exchange_code(code, "facebook")
    user_token = tok["access_token"]
    expires_in = int(tok.get("expires_in", 60 * 24 * 3600))

    pages = await _fetch_pages(user_token)
    fb_user_id = await _fetch_fb_user_id(user_token)
    now = datetime.now(timezone.utc)
    handle = pages[0]["name"] if pages else "Facebook"

    await db.facebook_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "fb_user_id": fb_user_id,
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
    return RedirectResponse(await _post_oauth_redirect("facebook", "facebook=connected"), 302)


@api.api_route("/oauth/instagram/callback", methods=["GET", "HEAD"])
async def instagram_callback(request: Request, code: str = "", state: str = "",
                             error: str = "", error_description: str = ""):
    if not code and not error and request.method == "HEAD":
        return {"ok": True}
    if error:
        logger.info("Instagram callback denied: %s — %s", error, error_description)
        return RedirectResponse(await _post_oauth_redirect("instagram", "instagram=denied"), 302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code/state")

    state_doc = await db.oauth_states.find_one({"_id": state, "provider": "instagram"})
    if not state_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    user_id = state_doc["user_id"]
    await db.oauth_states.delete_one({"_id": state})

    await _check_configured("instagram")
    tok = await _exchange_code(code, "instagram")
    user_token = tok["access_token"]
    expires_in = int(tok.get("expires_in", 60 * 24 * 3600))

    pages = await _fetch_pages(user_token)
    ig_accounts = await _resolve_instagram_accounts(pages)
    fb_user_id = await _fetch_fb_user_id(user_token)

    now = datetime.now(timezone.utc)
    if not ig_accounts:
        # No linked Instagram Business account — friendly error so the user
        # knows what to fix on Meta's side instead of a silent "Connected".
        logger.info("Instagram OAuth: user %s has no IG Business account linked", user_id)
        return RedirectResponse(
            await _post_oauth_redirect("instagram", "instagram=no_business_account"), 302,
        )

    handle = f"@{ig_accounts[0]['ig_username']}" if ig_accounts[0].get("ig_username") else "Instagram"

    await db.instagram_connections.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "fb_user_id": fb_user_id,
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
    return RedirectResponse(await _post_oauth_redirect("instagram", "instagram=connected"), 302)


# --- /status -----------------------------------------------------------------

@api.get("/oauth/facebook/status")
async def facebook_status(request: Request):
    user = await get_current_user(request)
    conn = await db.facebook_connections.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "user_access_token": 0,
         "pages.access_token": 0},  # strip secrets from the response
    )
    is_configured = bool(await _meta_app_id() and await _meta_app_secret())
    return {
        "configured": is_configured,
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
    is_configured = bool(await _meta_app_id() and await _meta_app_secret())
    return {
        "configured": is_configured,
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


# ===========================================================================
# Publishing helpers — called from routes/channels.py + routes/scheduler.py
# ===========================================================================

# Facebook + Instagram captions can be very long, but Pages prefer concise
# posts and Instagram tops out at 2,200 chars. We trim with `…` on overflow
# to avoid a 400 from the Graph API.
FB_TEXT_LIMIT = 5000
IG_CAPTION_LIMIT = 2200


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def publish_to_facebook(user_id: str, text: str, *,
                              image_url: str | None = None,
                              page_id: str | None = None) -> dict:
    """Post to the user's Facebook Page. Returns {ok, post_id, permalink} or
    a structured failure dict matching the other publish_to_* helpers.

    Routes through `/{page_id}/feed` for text/link posts, or `/{page_id}/photos`
    when an image_url is supplied. If `page_id` is not specified, posts to
    the user's first connected Page.
    """
    conn = await db.facebook_connections.find_one({"user_id": user_id}, {"_id": 0})
    if not conn or not (conn.get("pages") or []):
        return {"ok": False, "reason": "not_connected"}

    pages = conn["pages"]
    target = None
    if page_id:
        target = next((p for p in pages if p.get("id") == page_id), None)
        if not target:
            return {"ok": False, "reason": "page_not_found"}
    else:
        target = pages[0]
    page_token = target.get("access_token")
    pg_id = target.get("id")
    if not page_token or not pg_id:
        return {"ok": False, "reason": "missing_page_token"}

    body_text = _trim(text, FB_TEXT_LIMIT)
    async with httpx.AsyncClient(timeout=30) as cli:
        if image_url:
            r = await cli.post(await _graph_url(f"{pg_id}/photos"), data={
                "url": image_url,
                "caption": body_text,
                "access_token": page_token,
            })
        else:
            r = await cli.post(await _graph_url(f"{pg_id}/feed"), data={
                "message": body_text,
                "access_token": page_token,
            })
    if r.status_code not in (200, 201):
        logger.warning("Facebook publish failed for %s: %s %s",
                       user_id, r.status_code, r.text[:300])
        return {"ok": False, "reason": "api_error",
                "status": r.status_code, "body": r.text[:400]}

    data = r.json() or {}
    # /feed returns {id: "pageid_postid"}; /photos returns {id, post_id}
    fb_post_id = data.get("post_id") or data.get("id")
    return {
        "ok": True,
        "post_id": fb_post_id,
        "page_id": pg_id,
        "permalink": (f"https://www.facebook.com/{fb_post_id}"
                      if fb_post_id else None),
    }


async def publish_to_instagram(user_id: str, text: str, *,
                               image_url: str | None = None,
                               ig_user_id: str | None = None) -> dict:
    """Two-step IG Graph publish: create container → /media_publish.

    Instagram REQUIRES an image_url for feed posts — there is no
    text-only IG post via the API. We return a clear `instagram_requires_image_url`
    failure so the Compose UI can surface a friendly message.
    """
    if not image_url:
        return {"ok": False, "reason": "instagram_requires_image_url"}

    conn = await db.instagram_connections.find_one({"user_id": user_id}, {"_id": 0})
    if not conn or not (conn.get("ig_accounts") or []):
        return {"ok": False, "reason": "not_connected"}

    accounts = conn["ig_accounts"]
    target = None
    if ig_user_id:
        target = next((a for a in accounts if a.get("ig_user_id") == ig_user_id), None)
        if not target:
            return {"ok": False, "reason": "ig_account_not_found"}
    else:
        target = accounts[0]

    target_ig = target.get("ig_user_id")
    # Look up the matching Page access token (IG publish uses the Page token).
    page_id = target.get("page_id")
    page_token = None
    for p in (conn.get("pages") or []):
        if p.get("id") == page_id:
            page_token = p.get("access_token")
            break
    if not page_token or not target_ig:
        return {"ok": False, "reason": "missing_credentials"}

    caption = _trim(text, IG_CAPTION_LIMIT)
    async with httpx.AsyncClient(timeout=60) as cli:
        # Step 1: create media container
        c = await cli.post(await _graph_url(f"{target_ig}/media"), data={
            "image_url": image_url,
            "caption": caption,
            "access_token": page_token,
        })
        if c.status_code not in (200, 201):
            logger.warning("Instagram media container failed for %s: %s %s",
                           user_id, c.status_code, c.text[:300])
            return {"ok": False, "reason": "container_failed",
                    "status": c.status_code, "body": c.text[:400]}
        creation_id = (c.json() or {}).get("id")
        if not creation_id:
            return {"ok": False, "reason": "no_creation_id"}

        # Step 2: publish the container
        p = await cli.post(await _graph_url(f"{target_ig}/media_publish"), data={
            "creation_id": creation_id,
            "access_token": page_token,
        })
        if p.status_code not in (200, 201):
            logger.warning("Instagram media_publish failed for %s: %s %s",
                           user_id, p.status_code, p.text[:300])
            return {"ok": False, "reason": "publish_failed",
                    "status": p.status_code, "body": p.text[:400]}
        ig_post_id = (p.json() or {}).get("id")

    return {
        "ok": True,
        "post_id": ig_post_id,
        "ig_user_id": target_ig,
        "permalink": (f"https://www.instagram.com/p/{ig_post_id}"
                      if ig_post_id else None),
    }


# ---------------------------------------------------------------------------
# Analytics — Graph API /{post-id}/insights
# ---------------------------------------------------------------------------
async def fetch_facebook_post_metrics(user_id: str, fb_post_id: str) -> dict | None:
    """Returns {impressions, engaged_users, reactions, fetched_at} for a
    Facebook Page post. Uses /{post-id}/insights with the standard metric
    suite that any Page can read with `read_insights` scope."""
    if not fb_post_id:
        return None
    conn = await db.facebook_connections.find_one({"user_id": user_id}, {"_id": 0})
    if not conn or not (conn.get("pages") or []):
        return None
    # FB post IDs are of the form "{page_id}_{post_id}" — extract the page
    # to find the right page token.
    page_id_from_post = fb_post_id.split("_", 1)[0] if "_" in fb_post_id else None
    page_token = None
    for p in conn["pages"]:
        if p.get("id") == page_id_from_post or len(conn["pages"]) == 1:
            page_token = p.get("access_token")
            break
    if not page_token:
        return None

    params = {
        "metric": "post_impressions,post_engaged_users,post_reactions_by_type_total",
        "access_token": page_token,
    }
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(await _graph_url(f"{fb_post_id}/insights"), params=params)
    if r.status_code != 200:
        logger.info("Facebook analytics %s for %s: %s", r.status_code, fb_post_id, r.text[:200])
        return None
    data = (r.json() or {}).get("data") or []
    out = {"impressions": 0, "engaged_users": 0, "reactions": 0}
    for row in data:
        name = row.get("name")
        values = row.get("values") or []
        val = values[0].get("value") if values else 0
        if name == "post_impressions":
            out["impressions"] = int(val or 0)
        elif name == "post_engaged_users":
            out["engaged_users"] = int(val or 0)
        elif name == "post_reactions_by_type_total":
            # `value` here is a dict like {"like": 12, "love": 3, ...}
            if isinstance(val, dict):
                out["reactions"] = int(sum(int(v or 0) for v in val.values()))
    out["fetched_at"] = datetime.now(timezone.utc)
    return out


async def fetch_instagram_post_metrics(user_id: str, ig_media_id: str) -> dict | None:
    """Returns {impressions, reach, saved, likes, comments, fetched_at} for
    an IG Business / Creator post. Uses /{media-id}/insights."""
    if not ig_media_id:
        return None
    conn = await db.instagram_connections.find_one({"user_id": user_id}, {"_id": 0})
    if not conn or not (conn.get("pages") or []):
        return None
    # Use the first connected Page token — IG media is owned by exactly one
    # Page within the user's connection so this is safe.
    page_token = (conn["pages"][0] or {}).get("access_token")
    if not page_token:
        return None

    params = {
        "metric": "impressions,reach,saved,likes,comments",
        "access_token": page_token,
    }
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(await _graph_url(f"{ig_media_id}/insights"), params=params)
    if r.status_code != 200:
        logger.info("Instagram analytics %s for %s: %s", r.status_code, ig_media_id, r.text[:200])
        return None
    data = (r.json() or {}).get("data") or []
    out = {"impressions": 0, "reach": 0, "saved": 0, "likes": 0, "comments": 0}
    for row in data:
        name = row.get("name")
        values = row.get("values") or []
        val = values[0].get("value") if values else 0
        if name in out:
            out[name] = int(val or 0)
    out["fetched_at"] = datetime.now(timezone.utc)
    return out
