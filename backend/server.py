"""Automatex backend — auth + AI marketing endpoints"""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Cookie, Header, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import httpx
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import socket

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]

# ---------- App ----------
app = FastAPI(title="Automatex API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("automatex")


# ==================== MODELS ====================
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_admin: bool = False
    status: str = "active"  # active | suspended
    created_at: datetime


class Ticket(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: str
    user_name: str
    subject: str
    status: str = "open"  # open | answered | closed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TicketCreate(BaseModel):
    subject: str
    message: str


class TicketMessage(BaseModel):
    message: str


class SupportChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class AdminUserAction(BaseModel):
    reason: Optional[str] = None


class BroadcastCreate(BaseModel):
    title: str
    body: str
    severity: Optional[Literal["info", "success", "warning", "critical"]] = "info"
    active: bool = True


class BroadcastUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    severity: Optional[Literal["info", "success", "warning", "critical"]] = None
    active: Optional[bool] = None


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    agent_id: str
    name: Optional[str] = None
    email: str
    website: Optional[str] = None
    platforms: List[str] = []
    pain_points: Optional[str] = None
    competitors: Optional[str] = None
    keywords: Optional[str] = None
    email_platform: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeadCreate(BaseModel):
    agent_id: str
    name: Optional[str] = None
    email: EmailStr
    website: Optional[str] = None
    platforms: List[str] = []
    pain_points: Optional[str] = None
    competitors: Optional[str] = None
    keywords: Optional[str] = None
    email_platform: Optional[str] = None


class AIRequest(BaseModel):
    url: Optional[str] = None
    prompt: Optional[str] = None
    context: Optional[str] = None


class SocialPostRequest(BaseModel):
    topic: str
    platform: Optional[str] = "instagram"
    tone: Optional[str] = "friendly"
    listing_url: Optional[str] = None


class NewsletterRequest(BaseModel):
    topic: str
    audience: Optional[str] = "general subscribers"
    tone: Optional[str] = "friendly"
    sections: Optional[int] = 3


class BlogRequest(BaseModel):
    topic: str
    keywords: Optional[List[str]] = []
    tone: Optional[str] = "professional"
    length: Optional[Literal["short", "medium", "long"]] = "medium"


class UpdateRequest(BaseModel):
    product: str
    changes: str  # bullet list / paragraph of what's new
    tone: Optional[str] = "friendly"


class VideoScriptRequest(BaseModel):
    topic: str
    platform: Optional[str] = "tiktok"  # tiktok / reels / shorts
    duration_seconds: Optional[int] = 30
    tone: Optional[str] = "energetic"


class MultiPostRequest(BaseModel):
    listing: str  # description of the item / listing / news
    platforms: List[str]
    tone: Optional[str] = "friendly"


class ChannelConnectRequest(BaseModel):
    platform: str  # instagram, tiktok, x, facebook, linkedin, reddit


class PublishRequest(BaseModel):
    content: str
    platforms: List[str]
    media_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None  # if set, post is scheduled


class ScheduledUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    platforms: Optional[List[str]] = None
    content: Optional[str] = None


class OptimalTimesRequest(BaseModel):
    platforms: List[str]
    niche: Optional[str] = None
    audience: Optional[str] = None
    timezone: Optional[str] = "UTC"


# ==================== AUTH HELPERS ====================
async def get_current_user(request: Request) -> User:
    """Returns the current authenticated user or raises 401."""
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")

    # Backfill defaults
    user_doc.setdefault("is_admin", user_doc.get("email", "").lower() in ADMIN_EMAILS)
    user_doc.setdefault("status", "active")

    if user_doc.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")

    return User(**user_doc)


async def require_admin(request: Request) -> User:
    """Returns the current user if they are an admin, otherwise raises 403."""
    user = await get_current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def log_admin_action(admin: User, action: str, target_user_id: Optional[str] = None, target_email: Optional[str] = None, details: Optional[dict] = None):
    """Append an entry to the admin audit log."""
    await db.audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "admin_id": admin.user_id,
        "admin_email": admin.email,
        "admin_name": admin.name,
        "action": action,
        "target_user_id": target_user_id,
        "target_email": target_email,
        "details": details or {},
        "created_at": datetime.now(timezone.utc),
    })


