"""AI / LLM endpoints — content generation, SEO review, optimal times."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional

from core import db, api, logger, EMERGENT_LLM_KEY
from deps import get_current_user
from routes.plans import assert_can_generate_ai, record_ai_generation
from models import (
    User, AIRequest, SocialPostRequest, NewsletterRequest, BlogRequest, UpdateRequest, VideoScriptRequest, MultiPostRequest,
)
from emergentintegrations.llm.chat import LlmChat, UserMessage
import httpx
import re
import json


async def _gated_user(request: Request):
    """Auth + plan gate. Use for any AI endpoint that should count against
    the user's monthly AI-generation quota."""
    auth_user = await get_current_user(request)
    await assert_can_generate_ai(auth_user.user_id)
    return auth_user


# -----------------------------------------------------------------------------
# Per-user context preamble — built from the onboarding profile so every AI
# call is tailored to the user's niche, goals, and challenge instead of
# returning generic marketing-slop.
# -----------------------------------------------------------------------------
async def _user_context_block(user_id: str) -> str:
    doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "brand_name": 1, "website": 1, "niche": 1,
         "goals": 1, "platforms": 1, "challenge": 1},
    ) or {}
    parts = []
    if doc.get("brand_name") or doc.get("website"):
        parts.append(
            "BRAND: "
            + (doc.get("brand_name") or "(no name)")
            + (f' ({doc.get("website")})' if doc.get("website") else "")
        )
    if doc.get("niche"):
        parts.append(f"NICHE: {doc['niche']}")
    if doc.get("goals"):
        parts.append("GOALS: " + ", ".join(doc["goals"]))
    if doc.get("platforms"):
        parts.append("PRIMARY PLATFORMS: " + ", ".join(doc["platforms"]))
    if doc.get("challenge"):
        # Truncate the user's free-text challenge to keep the prompt focused.
        ch = doc["challenge"][:280].replace("\n", " ").strip()
        parts.append(f'STATED CHALLENGE: "{ch}"')
    if not parts:
        return ""
    return (
        "\n\nUSER CONTEXT (use this to keep advice specific, NOT generic):\n- "
        + "\n- ".join(parts)
        + "\n\nWhen the user's request relates to their brand/niche/goals, "
        "tailor your output to them. Don't restate the context back to them — "
        "just make the output reflect it. Avoid generic platitudes."
    )


async def _llm_for_user(user_id: str, session_id: str, system: str,
                        model: str = "gpt-5",
                        provider: str = "openai"):
    """Wrap _llm with the user's onboarding context block. Use this for every
    user-facing AI generation so output is niche-aware. `provider` + `model`
    can be overridden by the per-task router (see `model_router.py`)."""
    ctx = await _user_context_block(user_id)
    return _llm(session_id, system + ctx, model=model, provider=provider)


def _llm(session_id: str, system: str,
         model: str = "gpt-5",
         provider: str = "openai"):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model(provider, model)
    return chat


async def send_with_usage(chat, user_message, *,
                          agent_id: Optional[str] = None,
                          user_id: Optional[str] = None,
                          model: str = "gpt-5-mini") -> tuple[str, dict]:
    """Drop-in replacement for `chat.send_message(user_message)` that ALSO
    returns the raw LLM token usage. Returns `(text, {prompt_tokens,
    completion_tokens, total_tokens})`.

    Phase 5 hookup: when `agent_id` AND `user_id` are passed, the function
    also ticks `routes.autonomy.record_usage()` with the token count + an
    estimated USD spend. This is what makes the Team Performance + Autonomy
    headroom bars reflect real burn. Callers that don't supply these args
    (e.g. anonymous code paths or tests) get the legacy behavior.

    We bypass `LlmChat.send_message` so we can read `response.usage` off
    the underlying `litellm.ModelResponse` (the public `send_message`
    discards it and only returns the text).

    Mirrors the side-effects of `send_message`: appends both the user
    message and the assistant reply to the chat's history so subsequent
    turns in the same session still work. Any exception is wrapped in a
    `ChatError` exactly like the public method does."""
    from emergentintegrations.llm.chat import ChatError
    messages = await chat.get_messages()
    await chat._add_user_message(messages, user_message)
    try:
        response = await chat._execute_completion(messages)
        text = await chat._extract_response_text(response)
        await chat._add_assistant_message(messages, text)
    except Exception as e:
        raise ChatError(f"Failed to generate chat completion: {str(e)}")
    usage = {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    }
    u = getattr(response, "usage", None)
    if u is not None:
        # Different providers shape this slightly differently; pull the
        # canonical OpenAI-style fields and fall back to 0 otherwise.
        usage["prompt_tokens"]     = int(getattr(u, "prompt_tokens", 0) or 0)
        usage["completion_tokens"] = int(getattr(u, "completion_tokens", 0) or 0)
        usage["total_tokens"]      = int(getattr(u, "total_tokens", 0) or 0)

    # Phase 5: tick the agent budget ledger. Best-effort — never block on it.
    if agent_id and user_id and usage["total_tokens"] > 0:
        try:
            from routes.autonomy import record_usage
            usd = _estimate_usd(model, usage["prompt_tokens"], usage["completion_tokens"])
            await record_usage(
                agent_id, user_id,
                tokens=usage["total_tokens"], usd=usd,
            )
        except Exception:
            logger.debug("send_with_usage ledger tick skipped", exc_info=True)
    return text, usage


