"""User-facing support: FAQ articles, AI chat assistant, ticket inbox."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from core import db, api, EMERGENT_LLM_KEY
from deps import get_current_user
from models import User, Ticket, TicketCreate, TicketMessage, SupportChatRequest
from emergentintegrations.llm.chat import LlmChat, UserMessage


FAQ_ARTICLES = [
    {
        "id": "getting-started",
        "category": "Getting Started",
        "title": "How do I get started with CortexViral?",
        "body": (
            "After signing in, you land on the Command Center — that's your Cortex "
            "chat. Type any growth outcome in plain English (e.g. \"get 50 seller "
            "signups in 14 days\") and Cortex assembles the right team (Scout, "
            "Creator, Operator, Intelligence), plans the mission, and executes at "
            "your chosen autonomy level. From the sidebar you can connect real "
            "social channels (Instagram, Facebook, LinkedIn, TikTok, Pinterest, "
            "YouTube), track missions in Mission Control, and monitor performance "
            "in Analytics."
        ),
    },
    {
        "id": "how-cortex-works",
        "category": "AI Agents",
        "title": "How does Cortex work?",
        "body": (
            "Cortex is the master orchestrator. When you brief it, it runs a "
            "5-stage loop: discovery (asks clarifying questions), analysis "
            "(scans your site + market signals), recommendation (proposes a "
            "concrete plan), execution (delegates to Scout / Creator / Operator "
            "/ Intelligence), and measurement (feeds results back into memory "
            "so the next mission is smarter). All of this is real — you can "
            "watch it happen in the right-rail Active Mission Rail."
        ),
    },
    {
        "id": "autonomy-levels",
        "category": "AI Agents",
        "title": "What do the autonomy levels (L0–L5) mean?",
        "body": (
            "L0 = draft only, Cortex proposes and you do the work manually. "
            "L1 = auto-create drafts you must approve. L2 = auto-publish with "
            "your approval on each post. L3 = auto-optimize (Cortex reallocates "
            "budget and pauses underperformers without asking). L4 = full "
            "campaign automation with weekly review. L5 = full autonomous — "
            "Cortex runs the mission end-to-end within your guardrails. "
            "You can change the level on any running mission from the card."
        ),
    },
    {
        "id": "seo-review",
        "category": "Features",
        "title": "How does SEO Review work?",
        "body": (
            "Paste any URL in /dashboard/seo and Cortex fetches the page, "
            "analyzes content + meta + structure, and returns a scored audit "
            "(0-100) with strengths, prioritized issues, recommendations, and "
            "keyword suggestions. Findings that look actionable can be "
            "converted into a mission with one click."
        ),
    },
    {
        "id": "site-scan",
        "category": "Features",
        "title": "What does Site Scan do?",
        "body": (
            "Site Scan crawls a URL of your choice and uses Cortex's Creator "
            "team to detect notable items (products, listings, news), generate "
            "ready-to-publish social post drafts, and suggest improvements."
        ),
    },
    {
        "id": "content-generation",
        "category": "Content",
        "title": "How do I generate posts, campaigns, and creatives?",
        "body": (
            "Ask Cortex directly in the Command Center — e.g. \"draft this "
            "week's Instagram content\" or \"launch a 14-day paid campaign for "
            "our new product.\" Cortex's Creator team drafts copy, generates "
            "images (Gemini Nano Banana), and hands them to Operator for "
            "scheduling. You can also brief a full campaign at "
            "/dashboard/campaigns."
        ),
    },
    {
        "id": "channels-live",
        "category": "Channels & Publishing",
        "title": "Which social channels can I connect?",
        "body": (
            "Five platforms are live with real OAuth and publishing: Instagram, "
            "Facebook (Meta Business), LinkedIn, TikTok, Pinterest, and "
            "YouTube. Connect them under Settings → Channels. Once connected, "
            "Cortex's Operator team can schedule and publish posts on your "
            "behalf at your autonomy level. X (Twitter) and Reddit are on "
            "the roadmap."
        ),
    },
    {
        "id": "billing",
        "category": "Account",
        "title": "How does billing work?",
        "body": (
            "CortexViral is subscription-based, billed monthly through Stripe. "
            "You can see your current plan, usage, and next invoice under "
            "Settings → Billing. Plans start at $39/mo. You can upgrade, "
            "downgrade, or cancel at any time."
        ),
    },
    {
        "id": "data-privacy",
        "category": "Privacy",
        "title": "Is my data safe?",
        "body": (
            "Your data lives in our database and is not shared. Uploaded "
            "assets are stored in Cloudflare R2 with per-user access "
            "controls — bytes are only served to you after a session-cookie "
            "auth check. OAuth tokens are encrypted at rest. Forms submitted "
            "on the public landing page are stored as leads and visible only "
            "to the account owner."
        ),
    },
]


@api.get("/support/faq")
async def support_faq():
    return FAQ_ARTICLES


SUPPORT_SYSTEM_PROMPT = (
    "You are CortexBot, the friendly support assistant for CortexViral "
    "(cortexviral.com) — an AI marketing OS. Help users with questions about "
    "features, navigation, and troubleshooting. CortexViral is centered on "
    "the Command Center (Cortex chat orchestrator) at /dashboard, backed by "
    "Mission Control (/dashboard/missions), Campaigns (/dashboard/campaigns), "
    "SEO Review (/dashboard/seo), Site Scan, Assets, Analytics, and Memory. "
    "Cortex orchestrates 4 agent teams: Scout (discovery + qualification), "
    "Creator (drafts + images), Operator (scheduling + publishing), "
    "Intelligence (measurement + optimization). Autonomy levels run L0 "
    "(draft only) → L5 (fully autonomous). Real social channels: Instagram, "
    "Facebook, LinkedIn, TikTok, Pinterest, YouTube — all connect via real "
    "OAuth and can publish live at the user's autonomy level. Billing is "
    "live via Stripe, plans start at $39/mo. If the user asks something you "
    "cannot answer, or wants to talk to a human, tell them to click 'Talk "
    "to a human' to open a support ticket. Keep replies concise and "
    "friendly (under 120 words)."
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
