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


# DASHBOARD
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
