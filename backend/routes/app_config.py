"""DB-backed runtime config for third-party API credentials.

Lets admins rotate keys (Meta, future Stripe variations, etc.) without a
redeploy. Each row is one secret under a known KEY. The collection is
admin-only — never exposed to regular users — and secrets are masked
when read back via the admin API (returns last 4 chars of the value
plus an `is_set` flag).

Resolution order on a `get_config()` call:
  1. DB row (if present and non-empty)
  2. Environment variable (legacy fallback, lets you migrate gradually)
  3. The `default` arg passed by the caller (e.g. for version strings)

Cache: 60-second TTL on the in-process cache, so admins see new keys take
effect within a minute without a backend restart, and we don't hit Mongo
on every OAuth start.
"""
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import require_admin, log_admin_action

logger = logging.getLogger(__name__)

# Which keys are allowed to be set via this surface. Hardcoded so a
# compromised admin session can't write arbitrary keys (e.g. flipping
# MONGO_URL would be catastrophic).
ALLOWED_KEYS: dict[str, dict] = {
    "META_APP_ID": {
        "label":       "Meta — App ID",
        "description": "Facebook app's numeric App ID (from developers.facebook.com → App Settings → Basic).",
        "secret":      False,
        "group":       "meta",
    },
    "META_APP_SECRET": {
        "label":       "Meta — App Secret",
        "description": "Facebook app's secret (32-char hex). Rotate via Meta dashboard if compromised.",
        "secret":      True,
        "group":       "meta",
    },
    "META_GRAPH_VERSION": {
        "label":       "Meta — Graph API Version",
        "description": "e.g. v22.0. Leave blank to use the default (v22.0).",
        "secret":      False,
        "group":       "meta",
    },
    "META_REDIRECT_URI": {
        "label":       "Meta — Redirect URI Override",
        "description": "Optional. Use to point OAuth at the preview backend during testing.",
        "secret":      False,
        "group":       "meta",
    },
    "IG_APP_ID": {
        "label":       "Instagram — App ID",
        "description": "Instagram-specific App ID (from developers.facebook.com → Instagram product → API setup). Falls back to META_APP_ID if blank.",
        "secret":      False,
        "group":       "meta",
    },
    "IG_APP_SECRET": {
        "label":       "Instagram — App Secret",
        "description": "Instagram-specific App Secret. Falls back to META_APP_SECRET if blank.",
        "secret":      True,
        "group":       "meta",
    },
    "YOUTUBE_CLIENT_ID": {
        "label":       "YouTube — OAuth Client ID",
        "description": "Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID (Web application). Required for YouTube channel sign-in + uploads.",
        "secret":      False,
        "group":       "youtube",
    },
    "YOUTUBE_CLIENT_SECRET": {
        "label":       "YouTube — OAuth Client Secret",
        "description": "The Client Secret shown next to the Client ID in Google Cloud Console. Rotate via the same screen if compromised.",
        "secret":      True,
        "group":       "youtube",
    },
    "YOUTUBE_REDIRECT_URI": {
        "label":       "YouTube — Redirect URI Override",
        "description": "Optional. Use to point OAuth at the preview backend during testing. Falls back to PUBLIC_SITE_URL when blank.",
        "secret":      False,
        "group":       "youtube",
    },
    "LINKEDIN_CLIENT_ID": {
        "label":       "LinkedIn — OAuth Client ID",
        "description": "LinkedIn developer app's Client ID (from linkedin.com/developers → My apps → Auth tab). Required for member sign-in + posting.",
        "secret":      False,
        "group":       "linkedin",
    },
    "LINKEDIN_CLIENT_SECRET": {
        "label":       "LinkedIn — OAuth Client Secret",
        "description": "The Primary client secret shown next to the Client ID. Rotate via the same screen if compromised.",
        "secret":      True,
        "group":       "linkedin",
    },
    "TIKTOK_CLIENT_KEY": {
        "label":       "TikTok — Client Key",
        "description": "TikTok developer app's Client Key (from developers.tiktok.com → My apps → app details). Required for Login + Content Posting.",
        "secret":      False,
        "group":       "tiktok",
    },
    "TIKTOK_CLIENT_SECRET": {
        "label":       "TikTok — Client Secret",
        "description": "The Client Secret shown next to the Client Key. Rotate via the same screen if compromised.",
        "secret":      True,
        "group":       "tiktok",
    },
    "TIKTOK_REDIRECT_URI": {
        "label":       "TikTok — Redirect URI Override",
        "description": "Optional. Use to point OAuth at the preview backend during testing. Falls back to PUBLIC_SITE_URL when blank.",
        "secret":      False,
        "group":       "tiktok",
    },
    "PINTEREST_APP_ID": {
        "label":       "Pinterest — App ID",
        "description": "Pinterest developer app's App ID (from developers.pinterest.com → My apps). Required for board sign-in + publishing pins.",
        "secret":      False,
        "group":       "pinterest",
    },
    "PINTEREST_APP_SECRET": {
        "label":       "Pinterest — App Secret",
        "description": "The App Secret shown next to the App ID. Rotate via the same screen if compromised.",
        "secret":      True,
        "group":       "pinterest",
    },
    "PINTEREST_REDIRECT_URI": {
        "label":       "Pinterest — Redirect URI Override",
        "description": "Optional. Use to point OAuth at the preview backend during testing. Falls back to PUBLIC_SITE_URL when blank.",
        "secret":      False,
        "group":       "pinterest",
    },
    "SENDGRID_API_KEY": {
        "label":       "SendGrid — API Key",
        "description": "Full Access API key from app.sendgrid.com → Settings → API Keys. Used as the primary provider for transactional + seller-lifecycle emails. Falls back to Mailtrap then Mailgun if missing.",
        "secret":      True,
        "group":       "sendgrid",
    },
    "SENDGRID_FROM": {
        "label":       "SendGrid — Sender",
        "description": "Verified sender address (e.g. 'CortexViral <hello@cortexviral.com>'). Must be authenticated via Sender Authentication in SendGrid before mail will deliver.",
        "secret":      False,
        "group":       "sendgrid",
    },
    "SENDGRID_WEBHOOK_VERIFY_KEY": {
        "label":       "SendGrid — Event Webhook Public Key",
        "description": "Base64 ECDSA public key from Settings → Mail Settings → Signed Event Webhook Requests. When set, /api/sendgrid/webhook verifies signatures. Optional but recommended in production.",
        "secret":      True,
        "group":       "sendgrid",
    },
    "SENDGRID_TEMPLATE_WELCOME": {
        "label":       "SendGrid — Welcome Template ID",
        "description": "Dynamic Template ID (starts with `d-`) for the welcome email sent when a seller becomes active. When set, SendGrid renders the template using dynamic data `{business_name, dashboard_url}`. When blank, the helper falls back to inline HTML.",
        "secret":      False,
        "group":       "sendgrid",
    },
    "SENDGRID_TEMPLATE_AUDIT": {
        "label":       "SendGrid — Audit Template ID",
        "description": "Dynamic Template ID for Phase-4 audit delivery. Dynamic data: `{business_name, audit_title, audit_summary, audit_score, audit_url}`.",
        "secret":      False,
        "group":       "sendgrid",
    },
    "SENDGRID_TEMPLATE_NUDGE": {
        "label":       "SendGrid — Nudge Template ID",
        "description": "Dynamic Template ID for the Phase-8 retention nudge email. Dynamic data: `{business_name, churn_score, dashboard_url}`.",
        "secret":      False,
        "group":       "sendgrid",
    },
    "SENDGRID_TEMPLATE_RECOVERY": {
        "label":       "SendGrid — Churn-Recovery Template ID",
        "description": "Dynamic Template ID for the Phase-8 churn-recovery email. Dynamic data: `{business_name, audit_title, audit_summary, audit_score, audit_url, churn_score}`.",
        "secret":      False,
        "group":       "sendgrid",
    },
}

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, Optional[str]]] = {}


