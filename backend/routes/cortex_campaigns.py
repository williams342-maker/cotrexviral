"""Campaigns — Phase C orchestrator endpoints.

Routes:
  POST   /api/cortex/campaigns                  body: {brief_id}
         Kick off a full campaign build from an existing brief.

  GET    /api/cortex/campaigns                  ?status=...&limit=...
         List the user's campaigns, newest first.

  GET    /api/cortex/campaigns/{id}             ?include=posts,emails,landing_page,creatives
         Hydrate full campaign with related artifacts.

  DELETE /api/cortex/campaigns/{id}             soft delete
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user
from cortex.campaign_builder import build_campaign
from cortex.asset_storage import storage

logger = logging.getLogger(__name__)


class CampaignCreatePayload(BaseModel):
    brief_id: str


def _iso(row: dict) -> dict:
    out = dict(row)
    out.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@api.post("/cortex/campaigns")
async def create_campaign(payload: CampaignCreatePayload, request: Request):
    user = await get_current_user(request)
    brief = await db.cortex_creative_briefs.find_one(
        {"id": payload.brief_id, "user_id": user.user_id}, {"_id": 0})
    if not brief:
        raise HTTPException(404, "Brief not found.")

    asset_intel = None
    if brief.get("asset_id"):
        asset_intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})

    row = await build_campaign(brief=brief, asset_intel=asset_intel,
                                  user_id=user.user_id)
    return _iso(row)


@api.get("/cortex/campaigns")
async def list_campaigns(request: Request, limit: int = 30,
                           status: Optional[str] = None):
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 30), 100))
    flt: dict = {"user_id": user.user_id, "deleted_at": {"$exists": False}}
    if status:
        flt["status"] = status
    cur = db.cortex_campaigns.find(flt, {"_id": 0}) \
                              .sort("created_at", -1).limit(limit)
    rows = [_iso(r) async for r in cur]
    return {"campaigns": rows, "count": len(rows)}


@api.get("/cortex/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request,
                         include: str = "posts,emails,landing_page,creatives,brief"):
    user = await get_current_user(request)
    row = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not row or row.get("deleted_at"):
        raise HTTPException(404, "Campaign not found.")
    out = _iso(row)
    wanted = {p.strip() for p in (include or "").split(",") if p.strip()}

    if "brief" in wanted and out.get("brief_id"):
        brief = await db.cortex_creative_briefs.find_one(
            {"id": out["brief_id"], "user_id": user.user_id}, {"_id": 0})
        if brief:
            out["brief"] = _iso(brief)

    if "posts" in wanted:
        posts = []
        async for p in db.cortex_social_posts.find(
                {"campaign_id": campaign_id, "user_id": user.user_id},
                {"_id": 0}).sort("platform", 1):
            posts.append(_iso(p))
        out["social_posts"] = posts

    if "emails" in wanted:
        emails = []
        async for e in db.cortex_email_drafts.find(
                {"campaign_id": campaign_id, "user_id": user.user_id},
                {"_id": 0}).sort("step", 1):
            emails.append(_iso(e))
        out["email_sequence"] = emails

    if "landing_page" in wanted:
        lp = await db.cortex_landing_pages.find_one(
            {"campaign_id": campaign_id, "user_id": user.user_id}, {"_id": 0})
        if lp:
            out["landing_page"] = _iso(lp)

    if "creatives" in wanted:
        creatives = []
        async for c in db.cortex_creatives.find(
                {"campaign_id": campaign_id, "user_id": user.user_id,
                  "deleted_at": {"$exists": False}}, {"_id": 0}) \
                  .sort("concept_index", 1):
            row = _iso(c)
            if row.get("storage_key"):
                row["file_url"] = storage.public_url(row["storage_key"])
            creatives.append(row)
        # Fall back to brief-level creatives if the campaign doesn't
        # have its own (Phase B may have generated them upstream
        # before the campaign was built — they belong here too).
        if not creatives and out.get("brief_id"):
            async for c in db.cortex_creatives.find(
                    {"brief_id": out["brief_id"], "user_id": user.user_id,
                      "deleted_at": {"$exists": False}}, {"_id": 0}) \
                      .sort("concept_index", 1):
                row = _iso(c)
                if row.get("storage_key"):
                    row["file_url"] = storage.public_url(row["storage_key"])
                creatives.append(row)
        out["creatives"] = creatives

    return out


@api.delete("/cortex/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, request: Request):
    user = await get_current_user(request)
    row = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Campaign not found.")
    # Cancel any in-flight build pipeline so the LLM/credit spend stops
    # immediately and we don't race the build's update_one() calls with
    # this soft-delete write.
    from cortex.campaign_builder import cancel_pipeline
    cancelled = cancel_pipeline(campaign_id)
    await db.cortex_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"deleted_at": datetime.now(timezone.utc),
                   "status":     "deleted"}})
    return {"ok": True, "id": campaign_id,
              "pipeline_cancelled": cancelled}


# ---------------------------------------------------------------- push to calendar
# Platforms whose `publish_to_*` helpers are wired up in routes/oauth_*
# AND which accept image+text social posts. Other platforms in a brief
# (email/blog/google_ads/x) are skipped during bulk push because they
# need different surfaces (SendGrid / WordPress / Ads Manager / Twitter API).
_PUSHABLE_PLATFORMS = {
    "facebook", "instagram", "instagram_story",
    "linkedin", "pinterest",
}


# Map cortex_social_post.platform → canonical channels.SUPPORTED_PLATFORMS value.
_PLATFORM_ALIASES = {
    "instagram_story": "instagram",
    "youtube_shorts":  "youtube",
}


def _abs_media_url(storage_key: Optional[str]) -> Optional[str]:
    """Resolve a campaign creative's storage_key → absolute, signed,
    publicly fetchable URL. Token TTL is 7 days — comfortably covers
    drafts that sit unscheduled for a week before publishing. Social
    dispatchers (Meta/IG/LinkedIn/Pinterest) fetch this URL at publish
    time without needing the user's session cookie."""
    if not storage_key:
        return None
    from routes.cortex_assets import make_signed_asset_url
    return make_signed_asset_url(storage_key, ttl_seconds=7 * 86400)