# ==================== AUTH ROUTES ====================
@api.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange Emergent session_id for our session_token cookie."""
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-ID header")

    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")

    data = r.json()
    email = data["email"]
    name = data["name"]
    picture = data.get("picture")
    session_token = data["session_token"]

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    is_admin_flag = email.lower() in ADMIN_EMAILS
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "is_admin": is_admin_flag or existing.get("is_admin", False)}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "is_admin": is_admin_flag,
                "status": "active",
                "created_at": datetime.now(timezone.utc),
            }
        )

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one(
        {
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    return {"user_id": user_id, "email": email, "name": name, "picture": picture}


@api.get("/auth/me")
async def auth_me(request: Request):
    user = await get_current_user(request)
    return user.model_dump()


@api.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie(key="session_token", path="/")
    return {"ok": True}


# ==================== LEADS (Marketing page forms) ====================
@api.post("/leads")
async def create_lead(payload: LeadCreate, request: Request):
    user_id = None
    try:
        user = await get_current_user(request)
        user_id = user.user_id
    except HTTPException:
        pass

    lead = Lead(user_id=user_id, **payload.model_dump())
    await db.leads.insert_one(lead.model_dump())
    return {"ok": True, "id": lead.id}


@api.get("/leads")
async def list_leads(request: Request):
    user = await get_current_user(request)
    cursor = db.leads.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(200)


# ==================== AI / LLM ====================
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


# ==================== CHANNELS (mocked connections) ====================
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
    doc = {
        "user_id": user.user_id,
        "platform": payload.platform,
        "handle": f"@{user.name.lower().replace(' ', '_')}",
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
    post = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "content": payload.content,
        "platforms": payload.platforms,
        "media_url": payload.media_url,
        "status": "scheduled" if is_scheduled else "published",
        "scheduled_at": payload.scheduled_at if is_scheduled else None,
        "created_at": datetime.now(timezone.utc),
    }
    await db.posts.insert_one(post)
    return {"ok": True, "id": post["id"], "platforms": payload.platforms, "status": post["status"]}


@api.get("/posts/scheduled")
async def list_scheduled(request: Request, start: Optional[str] = None, end: Optional[str] = None):
    user = await get_current_user(request)
    query = {"user_id": user.user_id, "status": "scheduled"}
    if start or end:
        sched = {}
        if start:
            sched["$gte"] = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            sched["$lte"] = datetime.fromisoformat(end.replace("Z", "+00:00"))
        query["scheduled_at"] = sched
    cursor = db.posts.find(query, {"_id": 0}).sort("scheduled_at", 1)
    return await cursor.to_list(500)


@api.delete("/posts/scheduled/{post_id}")
async def cancel_scheduled(post_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.posts.delete_one({"id": post_id, "user_id": user.user_id, "status": "scheduled"})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    return {"ok": True}


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
    Combines a static heuristic baseline with optional AI refinement based on the user's niche/audience.
    """
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    day_index = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    results = {}
    for p in payload.platforms:
        slots = OPTIMAL_BASE.get(p, [{"day": "Tue", "hour": 10}, {"day": "Thu", "hour": 15}])
        upcoming = []
        for slot in slots:
            target_dow = day_index[slot["day"]]
            today_dow = now.weekday()
            delta = (target_dow - today_dow) % 7
            if delta == 0 and now.hour >= slot["hour"]:
                delta = 7
            d = now + timedelta(days=delta)
            d = d.replace(hour=slot["hour"], minute=0, second=0, microsecond=0)
            upcoming.append({
                "platform": p,
                "datetime": d.isoformat(),
                "day": slot["day"],
                "hour": slot["hour"],
                "score": 100 - len(upcoming) * 7,
            })
        upcoming.sort(key=lambda s: s["datetime"])
        results[p] = upcoming[:6]

    # Optional AI rationale (kept short to avoid heavy LLM cost on every call)
    rationale = None
    if payload.niche or payload.audience:
        try:
            system = (
                "You are Kai, social timing strategist. In ONE short paragraph (<60 words) "
                "explain why these timing recommendations fit the user's niche & audience. "
                "Be specific and confident."
            )
            chat = _llm(f"times-{user.user_id}", system)
            ask = f"Niche: {payload.niche}\nAudience: {payload.audience}\nPlatforms: {', '.join(payload.platforms)}"
            rationale = await chat.send_message(UserMessage(text=ask))
        except Exception:
            rationale = None

    return {"slots": results, "rationale": rationale}


