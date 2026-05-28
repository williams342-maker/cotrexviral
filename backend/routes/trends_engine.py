"""Trend ingestion engine — pulls real-world signals into user memory.

Sources (no extra API keys required):
  • Reddit — public JSON endpoints `/r/{sub}/hot.json` (top 5 hot posts).
  • Google Trends — `pytrends` (unofficial scraper, but stable).
  • X (Twitter) — TODO. Requires paid API tier, scaffolded for later.

Storage:
  Every trend becomes a `cortex_memory` row with kind="trend" + meta:
    {source: "reddit"|"gtrends", subreddit?: str, keyword?: str,
     created_at: datetime}
  Deduped by `dedupe_key = f"{source}:{external_id}"` so re-running the
  job updates instead of duplicating.

Endpoints:
  POST /api/trends/ingest body {keywords?: [str], subreddits?: [str]}
       → on-demand pull for the calling user. Limits: 10 subs, 5 keywords.
  GET  /api/trends/recent → user's last 30 trend memories.

Background job:
  `refresh_trends_for_all_users` runs every 6h via the scheduler. Iterates
  users with a `niche_keywords` / `niche_subreddits` list set on their
  profile (best-effort heuristic: derive from `users.niche` if not set).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field

from core import db, api
from deps import get_current_user
from routes.memory import remember

logger = logging.getLogger(__name__)


# Niche → default subreddits / keyword seeds. Used when the user hasn't
# manually configured their watch-list. Tuned for SMB marketing audiences.
DEFAULT_NICHE_SUBREDDITS: dict[str, list[str]] = {
    "saas":            ["SaaS", "startups", "Entrepreneur"],
    "ecommerce":       ["ecommerce", "shopify", "FulfillmentByAmazon"],
    "creator":         ["NewTubers", "ContentCreators", "InstagramMarketing"],
    "agency":          ["agency", "marketing", "PPC"],
    "fitness":         ["Fitness", "loseit", "personaltraining"],
    "skincare":        ["SkincareAddiction", "30PlusSkinCare"],
    "yoga":            ["yoga", "mindfulness"],
    "food":            ["FoodPorn", "EatCheapAndHealthy"],
    "default":         ["marketing", "smallbusiness", "Entrepreneur"],
}


def _seeds_for_user(user_doc: dict) -> tuple[list[str], list[str]]:
    """Return (subreddits, keywords) to scan for this user. Respects any
    user-set watch-list; falls back to niche-default heuristics."""
    sub_list = (user_doc.get("niche_subreddits") or [])[:10]
    kw_list = (user_doc.get("niche_keywords") or [])[:5]
    if not sub_list:
        niche = (user_doc.get("niche") or "").strip().lower()
        sub_list = DEFAULT_NICHE_SUBREDDITS.get(niche, DEFAULT_NICHE_SUBREDDITS["default"])
    if not kw_list:
        brand = user_doc.get("brand_name") or ""
        kw_list = [user_doc.get("niche")] if user_doc.get("niche") else []
        if brand and brand not in kw_list:
            kw_list.append(brand)
    return [s for s in sub_list if s][:10], [k for k in kw_list if k][:5]


# ---------------------------------------------------------------------------
# Reddit ingestion
# ---------------------------------------------------------------------------
async def _fetch_reddit_hot(subreddit: str, limit: int = 5) -> list[dict]:
    """Returns a list of {id, title, score, url, comments} for the top
    `limit` hot posts in /r/{subreddit}. Empty list on any failure.

    NOTE: Reddit blocks the unauthenticated JSON endpoint from many
    datacenter IPs (AWS/GCP/etc.) with a 403. The code path below is
    correct and works from residential IPs. For production reliability,
    set up Reddit OAuth (https://www.reddit.com/prefs/apps) and switch
    to `oauth.reddit.com` with an access token — see the TODO note in
    the module docstring.
    """
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}&raw_json=1"
    headers = {
        "User-Agent": "CortexViralBot/1.0 (+https://cortexviral.com)",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(url, headers=headers)
        if r.status_code != 200:
            return []
        children = ((r.json() or {}).get("data") or {}).get("children") or []
        out = []
        for c in children:
            d = c.get("data") or {}
            if d.get("stickied"):
                continue
            out.append({
                "id": d.get("id"),
                "title": d.get("title") or "",
                "score": int(d.get("score") or 0),
                "num_comments": int(d.get("num_comments") or 0),
                "permalink": f"https://reddit.com{d.get('permalink', '')}",
                "subreddit": d.get("subreddit") or subreddit,
            })
        return out
    except Exception:
        logger.exception("Reddit fetch failed for /r/%s", subreddit)
        return []


# ---------------------------------------------------------------------------
# Google Trends ingestion
# ---------------------------------------------------------------------------
def _pytrends_safely() -> Optional[object]:
    """Build a pytrends client; returns None if pytrends/lxml stack failed
    to import for any reason (we never want a missing-dep to blow up the
    whole route module)."""
    try:
        from pytrends.request import TrendReq
        return TrendReq(hl="en-US", tz=0)
    except Exception:
        logger.exception("pytrends init failed")
        return None


async def _fetch_gtrends_for(keyword: str) -> list[dict]:
    """Returns 5 related queries for `keyword` as {query, value} dicts.
    pytrends is blocking, so we run it in a thread."""
    if not keyword.strip():
        return []

    def _go():
        client = _pytrends_safely()
        if not client:
            return []
        try:
            client.build_payload([keyword[:50]], timeframe="now 7-d")
            data = client.related_queries() or {}
            rq = (data.get(keyword[:50]) or {}).get("rising")
            if rq is None or rq.empty:
                return []
            rows = rq.head(5).to_dict("records")
            return [{"query": r.get("query"), "value": int(r.get("value") or 0)}
                    for r in rows if r.get("query")]
        except Exception:
            logger.exception("pytrends fetch failed for %r", keyword)
            return []
    return await asyncio.to_thread(_go)


# ---------------------------------------------------------------------------
# Ingestion orchestrator
# ---------------------------------------------------------------------------
async def ingest_trends_for_user(user_id: str) -> dict:
    """Pull Reddit hot posts + Google Trends rising queries for one user
    and write them into the memory system as kind='trend'. Returns a
    summary {reddit, gtrends, errors}."""
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0}) or {}
    subreddits, keywords = _seeds_for_user(user_doc)

    reddit_count = 0
    for sub in subreddits:
        posts = await _fetch_reddit_hot(sub, limit=5)
        for p in posts:
            text = f"r/{p['subreddit']} ({p['score']} upvotes, {p['num_comments']} comments): {p['title']}"
            await remember(
                user_id, "trend", text,
                meta={
                    "source": "reddit",
                    "subreddit": p["subreddit"],
                    "score": p["score"],
                    "permalink": p["permalink"],
                },
                dedupe_key=f"reddit:{p['id']}",
            )
            reddit_count += 1

    gtrends_count = 0
    for kw in keywords:
        rising = await _fetch_gtrends_for(kw)
        for r in rising:
            text = f"Google Trends rising query for '{kw}': {r['query']} (+{r['value']}%)"
            # Use the query itself as the dedupe key so repeated runs update.
            await remember(
                user_id, "trend", text,
                meta={"source": "gtrends", "keyword": kw, "growth": r["value"]},
                dedupe_key=f"gtrends:{kw}:{r['query']}",
            )
            gtrends_count += 1

    return {"reddit": reddit_count, "gtrends": gtrends_count,
            "subreddits": subreddits, "keywords": keywords}


# ---------------------------------------------------------------------------
# Background job — registered from scheduler.py
# ---------------------------------------------------------------------------
async def refresh_trends_for_all_users():
    """Iterates every active user and ingests their trend feed. Bounded
    at 100 users per tick to keep the loop predictable."""
    cursor = db.users.find(
        {"status": {"$ne": "suspended"}},
        {"_id": 0, "user_id": 1, "niche": 1,
         "niche_subreddits": 1, "niche_keywords": 1, "brand_name": 1},
    ).limit(100)
    ingested = 0
    async for u in cursor:
        try:
            res = await ingest_trends_for_user(u["user_id"])
            if res["reddit"] or res["gtrends"]:
                ingested += 1
        except Exception:
            logger.exception("Trend ingestion failed for %s", u.get("user_id"))
    if ingested:
        logger.info("Trend refresh: ingested for %s user(s)", ingested)


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
class _IngestRequest(BaseModel):
    subreddits: Optional[list[str]] = Field(default=None, max_length=10)
    keywords: Optional[list[str]] = Field(default=None, max_length=5)


@api.post("/trends/ingest")
async def trigger_ingest(payload: _IngestRequest, request: Request):
    """On-demand trend pull for the calling user. If `subreddits`/`keywords`
    are passed we ALSO persist them on the user doc so the background job
    picks them up next time."""
    user = await get_current_user(request)
    update = {}
    if payload.subreddits is not None:
        update["niche_subreddits"] = payload.subreddits[:10]
    if payload.keywords is not None:
        update["niche_keywords"] = payload.keywords[:5]
    if update:
        await db.users.update_one({"user_id": user.user_id}, {"$set": update})

    summary = await ingest_trends_for_user(user.user_id)
    return {"ok": True, **summary}


@api.get("/trends/recent")
async def list_recent_trends(request: Request, limit: int = 30):
    """User's most recent trend memories (no embedding payload)."""
    user = await get_current_user(request)
    rows = await db.cortex_memory.find(
        {"user_id": user.user_id, "kind": "trend"},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1).limit(min(100, max(1, limit))).to_list(length=100)
    return {"trends": rows, "count": len(rows)}


@api.get("/trends/seeds")
async def get_seeds(request: Request):
    """Returns the user's current trend watch-list (effective values,
    including defaults if none set)."""
    user = await get_current_user(request)
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    subs, kws = _seeds_for_user(doc)
    return {
        "subreddits": subs,
        "keywords": kws,
        "user_configured": bool(doc.get("niche_subreddits") or doc.get("niche_keywords")),
    }
