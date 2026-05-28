"""Trend ingestion engine — pulls real-world signals into user memory.

Sources:
  • Reddit — via OAuth2 `client_credentials` on `oauth.reddit.com`.
    Reddit's anonymous JSON endpoints (`www.reddit.com/r/*.json`) return
    403 from datacenter IPs since the 2023 API lockdown, so we use the
    free "application-only" OAuth grant. Requires REDDIT_CLIENT_ID +
    REDDIT_CLIENT_SECRET (create a "script" app at
    https://www.reddit.com/prefs/apps). Gracefully skipped if missing.
  • Google Trends — `pytrends` (unofficial, but stable). No key needed.
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
  GET  /api/trends/status → reports which sources are configured.

Background job:
  `refresh_trends_for_all_users` runs every 6h via the scheduler. Iterates
  users with a `niche_keywords` / `niche_subreddits` list set on their
  profile (best-effort heuristic: derive from `users.niche` if not set).
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request, HTTPException
from pydantic import BaseModel, Field

from core import db, api
from deps import get_current_user
from routes.memory import remember

logger = logging.getLogger(__name__)

REDDIT_CLIENT_ID = (os.environ.get("REDDIT_CLIENT_ID") or "").strip()
REDDIT_CLIENT_SECRET = (os.environ.get("REDDIT_CLIENT_SECRET") or "").strip()
REDDIT_USER_AGENT = (
    os.environ.get("REDDIT_USER_AGENT")
    or "python:cortexviral.trends:v1.0 (by /u/cortexviral)"
).strip()


def _reddit_configured() -> bool:
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)


# In-process Reddit OAuth token cache. App-only tokens last 24h; we
# refresh after 50min to leave buffer. Single-process worker → in-memory
# is fine; tokens are not user-specific.
_reddit_token_cache: dict = {"token": None, "expires_at": 0.0}


async def _reddit_app_token() -> Optional[str]:
    """Fetch (and cache) a Reddit application-only OAuth bearer token.
    Returns None if creds aren't configured or the auth call fails."""
    if not _reddit_configured():
        return None
    now = time.time()
    if _reddit_token_cache["token"] and _reddit_token_cache["expires_at"] > now + 30:
        return _reddit_token_cache["token"]
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": REDDIT_USER_AGENT},
            )
        if r.status_code != 200:
            logger.warning("Reddit token fetch failed: %s %s", r.status_code, r.text[:200])
            return None
        body = r.json() or {}
        token = body.get("access_token")
        ttl = int(body.get("expires_in") or 3600)
        if not token:
            return None
        _reddit_token_cache["token"] = token
        _reddit_token_cache["expires_at"] = now + min(ttl, 3000)
        return token
    except Exception:
        logger.exception("Reddit token fetch crashed")
        return None


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

    Uses Reddit's app-only OAuth flow on `oauth.reddit.com`. Anonymous
    `www.reddit.com/r/*.json` access returns 403 from datacenter IPs.
    When `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are not set we return
    an empty list quickly (no network call).
    """
    token = await _reddit_app_token()
    if not token:
        return []
    url = f"https://oauth.reddit.com/r/{subreddit}/hot?limit={limit}&raw_json=1"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": REDDIT_USER_AGENT,
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(url, headers=headers)
        if r.status_code == 401:
            # token possibly expired mid-flight; flush and bail (next run retries).
            _reddit_token_cache["token"] = None
            _reddit_token_cache["expires_at"] = 0.0
            return []
        if r.status_code != 200:
            logger.warning("Reddit %s returned %s", subreddit, r.status_code)
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
    reddit_skipped = not _reddit_configured()
    if not reddit_skipped:
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
            "reddit_configured": not reddit_skipped,
            "subreddits": subreddits if not reddit_skipped else [],
            "keywords": keywords}


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



@api.get("/trends/status")
async def trends_source_status(request: Request):
    """Reports which trend sources are currently usable. Helps the
    frontend show a "Reddit not configured" hint to the user/admin."""
    await get_current_user(request)
    return {
        "reddit": {
            "configured": _reddit_configured(),
            "note": (
                "Set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (create a "
                "'script' app at https://www.reddit.com/prefs/apps) to "
                "enable Reddit ingestion."
                if not _reddit_configured() else "Reddit OAuth ready."
            ),
        },
        "gtrends": {
            "configured": True,
            "note": "Google Trends always available (pytrends, no key).",
        },
    }



# ---------------------------------------------------------------------------
# "Draft post from signal" — closes the loop: signal → memory → content
# ---------------------------------------------------------------------------
class _DraftFromSignalRequest(BaseModel):
    trend_id: str = Field(..., min_length=1, max_length=64)
    platform: Optional[str] = Field(default="linkedin", max_length=24)


_PLATFORM_GUIDANCE = {
    "linkedin":  "LinkedIn post (200-300 words, professional tone, 1 sharp hook, line breaks for skim-ability, no hashtag dump — 3 max).",
    "twitter":   "Twitter / X thread (4-6 tweets, each <=280 chars, lead with the spiciest insight).",
    "x":         "X (Twitter) thread (4-6 tweets, each <=280 chars, lead with the spiciest insight).",
    "instagram": "Instagram caption (120-180 words, conversational, line breaks for readability, ~5 hashtags).",
    "tiktok":    "TikTok caption + hook (under 150 chars caption, plus a 3-line voiceover script with a pattern-interrupt opener).",
    "pinterest": "Pinterest pin title (<=100 chars) + description (200-300 chars) + 4 hashtags.",
    "facebook":  "Facebook post (150-220 words, friendly tone, 1 question to drive comments, 2-3 hashtags).",
}


@api.post("/trends/draft-post")
async def draft_post_from_trend(payload: _DraftFromSignalRequest, request: Request):
    """Generate a platform-tailored draft post from one ingested trend
    signal. Uses Nova (Copy specialist) so the voice matches what the
    user gets from the Agent Workspace.

    Returns `{draft, platform, signal: {text, source}, suggested_hashtags}`.
    The draft is also persisted as a `draft_from_trend` memory row so
    Compose can pick it up later and the user has audit history.

    Routes through Nova's existing LLM model (creative/Sonnet by default,
    or the user's per-agent mode preference). Counts towards the user's
    AI generation quota + appears in the admin spend dashboard."""
    from routes.ai import _gated_user
    user = await _gated_user(request)
    platform = (payload.platform or "linkedin").strip().lower()
    if platform not in _PLATFORM_GUIDANCE:
        raise HTTPException(status_code=422, detail="Unsupported platform")

    # Fetch the signal — both ownership and existence in one query.
    signal = await db.cortex_memory.find_one(
        {"id": payload.trend_id, "user_id": user.user_id, "kind": "trend"},
        {"_id": 0, "id": 1, "text": 1, "meta": 1},
    )
    if not signal:
        raise HTTPException(status_code=404, detail="Trend signal not found")

    # Build the brief for Nova. We embed the signal verbatim so she can
    # quote the actual upvote count / growth % when useful.
    from routes.agent_chat import AGENTS
    from routes.ai import _llm_for_user
    from routes.model_router import resolve_user_mode
    from routes.plans import record_ai_generation
    from emergentintegrations.llm.chat import UserMessage

    nova = AGENTS["nova"]
    # Honor the user's saved per-agent mode preference if they've set one.
    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "agent_prefs": 1, "brand_name": 1, "niche": 1},
    ) or {}
    user_mode = (user_doc.get("agent_prefs") or {}).get("nova", "auto")
    provider, model, task_used = resolve_user_mode(user_mode, "nova")

    brand_block = ""
    if user_doc.get("brand_name") or user_doc.get("niche"):
        brand_block = (
            f"\n\nBrand: {user_doc.get('brand_name') or 'n/a'} · "
            f"Niche: {user_doc.get('niche') or 'n/a'}"
        )

    system = nova["system"] + (
        f"\n\nYou are turning a viral signal into one shippable {platform} draft. "
        f"Format spec: {_PLATFORM_GUIDANCE[platform]} "
        "Lead with what the SIGNAL itself says, not generic advice. "
        "End your reply with a separate line: `HASHTAGS: #tag1 #tag2 #tag3`."
        + brand_block
    )
    chat = await _llm_for_user(
        user.user_id, f"draft-from-signal-{user.user_id}", system,
        provider=provider, model=model,
    )
    user_msg = f"Signal:\n{signal['text']}\n\nDraft the {platform} post now."
    try:
        from routes.ai import send_with_usage
        raw, draft_usage = await send_with_usage(chat, UserMessage(text=user_msg))
    except Exception as e:
        # Surface a clean error instead of a generic 500.
        if "budget" in str(e).lower():
            raise HTTPException(status_code=503, detail="LLM budget exceeded — top up the universal key")
        raise HTTPException(status_code=502, detail=f"Draft generation failed: {str(e)[:200]}")
    raw = (raw or "").strip()

    # Pull out the trailing HASHTAGS line so the frontend can render
    # them as separate pills.
    suggested_hashtags: list[str] = []
    draft_body = raw
    for line in reversed(raw.splitlines()):
        if line.upper().startswith("HASHTAGS:"):
            tags = line.split(":", 1)[1].strip()
            suggested_hashtags = [
                t if t.startswith("#") else f"#{t}"
                for t in tags.replace(",", " ").split() if t.strip("#")
            ][:8]
            draft_body = raw.replace(line, "").rstrip()
            break

    # Persist + bookkeeping (best-effort each).
    try:
        from routes.memory import remember
        await remember(
            user.user_id, "draft_from_trend",
            f"Draft ({platform}) from signal: {signal['text'][:160]}",
            meta={
                "signal_id": signal["id"], "platform": platform,
                "draft": draft_body[:1200],
                "hashtags": suggested_hashtags,
            },
            dedupe_key=f"draft:{signal['id']}:{platform}",
        )
    except Exception:
        pass
    try:
        await record_ai_generation(user.user_id, f"trend_draft:{platform}")
    except Exception:
        pass
    try:
        from routes.llm_spend import record_llm_call
        await record_llm_call(user.user_id, "nova", task_used, model, draft_usage)
    except Exception:
        pass

    return {
        "draft": draft_body,
        "platform": platform,
        "suggested_hashtags": suggested_hashtags,
        "signal": {
            "id":     signal["id"],
            "text":   signal["text"],
            "source": (signal.get("meta") or {}).get("source"),
        },
        "model": model,
        "mode":  task_used,
    }