# ==================== PERFORMANCE (mocked analytics) ====================
import random as _rand


def _mock_series(days: int, base: int = 50, volatility: int = 30):
    _rand.seed(days)
    return [max(0, base + _rand.randint(-volatility, volatility)) for _ in range(days)]


PERFORMANCE_RANGES = {"24h": 24, "48h": 48, "7d": 7, "30d": 30, "60d": 60, "90d": 90, "year": 365, "lastyear": 365}


@api.get("/performance/overview")
async def performance_overview(request: Request, range: str = "24h"):
    await get_current_user(request)
    points = PERFORMANCE_RANGES.get(range, 24)
    sessions = _mock_series(points, 80, 50)
    revenue = _mock_series(points + 1, 25, 30)
    total_sessions = sum(sessions)
    total_revenue = sum(revenue)
    prev_sessions = max(1, int(total_sessions * _rand.uniform(0.85, 1.35)))
    prev_revenue = max(1, int(total_revenue * _rand.uniform(0.85, 1.30)))

    def pct(now, prev):
        return round((now - prev) / prev * 100, 1) if prev else 0

    is_hourly = range in ("24h", "48h")
    labels = []
    now = datetime.now(timezone.utc)
    import builtins as _b
    for i in _b.range(points):
        labels.append(
            (now - timedelta(hours=points - 1 - i)).strftime("%I%p").lstrip("0").lower()
            if is_hourly
            else (now - timedelta(days=points - 1 - i)).strftime("%b %d")
        )

    return {
        "range": range,
        "metrics": [
            {"key": "sessions", "label": "Sessions", "value": total_sessions, "change_pct": pct(total_sessions, prev_sessions), "color": "sky"},
            {"key": "revenue", "label": "Stripe Revenue", "value": f"${total_revenue:,}", "change_pct": pct(total_revenue, prev_revenue), "color": "violet"},
        ],
        "series": [
            {"key": "sessions", "label": "Sessions", "color": "#1B7BFF", "data": sessions},
            {"key": "revenue", "label": "Stripe Revenue", "color": "#7C3AED", "data": revenue[:points]},
        ],
        "labels": labels,
    }


@api.get("/performance/sources")
async def performance_sources(request: Request, period: str = Query("24h", alias="range")):
    await get_current_user(request)
    _rand.seed(hash(period))
    sources = [
        ("fb / paid", "facebook"),
        ("(direct) / (none)", "direct"),
        ("(not set) / (not set)", None),
        ("google / organic", "google"),
        ("instagram / referral", "instagram"),
        ("linkedin / referral", "linkedin"),
        ("tiktok / paid", "tiktok"),
    ]
    rows = []
    for name, kind in sources:
        n = _rand.randint(1, 35)
        prev = max(1, n + _rand.randint(-15, 15))
        rows.append({"source": name, "kind": kind, "now": n, "prev": prev, "change_pct": round((n - prev) / prev * 100, 1)})
    rows.sort(key=lambda r: r["now"], reverse=True)
    return rows


