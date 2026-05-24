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
