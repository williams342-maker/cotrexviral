"""Real trending-hashtag feed for the Trend Engine.

Strategy:
  • Pull publicly-listed trending TikTok hashtags from TikTok's Creative Center
    discovery page (https://ads.tiktok.com/business/creativecenter/inspiration/topads/...)
    via a polite scrape. This data is public, no auth required.
  • Cache results in MongoDB (`trend_cache` collection) for 1 hour so we
    don't hammer their endpoint and stay well within polite-scraping norms.
  • If the scrape fails (network/blocked/HTML changes), fall back to a
    curated seed list so the Trend Engine never looks empty.

Endpoint:
  GET /api/ai/trends
      → { trends: [{ hashtag, velocity, platform, sample, source }], cached_at, ttl_seconds }

Velocity is a 0-100 score derived from the trend's rank on the source page
(rank 1 → 95, rank 30 → ~65). Sample hooks are LLM-generated from the
hashtag using the Emergent LLM key — cached alongside the trend so we
don't regenerate every request.
"""
import asyncio
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, Request

from core import db, api, logger, EMERGENT_LLM_KEY
from deps import get_current_user
from routes.plans import _get_plan


CACHE_KEY = "tiktok_trending"
CACHE_TTL = timedelta(hours=1)


# Fallback / seed pool — keeps UI alive when the scrape fails. These are
# stable "hook archetypes" that perform well regardless of week.
FALLBACK_TRENDS = [
    {"hashtag": "#PovHook",        "platform": "TikTok",  "sample": "\"POV: you finally understand the algorithm…\""},
    {"hashtag": "#Tutorial",        "platform": "Reels",   "sample": "\"3 hooks that crushed it this week:\""},
    {"hashtag": "#StoryTime",       "platform": "Shorts",  "sample": "\"Nobody talks about this, but…\""},
    {"hashtag": "#BeforeAfter",     "platform": "TikTok",  "sample": "\"This took me 7 years to figure out.\""},
    {"hashtag": "#Reveal",          "platform": "Reels",   "sample": "\"You won't guess what happened next…\""},
    {"hashtag": "#Challenge",       "platform": "TikTok",  "sample": "\"Day 1 of trying this for 30 days.\""},
    {"hashtag": "#HiddenGems",      "platform": "Shorts",  "sample": "\"The setting nobody enables on iPhone.\""},
    {"hashtag": "#Mistake",         "platform": "TikTok",  "sample": "\"Stop doing this — it's killing your reach.\""},
]


async def _scrape_tiktok_creative_center(limit: int = 12) -> list[dict]:
    """Pulls trending hashtags from TikTok's public Creative Center discovery
    page. Best-effort; returns [] when blocked / shape changes."""
    url = (
        "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
        "?period=7&page=1&limit=" + str(limit) + "&order_by=popular&country_code=US"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as cli:
            r = await cli.get(url, headers=headers)
        if r.status_code != 200:
            logger.info("TrendTok scrape: HTTP %s — falling back", r.status_code)
            return []
        data = r.json()
        items = (data or {}).get("data", {}).get("list") or []
        # Map → our schema. TikTok's response shape: {hashtag_name, rank, ...}
        out = []
        for i, item in enumerate(items):
            tag = item.get("hashtag_name") or item.get("name")
            if not tag:
                continue
            tag = tag if tag.startswith("#") else f"#{tag}"
            rank = int(item.get("rank") or i + 1)
            # rank 1 → 95; each step down loses ~1pt
            velocity = max(50, min(98, 96 - (rank - 1)))
            out.append({
                "hashtag": tag,
                "platform": "TikTok",
                "velocity": velocity,
                "rank": rank,
                "publish_cnt": item.get("publish_cnt"),
                "video_views": item.get("video_views"),
            })
        return out
    except Exception:
        logger.exception("TrendTok scrape failed")
        return []


async def _generate_sample_hooks(hashtags: list[str]) -> dict[str, str]:
    """Bulk-generate one short hook per hashtag via the LLM. Returns
    a {hashtag: sample_hook} dict. Best-effort — empty on failure."""
    if not EMERGENT_LLM_KEY or not hashtags:
        return {}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id="trend_hooks",
            system_message=(
                "You write scroll-stopping TikTok/Reels hooks. For each hashtag, "
                "produce ONE 6-12 word first-line hook. Return JSON only: "
                '{"hooks":[{"tag":"#foo","hook":"…"}, …]} no commentary.'
            ),
        ).with_model("openai", "gpt-4o-mini")
        prompt = "Generate one hook for each of: " + ", ".join(hashtags[:12])
        raw = await chat.send_message(UserMessage(text=prompt))
        # Extract JSON
        import json
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if not m:
            return {}
        parsed = json.loads(m.group(0))
        out = {}
        for entry in parsed.get("hooks") or []:
            tag = entry.get("tag", "").strip()
            if tag and entry.get("hook"):
                out[tag.lower()] = entry["hook"].strip().strip('"').strip("'")
        return out
    except Exception:
        logger.exception("Sample-hook LLM batch failed")
        return {}


