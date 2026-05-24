"""Plan-gating helpers: usage limits + entitlement checks.

Single source of truth for what each plan allows. Keep this in sync with the
PLANS dict in routes/billing.py (which only stores prices, not entitlements).

Usage counters live on the user document under `usage.{month_key}.ai_generations`.
Month key is YYYY-MM (UTC). This means counters auto-reset on the 1st of each
month without any cron job — we just look at the current month's bucket.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from core import db, logger


# -----------------------------------------------------------------------------
# Entitlements per plan
# -----------------------------------------------------------------------------
ENTITLEMENTS = {
    "free": {
        "ai_generations_per_month": 20,   # "5 hooks per week" in marketing copy
        "max_channels": 1,                 # TikTok only
        "features": {
            "trend_engine": False,
            "ab_variations": False,
            "batch_generation": False,
            "api_access": False,
            "multi_workspace": False,
        },
        "label": "Free",
    },
    "starter": {
        "ai_generations_per_month": 30,
        "max_channels": 2,                 # TikTok + Instagram Reels
        "features": {
            "trend_engine": False,
            "ab_variations": False,
            "batch_generation": False,
            "api_access": False,
            "multi_workspace": False,
        },
        "label": "Starter",
    },
    "growth": {
        "ai_generations_per_month": None,  # unlimited
        "max_channels": None,              # unlimited
        "features": {
            "trend_engine": True,
            "ab_variations": True,
            "batch_generation": False,
            "api_access": False,
            "multi_workspace": False,
        },
        "label": "Growth",
    },
    "agency": {
        "ai_generations_per_month": None,
        "max_channels": None,
        "features": {
            "trend_engine": True,
            "ab_variations": True,
            "batch_generation": True,
            "api_access": True,
            "multi_workspace": True,
        },
        "label": "Agency",
    },
    # Legacy mappings — anyone still on old "pro"/"scale" subs gets graceful
    # behaviour until they swap. Pro ~= Growth, Scale ~= Agency.
    "pro": {
        "ai_generations_per_month": None,
        "max_channels": 10,
        "features": {
            "trend_engine": True,
            "ab_variations": True,
            "batch_generation": False,
            "api_access": False,
            "multi_workspace": False,
        },
        "label": "Pro (legacy)",
    },
    "scale": {
        "ai_generations_per_month": None,
        "max_channels": None,
        "features": {
            "trend_engine": True,
            "ab_variations": True,
            "batch_generation": True,
            "api_access": True,
            "multi_workspace": True,
        },
        "label": "Scale (legacy)",
    },
}


def _month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


async def _get_plan(user_id: str) -> str:
    doc = await db.users.find_one(
        {"user_id": user_id},
        {"plan": 1, "subscription_status": 1, "comped": 1},
    )
    if not doc:
        return "free"
    plan = doc.get("plan") or "free"
    # Comped users keep their plan regardless of Stripe status.
    if doc.get("comped"):
        return plan
    # Past-due subscribers fall back to free (Stripe will recover them or cancel)
    if doc.get("subscription_status") == "past_due":
        return "free"
    return plan


async def get_usage(user_id: str) -> dict:
    """Return the user's plan + this month's usage + limits."""
    plan = await _get_plan(user_id)
    ent = ENTITLEMENTS.get(plan, ENTITLEMENTS["free"])
    month = _month_key()

    doc = await db.users.find_one(
        {"user_id": user_id},
        {"usage": 1, "plan": 1, "comped": 1},
    ) or {}
    ai_count = ((doc.get("usage") or {}).get(month) or {}).get("ai_generations", 0)

    channel_count = await db.channels.count_documents(
        {"user_id": user_id, "connected": True},
    )

    return {
        "plan": plan,
        "plan_label": ent["label"],
        "comped": bool(doc.get("comped")),
        "month": month,
        "ai_generations_used": ai_count,
        "ai_generations_limit": ent["ai_generations_per_month"],
        "ai_generations_remaining": (
            None if ent["ai_generations_per_month"] is None
            else max(0, ent["ai_generations_per_month"] - ai_count)
        ),
        "channels_used": channel_count,
        "channels_limit": ent["max_channels"],
        "channels_remaining": (
            None if ent["max_channels"] is None
            else max(0, ent["max_channels"] - channel_count)
        ),
        "features": ent.get("features", {}),
    }


async def assert_can_generate_ai(user_id: str):
    """Raise 402 Payment Required when the user has hit their AI cap."""
    plan = await _get_plan(user_id)
    ent = ENTITLEMENTS.get(plan, ENTITLEMENTS["free"])
    cap = ent["ai_generations_per_month"]
    if cap is None:
        return  # unlimited

    month = _month_key()
    doc = await db.users.find_one(
        {"user_id": user_id},
        {"usage": 1},
    ) or {}
    used = ((doc.get("usage") or {}).get(month) or {}).get("ai_generations", 0)
    if used >= cap:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "ai_generation_limit_reached",
                "message": (
                    f"You've used all {cap} AI generations on the {ent['label']} plan "
                    "this month. Upgrade to Pro for unlimited generations."
                ),
                "plan": plan,
                "used": used,
                "limit": cap,
            },
        )


async def record_ai_generation(user_id: str, kind: str = "post") -> int:
    """Increment the user's monthly AI counter. Returns the new total."""
    month = _month_key()
    res = await db.users.find_one_and_update(
        {"user_id": user_id},
        {
            "$inc": {f"usage.{month}.ai_generations": 1, f"usage.{month}.kinds.{kind}": 1},
            "$set": {f"usage.{month}.updated_at": datetime.now(timezone.utc)},
        },
        return_document=True,
        upsert=True,
    )
    new_total = ((res or {}).get("usage", {}).get(month, {})).get("ai_generations", 1)
    return new_total


async def assert_can_connect_channel(user_id: str):
    """Raise 402 when the user has hit their channel-connection cap."""
    plan = await _get_plan(user_id)
    ent = ENTITLEMENTS.get(plan, ENTITLEMENTS["free"])
    cap = ent["max_channels"]
    if cap is None:
        return

    current = await db.channels.count_documents(
        {"user_id": user_id, "connected": True},
    )
    if current >= cap:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "channel_limit_reached",
                "message": (
                    f"The {ent['label']} plan allows up to {cap} connected channels. "
                    "Upgrade to Pro for 10 channels, or Scale for unlimited."
                ),
                "plan": plan,
                "used": current,
                "limit": cap,
            },
        )


async def assert_has_feature(user_id: str, feature: str):
    """Raise 402 when the user's plan doesn't include the named feature flag."""
    plan = await _get_plan(user_id)
    ent = ENTITLEMENTS.get(plan, ENTITLEMENTS["free"])
    if ent.get("features", {}).get(feature):
        return
    raise HTTPException(
        status_code=402,
        detail={
            "code": "feature_not_in_plan",
            "message": f"'{feature}' is not included in the {ent['label']} plan. Upgrade to Growth to unlock it.",
            "plan": plan,
            "feature": feature,
        },
    )
