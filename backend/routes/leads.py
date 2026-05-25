"""Public lead-capture forms from the marketing landing pages."""

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

    # Fire the two lifecycle emails in background. Either failure must NOT
    # break the form submission — leads are persisted regardless.
    try:
        from routes.email import send_lead_admin_notification, send_lead_auto_reply, fire
        if LEADS_NOTIFY_EMAILS:
            fire(send_lead_admin_notification(lead_doc, LEADS_NOTIFY_EMAILS))
        else:
            logger.warning(
                "New lead saved but LEADS_NOTIFY_EMAILS is empty — set it in .env "
                "to receive new-lead alerts.",
            )
        fire(send_lead_auto_reply(lead_doc))
    except Exception:
        logger.exception("Failed to schedule lead emails (lead is still saved)")

    return {"ok": True, "id": lead.id}


@api.get("/leads")
async def list_leads(request: Request):
    user = await get_current_user(request)
    cursor = db.leads.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(200)
