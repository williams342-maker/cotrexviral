"""AI / LLM endpoints — content generation, SEO review, optimal times."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from core import db, api, logger, EMERGENT_LLM_KEY
from deps import get_current_user
from models import (
    User, AIRequest, SocialPostRequest, NewsletterRequest, BlogRequest, UpdateRequest, VideoScriptRequest, MultiPostRequest,
)
from emergentintegrations.llm.chat import LlmChat, UserMessage
import httpx
import re
import json


def _llm(session_id: str, system: str, model: str = "gpt-5"):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model("openai", model)
    return chat


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
    user = await get_current_user(request)
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
    chat = _llm(f"seo-{user.user_id}", system)
    msg = UserMessage(text=f"URL: {payload.url}\n\nContent:\n{snippet}")
    raw = await chat.send_message(msg)
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
    return {"id": report["id"], "url": payload.url, "report": data}


@api.post("/ai/site-scan")
async def ai_site_scan(payload: AIRequest, request: Request):
    user = await get_current_user(request)
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
    chat = _llm(f"scan-{user.user_id}", system)
    msg = UserMessage(text=f"URL: {payload.url}\n\nContent:\n{snippet}")
    raw = await chat.send_message(msg)
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
    return {"id": report["id"], "url": payload.url, "report": data}


@api.post("/ai/insights")
async def ai_insights(payload: AIRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are an AI marketing advisor. Given the user's context, produce: "
        "1) 5 actionable marketing insights tailored to them, "
        "2) 3 trends to watch in their niche, "
        "3) A 1-week action plan (5 bullet steps). "
        "Respond ONLY in JSON: "
        '{"insights": [str], "trends": [str], "action_plan": [str]}'
    )
    chat = _llm(f"insights-{user.user_id}", system)
    text = payload.context or payload.prompt or "general small business marketing"
    raw = await chat.send_message(UserMessage(text=text))
    data = _safe_json(raw)
    return {"insights": data}


@api.post("/ai/generate-post")
async def ai_generate_post(payload: SocialPostRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are Kai, an AI social media manager. Write a high-performing social post. "
        "Respond ONLY in JSON: "
        '{"caption": str, "hashtags": [str], "hook": str, "cta": str}'
    )
    chat = _llm(f"post-{user.user_id}", system)
    prompt = (
        f"Platform: {payload.platform}\nTone: {payload.tone}\nTopic: {payload.topic}"
    )
    if payload.listing_url:
        prompt += f"\nListing/Source URL: {payload.listing_url}"
    raw = await chat.send_message(UserMessage(text=prompt))
    data = _safe_json(raw)
    return data


@api.post("/ai/generate-newsletter")
async def ai_generate_newsletter(payload: NewsletterRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are Angela, an AI email marketer. Write a complete newsletter. "
        "Respond ONLY in JSON with this shape: "
        '{"subject": str, "preheader": str, "intro": str, '
        '"sections": [{"heading": str, "body": str}], "cta": {"text": str, "url_suggestion": str}, "ps": str}'
    )
    chat = _llm(f"newsletter-{user.user_id}", system)
    prompt = (
        f"Topic: {payload.topic}\nAudience: {payload.audience}\n"
        f"Tone: {payload.tone}\nSections: {payload.sections}"
    )
    raw = await chat.send_message(UserMessage(text=prompt))
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "newsletter",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    return data


@api.post("/ai/generate-content")
async def ai_generate_content(payload: BlogRequest, request: Request):
    user = await get_current_user(request)
    length_words = {"short": 400, "medium": 800, "long": 1500}.get(payload.length, 800)
    system = (
        "You are Sam, an AI SEO content writer. Write a complete blog article. "
        "Respond ONLY in JSON with this shape: "
        '{"title": str, "meta_description": str, "slug": str, '
        '"outline": [str], "intro": str, '
        '"sections": [{"heading": str, "body": str}], "conclusion": str, '
        '"tags": [str], "estimated_read_minutes": int}'
    )
    chat = _llm(f"content-{user.user_id}", system)
    prompt = (
        f"Topic: {payload.topic}\nKeywords: {', '.join(payload.keywords or [])}\n"
        f"Tone: {payload.tone}\nTarget length: ~{length_words} words"
    )
    raw = await chat.send_message(UserMessage(text=prompt))
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "blog",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    return data


@api.post("/ai/generate-update")
async def ai_generate_update(payload: UpdateRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are a product marketing writer. Turn raw release notes into a polished "
        "customer-facing update announcement. Respond ONLY in JSON: "
        '{"headline": str, "subheadline": str, "highlights": [{"title": str, "desc": str}], '
        '"social_post": str, "email_subject": str, "email_body": str}'
    )
    chat = _llm(f"update-{user.user_id}", system)
    prompt = f"Product: {payload.product}\nTone: {payload.tone}\nWhat's new:\n{payload.changes}"
    raw = await chat.send_message(UserMessage(text=prompt))
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "update",
        "title": payload.product,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
    return data


@api.post("/ai/generate-video-script")
async def ai_generate_video_script(payload: VideoScriptRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are a short-form video scriptwriter (TikTok/Reels/Shorts). "
        "Create a scene-by-scene script optimized for high retention. "
        "Respond ONLY in JSON: "
        '{"hook": str, "title": str, "scenes": [{"timestamp": str, "visual": str, "voiceover": str, "on_screen_text": str}], '
        '"caption": str, "hashtags": [str], "music_vibe": str}'
    )
    chat = _llm(f"video-{user.user_id}", system)
    prompt = (
        f"Platform: {payload.platform}\nDuration: ~{payload.duration_seconds}s\n"
        f"Tone: {payload.tone}\nTopic: {payload.topic}"
    )
    raw = await chat.send_message(UserMessage(text=prompt))
    data = _safe_json(raw)
    await db.reports.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "type": "video_script",
        "title": payload.topic,
        "report": data,
        "created_at": datetime.now(timezone.utc),
    })
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
    user = await get_current_user(request)

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
    chat = _llm(f"multipost-{user.user_id}", system)
    prompt = (
        f"Listing/News: {payload.listing}\nTone: {payload.tone}\n"
        f"Generate posts for these platforms: {', '.join(payload.platforms)}"
    )
    raw = await chat.send_message(UserMessage(text=prompt))
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
