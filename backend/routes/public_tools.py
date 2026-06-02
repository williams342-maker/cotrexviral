"""Public marketing tools — no auth required, rate-limited per IP.

These power the on-site free tools (viral post generator, etc.) used as
lead magnets on the marketing site. They run a single Claude Haiku 4.5
tool-call and return structured results."""
from __future__ import annotations

import logging
import time
from typing import Dict, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api
from cortex.llm_provider import cortex_tool_call

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Simple in-memory IP rate limiter. Public, unauthenticated endpoints need
# *some* abuse guard — but anything heavier (Redis, distributed) is overkill
# for a free landing-page tool. 8 generations/hour/IP is generous for real
# users but stings scrapers.
# -----------------------------------------------------------------------------
_IP_BUCKET: Dict[str, List[float]] = {}
_RATE_WINDOW_S = 60 * 60      # 1 hour
_RATE_MAX_HITS = 8            # per IP per window


def _ratelimit(request: Request, key: str) -> None:
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    bucket_key = f"{key}::{ip}"
    now = time.time()
    bucket = _IP_BUCKET.get(bucket_key, [])
    # Drop expired entries
    bucket = [t for t in bucket if (now - t) < _RATE_WINDOW_S]
    if len(bucket) >= _RATE_MAX_HITS:
        raise HTTPException(
            429,
            "Whoa — you've hit the free-tool limit for this hour. "
            "Sign up for an account to keep generating.",
        )
    bucket.append(now)
    _IP_BUCKET[bucket_key] = bucket
    # Janitor: trim the global dict periodically so it can't grow unbounded.
    if len(_IP_BUCKET) > 5000:
        for k in list(_IP_BUCKET.keys())[:1000]:
            _IP_BUCKET.pop(k, None)


# -----------------------------------------------------------------------------
# Viral Post Generator
# -----------------------------------------------------------------------------
_ALLOWED_PLATFORMS = {"tiktok", "instagram", "x", "twitter", "linkedin",
                       "youtube", "facebook", "threads", "reddit", "pinterest"}


class ViralPostRequest(BaseModel):
    niche: str = Field(..., min_length=2, max_length=200)
    platform: str = Field(..., min_length=1, max_length=40)


def _platform_norm(p: str) -> str:
    p = (p or "").strip().lower()
    if p == "twitter":
        return "x"
    return p


_PLATFORM_NOTE = {
    "tiktok":    "TikTok — open with a 1-2 line spoken hook, then 3-5 timed beats. Include on-screen text suggestion. 60-180 sec total.",
    "instagram": "Instagram Reels or carousel — first line is the hook, then 5-8 short paragraphs of value, finish with CTA + 5-8 niche hashtags.",
    "x":         "X (Twitter) — single tweet OR a 5-tweet thread. Tight hook, no fluff, no hashtags.",
    "linkedin":  "LinkedIn — long-form post. Strong first 2 lines (cuts off at 'see more'). 8-12 short paragraphs. Personal-pro voice.",
    "youtube":   "YouTube Shorts — 45-60 sec script with timed beats. Open with a pattern interrupt.",
    "facebook":  "Facebook post — 3-5 paragraphs, conversational, ends with a question to drive comments.",
    "threads":   "Threads — under 500 chars, conversational, one strong opinion or insight.",
    "reddit":    "Reddit — title is the hook, body is a personal story or genuine value. No marketing voice.",
    "pinterest": "Pinterest — pin title + 2-sentence description optimised for search. Add 3-5 keywords.",
}


@api.post("/tools/viral-post")
async def public_viral_post(payload: ViralPostRequest, request: Request):
    """Generate 3 hook-tested post variants for a given niche + platform.
    Public endpoint — no auth, IP rate-limited to 8/hour."""
    _ratelimit(request, "viral_post")

    platform = _platform_norm(payload.platform)
    if platform not in _ALLOWED_PLATFORMS:
        raise HTTPException(400, "Unsupported platform.")
    niche = payload.niche.strip()
    if not niche:
        raise HTTPException(400, "Tell us your niche so we can write good hooks.")

    platform_note = _PLATFORM_NOTE.get(platform, "")
    system_prompt = (
        "You are CortexViral's viral-post engine. Generate THREE distinct "
        "hook-tested social posts for the given niche and platform. Each "
        "must use a *different* proven hook framework: 'contrarian take', "
        "'curiosity gap', and 'data shock'. Posts must be ready to ship — "
        "no placeholders, no '[insert X]', no generic advice."
    )
    user_text = (
        f"NICHE: {niche}\n"
        f"PLATFORM: {platform.upper()}\n"
        f"PLATFORM FORMAT: {platform_note}"
    )
    tool_schema = {
        "name": "emit_viral_posts",
        "description": "Return exactly 3 hook-tested social posts.",
        "parameters": {
            "type": "object",
            "properties": {
                "posts": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "hook_type":    {"type": "string", "enum": ["contrarian", "curiosity", "data_shock"]},
                            "hook":         {"type": "string", "description": "First line — must stop the scroll."},
                            "body":         {"type": "string", "description": "Full post body, ready to paste."},
                            "cta":          {"type": "string", "description": "One short CTA."},
                            "why_it_works": {"type": "string", "description": "One sentence on the psychological lever."},
                        },
                        "required": ["hook_type", "hook", "body", "cta", "why_it_works"],
                    },
                },
            },
            "required": ["posts"],
        },
    }

    try:
        # Haiku is fast (~3-5s) and quality is plenty for a top-funnel demo.
        # Failover chain: haiku → claude → gpt keeps the endpoint resilient.
        args, _label, _mode = await cortex_tool_call(
            system_prompt,
            user_text,
            tool=tool_schema,
            session_id=f"public_viral_post_{int(time.time())}",
            user_id="public",
            prefer="haiku",
            required=["posts"],
        )
    except Exception:   # noqa: BLE001
        logger.exception("public_viral_post: LLM call failed")
        raise HTTPException(503,
            "Generation engine is busy right now — try again in a moment.")

    data = args or {}

    posts = (data or {}).get("posts")
    if not isinstance(posts, list) or len(posts) == 0:
        raise HTTPException(502, "Generator returned no posts — try again.")
    # Trim to 3 and normalize fields.
    cleaned = []
    for p in posts[:3]:
        if not isinstance(p, dict):
            continue
        cleaned.append({
            "hook_type":    str(p.get("hook_type") or "")[:40],
            "hook":         str(p.get("hook") or "").strip()[:280],
            "body":         str(p.get("body") or "").strip()[:3000],
            "cta":          str(p.get("cta") or "").strip()[:140],
            "why_it_works": str(p.get("why_it_works") or "").strip()[:240],
        })
    if not cleaned:
        raise HTTPException(502, "Generator returned no usable posts.")
    return {
        "ok":       True,
        "niche":    niche,
        "platform": platform,
        "posts":    cleaned,
    }