def _validate_key(key: str) -> None:
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown config key: {key}")


async def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve a runtime config value. DB → env → default. Cached 60s."""
    if key not in ALLOWED_KEYS:
        logger.warning("get_config: refusing to look up unknown key %s", key)
        return os.environ.get(key, default)

    now = time.monotonic()
    cached = _cache.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    value: Optional[str] = None
    try:
        doc = await db.app_config.find_one({"key": key}, {"_id": 0, "value": 1})
        if doc and doc.get("value"):
            value = str(doc["value"])
    except Exception as exc:  # pragma: no cover
        logger.warning("get_config: DB lookup failed for %s — %s", key, exc)

    if not value:
        value = os.environ.get(key) or default

    _cache[key] = (now, value)
    return value


def invalidate_cache(key: Optional[str] = None) -> None:
    """Drop the cache so the next read hits Mongo. Called on every write."""
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)


def _mask(value: str, *, secret: bool) -> str:
    """Return a UI-safe preview. Secrets show only the last 4 chars."""
    if not value:
        return ""
    if not secret:
        return value
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * (len(value) - 4) + value[-4:]


# ---------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------
class ConfigSetRequest(BaseModel):
    key: str
    value: str


@api.get("/admin/app-config")
async def list_app_config(request: Request):
    """Return every allowed key, masked, with metadata. Admins use this
    to render the integrations panel. Never returns raw secrets."""
    user = await require_admin(request)

    docs = {}
    async for d in db.app_config.find({}, {"_id": 0}):
        docs[d["key"]] = d

    items = []
    for key, meta in ALLOWED_KEYS.items():
        doc = docs.get(key) or {}
        env_value = os.environ.get(key) or ""
        db_value = doc.get("value") or ""
        effective = db_value or env_value
        items.append({
            "key":          key,
            "label":        meta["label"],
            "description":  meta["description"],
            "group":        meta["group"],
            "secret":       meta["secret"],
            "is_set":       bool(effective),
            "source":       "database" if db_value else ("environment" if env_value else "unset"),
            "preview":      _mask(effective, secret=meta["secret"]),
            "updated_at":   doc.get("updated_at"),
            "updated_by":   doc.get("updated_by"),
        })

    return {"items": items, "count_set": sum(1 for it in items if it["is_set"])}


@api.put("/admin/app-config")
async def set_app_config(payload: ConfigSetRequest, request: Request):
    """Upsert one config key. Value is stored in plaintext — Mongo's
    encryption-at-rest is relied on for storage security."""
    user = await require_admin(request)
    _validate_key(payload.key)

    value = (payload.value or "").strip()
    now = datetime.now(timezone.utc)

    if not value:
        # Empty value means "use env / default". Clear the row.
        await db.app_config.delete_one({"key": payload.key})
        invalidate_cache(payload.key)
        await log_admin_action(user, "app_config_cleared", details={"key": payload.key})
        return {"ok": True, "cleared": True}

    await db.app_config.update_one(
        {"key": payload.key},
        {
            "$set": {
                "key":        payload.key,
                "value":      value,
                "updated_at": now,
                "updated_by": getattr(user, "email", None) or getattr(user, "user_id", None),
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    invalidate_cache(payload.key)
    await log_admin_action(user, "app_config_set", details={"key": payload.key})
    return {"ok": True, "cleared": False}


@api.delete("/admin/app-config/{key}")
async def delete_app_config(key: str, request: Request):
    user = await require_admin(request)
    _validate_key(key)
    res = await db.app_config.delete_one({"key": key})
    invalidate_cache(key)
    await log_admin_action(user, "app_config_cleared", details={"key": key})
    return {"ok": True, "deleted": res.deleted_count}
