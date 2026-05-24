"""Social-media channels: connect/disconnect, publish, scheduled posts, AI optimal times."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import db, api
from deps import get_current_user
from models import ChannelConnectRequest, PublishRequest, ScheduledUpdate, OptimalTimesRequest
from routes.ai import _llm, LlmChat, UserMessage  # reuse LLM client


SUPPORTED_PLATFORMS = [
    # Social
    "instagram", "tiktok", "x", "facebook", "linkedin", "youtube",
    "pinterest", "threads", "reddit",
    # Publishing / CMS
    "wordpress", "wordpress_selfhosted", "substack", "webflow", "ghost",
    "framer", "blogger", "shopify",
    # Analytics
    "google_analytics", "google_search_console", "omni_analytics",
    "posthog", "semrush",
    # Ads
    "google_ads", "meta_ads", "tiktok_ads",
    # Email / marketing
    "klaviyo", "mailchimp", "instantly", "brevo", "beehiiv",
    # Productivity
    "google_docs", "notion", "airtable", "github",
    # Payments
    "stripe", "revenuecat",
    # CRM
    "hubspot", "zoho_crm",
]


PLATFORM_CATEGORIES = {
    "Social": ["instagram", "tiktok", "x", "facebook", "linkedin", "youtube", "pinterest", "threads", "reddit"],
    "Publishing & CMS": ["wordpress", "wordpress_selfhosted", "substack", "webflow", "ghost", "framer", "blogger", "shopify"],
    "Analytics": ["google_analytics", "google_search_console", "omni_analytics", "posthog", "semrush"],
    "Ads": ["google_ads", "meta_ads", "tiktok_ads"],
    "Email & Marketing": ["klaviyo", "mailchimp", "instantly", "brevo", "beehiiv"],
    "Productivity": ["google_docs", "notion", "airtable", "github"],
    "Payments": ["stripe", "revenuecat"],
    "CRM": ["hubspot", "zoho_crm"],
}


@api.get("/channels/catalog")
async def channels_catalog(request: Request):
    """Returns the full catalog of supported platforms grouped by category."""
    await get_current_user(request)
    return PLATFORM_CATEGORIES


@api.get("/channels")
async def list_channels(request: Request):
    user = await get_current_user(request)
    docs = await db.channels.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    connected = {d["platform"]: d for d in docs}
    return [
        {
            "platform": p,
            "connected": p in connected,
            "handle": connected.get(p, {}).get("handle"),
            "connected_at": connected.get(p, {}).get("connected_at"),
        }
        for p in SUPPORTED_PLATFORMS
    ]


@api.post("/channels/connect")
async def connect_channel(payload: ChannelConnectRequest, request: Request):
    user = await get_current_user(request)
    if payload.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")

    # If user already has this channel (just reconnecting), bypass the cap.
    existing = await db.channels.find_one(
        {"user_id": user.user_id, "platform": payload.platform, "connected": True},
    )
    if not existing:
        from routes.plans import assert_can_connect_channel  # lazy import (circular safe)
        await assert_can_connect_channel(user.user_id)

    doc = {
        "user_id": user.user_id,
        "platform": payload.platform,
        "handle": f"@{user.name.lower().replace(' ', '_')}",
        "connected": True,
        "connected_at": datetime.now(timezone.utc),
    }
    await db.channels.update_one(
        {"user_id": user.user_id, "platform": payload.platform},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True, "platform": payload.platform, "handle": doc["handle"]}


@api.post("/channels/disconnect")
async def disconnect_channel(payload: ChannelConnectRequest, request: Request):
    user = await get_current_user(request)
    await db.channels.delete_one({"user_id": user.user_id, "platform": payload.platform})
    return {"ok": True}


@api.post("/channels/publish")
async def publish(payload: PublishRequest, request: Request):
    user = await get_current_user(request)
    is_scheduled = payload.scheduled_at and payload.scheduled_at > datetime.now(timezone.utc)
    post = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "content": payload.content,
        "platforms": payload.platforms,
        "media_url": payload.media_url,
        "status": "scheduled" if is_scheduled else "published",
        "scheduled_at": payload.scheduled_at if is_scheduled else None,
        "created_at": datetime.now(timezone.utc),
    }
    await db.posts.insert_one(post)

    # Immediate dispatch to live APIs (currently: LinkedIn + TikTok).
    # Scheduled posts are picked up by the background scheduler instead.
    dispatch = {}
    if not is_scheduled and "linkedin" in (payload.platforms or []):
        from routes.oauth_linkedin import publish_to_linkedin  # lazy import (circular safe)
        dispatch["linkedin"] = await publish_to_linkedin(user.user_id, payload.content)
    if not is_scheduled and "tiktok" in (payload.platforms or []):
        from routes.oauth_tiktok import publish_to_tiktok  # lazy import (circular safe)
        dispatch["tiktok"] = await publish_to_tiktok(
            user.user_id, payload.content, payload.media_url,
        )
    if dispatch:
        await db.posts.update_one({"id": post["id"]}, {"$set": {"dispatch": dispatch}})

    return {
        "ok": True,
        "id": post["id"],
        "platforms": payload.platforms,
        "status": post["status"],
        "dispatch": dispatch,
    }


@api.get("/posts/scheduled")
async def list_scheduled(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    user = await get_current_user(request)
    query = {"user_id": user.user_id, "status": "scheduled"}
    if start or end:
        sched = {}
        if start:
            sched["$gte"] = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            sched["$lte"] = datetime.fromisoformat(end.replace("Z", "+00:00"))
        query["scheduled_at"] = sched
    cursor = db.posts.find(query, {"_id": 0}).sort("scheduled_at", 1)
    return await cursor.to_list(500)


@api.delete("/posts/scheduled/{post_id}")
async def cancel_scheduled(post_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.posts.delete_one({"id": post_id, "user_id": user.user_id, "status": "scheduled"})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    return {"ok": True}


@api.patch("/posts/scheduled/{post_id}")
async def update_scheduled(post_id: str, payload: ScheduledUpdate, request: Request):
    user = await get_current_user(request)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    res = await db.posts.update_one(
        {"id": post_id, "user_id": user.user_id, "status": "scheduled"},
        {"$set": updates},
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    return {"ok": True}


# Industry-standard optimal posting times (heuristic baseline)
OPTIMAL_BASE = {
    "instagram":  [{"day": d, "hour": h} for d in ["Mon", "Tue", "Wed"] for h in [11, 14, 19]] + [{"day": "Fri", "hour": 11}],
    "tiktok":     [{"day": d, "hour": h} for d in ["Tue", "Thu", "Fri"] for h in [9, 19, 21]],
    "x":          [{"day": d, "hour": h} for d in ["Mon", "Tue", "Wed", "Thu"] for h in [8, 12, 17]],
    "facebook":   [{"day": d, "hour": h} for d in ["Tue", "Wed", "Thu"] for h in [9, 13, 15]],
    "linkedin":   [{"day": d, "hour": h} for d in ["Tue", "Wed", "Thu"] for h in [8, 10, 12]],
    "youtube":    [{"day": d, "hour": h} for d in ["Thu", "Fri", "Sat"] for h in [15, 17, 20]],
    "pinterest":  [{"day": d, "hour": h} for d in ["Fri", "Sat", "Sun"] for h in [20, 21, 22]],
    "threads":    [{"day": d, "hour": h} for d in ["Mon", "Wed", "Fri"] for h in [10, 13, 18]],
    "reddit":     [{"day": d, "hour": h} for d in ["Tue", "Wed", "Sun"] for h in [9, 17, 20]],
    "substack":   [{"day": "Tue", "hour": 9}, {"day": "Thu", "hour": 9}, {"day": "Sun", "hour": 8}],
    "blogger":    [{"day": "Tue", "hour": 10}, {"day": "Thu", "hour": 14}],
}


@api.post("/ai/optimal-times")
async def ai_optimal_times(payload: OptimalTimesRequest, request: Request):
    """Returns the next best posting slots for each requested platform.
    Combines a static heuristic baseline with optional AI refinement based on the user's niche/audience.
    """
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    day_index = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    results = {}
    for p in payload.platforms:
        slots = OPTIMAL_BASE.get(p, [{"day": "Tue", "hour": 10}, {"day": "Thu", "hour": 15}])
        upcoming = []
        for slot in slots:
            target_dow = day_index[slot["day"]]
            today_dow = now.weekday()
            delta = (target_dow - today_dow) % 7
            if delta == 0 and now.hour >= slot["hour"]:
                delta = 7
            d = now + timedelta(days=delta)
            d = d.replace(hour=slot["hour"], minute=0, second=0, microsecond=0)
            upcoming.append({
                "platform": p,
                "datetime": d.isoformat(),
                "day": slot["day"],
                "hour": slot["hour"],
                "score": 100 - len(upcoming) * 7,
            })
        upcoming.sort(key=lambda s: s["datetime"])
        results[p] = upcoming[:6]

    # Optional AI rationale (kept short to avoid heavy LLM cost on every call)
    rationale = None
    if payload.niche or payload.audience:
        try:
            system = (
                "You are Kai, social timing strategist. In ONE short paragraph (<60 words) "
                "explain why these timing recommendations fit the user's niche & audience. "
                "Be specific and confident."
            )
            chat = _llm(f"times-{user.user_id}", system)
            ask = f"Niche: {payload.niche}\nAudience: {payload.audience}\nPlatforms: {', '.join(payload.platforms)}"
            rationale = await chat.send_message(UserMessage(text=ask))
        except Exception:
            rationale = None

    return {"slots": results, "rationale": rationale}
