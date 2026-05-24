"""Automatex backend — auth + AI marketing endpoints"""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Cookie, Header
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

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
    created_at: datetime


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
    return User(**user_doc)


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
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
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


@api.post("/ai/multi-post")
async def ai_multi_post(payload: MultiPostRequest, request: Request):
    user = await get_current_user(request)
    system = (
        "You are a multi-platform social media manager. Given a listing or news item, "
        "generate platform-tailored posts. Each platform has different character limits and styles. "
        "Respond ONLY in JSON: "
        '{"posts": [{"platform": str, "content": str, "hashtags": [str]}]}'
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
SUPPORTED_PLATFORMS = ["instagram", "tiktok", "x", "facebook", "linkedin", "reddit"]


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
    post = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "content": payload.content,
        "platforms": payload.platforms,
        "media_url": payload.media_url,
        "status": "published",
        "created_at": datetime.now(timezone.utc),
    }
    await db.posts.insert_one(post)
    return {"ok": True, "id": post["id"], "platforms": payload.platforms, "status": "published"}


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


# ==================== HEALTH ====================
@api.get("/")
async def root():
    return {"app": "Automatex", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