@api.get("/performance/pages")
async def performance_pages(request: Request, period: str = Query("24h", alias="range")):
    await get_current_user(request)
    _rand.seed(hash(period) + 1)
    pages = ["/", "/shop", "/dashboard", "/login", "/admin", "/admin/users", "/community", "/listings/new", "/blog", "/pricing", "/contact", "/about"]
    rows = []
    for p in pages:
        n = _rand.randint(0, 55)
        prev = max(0, n + _rand.randint(-20, 20))
        change = round((n - prev) / prev * 100, 1) if prev else (100.0 if n else 0.0)
        rows.append({"page": p, "now": n, "prev": prev, "change_pct": change})
    rows.sort(key=lambda r: r["now"], reverse=True)
    return rows[:10]


# ==================== ACTIVITY FEED ====================
@api.get("/activity")
async def activity_feed(request: Request, limit: int = 30):
    user = await get_current_user(request)
    posts = await db.posts.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    leads = await db.leads.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    reports = await db.reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    items = []
    for p in posts:
        items.append({"type": "post", "id": p["id"], "title": (p.get("content") or "")[:120], "platforms": p.get("platforms", []), "status": p.get("status"), "at": p["created_at"]})
    for l in leads:
        items.append({"type": "lead", "id": l["id"], "title": f"New lead from {l.get('agent_id', 'agent')}", "subtitle": l.get("email"), "at": l["created_at"]})
    for r in reports:
        items.append({"type": "report", "id": r["id"], "title": f"{r.get('type', 'report').replace('_', ' ').title()}: {r.get('title') or r.get('url') or 'untitled'}", "at": r["created_at"]})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


@api.get("/posts")
async def list_posts(request: Request):
    user = await get_current_user(request)
    cursor = db.posts.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(100)


# ==================== DASHBOARD ====================
@api.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    user = await get_current_user(request)
    posts_count = await db.posts.count_documents({"user_id": user.user_id})
    reports_count = await db.reports.count_documents({"user_id": user.user_id})
    channels_count = await db.channels.count_documents({"user_id": user.user_id})
    leads_count = await db.leads.count_documents({"user_id": user.user_id})
    return {
        "posts": posts_count,
        "reports": reports_count,
        "channels": channels_count,
        "leads": leads_count,
    }


@api.get("/reports")
async def list_reports(request: Request):
    user = await get_current_user(request)
    cursor = db.reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(50)


# ==================== SUPPORT (User-facing) ====================
FAQ_ARTICLES = [
    {
        "id": "getting-started",
        "category": "Getting Started",
        "title": "How do I get started with CortexViral?",
        "body": "After signing in with Google, you'll land on the Overview page. From there you can: 1) Connect your social channels (mocked for now), 2) Run an SEO Review on your site, 3) Use Content Studio to generate newsletters, blog posts, or video scripts, and 4) Use Compose & Publish to push posts to your channels.",
    },
    {
        "id": "ai-agents",
        "category": "AI Agents",
        "title": "Who are Nova, Sam, Kai, and Angela?",
        "body": "They are our 4 specialist AI marketing agents. Nova is your digital marketer, Sam handles SEO/GEO content, Kai manages social listening, and Angela writes email campaigns. Each agent powers a different part of the dashboard.",
    },
    {
        "id": "seo-review",
        "category": "Features",
        "title": "How does SEO Review work?",
        "body": "Paste any URL in /dashboard/seo and Sam fetches the page, analyzes content + meta + structure, and returns a scored audit (0-100) with strengths, prioritized issues, recommendations, and keyword suggestions.",
    },
    {
        "id": "site-scan",
        "category": "Features",
        "title": "What does Site Scan do?",
        "body": "Site Scan crawls a URL of your choice and uses Nova to detect notable items (products, listings, news), generate 3 ready-to-publish social post drafts, and suggest improvements.",
    },
    {
        "id": "content-studio",
        "category": "Content",
        "title": "How do I generate newsletters, blogs, or video scripts?",
        "body": "Go to /dashboard/studio. Pick a tab (Newsletter, Blog Article, Product Update, Video Script, or Multi-Platform Posts), fill the form, and click Generate. Results are saved to your Reports.",
    },
    {
        "id": "channels-mocked",
        "category": "Channels & Publishing",
        "title": "Why are channel connections labelled MOCKED?",
        "body": "Real platform OAuth (Instagram, TikTok, X, etc.) requires developer credentials per platform and platform-specific app review. The toggles work in the demo but no posts are pushed to live platforms yet.",
    },
    {
        "id": "billing",
        "category": "Account",
        "title": "How does billing work?",
        "body": "CortexViral is currently in demo mode — no billing is active. Plans start from $39/mo once we launch.",
    },
    {
        "id": "data-privacy",
        "category": "Privacy",
        "title": "Is my data safe?",
        "body": "Your data is stored in our database and is not shared. Forms submitted on the public landing page are stored as leads and visible only to the account owner.",
    },
]


