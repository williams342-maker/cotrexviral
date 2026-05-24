"""Auto-extracted from server.py — refactored to /app/backend/routes/."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import HTTPException, Request, Response, Query, Cookie, Header
from fastapi.responses import JSONResponse

from core import db, api, app, logger, EMERGENT_LLM_KEY, ADMIN_EMAILS
from deps import get_current_user, require_admin, log_admin_action
from models import (
    User, Ticket, TicketCreate, TicketMessage, SupportChatRequest,
    AdminUserAction, BroadcastCreate, BroadcastUpdate,
    Lead, LeadCreate, AIRequest, SocialPostRequest, NewsletterRequest,
    BlogRequest, UpdateRequest, VideoScriptRequest, MultiPostRequest,
    ChannelConnectRequest, PublishRequest, ScheduledUpdate, OptimalTimesRequest,
)


# LEADS (Marketing page forms)
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
