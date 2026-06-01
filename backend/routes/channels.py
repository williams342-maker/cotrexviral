"""Social-media channels: connect/disconnect, publish, scheduled posts, AI optimal times."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import db, api, logger
from deps import get_current_user
from models import ChannelConnectRequest, PublishRequest, ScheduledUpdate, OptimalTimesRequest
from routes.ai import _llm, LlmChat, UserMessage  # reuse LLM client
from routes.content_layer import (
    mirror_post_to_normalized,
    propagate_status_to_variants,
    cascade_delete_for_posts,
    resolve_post_ids_for_status,
)


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

    # Platform-level admin kill-switch — blocks new connects but doesn't yank
    # existing channels (so an admin can disable a misbehaving integration
    # without breaking already-scheduled posts).
    from routes.admin_settings import is_platform_enabled
    if not await is_platform_enabled(payload.platform):
        raise HTTPException(
            status_code=403,
            detail=f"The {payload.platform} integration is temporarily disabled by the admin.",
        )

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

    # Approval gate — if the user has `require_post_approval` on, scheduled
    # posts are parked in status="pending_approval" until they hit /approve.
    # Immediate publishes (is_scheduled=False) bypass this since the user is
    # actively clicking publish themselves.
    user_doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "require_post_approval": 1},
    ) or {}
    requires_approval = bool(user_doc.get("require_post_approval", False)) and is_scheduled
    scheduled_status = "pending_approval" if requires_approval else "scheduled"

    # --- Weekly recurrence: only valid for scheduled posts. ---
    # When `repeat_weeks` is set (and the post is scheduled into the future),
    # we materialise N instances of the same content at +0w, +1w, ..., +(N-1)w.
    # Each shares a `recurrence_group_id` so future edits/deletes can operate
    # on the whole series.
    if payload.repeat_weeks and is_scheduled:
        group_id = str(uuid.uuid4())
        created_posts = []
        for week_offset in range(payload.repeat_weeks):
            sched_at = payload.scheduled_at + timedelta(weeks=week_offset)
            post = {
                "id": str(uuid.uuid4()),
                "user_id": user.user_id,
                "content": payload.content,
                "platforms": payload.platforms,
                "media_url": payload.media_url,
                "status": scheduled_status,
                "scheduled_at": sched_at,
                "recurrence_group_id": group_id,
                "recurrence_index": week_offset,
                "recurrence_total": payload.repeat_weeks,
                "campaign_id": payload.campaign_id,
                "created_at": datetime.now(timezone.utc),
            }
            if "pinterest" in (payload.platforms or []):
                post["pinterest_board_id"] = payload.pinterest_board_id
                post["pinterest_link"] = payload.pinterest_link
                post["pinterest_title"] = payload.pinterest_title
            if "youtube" in (payload.platforms or []):
                post["video_url"]       = payload.video_url
                post["youtube_title"]   = payload.youtube_title
                post["youtube_tags"]    = payload.youtube_tags
                post["youtube_privacy"] = payload.youtube_privacy
            await db.posts.insert_one(post)
            await mirror_post_to_normalized(post)
            created_posts.append(post["id"])
        return {
            "ok": True,
            "ids": created_posts,
            "recurrence_group_id": group_id,
            "repeat_weeks": payload.repeat_weeks,
            "platforms": payload.platforms,
            "status": scheduled_status,
        }

    post = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "content": payload.content,
        "platforms": payload.platforms,
        "media_url": payload.media_url,
        "status": scheduled_status if is_scheduled else "published",
        "scheduled_at": payload.scheduled_at if is_scheduled else None,
        "campaign_id": payload.campaign_id,
        "created_at": datetime.now(timezone.utc),
    }
    if "pinterest" in (payload.platforms or []):
        post["pinterest_board_id"] = payload.pinterest_board_id
        post["pinterest_link"] = payload.pinterest_link
        post["pinterest_title"] = payload.pinterest_title
        if payload.pinterest_images:
            post["pinterest_images"] = payload.pinterest_images
    if "youtube" in (payload.platforms or []):
        post["video_url"]       = payload.video_url
        post["youtube_title"]   = payload.youtube_title
        post["youtube_tags"]    = payload.youtube_tags
        post["youtube_privacy"] = payload.youtube_privacy
    await db.posts.insert_one(post)
    await mirror_post_to_normalized(post)

    # Immediate dispatch to live platform APIs (currently: LinkedIn + TikTok + Pinterest).
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
    if not is_scheduled and "pinterest" in (payload.platforms or []):
        from routes.oauth_pinterest import publish_to_pinterest  # lazy import (circular safe)
        dispatch["pinterest"] = await publish_to_pinterest(
            user.user_id, payload.content,
            image_url=payload.media_url,
            images=payload.pinterest_images,
            board_id=payload.pinterest_board_id,
            link=payload.pinterest_link,
            title=payload.pinterest_title,
        )
    if not is_scheduled and "facebook" in (payload.platforms or []):
        from routes.oauth_meta import publish_to_facebook  # lazy import (circular safe)
        dispatch["facebook"] = await publish_to_facebook(
            user.user_id, payload.content, image_url=payload.media_url,
        )
    if not is_scheduled and "instagram" in (payload.platforms or []):
        from routes.oauth_meta import publish_to_instagram  # lazy import (circular safe)
        dispatch["instagram"] = await publish_to_instagram(
            user.user_id, payload.content, image_url=payload.media_url,
        )
    if dispatch:
        await db.posts.update_one({"id": post["id"]}, {"$set": {"dispatch": dispatch}})
        # Mirror published status + per-platform external ids/urls into variants.
        await propagate_status_to_variants(
            post["id"],
            status=post["status"],
            published_at=post.get("published_at"),
            external_dispatch=dispatch,
        )

    # Memory ingest — store the post content + which platforms received it
    # so subsequent agent prompts can recall it ("write me another like
    # the one we shipped on TikTok about ...").
    if not is_scheduled:
        try:
            from routes.memory import remember
            await remember(
                user.user_id, "post",
                payload.content,
                meta={
                    "post_id": post["id"],
                    "platform": (payload.platforms or [""])[0],
                    "platforms": payload.platforms,
                },
                dedupe_key=f"post:{post['id']}",
            )
        except Exception:
            logger.exception("Memory ingest of published post failed")

    return {
        "ok": True,
        "id": post["id"],
        "platforms": payload.platforms,
        "status": post["status"],
        "dispatch": dispatch,
    }


@api.get("/posts/scheduled")
async def list_scheduled(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    """List scheduled posts for the user. Phase 3 reads the normalized
    `content_variants` index to resolve which posts match, then fetches
    full post documents via the cross-ref. Falls back leniently to the
    legacy `posts` query for any un-mirrored stragglers."""
    user = await get_current_user(request)
    sched_after = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
    sched_before = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
    post_ids, _ = await resolve_post_ids_for_status(
        user.user_id, status="scheduled",
        scheduled_after=sched_after, scheduled_before=sched_before,
    )
    if not post_ids:
        return []
    cursor = db.posts.find({"id": {"$in": post_ids}}, {"_id": 0}).sort("scheduled_at", 1)
    return await cursor.to_list(500)


@api.delete("/posts/scheduled/{post_id}")
async def cancel_scheduled(post_id: str, request: Request, scope: str = "only"):
    """Cancel a scheduled post.
    scope:
      - "only"   (default): just this post. Preserves existing behavior.
      - "future": this post + every post in the same recurrence_group_id whose
                  scheduled_at is >= this one. Past instances are kept.
      - "all":    every post in the same recurrence_group_id, including past.
    For non-recurring posts, any scope behaves like "only".
    """
    user = await get_current_user(request)
    target = await db.posts.find_one(
        {"id": post_id, "user_id": user.user_id, "status": "scheduled"},
        {"_id": 0},
    )
    if not target:
        raise HTTPException(status_code=404, detail="Scheduled post not found")

    group_id = target.get("recurrence_group_id")
    if scope == "only" or not group_id:
        await db.posts.delete_one({"id": post_id, "user_id": user.user_id, "status": "scheduled"})
        await cascade_delete_for_posts([post_id])
        return {"ok": True, "deleted": 1, "scope": "only"}

    if scope not in {"future", "all"}:
        raise HTTPException(status_code=400, detail="scope must be one of: only, future, all")

    query = {
        "user_id": user.user_id,
        "status": "scheduled",
        "recurrence_group_id": group_id,
    }
    if scope == "future":
        query["scheduled_at"] = {"$gte": target["scheduled_at"]}
    victims = await db.posts.find(query, {"_id": 0, "id": 1}).to_list(500)
    victim_ids = [v["id"] for v in victims]
    res = await db.posts.delete_many(query)
    await cascade_delete_for_posts(victim_ids)
    return {"ok": True, "deleted": res.deleted_count, "scope": scope}


from pydantic import BaseModel as _BaseModel  # local import to avoid pydantic deps at top


class _SeriesShift(_BaseModel):
    delta_days: int
    anchor_post_id: Optional[str] = None  # if set, only shift this + future


@api.patch("/posts/series/{group_id}")
async def shift_series(group_id: str, payload: _SeriesShift, request: Request):
    """Shift every still-scheduled post in a recurrence series by N days.
    If `anchor_post_id` is provided, only shift posts whose scheduled_at is
    >= the anchor's scheduled_at (i.e. "this and future").
    """
    user = await get_current_user(request)
    if payload.delta_days == 0:
        return {"ok": True, "updated": 0}
    if abs(payload.delta_days) > 365:
        raise HTTPException(status_code=400, detail="delta_days out of range")

    query = {
        "user_id": user.user_id,
        "status": "scheduled",
        "recurrence_group_id": group_id,
    }
    if payload.anchor_post_id:
        anchor = await db.posts.find_one(
            {"id": payload.anchor_post_id, "user_id": user.user_id},
            {"scheduled_at": 1, "_id": 0},
        )
        if not anchor:
            raise HTTPException(status_code=404, detail="Anchor post not found")
        query["scheduled_at"] = {"$gte": anchor["scheduled_at"]}

    members = await db.posts.find(query, {"_id": 0, "id": 1, "scheduled_at": 1}).to_list(500)
    if not members:
        raise HTTPException(status_code=404, detail="Series has no members in scope")

    updated = 0
    for m in members:
        new_at = m["scheduled_at"] + timedelta(days=payload.delta_days)
        await db.posts.update_one(
            {"id": m["id"], "user_id": user.user_id},
            {"$set": {"scheduled_at": new_at}},
        )
        updated += 1
    return {"ok": True, "updated": updated, "delta_days": payload.delta_days}


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
    # Mirror content / scheduled_at edits into the variant rows.
    await propagate_status_to_variants(
        post_id,
        body=updates.get("content"),
        scheduled_at=updates.get("scheduled_at"),
    )
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

    Tries in order:
      1. **Learned times** — aggregate this user's own historical
         publishing pattern (`db.posts` grouped by weekday+hour). Once a
         user has ≥ `MIN_POSTS_FOR_LEARNED` posts on a platform, we use
         the top engagement windows they've personally seen, not a
         heuristic.
      2. **Static heuristic** — falls back to `OPTIMAL_BASE` for users
         without enough publishing history yet.

    Returned slots are tagged with `source: 'learned' | 'heuristic'` so
    the UI can render a small "personalized" badge when applicable.
    """
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    day_index = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # ------------------------------------------------------------------
    # Step 1 — pull per-platform learned slots in ONE aggregation. We
    # consider posts within the last 180 days so seasonal drift doesn't
    # drown out recent behavior, and we score each (weekday, hour) by
    # a blend of post count + engagement (likes + comments + shares).
    # ------------------------------------------------------------------
    MIN_POSTS_FOR_LEARNED = 6   # threshold per platform before we trust learned data
    LEARNED_WINDOW_DAYS   = 180

    since = now - timedelta(days=LEARNED_WINDOW_DAYS)
    pipeline = [
        {"$match": {
            "user_id":      user.user_id,
            "status":       "published",
            "platform":     {"$in": payload.platforms},
            "published_at": {"$gte": since},
        }},
        # Mongo's $isoDayOfWeek is 1-7 (Mon=1..Sun=7), aligns with day_name when we -1.
        {"$project": {
            "platform":   1,
            "weekday":    {"$subtract": [{"$isoDayOfWeek": "$published_at"}, 1]},
            "hour":       {"$hour": "$published_at"},
            "engagement": {"$add": [
                {"$ifNull": ["$metrics.likes", 0]},
                {"$ifNull": ["$metrics.comments", 0]},
                {"$ifNull": ["$metrics.shares", 0]},
                {"$ifNull": ["$metrics.impressions", 0]},
            ]},
        }},
        {"$group": {
            "_id":         {"platform": "$platform", "weekday": "$weekday", "hour": "$hour"},
            "post_count":  {"$sum": 1},
            "engagement":  {"$sum": "$engagement"},
        }},
        {"$sort": {"engagement": -1, "post_count": -1}},
    ]
    try:
        agg_rows = await db.posts.aggregate(pipeline).to_list(length=500)
    except Exception:
        logger.exception("ai_optimal_times: learned aggregation failed")
        agg_rows = []

    # Bucket the rows by platform + count totals to know who qualifies.
    by_plat: dict[str, list[dict]] = {p: [] for p in payload.platforms}
    plat_totals: dict[str, int] = {p: 0 for p in payload.platforms}
    for row in agg_rows:
        k = row["_id"]
        by_plat[k["platform"]].append({
            "weekday": k["weekday"], "hour": k["hour"],
            "count":   row["post_count"], "engagement": row["engagement"],
        })
        plat_totals[k["platform"]] += row["post_count"]

    # ------------------------------------------------------------------
    # Step 2 — build the 6-slot upcoming schedule per platform, mixing
    # learned + heuristic as available. Each slot carries its source.
    # We require ≥ MIN_POSTS_FOR_LEARNED posts AND at least one
    # learned bucket. If the user concentrates all their posts in one
    # weekday+hour, we still trust that — better to surface their own
    # proven slot than override it with a heuristic.
    # ------------------------------------------------------------------
    results: dict[str, list[dict]] = {}
    for p in payload.platforms:
        learned = by_plat.get(p) or []
        use_learned = (plat_totals[p] >= MIN_POSTS_FOR_LEARNED
                        and len(learned) >= 1)

        if use_learned:
            base_slots = [
                {"day": day_name[r["weekday"]] if 0 <= r["weekday"] < 7 else "Tue",
                 "hour": int(r["hour"]),
                 "source": "learned",
                 "support_posts":      r["count"],
                 "support_engagement": r["engagement"]}
                for r in learned[:6]
            ]
        else:
            base_slots = [
                {**s, "source": "heuristic"}
                for s in OPTIMAL_BASE.get(
                    p, [{"day": "Tue", "hour": 10}, {"day": "Thu", "hour": 15}])
            ]

        upcoming = []
        for idx, slot in enumerate(base_slots):
            target_dow = day_index[slot["day"]]
            today_dow  = now.weekday()
            delta = (target_dow - today_dow) % 7
            if delta == 0 and now.hour >= slot["hour"]:
                delta = 7
            d = now + timedelta(days=delta)
            d = d.replace(hour=slot["hour"], minute=0, second=0, microsecond=0)
            entry = {
                "platform": p,
                "datetime": d.isoformat(),
                "day":      slot["day"],
                "hour":     slot["hour"],
                "score":    100 - idx * 7,
                "source":   slot.get("source", "heuristic"),
            }
            if slot.get("source") == "learned":
                entry["support_posts"]      = slot["support_posts"]
                entry["support_engagement"] = slot["support_engagement"]
            upcoming.append(entry)
        upcoming.sort(key=lambda s: s["datetime"])
        results[p] = upcoming[:6]

    # ------------------------------------------------------------------
    # Step 3 — optional AI rationale (unchanged from prior version).
    # ------------------------------------------------------------------
    rationale = None
    ori_insight = None
    if payload.niche or payload.audience:
        try:
            from routes.agent_messaging import query_agent
            r = await query_agent(
                user_id=user.user_id, from_agent="echo", to_agent="ori",
                query=("For these platforms, which winning content patterns from "
                       "your experiment memory should we lean on when picking a "
                       "time? Cite specifics if you have them, else say 'no priors'."),
                context_str=(f"Niche: {payload.niche or '—'}\n"
                             f"Audience: {payload.audience or '—'}\n"
                             f"Platforms: {', '.join(payload.platforms)}"),
            )
            if r.get("ok"):
                ori_insight = (r.get("response") or "").strip()
        except Exception:
            logger.debug("Echo→Ori hand-off skipped", exc_info=True)

        try:
            system = (
                "You are Kai, social timing strategist. In ONE short paragraph (<60 words) "
                "explain why these timing recommendations fit the user's niche & audience. "
                "Be specific and confident."
                + (f"\n\nLean on this learning from Ori's memory if relevant:\n{ori_insight}"
                   if ori_insight else "")
            )
            chat = _llm(f"times-{user.user_id}", system)
            ask = f"Niche: {payload.niche}\nAudience: {payload.audience}\nPlatforms: {', '.join(payload.platforms)}"
            from routes.ai import send_with_usage
            rationale, _usage = await send_with_usage(
                chat, UserMessage(text=ask),
                agent_id="echo", user_id=user.user_id, model="gpt-5",
            )
        except Exception:
            rationale = None

    return {
        "slots":         results,
        "rationale":     rationale,
        "ori_insight":   ori_insight,
        # Per-platform diagnostics so the UI can show "Learned from your
        # 23 LinkedIn posts" vs "Industry baseline (post more to unlock
        # personalized timing)".
        "learned_support": {
            p: {"post_count": plat_totals[p],
                "uses_learned": (plat_totals[p] >= MIN_POSTS_FOR_LEARNED
                                  and len(by_plat.get(p) or []) >= 1),
                "min_required": MIN_POSTS_FOR_LEARNED}
            for p in payload.platforms
        },
    }