@api.get("/support/faq")
async def support_faq():
    return FAQ_ARTICLES


SUPPORT_SYSTEM_PROMPT = (
    "You are CortexBot, the friendly support assistant for CortexViral (cortexviral.com) — an AI marketing platform. "
    "Help users with questions about features, navigation, and troubleshooting. "
    "CortexViral includes: a Dashboard (Overview), AI Insights, Content Studio (Newsletter/Blog/Update/Video Script/Multi-Platform Posts), "
    "SEO Review, Site Scan, Channels (Instagram/TikTok/X/Facebook/LinkedIn/Reddit — currently MOCKED, no real OAuth yet), "
    "Compose & Publish, Posts feed, and Leads inbox. The AI agents are Nova (digital marketing), "
    "Sam (SEO/GEO content), Kai (social listening), and Angela (email marketing). "
    "Pricing starts from $39/mo when launched (currently demo). "
    "If the user asks something you cannot answer, or wants to talk to a human, tell them to "
    "click 'Talk to a human' to open a support ticket. Keep replies concise and friendly (under 120 words)."
)


@api.post("/support/chat")
async def support_chat(payload: SupportChatRequest, request: Request):
    user = await get_current_user(request)
    sid = payload.session_id or f"support-{user.user_id}"
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=sid, system_message=SUPPORT_SYSTEM_PROMPT).with_model("openai", "gpt-5")
    raw = await chat.send_message(UserMessage(text=payload.message))

    # store conversation log
    await db.support_chat_log.insert_one({
        "user_id": user.user_id,
        "session_id": sid,
        "user_message": payload.message,
        "assistant_message": raw,
        "created_at": datetime.now(timezone.utc),
    })
    return {"reply": raw, "session_id": sid}


@api.post("/support/tickets")
async def create_ticket(payload: TicketCreate, request: Request):
    user = await get_current_user(request)
    ticket = Ticket(
        user_id=user.user_id,
        user_email=user.email,
        user_name=user.name,
        subject=payload.subject,
    )
    await db.tickets.insert_one(ticket.model_dump())
    # first message
    await db.ticket_messages.insert_one({
        "id": str(uuid.uuid4()),
        "ticket_id": ticket.id,
        "author_id": user.user_id,
        "author_role": "user",
        "author_name": user.name,
        "message": payload.message,
        "created_at": datetime.now(timezone.utc),
    })
    return {"id": ticket.id, "status": ticket.status}


@api.get("/support/tickets")
async def list_my_tickets(request: Request):
    user = await get_current_user(request)
    cursor = db.tickets.find({"user_id": user.user_id}, {"_id": 0}).sort("updated_at", -1)
    return await cursor.to_list(100)


