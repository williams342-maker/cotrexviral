"""Self-improving feedback loop — turns published-post performance into
agent memory that subsequent generations consume.

The loop:
  • Every 6h, scan posts published in the last 7 days that have metrics.
  • Compute an `engagement_rate = engagement / max(impressions, 1)`.
  • Per platform per user, classify each post:
      - top 33% → "winning_hook" memory
      - bottom 33% → "failed_pattern" memory
  • Memory rows include the first 240 chars of the post body (the "hook"),
    platform, engagement_rate, and a `post_id` link.
  • Nova's chat orchestration already pulls top-K memories via the
    existing retrieval layer, so winning hooks automatically influence
    future generations without any agent-prompt changes.

Endpoints:
    GET  /api/feedback/insights        — UI surface: top winning + recent failed patterns
    POST /api/feedback/analyze-now     — manual trigger for the calling user

The "what worked" rows are also keyed by hook PREFIX so the dedupe layer
catches near-identical hooks across runs.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Request

from core import api, db
from deps import get_current_user
from routes.memory import remember

logger = logging.getLogger(__name__)

# Posts must have at least this many impressions before they count —
# otherwise a fluky 100% engagement rate on a post seen by 3 people would
# pollute the winners list.
MIN_IMPRESSIONS = 50
LOOKBACK_DAYS = 7
WINNER_TOP_PCT = 0.33
LOSER_BOTTOM_PCT = 0.33


def _engagement(post: dict) -> float:
    """engagement_rate ∈ [0, 1+] — engagement / impressions. Falls back
    to 0 when impressions missing. We allow > 1 (videos can rack up more
    likes than impressions counted)."""
    m = post.get("metrics") or {}
    impr = int(m.get("impressions") or 0)
    if impr < MIN_IMPRESSIONS:
        return -1.0  # sentinel: not enough data
    eng = int(m.get("engagement") or m.get("likes") or 0) + \
          int(m.get("comments") or 0) + int(m.get("shares") or 0)
    return eng / impr


_HOOK_TRIM_RE = re.compile(r"^[\s\d\W]+|[\s]+$")


def _hook(content: str) -> str:
    """Extract the opening "hook" of a post — the first sentence, capped
    at 240 chars. Strips leading whitespace, numbers, emoji-only prefixes
    so two posts that open with "1. " and "🚀 " match each other."""
    if not content:
        return ""
    text = content.strip()
    # First line that has more than 12 chars wins — skip leading hashtags
    # or single-emoji lines that some users post on their own line.
    for line in text.splitlines():
        line = _HOOK_TRIM_RE.sub("", line)
        if len(line) >= 12:
            return line[:240]
    return text[:240]


async def analyze_user_feedback(user_id: str) -> dict:
    """Score one user's recent published posts and write winning/failed
    memory rows. Returns `{scanned, winners_written, losers_written}`."""
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    posts = await db.posts.find(
        {
            "user_id":      user_id,
            "status":       "published",
            "published_at": {"$gte": since},
        },
        {"_id": 0},
    ).to_list(length=500)

    # Bucket by platform — the engagement-rate distributions look very
    # different across IG vs LinkedIn vs Twitter, so we tier within
    # each platform separately.
    by_platform: dict[str, list[dict]] = {}
    for p in posts:
        rate = _engagement(p)
        if rate < 0:
            continue
        plats = p.get("platforms") or ["unknown"]
        for plat in plats:
            by_platform.setdefault(plat, []).append({"post": p, "rate": rate})

    winners = losers = 0
    for plat, rows in by_platform.items():
        if len(rows) < 3:
            # Not enough to meaningfully rank — wait for more data.
            continue
        rows.sort(key=lambda r: r["rate"], reverse=True)
        winner_cut = max(1, int(len(rows) * WINNER_TOP_PCT))
        loser_cut = max(1, int(len(rows) * LOSER_BOTTOM_PCT))

        for r in rows[:winner_cut]:
            p = r["post"]
            hook = _hook(p.get("content") or "")
            if not hook:
                continue
            await remember(
                user_id, "winning_hook",
                f"[{plat}] {hook}  (engagement rate: {r['rate']:.1%})",
                meta={
                    "platform":        plat,
                    "engagement_rate": round(r["rate"], 4),
                    "post_id":         p.get("id"),
                },
                dedupe_key=f"winner:{plat}:{hook[:80].lower()}",
            )
            winners += 1

        for r in rows[-loser_cut:]:
            # Don't double-count: if the corpus is tiny (3-5 posts), the
            # bottom might overlap with the top. Skip if already counted.
            if any(r is w for w in rows[:winner_cut]):
                continue
            p = r["post"]
            hook = _hook(p.get("content") or "")
            if not hook:
                continue
            await remember(
                user_id, "failed_pattern",
                f"[{plat}] {hook}  (engagement rate: {r['rate']:.1%} — below median)",
                meta={
                    "platform":        plat,
                    "engagement_rate": round(r["rate"], 4),
                    "post_id":         p.get("id"),
                },
                dedupe_key=f"loser:{plat}:{hook[:80].lower()}",
            )
            losers += 1

    return {
        "scanned":         len(posts),
        "winners_written": winners,
        "losers_written":  losers,
    }


async def run_feedback_analysis_all_users() -> dict:
    """Cron entry point: iterate users with at least one published post
    in the lookback window."""
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    user_ids = await db.posts.distinct(
        "user_id",
        {"status": "published", "published_at": {"$gte": since}},
    )
    total_winners = total_losers = 0
    for uid in user_ids:
        try:
            r = await analyze_user_feedback(uid)
            total_winners += r["winners_written"]
            total_losers  += r["losers_written"]
        except Exception:
            logger.exception("feedback analysis failed for user=%s", uid)
    return {
        "users_processed": len(user_ids),
        "winners_written": total_winners,
        "losers_written":  total_losers,
    }


def register_feedback_job(scheduler) -> None:
    """Attach the every-6h feedback scan to the existing apscheduler.
    Idempotent across restarts because the memory writes use dedupe_keys."""
    scheduler.add_job(
        run_feedback_analysis_all_users,
        trigger=IntervalTrigger(hours=6),
        id="feedback_loop",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=11),
    )


@api.post("/feedback/analyze-now")
async def feedback_analyze_now(request: Request):
    """Manual trigger — runs the analyzer for the calling user only.
    Useful when the user just got new metrics and wants their next
    Nova draft to incorporate the learnings immediately."""
    user = await get_current_user(request)
    result = await analyze_user_feedback(user.user_id)
    return {"ok": True, **result}


@api.get("/feedback/insights")
async def feedback_insights(request: Request, limit: int = 5):
    """Surface the calling user's top winning + recent failed memory
    rows. Powers a Performance dashboard panel + tooltip on Nova drafts."""
    user = await get_current_user(request)
    limit = max(1, min(20, int(limit or 5)))

    async def _top(kind: str, sort_field: str, direction: int):
        return await db.cortex_memory.find(
            {"user_id": user.user_id, "kind": kind},
            {"_id": 0, "embedding": 0},
        ).sort(sort_field, direction).limit(limit).to_list(length=limit)

    winners = await _top("winning_hook", "meta.engagement_rate", -1)
    losers  = await _top("failed_pattern", "created_at", -1)
    return {
        "winning_hooks":  winners,
        "failed_patterns": losers,
    }