def _compose_content(post: dict) -> str:
    """Compose the published content body from a cortex_social_post row.
    Order: optional headline → body → hashtags. CTA stays out of the
    body — the user generally moves it into the post manually since
    each platform's CTA conventions differ (link in bio / first comment / etc)."""
    parts: list[str] = []
    h = (post.get("headline") or "").strip()
    body = (post.get("body") or "").strip()
    if h and h.lower() not in body.lower()[:160]:
        parts.append(h)
    if body:
        parts.append(body)
    tags = post.get("hashtags") or []
    if tags:
        parts.append(" ".join("#" + str(t).lstrip("#") for t in tags))
    return "\n\n".join(parts).strip()


class CampaignPushPayload(BaseModel):
    mode: str = "draft"             # draft | scheduled | optimal_times
    # When mode=scheduled, posts are spread starting at start_at with
    # cadence_hours between consecutive items. UTC ISO string accepted.
    start_at: Optional[datetime] = None
    cadence_hours: int = 24
    # When mode=optimal_times, posts are scheduled at AI-recommended
    # slots per channel (see _compute_optimal_slot). No user inputs
    # required — slots come from routes/channels.OPTIMAL_BASE.


def _compute_optimal_slot(platform: str, *, after: datetime,
                            already_used: set) -> Optional[datetime]:
    """Return the next available best-time slot for `platform` strictly
    after `after`, that isn't already in `already_used`. Falls through
    weeks until a free slot lands.

    Uses the same heuristic baseline as routes.channels._ai_optimal_times
    (Tue/Wed/Thu mornings for B2B; Mon/Tue/Wed late-morning + evenings
    for IG; weekend evenings for Pinterest, etc.)."""
    from routes.channels import OPTIMAL_BASE
    day_index = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
                 "Fri": 4, "Sat": 5, "Sun": 6}
    slots = OPTIMAL_BASE.get(platform) or [
        {"day": "Tue", "hour": 10}, {"day": "Thu", "hour": 15}]

    # Generate candidate datetimes for the next 6 weeks, sort ascending,
    # pick the first that's strictly after `after` and not already used.
    candidates: list[datetime] = []
    base = after.replace(minute=0, second=0, microsecond=0)
    for week_offset in range(6):
        for slot in slots:
            target_dow = day_index.get(slot["day"], 1)
            today_dow = base.weekday()
            delta = (target_dow - today_dow) % 7 + week_offset * 7
            d = base + timedelta(days=delta)
            d = d.replace(hour=int(slot["hour"]),
                          minute=0, second=0, microsecond=0)
            if d > after and d not in already_used:
                candidates.append(d)
    if not candidates:
        return None
    candidates.sort()
    return candidates[0]


class SinglePostPushPayload(BaseModel):
    mode: str = "draft"             # draft | scheduled
    scheduled_at: Optional[datetime] = None
    creative_id: Optional[str] = None      # override default creative


def _normalize_platform(raw: str) -> str:
    """Lower + collapse whitespace → underscore + apply alias map."""
    norm = "_".join((raw or "").strip().lower().split())
    return _PLATFORM_ALIASES.get(norm, norm)


