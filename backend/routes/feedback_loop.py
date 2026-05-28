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


# ---------------------------------------------------------------------------
# Prompt-injection helper — deterministic feedback signal
# ---------------------------------------------------------------------------
# Used by Nova's draft flows (`trends_engine.draft_post_from_trend`) and the
# Marketing OS chain (`marketing_os.run_marketing_os`). Returns a compact
# system-prompt block listing the top-3 winning hooks (optionally filtered
# by platform) so every Nova generation explicitly reuses what's worked
# instead of relying on the embedding retrieval to surface them.
async def winning_hooks_prompt_block(
    user_id: str,
    *,
    platform: str = "",
    limit: int = 3,
) -> str:
    """Return a `<winning_hooks>...</winning_hooks>` block ready to be
    appended to an agent's system prompt. Returns "" when the user has no
    winners yet (brand-new accounts), so callers can safely concatenate
    without a `if block: ...` check at every call-site.
    """
    q: dict = {"user_id": user_id, "kind": "winning_hook"}
    if platform:
        q["meta.platform"] = platform.lower()
    rows = await db.cortex_memory.find(
        q, {"_id": 0, "embedding": 0},
    ).sort("meta.engagement_rate", -1).limit(max(1, min(10, limit))).to_list(length=limit)
    if not rows:
        return ""
    lines = []
    for r in rows:
        rate = (r.get("meta") or {}).get("engagement_rate") or 0
        plat = (r.get("meta") or {}).get("platform") or "?"
        # Strip the leading "[platform]" prefix and any trailing
        # "(engagement rate: …)" noise so the LLM gets a clean hook.
        text = (r.get("text") or "")
        import re as _re
        text = _re.sub(r"^\s*\[[^\]]+\]\s*", "", text)
        text = _re.sub(r"\s*\(engagement rate:[^)]+\)\s*$", "", text)
        lines.append(f"  - [{plat} · {rate * 100:.1f}%] {text.strip()[:240]}")
    body = "\n".join(lines)
    return (
        "\n\n<winning_hooks>\n"
        "Past posts from this user that beat the median engagement rate. "
        "When you draft something new, lean on the patterns below — same "
        "voice, same opener style, same length cadence. Do NOT copy them "
        "verbatim, but let them shape your output:\n"
        f"{body}\n"
        "</winning_hooks>"
    )


async def brand_voice_prompt_block(user_id: str, *, limit: int = 5) -> str:
    """Return a `<brand_voice>...</brand_voice>` block listing the
    user's explicitly-promoted voice patterns.

    Unlike `winning_hooks_prompt_block` (which is statistical — top
    performers by engagement), brand_voice rows are *user-curated*:
    the user clicked "Promote to Brand Voice" on a hook because they
    want THIS pattern to shape every future generation.

    Returned block is a stricter directive — the LLM should treat
    these as canonical voice anchors, not just performance hints.

    Returns "" when the user has promoted nothing yet, so callers can
    concatenate the block unconditionally."""
    rows = await db.cortex_memory.find(
        {"user_id": user_id, "kind": "brand_voice"},
        {"_id": 0, "embedding": 0},
    ).limit(max(1, min(20, limit)) * 2).to_list(length=limit * 2)
    if not rows:
        return ""
    # Sort by user-defined order (drag-reorder via /brand-voice/reorder)
    # with created_at desc as fallback for legacy rows that lack order.
    def _key(r: dict):
        meta = r.get("meta") or {}
        order = meta.get("order")
        ts = (r.get("created_at").timestamp() if r.get("created_at") else 0)
        return (1, 0, -ts) if order is None else (0, order, 0)
    rows.sort(key=_key)
    rows = rows[:limit]
    import re as _re
    lines = []
    for r in rows:
        text = (r.get("text") or "")
        # The promote-hook route wraps the hook in a "prefer this voice…"
        # template. Strip that wrapper for cleaner LLM context — pull out
        # only the quoted hook text.
        match = _re.search(r'"([^"]+)"', text)
        anchor = match.group(1) if match else text
        plat = (r.get("meta") or {}).get("platform") or ""
        plat_tag = f" ({plat})" if plat else ""
        lines.append(f"  - {anchor[:280]}{plat_tag}")
    body = "\n".join(lines)
    return (
        "\n\n<brand_voice>\n"
        "These are the user's canonical voice anchors — patterns they've "
        "explicitly chosen as representative of how their brand sounds. "
        "Every draft you produce MUST echo this voice (tone, opener style, "
        "sentence rhythm, level of directness). Treat these as harder "
        "constraints than the statistical winning_hooks:\n"
        f"{body}\n"
        "</brand_voice>"
    )

