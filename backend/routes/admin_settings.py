"""Admin-controlled system settings.

Two switches, persisted as a single doc in `system_settings`:

  - **signups_enabled**: when False, new Google-Auth signups are blocked
    (return 503 from `/api/auth/session` for first-time emails). Existing users
    can still log in. Admin-created accounts (magic-link path) + lead-form
    auto-create always work — admins can still onboard people manually.

  - **disabled_platforms**: list of platform IDs the admin has switched off
    globally. `POST /api/channels/connect` rejects with 403 when the platform
    is on the list. The frontend hides these from the catalog as well.

Settings are read-cached in-process (5-second TTL) so the hot path doesn't
hit Mongo on every connect/signup, but stay fresh enough that an admin's
toggle is visible to users near-instantly.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import db, api
from deps import require_admin, log_admin_action


SETTINGS_DOC_ID = "global"
_CACHE: dict = {"data": None, "expires_at": 0.0}
_CACHE_TTL_SECONDS = 5.0


# Default settings — used the first time the admin loads the page, or if Mongo
# is empty. signups ON, no platforms disabled.
_DEFAULTS = {
    "signups_enabled": True,
    "disabled_platforms": [],
}


async def get_settings() -> dict:
    """Returns the current settings doc, applying defaults for missing keys.
    Cached in-process for `_CACHE_TTL_SECONDS` to keep hot paths cheap."""
    now = time.monotonic()
    if _CACHE["data"] is not None and _CACHE["expires_at"] > now:
        return _CACHE["data"]
    doc = await db.system_settings.find_one({"_id": SETTINGS_DOC_ID})
    data = {**_DEFAULTS, **(doc or {})}
    data.pop("_id", None)
    _CACHE["data"] = data
    _CACHE["expires_at"] = now + _CACHE_TTL_SECONDS
    return data


def _invalidate_cache():
    _CACHE["data"] = None
    _CACHE["expires_at"] = 0.0


async def is_platform_enabled(platform: str) -> bool:
    s = await get_settings()
    return platform not in (s.get("disabled_platforms") or [])


async def are_signups_enabled() -> bool:
    s = await get_settings()
    return bool(s.get("signups_enabled", True))


# -----------------------------------------------------------------------------
# Admin endpoints
# -----------------------------------------------------------------------------
@api.get("/admin/settings")
async def admin_get_settings(request: Request):
    await require_admin(request)
    return await get_settings()


class _SettingsUpdate(BaseModel):
    signups_enabled: Optional[bool] = None
    disabled_platforms: Optional[List[str]] = Field(None, max_length=200)


@api.patch("/admin/settings")
async def admin_update_settings(payload: _SettingsUpdate, request: Request):
    admin = await require_admin(request)
    update = {}
    if payload.signups_enabled is not None:
        update["signups_enabled"] = bool(payload.signups_enabled)
    if payload.disabled_platforms is not None:
        # Dedupe + sort for stable diffs in the audit log.
        update["disabled_platforms"] = sorted({p.strip() for p in payload.disabled_platforms if p and p.strip()})
    if not update:
        return await get_settings()

    update["updated_at"] = datetime.now(timezone.utc)
    update["updated_by"] = admin.user_id
    await db.system_settings.update_one(
        {"_id": SETTINGS_DOC_ID},
        {"$set": update},
        upsert=True,
    )
    _invalidate_cache()
    await log_admin_action(
        admin, "update_system_settings",
        details={k: v for k, v in update.items()
                 if k not in {"updated_at", "updated_by"}},
    )
    return await get_settings()


# -----------------------------------------------------------------------------
# Public read endpoint — used by the SPA to hide disabled platforms in the
# Integrations catalog and to show a "signups paused" banner if needed.
# Returns ONLY the user-safe fields (no admin metadata).
# -----------------------------------------------------------------------------
@api.get("/system/settings")
async def public_system_settings():
    s = await get_settings()
    return {
        "signups_enabled": s.get("signups_enabled", True),
        "disabled_platforms": s.get("disabled_platforms") or [],
    }