async def _materialize_push(*, user_id: str, campaign_id: str, cp: dict,
                              default_media: Optional[str],
                              mode: str, scheduled_at: Optional[datetime],
                              now: datetime) -> dict:
    """Create a /posts row from a cortex_social_post and stamp the
    cross-references. Returns the pushed-entry dict."""
    import uuid
    from routes.content_layer import mirror_post_to_normalized

    platform_raw = cp.get("platform") or ""
    platform = _normalize_platform(platform_raw)
    post_id = str(uuid.uuid4())
    post_row = {
        "id":           post_id,
        "user_id":      user_id,
        "content":      _compose_content(cp),
        "platforms":    [platform],
        "media_url":    default_media,
        "status":       "scheduled" if scheduled_at else "draft",
        "scheduled_at": scheduled_at,
        "campaign_id":  campaign_id,
        "cortex_post_id":     cp.get("id"),
        "cortex_campaign_id": campaign_id,
        "source":       "cortex_campaign_push",
        "created_at":   now,
    }
    if platform == "pinterest":
        post_row["pinterest_title"] = (cp.get("headline") or "")[:100] or None
        post_row["pinterest_link"] = None
        post_row["pinterest_board_id"] = None

    await db.posts.insert_one(post_row)
    try:
        await mirror_post_to_normalized(post_row)
    except Exception:
        logger.exception("mirror_post_to_normalized failed for %s", post_id)

    await db.cortex_social_posts.update_one(
        {"id": cp.get("id"), "user_id": user_id},
        {"$set": {
            "pushed_at":  now,
            "posts_id":   post_id,
            "pushed_mode": mode,
            "pushed_platform": platform,
        }})

    return {"cortex_post_id": cp.get("id"),
              "posts_id":       post_id,
              "platform":       platform,
              "status":         post_row["status"],
              "scheduled_at":   scheduled_at.isoformat() if scheduled_at else None}


async def _resolve_default_media(*, user_id: str, campaign_id: str,
                                   brief_id: Optional[str],
                                   creative_id: Optional[str] = None) -> Optional[str]:
    """Pick the creative URL to attach. Override > campaign > brief.
    Returns absolute backend URL or None when no creative exists."""
    if creative_id:
        c = await db.cortex_creatives.find_one(
            {"id": creative_id, "user_id": user_id,
              "status": "complete", "deleted_at": {"$exists": False}},
            {"_id": 0})
        if c and c.get("storage_key"):
            return _abs_media_url(c["storage_key"])
    c = await db.cortex_creatives.find_one(
        {"campaign_id": campaign_id, "user_id": user_id,
          "status": "complete", "deleted_at": {"$exists": False}},
        {"_id": 0})
    if c and c.get("storage_key"):
        return _abs_media_url(c["storage_key"])
    if brief_id:
        c = await db.cortex_creatives.find_one(
            {"brief_id": brief_id, "user_id": user_id,
              "status": "complete", "deleted_at": {"$exists": False}},
            {"_id": 0})
        if c and c.get("storage_key"):
            return _abs_media_url(c["storage_key"])
    return None