async def _build_trend_payload(limit: int = 6) -> dict:
    """Refresh the cache: scrape + hook-generate + persist."""
    scraped = await _scrape_tiktok_creative_center(limit=limit * 2)
    if not scraped:
        # Pure fallback path
        trends = [
            {**t, "velocity": 92 - i * 4, "source": "fallback"}
            for i, t in enumerate(FALLBACK_TRENDS[:limit])
        ]
    else:
        # Generate fresh hook samples for the top N
        tags = [t["hashtag"] for t in scraped[:limit]]
        hooks_map = await _generate_sample_hooks(tags)
        trends = []
        for t in scraped[:limit]:
            sample = hooks_map.get(t["hashtag"].lower())
            if not sample:
                # Pull a sample line from the fallback pool keyed by index
                idx = len(trends) % len(FALLBACK_TRENDS)
                sample = FALLBACK_TRENDS[idx]["sample"]
            trends.append({**t, "sample": sample, "source": "tiktok_creative_center"})

    return {
        "trends": trends,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": int(CACHE_TTL.total_seconds()),
    }


async def _get_or_refresh() -> dict:
    """Returns the cached payload if fresh, else triggers refresh."""
    doc = await db.trend_cache.find_one({"_id": CACHE_KEY})
    if doc:
        cached_at = doc.get("cached_at")
        if isinstance(cached_at, str):
            cached_at = datetime.fromisoformat(cached_at)
        if cached_at and cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
        if cached_at and datetime.now(timezone.utc) - cached_at < CACHE_TTL:
            return doc["payload"]

    # Refresh
    payload = await _build_trend_payload(limit=6)
    await db.trend_cache.update_one(
        {"_id": CACHE_KEY},
        {"$set": {"_id": CACHE_KEY, "payload": payload,
                  "cached_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return payload


@api.get("/ai/trends")
async def get_trends(request: Request):
    """Live trending hashtag feed. Gated to Growth+ plans."""
    user = await get_current_user(request)
    plan = await _get_plan(user.user_id)

    # Feature gate: Growth/Agency/Scale only (Free/Starter blocked)
    from routes.plans import ENTITLEMENTS
    if not ENTITLEMENTS.get(plan, {}).get("features", {}).get("trend_engine"):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "feature_locked",
                "message": "Trend Engine requires Growth or higher.",
                "plan": plan,
                "feature": "trend_engine",
            },
        )

    return await _get_or_refresh()


@api.post("/ai/trends/refresh")
async def force_refresh_trends(request: Request):
    """Force a cache bust. Same gate as the GET."""
    user = await get_current_user(request)
    plan = await _get_plan(user.user_id)
    from routes.plans import ENTITLEMENTS
    if not ENTITLEMENTS.get(plan, {}).get("features", {}).get("trend_engine"):
        raise HTTPException(status_code=402, detail={"code": "feature_locked"})

    payload = await _build_trend_payload(limit=6)
    await db.trend_cache.update_one(
        {"_id": CACHE_KEY},
        {"$set": {"_id": CACHE_KEY, "payload": payload,
                  "cached_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return payload