@api.get("/support/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, request: Request):
    user = await get_current_user(request)
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["user_id"] != user.user_id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not your ticket")
    messages = await db.ticket_messages.find({"ticket_id": ticket_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return {"ticket": ticket, "messages": messages}


@api.post("/support/tickets/{ticket_id}/message")
async def add_ticket_message(ticket_id: str, payload: TicketMessage, request: Request):
    user = await get_current_user(request)
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["user_id"] != user.user_id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Not your ticket")

    role = "admin" if user.is_admin and ticket["user_id"] != user.user_id else "user"
    msg = {
        "id": str(uuid.uuid4()),
        "ticket_id": ticket_id,
        "author_id": user.user_id,
        "author_role": role,
        "author_name": user.name,
        "message": payload.message,
        "created_at": datetime.now(timezone.utc),
    }
    await db.ticket_messages.insert_one(msg)
    new_status = "answered" if role == "admin" else "open"
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {"updated_at": datetime.now(timezone.utc), "status": new_status}},
    )
    return {"ok": True}


@api.post("/support/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, request: Request):
    user = await get_current_user(request)
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket["user_id"] != user.user_id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.tickets.update_one({"id": ticket_id}, {"$set": {"status": "closed", "updated_at": datetime.now(timezone.utc)}})
    return {"ok": True}


# ==================== ADMIN ====================
@api.get("/admin/me")
async def admin_me(request: Request):
    user = await require_admin(request)
    return user.model_dump()


@api.get("/admin/stats")
async def admin_stats(request: Request):
    await require_admin(request)
    return {
        "total_users": await db.users.count_documents({}),
        "active_users": await db.users.count_documents({"status": {"$ne": "suspended"}}),
        "suspended_users": await db.users.count_documents({"status": "suspended"}),
        "admins": await db.users.count_documents({"is_admin": True}),
        "total_leads": await db.leads.count_documents({}),
        "total_posts": await db.posts.count_documents({}),
        "total_reports": await db.reports.count_documents({}),
        "total_channels": await db.channels.count_documents({}),
        "open_tickets": await db.tickets.count_documents({"status": "open"}),
        "answered_tickets": await db.tickets.count_documents({"status": "answered"}),
        "closed_tickets": await db.tickets.count_documents({"status": "closed"}),
    }


@api.get("/admin/users")
async def admin_list_users(request: Request, q: Optional[str] = None):
    await require_admin(request)
    query = {}
    if q:
        query = {"$or": [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]}
    users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # attach stats
    result = []
    for u in users:
        u.setdefault("is_admin", u.get("email", "").lower() in ADMIN_EMAILS)
        u.setdefault("status", "active")
        uid = u["user_id"]
        u["stats"] = {
            "posts": await db.posts.count_documents({"user_id": uid}),
            "leads": await db.leads.count_documents({"user_id": uid}),
            "reports": await db.reports.count_documents({"user_id": uid}),
            "channels": await db.channels.count_documents({"user_id": uid}),
        }
        result.append(u)
    return result


@api.get("/admin/users/{user_id}")
async def admin_user_detail(user_id: str, request: Request):
    await require_admin(request)
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.setdefault("is_admin", u.get("email", "").lower() in ADMIN_EMAILS)
    u.setdefault("status", "active")
    return {
        "user": u,
        "stats": {
            "posts": await db.posts.count_documents({"user_id": user_id}),
            "leads": await db.leads.count_documents({"user_id": user_id}),
            "reports": await db.reports.count_documents({"user_id": user_id}),
            "channels": await db.channels.count_documents({"user_id": user_id}),
            "tickets": await db.tickets.count_documents({"user_id": user_id}),
        },
        "recent_posts": await db.posts.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5),
        "recent_leads": await db.leads.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5),
    }