@api.post("/cortex/campaigns/{campaign_id}/push")
async def push_campaign_to_calendar(campaign_id: str,
                                       payload: CampaignPushPayload,
                                       request: Request):
    """Bulk-push every social post in a campaign to /posts as drafts
    (or scheduled rows). Each cortex_social_post gets at most one
    `posts` row — re-running the endpoint is a no-op for already-pushed
    posts (the cortex_social_post.pushed_at stamp gates this)."""
    user = await get_current_user(request)

    campaign = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not campaign or campaign.get("deleted_at"):
        raise HTTPException(404, "Campaign not found.")
    if campaign.get("status") != "complete":
        raise HTTPException(409, "Campaign is not complete yet.")

    if payload.mode not in ("draft", "scheduled", "optimal_times"):
        raise HTTPException(400,
            "mode must be 'draft', 'scheduled', or 'optimal_times'.")
    if payload.mode == "scheduled" and not payload.start_at:
        raise HTTPException(400, "start_at is required when mode='scheduled'.")
    cadence_hours = max(1, min(int(payload.cadence_hours or 24), 24 * 14))

    # Load posts once; default media resolves to the campaign's first
    # complete creative (fallback to brief-level).
    cortex_posts: list[dict] = []
    async for p in db.cortex_social_posts.find(
            {"campaign_id": campaign_id, "user_id": user.user_id},
            {"_id": 0}).sort("platform", 1):
        cortex_posts.append(p)
    default_media = await _resolve_default_media(
        user_id=user.user_id, campaign_id=campaign_id,
        brief_id=campaign.get("brief_id"))

    now = datetime.now(timezone.utc)
    cursor_at = payload.start_at
    pushed: list[dict] = []
    skipped: list[dict] = []
    # Per-platform cursor for optimal_times mode + a global set to
    # avoid scheduling two posts to the exact same minute.
    per_platform_after: dict = {}
    used_slots: set = set()

    for cp in cortex_posts:
        platform_raw = (cp.get("platform") or "")
        platform = _normalize_platform(platform_raw)
        if platform not in _PUSHABLE_PLATFORMS:
            skipped.append({"id": cp.get("id"),
                              "platform": platform_raw,
                              "reason": "platform_not_pushable"})
            continue
        if cp.get("pushed_at") and cp.get("posts_id"):
            skipped.append({"id": cp.get("id"),
                              "platform": platform_raw,
                              "reason": "already_pushed",
                              "posts_id": cp.get("posts_id")})
            continue

        sched_at = None
        if payload.mode == "scheduled":
            sched_at = cursor_at
            cursor_at = (cursor_at or now) + timedelta(hours=cadence_hours)
        elif payload.mode == "optimal_times":
            after = per_platform_after.get(platform, now)
            sched_at = _compute_optimal_slot(
                platform, after=after, already_used=used_slots)
            if sched_at:
                used_slots.add(sched_at)
                per_platform_after[platform] = sched_at

        entry = await _materialize_push(
            user_id=user.user_id, campaign_id=campaign_id, cp=cp,
            default_media=default_media, mode=payload.mode,
            scheduled_at=sched_at, now=now)
        pushed.append(entry)

    # Stamp summary on the campaign for the UI.
    await db.cortex_campaigns.update_one(
        {"id": campaign_id, "user_id": user.user_id},
        {"$set": {
            "last_pushed_at":   now,
            "last_pushed_mode": payload.mode,
            "last_pushed_count": len(pushed),
            "updated_at":       now,
        }})

    return {
        "ok":       True,
        "pushed":   pushed,
        "skipped":  skipped,
        "counts":   {"pushed": len(pushed), "skipped": len(skipped)},
    }


@api.post("/cortex/campaigns/{campaign_id}/posts/{post_id}/push")
async def push_single_post_to_calendar(campaign_id: str, post_id: str,
                                         payload: SinglePostPushPayload,
                                         request: Request):
    """Push a single cortex_social_post to the user's /posts calendar.
    Mirrors the bulk endpoint's persistence shape for full traceability."""
    user = await get_current_user(request)

    campaign = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not campaign or campaign.get("deleted_at"):
        raise HTTPException(404, "Campaign not found.")
    if campaign.get("status") != "complete":
        raise HTTPException(409, "Campaign is not complete yet.")

    cp = await db.cortex_social_posts.find_one(
        {"id": post_id, "user_id": user.user_id,
          "campaign_id": campaign_id}, {"_id": 0})
    if not cp:
        raise HTTPException(404, "Post not found in this campaign.")

    if payload.mode not in ("draft", "scheduled"):
        raise HTTPException(400, "mode must be 'draft' or 'scheduled'.")
    if payload.mode == "scheduled" and not payload.scheduled_at:
        raise HTTPException(400, "scheduled_at is required when mode='scheduled'.")

    platform_raw = cp.get("platform") or ""
    platform = _normalize_platform(platform_raw)
    if platform not in _PUSHABLE_PLATFORMS:
        raise HTTPException(
            422,
            f"Platform '{platform_raw}' is not pushable to the social calendar.")
    if cp.get("pushed_at") and cp.get("posts_id"):
        return {"ok": True, "already_pushed": True,
                "posts_id": cp.get("posts_id"),
                "platform": cp.get("pushed_platform"),
                "pushed_at": (cp["pushed_at"].isoformat()
                              if isinstance(cp["pushed_at"], datetime)
                              else cp["pushed_at"])}

    media = await _resolve_default_media(
        user_id=user.user_id, campaign_id=campaign_id,
        brief_id=campaign.get("brief_id"),
        creative_id=payload.creative_id)
    now = datetime.now(timezone.utc)
    entry = await _materialize_push(
        user_id=user.user_id, campaign_id=campaign_id, cp=cp,
        default_media=media, mode=payload.mode,
        scheduled_at=payload.scheduled_at, now=now)

    await db.cortex_campaigns.update_one(
        {"id": campaign_id, "user_id": user.user_id},
        {"$set": {"last_pushed_at": now,
                   "last_pushed_mode": payload.mode,
                   "updated_at": now},
          "$inc": {"last_pushed_count": 1}})

    return {"ok": True, **entry}
