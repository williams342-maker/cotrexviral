"""WordPress self-hosted connector (Option A — HTTP Basic Auth via Application Passwords).

User provides:
  * site_url (https:// only — Basic Auth over plain HTTP is refused)
  * WordPress username
  * an Application Password generated at /wp-admin/profile.php

We verify by calling GET {site}/wp-json/wp/v2/users/me?context=edit,
encrypt the application password with Fernet, and persist the channel
row on db.channels keyed by (user_id, platform="wordpress_selfhosted").

The channel is picked up by routes.channels.publish() dispatch (like
LinkedIn / TikTok / Meta) — see publish_to_wordpress() at the bottom.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db, logger
from deps import get_current_user


# ---------------------------------------------------------------------------
# Fernet key loading. Supports either:
#   CORTEXVIRAL_WORDPRESS_FERNET_KEY   = <single key>
#   CORTEXVIRAL_WORDPRESS_FERNET_KEYS  = <newest>,<older>,...  (MultiFernet)
# ---------------------------------------------------------------------------

def _load_fernet() -> Fernet | MultiFernet:
    keys_str = os.environ.get("CORTEXVIRAL_WORDPRESS_FERNET_KEYS", "").strip()
    if keys_str:
        keys = [Fernet(k.strip().encode("utf-8")) for k in keys_str.split(",") if k.strip()]
        return MultiFernet(keys)
    single = os.environ.get("CORTEXVIRAL_WORDPRESS_FERNET_KEY", "").strip()
    if not single:
        raise RuntimeError(
            "WordPress connector cannot start: neither "
            "CORTEXVIRAL_WORDPRESS_FERNET_KEY nor "
            "CORTEXVIRAL_WORDPRESS_FERNET_KEYS is set."
        )
    return Fernet(single.encode("utf-8"))


_fernet = _load_fernet()


def _encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode("ascii")).decode("utf-8")


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

class WPCreds(BaseModel):
    site_url: str
    username: str
    application_password: str


class WPPublishPayload(BaseModel):
    title: str
    content: str
    status: str = "publish"                     # publish | draft | future
    date_gmt: Optional[datetime] = None         # required when status == "future"


# ---------------------------------------------------------------------------
# URL & role validation helpers
# ---------------------------------------------------------------------------

def _normalize_site_url(raw: str) -> str:
    """Trim trailing slashes and reject non-HTTPS URLs (Basic Auth over
    plain HTTP would expose the application password on the wire)."""
    if not raw:
        raise HTTPException(status_code=400, detail="site_url is required")
    url = raw.strip().rstrip("/")
    if not url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="WordPress site URL must start with https:// (Basic Auth over http:// is refused).",
        )
    return url


_AUTHOR_ROLES = {"administrator", "editor", "author"}


async def _wp_verify(creds: WPCreds) -> dict:
    """Call GET /wp-json/wp/v2/users/me?context=edit and return the user
    record. Raises HTTPException on any failure with a user-friendly message."""
    site = _normalize_site_url(creds.site_url)
    url = f"{site}/wp-json/wp/v2/users/me?context=edit"
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                auth=(creds.username, creds.application_password),
                headers={"Accept": "application/json"},
            )
    except httpx.ConnectError as e:
        raise HTTPException(status_code=400, detail=f"Could not reach WordPress site: {e}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="WordPress site timed out (12s).")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"HTTP error contacting WordPress: {e}")

    if resp.status_code == 401:
        raise HTTPException(status_code=400, detail="Invalid WordPress credentials (401). Double-check the username and Application Password.")
    if resp.status_code == 403:
        raise HTTPException(status_code=400, detail="WordPress refused the request (403). A security plugin may be blocking Basic Auth for this user.")
    if resp.status_code == 404:
        raise HTTPException(status_code=400, detail="WordPress REST API not found at /wp-json/wp/v2/users/me — is the REST API enabled?")
    if resp.status_code >= 500:
        raise HTTPException(status_code=502, detail=f"WordPress server error {resp.status_code}.")
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"WordPress rejected the request ({resp.status_code}): {resp.text[:200]}")

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=400, detail="WordPress returned a non-JSON response — the site may be behind a login wall.")

    wp_id = data.get("id")
    name = data.get("name") or data.get("username") or ""
    roles = data.get("roles") or []
    if not isinstance(wp_id, int):
        raise HTTPException(status_code=400, detail="WordPress response missing user id.")
    if not any(r in _AUTHOR_ROLES for r in roles):
        raise HTTPException(
            status_code=400,
            detail=f"WordPress user '{name}' has roles {roles!r} — needs administrator, editor, or author to publish posts.",
        )
    return {"id": wp_id, "name": name, "roles": roles, "site_url": site}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@api.post("/wordpress/test")
async def wordpress_test(payload: WPCreds, request: Request):
    """Verify credentials WITHOUT persisting anything. Used by the connect
    dialog to give the user a live 'Test connection' button before saving."""
    await get_current_user(request)
    info = await _wp_verify(payload)
    return {
        "ok": True,
        "wp_user_id":   info["id"],
        "wp_user_name": info["name"],
        "wp_roles":     info["roles"],
        "site_url":     info["site_url"],
    }


@api.post("/wordpress/connect")
async def wordpress_connect(payload: WPCreds, request: Request):
    """Verify credentials, encrypt the application password, upsert the
    channel row."""
    user = await get_current_user(request)

    # Platform kill-switch
    from routes.admin_settings import is_platform_enabled
    if not await is_platform_enabled("wordpress_selfhosted"):
        raise HTTPException(status_code=403, detail="The WordPress integration is temporarily disabled by the admin.")

    # Plan cap (only when this is a *new* connection, not a reconnect)
    existing = await db.channels.find_one(
        {"user_id": user.user_id, "platform": "wordpress_selfhosted", "connected": True},
    )
    if not existing:
        from routes.plans import assert_can_connect_channel
        await assert_can_connect_channel(user.user_id)

    info = await _wp_verify(payload)

    doc = {
        "user_id":     user.user_id,
        "platform":    "wordpress_selfhosted",
        "handle":      f"@{info['name'] or payload.username}".replace(" ", "_"),
        "connected":   True,
        "connected_at": datetime.now(timezone.utc),
        "site_url":    info["site_url"],
        "wp_username": payload.username,
        "wp_user_id":  info["id"],
        "wp_user_name": info["name"],
        "wp_roles":    info["roles"],
        "credentials": {
            "encrypted_app_password": _encrypt(payload.application_password),
        },
        "last_verified_at": datetime.now(timezone.utc),
    }
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": "wordpress_selfhosted"},
        {"$set": doc},
        upsert=True,
    )
    return {
        "ok": True,
        "site_url":     info["site_url"],
        "wp_user_id":   info["id"],
        "wp_user_name": info["name"],
        "wp_roles":     info["roles"],
    }


@api.get("/wordpress/status")
async def wordpress_status(request: Request):
    user = await get_current_user(request)
    doc = await db.channels.find_one(
        {"user_id": user.user_id, "platform": "wordpress_selfhosted"},
        {"_id": 0, "credentials": 0},   # never leak encrypted secret
    )
    if not doc:
        return {"connected": False}
    return {
        "connected":    bool(doc.get("connected")),
        "site_url":     doc.get("site_url"),
        "wp_user_name": doc.get("wp_user_name"),
        "wp_user_id":   doc.get("wp_user_id"),
        "wp_roles":     doc.get("wp_roles"),
        "connected_at": doc.get("connected_at"),
    }


# ---------------------------------------------------------------------------
# publish_to_wordpress() — called from routes.channels.publish() for
# platform "wordpress_selfhosted".
# ---------------------------------------------------------------------------

async def publish_to_wordpress(
    user_id: str,
    title: str,
    content_html: str,
    status: str = "publish",
    date_gmt: Optional[datetime] = None,
) -> dict:
    """Publish a WP post. Returns {ok, post_id, link, status} on success,
    or {ok: False, error} on failure (never raises — callers store the
    result on the post's dispatch field the same way LinkedIn does).
    """
    doc = await db.channels.find_one(
        {"user_id": user_id, "platform": "wordpress_selfhosted", "connected": True},
    )
    if not doc:
        return {"ok": False, "error": "WordPress channel not connected"}

    site_url    = doc.get("site_url")
    wp_username = doc.get("wp_username")
    enc         = (doc.get("credentials") or {}).get("encrypted_app_password")
    if not (site_url and wp_username and enc):
        return {"ok": False, "error": "WordPress channel is missing site_url / username / credentials"}

    try:
        app_password = _decrypt(enc)
    except InvalidToken:
        logger.exception("WordPress credential decryption failed")
        return {"ok": False, "error": "Stored credentials could not be decrypted (Fernet key rotated?)"}

    body: dict[str, object] = {
        "title":   title,
        "content": content_html,
        "status":  status if status in {"publish", "draft", "future"} else "publish",
    }
    if body["status"] == "future":
        if date_gmt is None:
            return {"ok": False, "error": "date_gmt is required when status='future'"}
        # WordPress expects an ISO 8601 GMT timestamp with a "Z" suffix.
        iso = date_gmt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        body["date_gmt"] = iso.replace("+00:00", "").rstrip("Z") + "Z"

    url = f"{site_url}/wp-json/wp/v2/posts"
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.post(
                url,
                json=body,
                auth=(wp_username, app_password),
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Network error publishing to WordPress: {e}"}

    if resp.status_code >= 400:
        return {
            "ok": False,
            "error": f"WordPress rejected the post ({resp.status_code}): {resp.text[:200]}",
        }

    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": "WordPress returned a non-JSON response after publish."}

    # Record last-publish so status/GUI can surface it.
    await db.channels.update_one(
        {"user_id": user_id, "platform": "wordpress_selfhosted"},
        {"$set": {"last_published_at": datetime.now(timezone.utc)}},
    )

    return {
        "ok":       True,
        "post_id":  data.get("id"),
        "link":     data.get("link"),
        "status":   data.get("status"),
    }
