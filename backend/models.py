"""Pydantic models shared across routes."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, Field


# ---------- User & auth ----------
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_admin: bool = False
    status: str = "active"  # active | suspended
    created_at: datetime


# ---------- Support / tickets ----------
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


# ---------- Admin ----------
class AdminUserAction(BaseModel):
    reason: Optional[str] = None


class AdminSetPlanRequest(BaseModel):
    plan: Literal["free", "starter", "growth", "agency", "pro", "scale"]
    comped: bool = True   # default: admin overrides are immune to Stripe downgrades
    reason: Optional[str] = None


# ---------- Onboarding ----------
ONBOARDING_NICHES = [
    "Fitness", "SaaS", "eCommerce", "Creator/Influencer",
    "Agency", "Coaching/Course", "Local business", "Other",
]
ONBOARDING_GOALS = [
    "Grow followers", "Drive traffic", "Generate leads",
    "Sell products", "Build authority",
]
ONBOARDING_PLATFORMS = ["TikTok", "Instagram", "YouTube", "LinkedIn", "X"]


class OnboardingPayload(BaseModel):
    website: str = Field(..., min_length=3, max_length=300)
    brand_name: str = Field(..., min_length=1, max_length=120)
    niche: Literal[
        "Fitness", "SaaS", "eCommerce", "Creator/Influencer",
        "Agency", "Coaching/Course", "Local business", "Other",
    ]
    goals: List[str] = Field(default_factory=list)
    platforms: List[str] = Field(default_factory=list)
    challenge: Optional[str] = Field(None, max_length=1000)


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


# ---------- Leads ----------
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


# ---------- AI ----------
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
    changes: str
    tone: Optional[str] = "friendly"


class VideoScriptRequest(BaseModel):
    topic: str
    platform: Optional[str] = "tiktok"
    duration_seconds: Optional[int] = 30
    tone: Optional[str] = "energetic"


class MultiPostRequest(BaseModel):
    listing: str
    platforms: List[str]
    tone: Optional[str] = "friendly"


# ---------- Channels & posts ----------
class ChannelConnectRequest(BaseModel):
    platform: str


class PublishRequest(BaseModel):
    content: str
    platforms: List[str]
    media_url: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class ScheduledUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    platforms: Optional[List[str]] = None
    content: Optional[str] = None


class OptimalTimesRequest(BaseModel):
    platforms: List[str]
    niche: Optional[str] = None
    audience: Optional[str] = None
    timezone: Optional[str] = "UTC"
