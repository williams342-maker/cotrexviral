"""Public lead-capture forms from the marketing landing pages."""
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from core import db, api, logger, LEADS_NOTIFY_EMAILS
from deps import get_current_user
from models import Lead, LeadCreate


@api.post("/leads")
async def create_lead(payload: LeadCreate, request: Request):
    user_id = None
    try:
        user = await get_current_user(request)
        user_id = user.user_id
    except HTTPException:
        pass

    lead = Lead(user_id=user_id, **payload.model_dump())
    lead_doc = lead.model_dump()
    await db.leads.insert_one(lead_doc)

    # Auto-create a user account for this lead (if email provided and not
    # already a registered user) — so they can sign in with email + temp
    # password OR via the magic link in their auto-reply email.
    magic_link_url = None
    temp_password = None
    if lead.email and not user_id:
        try:
            existing = await db.users.find_one({"email": lead.email.lower()}, {"_id": 0})
            if existing:
                new_user_id = existing["user_id"]
            else:
                import uuid as _uuid
                new_user_id = f"user_{_uuid.uuid4().hex[:12]}"
                await db.users.insert_one({
                    "user_id": new_user_id,
                    "email": lead.email.lower().strip(),
                    "name": lead.name or lead.email.split("@")[0],
                    "is_admin": False,
                    "status": "active",
                    "plan": "free",
                    "comped": False,
                    "website": lead.website,
                    "created_at": datetime.now(timezone.utc),
                    "created_via": "lead_form",
                    "lead_agent": lead.agent_id,
                })
            # Generate a temp password — emailed separately (see send_temp_password_email
            # below). The user can sign in with email + temp pw and will be
            # forced to set their own password on first login.
            from routes.password_auth import generate_temp_password, _set_user_password
            temp_password = generate_temp_password()
            await _set_user_password(new_user_id, temp_password,
                                     require_change_on_next_login=True)
            # Also issue a magic link as a backup (one-click option in the email).
            from routes.magic_link import issue_magic_link
            magic_link_url = await issue_magic_link(new_user_id, lead.email, purpose="lead_claim")
        except Exception:
            logger.exception("Lead auto-create failed (lead still saved)")

    # Fire the two lifecycle emails in background. Either failure must NOT
    # break the form submission — leads are persisted regardless.
    try:
        from routes.email import (
            send_lead_admin_notification, send_lead_auto_reply,
            send_temp_password_email, fire,
        )
        if LEADS_NOTIFY_EMAILS:
            fire(send_lead_admin_notification(lead_doc, LEADS_NOTIFY_EMAILS))
        else:
            logger.warning(
                "New lead saved but LEADS_NOTIFY_EMAILS is empty — set it in .env "
                "to receive new-lead alerts.",
            )
        fire(send_lead_auto_reply(lead_doc, magic_link=magic_link_url))
        # Temp password sent as a SEPARATE email so the welcome message stays
        # personable and the credentials email is a clear "save this" signal.
        if temp_password and lead.email:
            fire(send_temp_password_email(
                to=lead.email,
                name=lead.name or lead.email.split("@")[0],
                temp_password=temp_password,
                reason="lead_form",
            ))
    except Exception:
        logger.exception("Failed to schedule lead emails (lead is still saved)")

    return {"ok": True, "id": lead.id}


@api.get("/leads")
async def list_leads(request: Request):
    user = await get_current_user(request)
    cursor = db.leads.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(200)