@api.post("/admin/users/{user_id}/suspend")
async def admin_suspend(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"status": "suspended"}})
    await db.user_sessions.delete_many({"user_id": user_id})
    await log_admin_action(admin, "suspend_user", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/unsuspend")
async def admin_unsuspend(user_id: str, request: Request):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"status": "active"}})
    await log_admin_action(admin, "unsuspend_user", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/promote")
async def admin_promote(user_id: str, request: Request):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_admin": True}})
    await log_admin_action(admin, "promote_admin", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/demote")
async def admin_demote(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_admin": False}})
    await log_admin_action(admin, "demote_admin", user_id, target.get("email"))
    return {"ok": True}


@api.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # cascade
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.leads.delete_many({"user_id": user_id})
    await db.posts.delete_many({"user_id": user_id})
    await db.reports.delete_many({"user_id": user_id})
    await db.channels.delete_many({"user_id": user_id})
    await db.tickets.delete_many({"user_id": user_id})
    await db.ticket_messages.delete_many({"author_id": user_id})
    await log_admin_action(admin, "delete_user", user_id, target.get("email"), {"cascaded": True})
    return {"ok": True}


@api.post("/admin/users/{user_id}/impersonate")
async def admin_impersonate(user_id: str, request: Request, response: Response):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    current_token = request.cookies.get("session_token")
    impersonate_token = f"imp_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": impersonate_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
        "impersonated_by": admin.user_id,
        "original_token": current_token,
    })

    response.set_cookie(
        key="session_token",
        value=impersonate_token,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=2 * 60 * 60,
    )
    await log_admin_action(admin, "impersonate_user", user_id, target.get("email"))
    return {
        "ok": True,
        "impersonating": {"user_id": target["user_id"], "name": target["name"], "email": target["email"]},
    }


@api.post("/admin/stop-impersonating")
async def admin_stop_impersonate(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="No active session")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session or not session.get("original_token"):
        raise HTTPException(status_code=400, detail="Not impersonating")

    original = session["original_token"]
    # remove the impersonation session
    await db.user_sessions.delete_one({"session_token": token})
    response.set_cookie(
        key="session_token",
        value=original,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=7 * 24 * 60 * 60,
    )
    return {"ok": True}


@api.get("/admin/tickets")
async def admin_list_tickets(request: Request, status: Optional[str] = None):
    await require_admin(request)
    query = {}
    if status:
        query["status"] = status
    cursor = db.tickets.find(query, {"_id": 0}).sort("updated_at", -1)
    return await cursor.to_list(500)


@api.get("/admin/audit-log")
async def admin_audit_log(request: Request, limit: int = 200):
    await require_admin(request)
    cursor = db.audit_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


# ==================== BROADCASTS ====================
@api.post("/admin/broadcasts")
async def create_broadcast(payload: BroadcastCreate, request: Request):
    admin = await require_admin(request)
    doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title,
        "body": payload.body,
        "severity": payload.severity,
        "active": payload.active,
        "created_by": admin.user_id,
        "created_by_name": admin.name,
        "created_at": datetime.now(timezone.utc),
    }
    await db.broadcasts.insert_one(doc)
    await log_admin_action(admin, "create_broadcast", details={"title": payload.title, "severity": payload.severity})
    doc.pop("_id", None)
    return doc