# Rough USD cost per 1M tokens for the models we use. Keep this conservative
# (round UP) so the Autonomy page tends to overestimate spend rather than
# under-report. Source: OpenAI pricing page (April 2026 snapshot).
_MODEL_USD_PER_1M = {
    "gpt-5":           {"input": 5.00, "output": 15.00},
    "gpt-5-mini":      {"input": 0.30, "output": 1.20},
    "gpt-5.2":         {"input": 5.00, "output": 15.00},
    "gpt-4o":          {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":     {"input": 0.15, "output": 0.60},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "gemini-2.5-pro":  {"input": 1.25, "output": 5.00},
}


def _estimate_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Token counts → estimated USD. Falls back to the gpt-5-mini price
    when the model isn't in the table (better than recording $0)."""
    pricing = _MODEL_USD_PER_1M.get(model) or _MODEL_USD_PER_1M["gpt-5-mini"]
    cost = (prompt_tokens / 1_000_000) * pricing["input"]
    cost += (completion_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


async def _fetch_url_snippet(url: str) -> str:
    """Fetch a website and return a cleaned text snippet."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http:
            r = await http.get(url, headers={"User-Agent": "Mozilla/5.0 AutomatexBot"})
        html = r.text[:60000]
        # crude text extraction
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        # capture meta info
        title_m = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
        desc_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text, flags=re.IGNORECASE)
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", text, flags=re.IGNORECASE | re.DOTALL)
        h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", text, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(r"<[^>]+>", " ", text)
        body = re.sub(r"\s+", " ", body).strip()[:6000]

        parts = []
        if title_m:
            parts.append(f"Title: {title_m.group(1).strip()}")
        if desc_m:
            parts.append(f"Description: {desc_m.group(1).strip()}")
        if h1s:
            parts.append("H1s: " + " | ".join([re.sub(r"<[^>]+>", "", h)[:120] for h in h1s[:5]]))
        if h2s:
            parts.append("H2s: " + " | ".join([re.sub(r"<[^>]+>", "", h)[:120] for h in h2s[:8]]))
        parts.append("Body excerpt: " + body[:3500])
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"fetch error {url}: {e}")
        return f"Could not fetch content from {url}: {e}"


@api.post("/ai/seo-review")
async def ai_seo_review(payload: AIRequest, request: Request):
    user = await _gated_user(request)
    if not payload.url:
        raise HTTPException(status_code=400, detail="url is required")

    snippet = await _fetch_url_snippet(payload.url)
    system = (
        "You are Sam, an expert SEO/GEO content marketer. "
        "Given website content, produce a concise SEO audit with: "
        "1) Overall score 0-100, 2) Top 3 strengths, 3) Top 5 issues (severity high/med/low), "
        "4) 5 quick-win recommendations, 5) 5 suggested keywords. "
        "Respond ONLY with valid JSON in this exact shape: "
        '{"score": int, "strengths": [str], "issues": [{"title": str, "severity": "high|medium|low", "fix": str}], '
        '"recommendations": [str], "keywords": [str]}'
    )
    chat = await _llm_for_user(user.user_id, f"seo-{user.user_id}", system)
    msg = UserMessage(text=f"URL: {payload.url}\n\nContent:\n{snippet}")
    raw, _usage = await send_with_usage(chat, msg,
                                         agent_id="rae", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)

    # store report
    report = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "seo_review",
        "url": payload.url,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    }
    await db.reports.insert_one(report)
    await record_ai_generation(user.user_id, "seo_review")
    return {"id": report["id"], "url": payload.url, "report": data}


@api.post("/ai/site-scan")
async def ai_site_scan(payload: AIRequest, request: Request):
    user = await _gated_user(request)
    if not payload.url:
        raise HTTPException(status_code=400, detail="url is required")

    snippet = await _fetch_url_snippet(payload.url)
    system = (
        "You are Nova, an AI digital marketing strategist. "
        "Given a snapshot of a website, produce a scan report: "
        "1) Detect new/notable content elements (products, listings, posts, headings), "
        "2) Identify 3 social-media post ideas from what's currently on the page, "
        "3) Suggest 3 improvements. "
        "Respond ONLY with valid JSON: "
        '{"summary": str, "notable_items": [str], "post_ideas": [{"title": str, "caption": str, "platform": str}], '
        '"improvements": [str]}'
    )
    chat = await _llm_for_user(user.user_id, f"scan-{user.user_id}", system)
    msg = UserMessage(text=f"URL: {payload.url}\n\nContent:\n{snippet}")
    raw, _usage = await send_with_usage(chat, msg,
                                         agent_id="rae", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)

    report = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "site_scan",
        "url": payload.url,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    }
    await db.reports.insert_one(report)
    await record_ai_generation(user.user_id, "site_scan")
    return {"id": report["id"], "url": payload.url, "report": data}


@api.post("/ai/insights")
async def ai_insights(payload: AIRequest, request: Request):
    user = await _gated_user(request)
    system = (
        "You are an AI marketing advisor. Given the user's context, produce: "
        "1) 5 actionable marketing insights tailored to them, "
        "2) 3 trends to watch in their niche, "
        "3) A 1-week action plan (5 bullet steps). "
        "Respond ONLY in JSON: "
        '{"insights": [str], "trends": [str], "action_plan": [str]}'
    )
    chat = await _llm_for_user(user.user_id, f"insights-{user.user_id}", system)
    text = payload.context or payload.prompt or "general small business marketing"
    raw, _usage = await send_with_usage(chat, UserMessage(text=text),
                                         agent_id="rae", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await record_ai_generation(user.user_id, "insights")
    # Pre-canned follow-up actions the SPA renders as quick-action chips so the
    # conversation has a clear "what's next?" entry point even before the user
    # types anything. The followup endpoint accepts these prompts verbatim.
    follow_ups = [
        "Turn the 1-week action plan into a content calendar with specific post ideas for each day.",
        "Draft 3 ready-to-publish posts for the highest-impact item in the action plan.",
        "What KPIs should I track to know if this plan is working?",
        "Which trend should I act on first, and why?",
    ]
    return {"insights": data, "follow_ups": follow_ups}


class _FollowupRequest(BaseModel):
    """Follow-up question in an existing insights conversation."""
    message: str
    history: Optional[List[dict]] = None  # SPA-side conversation log, not used
                                          # for memory (the LLM session already
                                          # keeps it) — included for debugging.


@api.post("/ai/insights/followup")
async def ai_insights_followup(payload: _FollowupRequest, request: Request):
    """Continue an insights conversation. Reuses the same session_id as
    /ai/insights so the LLM keeps full context (the user's original brief +
    every previous turn). Returns Markdown-flavoured text (NOT JSON) plus
    fresh follow-up suggestions tailored to what was just answered."""
    user = await _gated_user(request)
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    # Two-stage prompt: first, answer the user's question conversationally.
    # Then in a separate quick call, generate 3 contextual next-step prompts.
    answer_system = (
        "You are an AI marketing advisor continuing a planning conversation with "
        "the user. Stay specific and actionable. Use short headers and bullet "
        "lists where helpful. Reference earlier parts of OUR conversation by their "
        "actual content, not by index numbers. Keep responses under 350 words "
        "unless the user explicitly asks for more depth."
    )
    chat = await _llm_for_user(user.user_id, f"insights-{user.user_id}", answer_system)
    answer, _usage = await send_with_usage(chat, UserMessage(text=payload.message),
                                            agent_id="rae", user_id=user.user_id,
                                            model="gpt-5")

    # Lightweight second call for follow-ups. Use a separate session so this
    # meta-question doesn't pollute the planning conversation memory.
    meta_system = (
        "You suggest the next 3 questions a user would naturally ask after the "
        "AI answer below. Return ONLY a JSON array of 3 strings (each <= 120 "
        "chars). Each suggestion should be phrased as a FIRST-PERSON request "
        "(e.g. 'Draft me a post about X', 'Build me a calendar for Y'). No "
        "duplicates of obvious next questions."
    )
    meta = await _llm_for_user(
        user.user_id,
        f"insights-meta-{user.user_id}-{int(datetime.now(timezone.utc).timestamp())}",
        meta_system,
    )
    raw_meta, _usage_meta = await send_with_usage(meta, UserMessage(
        text=f"USER QUESTION:\n{payload.message}\n\nAI ANSWER:\n{answer[:1500]}",
    ), agent_id="rae", user_id=user.user_id, model="gpt-5")
    follow_ups = _safe_json(raw_meta)
    if not isinstance(follow_ups, list):
        follow_ups = []
    follow_ups = [str(f).strip() for f in follow_ups if f][:3]

    await record_ai_generation(user.user_id, "insights_followup")
    return {"answer": answer, "follow_ups": follow_ups}


@api.post("/ai/generate-post")
async def ai_generate_post(payload: SocialPostRequest, request: Request):
    user = await _gated_user(request)
    system = (
        "You are Kai, an AI social media manager. Write a high-performing social post. "
        "Respond ONLY in JSON: "
        '{"caption": str, "hashtags": [str], "hook": str, "cta": str}'
    )
    chat = await _llm_for_user(user.user_id, f"post-{user.user_id}", system)
    prompt = (
        f"Platform: {payload.platform}\nTone: {payload.tone}\nTopic: {payload.topic}"
    )
    if payload.listing_url:
        prompt += f"\nListing/Source URL: {payload.listing_url}"
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await record_ai_generation(user.user_id, "post")
    return data


@api.post("/ai/generate-newsletter")
async def ai_generate_newsletter(payload: NewsletterRequest, request: Request):
    user = await _gated_user(request)
    system = (
        "You are Angela, an AI email marketer. Write a complete newsletter. "
        "Respond ONLY in JSON with this shape: "
        '{"subject": str, "preheader": str, "intro": str, '
        '"sections": [{"heading": str, "body": str}], "cta": {"text": str, "url_suggestion": str}, "ps": str}'
    )
    chat = await _llm_for_user(user.user_id, f"newsletter-{user.user_id}", system)
    prompt = (
        f"Topic: {payload.topic}\nAudience: {payload.audience}\n"
        f"Tone: {payload.tone}\nSections: {payload.sections}"
    )
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "newsletter",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    await record_ai_generation(user.user_id, "newsletter")
    return data


@api.post("/ai/generate-content")
async def ai_generate_content(payload: BlogRequest, request: Request):
    user = await _gated_user(request)
    length_words = {"short": 400, "medium": 800, "long": 1500}.get(payload.length, 800)
    system = (
        "You are Sam, an AI SEO content writer. Write a complete blog article. "
        "Respond ONLY in JSON with this shape: "
        '{"title": str, "meta_description": str, "slug": str, '
        '"outline": [str], "intro": str, '
        '"sections": [{"heading": str, "body": str}], "conclusion": str, '
        '"tags": [str], "estimated_read_minutes": int}'
    )
    chat = await _llm_for_user(user.user_id, f"content-{user.user_id}", system)
    prompt = (
        f"Topic: {payload.topic}\nKeywords: {', '.join(payload.keywords or [])}\n"
        f"Tone: {payload.tone}\nTarget length: ~{length_words} words"
    )
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "blog",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    await record_ai_generation(user.user_id, "blog")
    return data


@api.post("/ai/generate-update")
async def ai_generate_update(payload: UpdateRequest, request: Request):
    user = await _gated_user(request)
    system = (
        "You are a product marketing writer. Turn raw release notes into a polished "
        "customer-facing update announcement. Respond ONLY in JSON: "
        '{"headline": str, "subheadline": str, "highlights": [{"title": str, "desc": str}], '
        '"social_post": str, "email_subject": str, "email_body": str}'
    )
    chat = await _llm_for_user(user.user_id, f"update-{user.user_id}", system)
    prompt = f"Product: {payload.product}\nTone: {payload.tone}\nWhat's new:\n{payload.changes}"
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "update",
        "title": payload.product,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    await record_ai_generation(user.user_id, "update")
    return data


@api.post("/ai/generate-video-script")
async def ai_generate_video_script(payload: VideoScriptRequest, request: Request):
    user = await _gated_user(request)
    system = (
        "You are a short-form video scriptwriter (TikTok/Reels/Shorts). "
        "Create a scene-by-scene script optimized for high retention. "
        "Respond ONLY in JSON: "
        '{"hook": str, "title": str, "scenes": [{"timestamp": str, "visual": str, "voiceover": str, "on_screen_text": str}], '
        '"caption": str, "hashtags": [str], "music_vibe": str}'
    )
    chat = await _llm_for_user(user.user_id, f"video-{user.user_id}", system)
    prompt = (
        f"Platform: {payload.platform}\nDuration: ~{payload.duration_seconds}s\n"
        f"Tone: {payload.tone}\nTopic: {payload.topic}"
    )
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "video_script",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    await record_ai_generation(user.user_id, "video_script")
    return data


PLATFORM_LIMITS = {
    "instagram": {"chars": 2200, "tag": "Up to 2,200 chars, 30 hashtags"},
    "tiktok": {"chars": 2200, "tag": "Up to 2,200 chars"},
    "x": {"chars": 280, "tag": "Up to 280 chars"},
    "facebook": {"chars": 63206, "tag": "Long-form, but best <500"},
    "linkedin": {"chars": 3000, "tag": "Up to 3,000 chars"},
    "youtube": {"chars": 5000, "tag": "Description up to 5,000 chars"},
    "pinterest": {"chars": 500, "tag": "Up to 500 chars"},
    "threads": {"chars": 500, "tag": "Up to 500 chars"},
    "reddit": {"chars": 40000, "tag": "Long-form supported"},
    "substack": {"chars": 100000, "tag": "Newsletter / long-form"},
    "blogger": {"chars": 100000, "tag": "Long-form"},
}

POSTABLE_PLATFORMS = list(PLATFORM_LIMITS.keys())


@api.get("/channels/limits")
async def channels_limits(request: Request):
    """Returns per-platform publishing limits used by the AI and UI."""
    await get_current_user(request)
    return PLATFORM_LIMITS


@api.post("/ai/multi-post")
async def ai_multi_post(payload: MultiPostRequest, request: Request):
    user = await _gated_user(request)

    # Build a tailored instruction with per-platform constraints
    selected_limits = {p: PLATFORM_LIMITS.get(p, {"chars": 2000, "tag": "No specific limit"}) for p in payload.platforms}
    limits_text = "\n".join([f"- {p}: max {info['chars']} chars ({info['tag']})" for p, info in selected_limits.items()])

    system = (
        "You are a multi-platform social media manager. Given a listing or news item, "
        "generate platform-tailored posts respecting EACH platform's character limit. "
        "Use the right voice for each: X is punchy, LinkedIn is professional, Instagram is visual+emoji-friendly, "
        "TikTok is energetic, Threads is casual, Pinterest is descriptive, YouTube is detail-rich, "
        "Reddit is conversational and authentic (no salesy tone), Substack/Blogger are long-form.\n\n"
        f"PLATFORM CONSTRAINTS:\n{limits_text}\n\n"
        'Respond ONLY in JSON: '
        '{"posts": [{"platform": str, "content": str, "hashtags": [str], "char_count": int}]}'
    )
    chat = await _llm_for_user(user.user_id, f"multipost-{user.user_id}", system)
    prompt = (
        f"Listing/News: {payload.listing}\nTone: {payload.tone}\n"
        f"Generate posts for these platforms: {', '.join(payload.platforms)}"
    )
    raw, _usage = await send_with_usage(chat, UserMessage(text=prompt),
                                         agent_id="nova", user_id=user.user_id,
                                         model="gpt-5")
    data = _safe_json(raw)
    return data


def _safe_json(raw: str):
    """Try to parse JSON, even with stray text."""
    try:
        return json.loads(raw)
    except Exception:
        # extract first {...}
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"raw": raw}
