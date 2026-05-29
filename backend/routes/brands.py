"""Brand lookup / auto-create helpers.

Idempotent: calling `ensure_default_brand_for_user(user_id)` is safe
to invoke many times — the first call creates the brand, every call
after returns the same brand_id. Used by:

  • Signup flow (`routes/auth.py`) — fires for every new user.
  • Migration script (`migrations/normalize_001.py`) — backfills brands
    for the 8 existing users.
  • Any future code path that needs `brand_id` on demand.

Why a separate module
---------------------
Putting this on `models_normalized` would force a `db` import there
and entangle the schema definitions with runtime logic. Keeping it
isolated means tests can monkey-patch the helper without touching
the models, and Phase 2 writer code can `from routes.brands import …`
without a circular import.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from core import db

logger = logging.getLogger(__name__)


async def ensure_default_brand_for_user(user_id: str, *, name_hint: Optional[str] = None) -> str:
    """Returns the user's default brand_id. Creates one if it doesn't exist.

    `name_hint` is the user's display name (e.g. "Mike Williams") so the
    auto-created brand is "Mike Williams's Brand" — friendlier than a
    UUID. Falls back to "My Brand" when no hint is provided.

    Concurrency: Mongo's `find_one_and_update` with `upsert=True` would
    be cleaner but doesn't return the inserted doc atomically across
    drivers. The two-step find→insert pattern below is racy in theory
    (two parallel signups for the same user could double-create), but
    in practice the signup endpoint is serialized per user_id by
    Mongo's `users` uniqueness, so this is fine. A future hardening
    could add `{user_id, is_default}` as a partial unique index."""
    existing = await db.brands.find_one(
        {"user_id": user_id, "is_default": True}, {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]

    brand_id = uuid.uuid4().hex
    display = (name_hint or "").strip()
    brand_name = (display + "'s Brand") if display else "My Brand"
    now = datetime.now(timezone.utc)

    await db.brands.insert_one({
        "id":         brand_id,
        "user_id":    user_id,
        "name":       brand_name,
        "is_default": True,
        "voice":      None,
        "palette":    None,
        "logo_url":   None,
        "website":    None,
        "created_at": now,
        "updated_at": now,
    })
    logger.info("created default brand %s for user %s", brand_id, user_id)
    return brand_id


async def get_user_brand_id(user_id: str) -> Optional[str]:
    """Read-only lookup — returns None if no brand exists yet. Callers
    that need the brand_id to be guaranteed should use
    `ensure_default_brand_for_user` instead."""
    doc = await db.brands.find_one(
        {"user_id": user_id, "is_default": True}, {"_id": 0, "id": 1},
    )
    return doc["id"] if doc else None