@api.get("/admin/broadcasts")
async def admin_list_broadcasts(request: Request):
    await require_admin(request)
    cursor = db.broadcasts.find({}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(200)


@api.patch("/admin/broadcasts/{broadcast_id}")
async def admin_update_broadcast(broadcast_id: str, payload: BroadcastUpdate, request: Request):
    admin = await require_admin(request)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    res = await db.broadcasts.update_one({"id": broadcast_id}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    await log_admin_action(admin, "update_broadcast", details={"broadcast_id": broadcast_id, "updates": updates})
    return {"ok": True}


@api.delete("/admin/broadcasts/{broadcast_id}")
async def admin_delete_broadcast(broadcast_id: str, request: Request):
    admin = await require_admin(request)
    res = await db.broadcasts.delete_one({"id": broadcast_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    await log_admin_action(admin, "delete_broadcast", details={"broadcast_id": broadcast_id})
    return {"ok": True}


@api.get("/broadcasts/active")
async def list_active_broadcasts(request: Request):
    """Public to logged-in users — shows currently active broadcasts."""
    await get_current_user(request)
    cursor = db.broadcasts.find({"active": True}, {"_id": 0}).sort("created_at", -1).limit(5)
    return await cursor.to_list(5)


# ==================== HEALTH ====================
@api.get("/")
async def root():
    return {"app": "Automatex", "status": "ok"}


@api.post("/admin/scheduler/run-once")
async def admin_scheduler_run_once(request: Request):
    """Admin debug: manually trigger the publish-due job once (bypasses scheduler lock)."""
    await require_admin(request)
    before = await db.posts.count_documents({"status": "scheduled"})
    result = await _publish_due_posts_now()
    after_scheduled = await db.posts.count_documents({"status": "scheduled"})
    return {
        "ok": True,
        "worker": WORKER_ID,
        "scheduled_before": before,
        "due_at_run": result["due"],
        "published_now": result["published"],
        "scheduled_after": after_scheduled,
        "ids": result["ids"][:20],
    }


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== BACKGROUND SCHEDULER ====================
# Flips posts with status='scheduled' and scheduled_at <= now → 'published'.
# Uses a Mongo-backed lock so multiple uvicorn workers don't double-publish.
SCHEDULER_LOCK_NAME = "publish_scheduled_posts"
SCHEDULER_LOCK_TTL_SECONDS = 55  # job runs every 60s
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
scheduler: Optional[AsyncIOScheduler] = None


async def _acquire_scheduler_lock() -> bool:
    """Try to acquire a TTL-style mongo lock. Returns True if this worker holds it."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=SCHEDULER_LOCK_TTL_SECONDS)
    # Either no existing doc, or it has expired → take ownership.
    res = await db.scheduler_locks.find_one_and_update(
        {
            "_id": SCHEDULER_LOCK_NAME,
            "$or": [{"expires_at": {"$lte": now}}, {"expires_at": {"$exists": False}}],
        },
        {"$set": {"worker": WORKER_ID, "expires_at": expires_at, "updated_at": now}},
        upsert=False,
    )
    if res:
        return True
    # Doc doesn't exist yet — try upsert.
    try:
        await db.scheduler_locks.insert_one(
            {"_id": SCHEDULER_LOCK_NAME, "worker": WORKER_ID, "expires_at": expires_at, "updated_at": now}
        )
        return True
    except Exception:
        return False


async def _publish_due_posts_now() -> dict:
    """Promote due scheduled posts to 'published'. Returns counts."""
    now = datetime.now(timezone.utc)
    due_cursor = db.posts.find({"status": "scheduled", "scheduled_at": {"$lte": now}})
    due = await due_cursor.to_list(length=200)
    if not due:
        return {"due": 0, "published": 0, "ids": []}
    ids = [p["id"] for p in due]
    result = await db.posts.update_many(
        {"id": {"$in": ids}, "status": "scheduled"},
        {"$set": {"status": "published", "published_at": now, "publish_mode": "scheduler"}},
    )
    # TODO once OAuth lands: dispatch to live platform APIs for each post in `due`.
    return {"due": len(due), "published": result.modified_count, "ids": ids}


async def publish_due_scheduled_posts():
    """Background job: acquire lock and publish due scheduled posts."""
    try:
        if not await _acquire_scheduler_lock():
            return  # another worker is handling this tick
        result = await _publish_due_posts_now()
        if result["published"]:
            logger.info(
                "scheduler: published %s due posts (worker=%s, ids=%s)",
                result["published"], WORKER_ID, result["ids"][:10],
            )
    except Exception:
        logger.exception("scheduler: publish_due_scheduled_posts failed")


@app.on_event("startup")
async def start_scheduler():
    global scheduler
    if os.environ.get("DISABLE_SCHEDULER", "").lower() in ("1", "true", "yes"):
        logger.info("scheduler: disabled via DISABLE_SCHEDULER env")
        return
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        publish_due_scheduled_posts,
        trigger=IntervalTrigger(seconds=60),
        id="publish_scheduled_posts",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    scheduler.start()
    logger.info("scheduler: started (worker=%s, every 60s)", WORKER_ID)


@app.on_event("shutdown")
async def shutdown():
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    client.close()
