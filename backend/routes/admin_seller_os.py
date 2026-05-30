"""Admin-side inspectors for Seller-OS data and email-log delivery.

Cross-user read-only listings (admin can see EVERY user's leads,
workflows, and email_log rows) plus a SendGrid test-send endpoint that
fires a single welcome email to a chosen address — used to verify the
provider chain after pasting `SENDGRID_API_KEY`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, EmailStr

from core import api, db
from routes.admin import require_admin

logger = logging.getLogger(__name__)


def _ser(doc: dict) -> dict:
    """Drop _id and ISO-format any datetime fields so the FastAPI JSON
    serializer doesn't choke on bson.ObjectId / aware datetimes."""
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ---------------------------------------------------------------------
# Seller-OS — leads inspector
# ---------------------------------------------------------------------
@api.get("/admin/seller-os/leads")
async def admin_list_seller_leads(
    request: Request,
    stage:  Optional[str] = None,
    user_id: Optional[str] = None,
    limit:  int = 100,
):
    """Cross-user list of seller_leads. Filterable by stage + user."""
    await require_admin(request)
    q: dict = {}
    if stage:   q["stage"] = stage
    if user_id: q["user_id"] = user_id
    cursor = db.seller_leads.find(q).sort([("seller_score", -1), ("created_at", -1)]).limit(
        min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    return {"leads": [_ser(r) for r in rows], "count": len(rows)}


@api.get("/admin/seller-os/workflows")
async def admin_list_seller_workflows(
    request: Request,
    status: Optional[str] = None,
    limit:  int = 100,
):
    """Cross-user list of retention workflows."""
    await require_admin(request)
    q: dict = {}
    if status: q["status"] = status
    cursor = db.seller_retention_workflows.find(q).sort("created_at", -1).limit(
        min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    return {"workflows": [_ser(r) for r in rows], "count": len(rows)}


@api.get("/admin/seller-os/funnel")
async def admin_seller_funnel(request: Request):
    """Aggregated funnel across all users — quick health-check view."""
    await require_admin(request)
    pipeline = [{"$group": {"_id": "$stage", "count": {"$sum": 1}}}]
    counts: dict = {}
    async for r in db.seller_leads.aggregate(pipeline):
        counts[r["_id"] or "unknown"] = r["count"]
    return {"funnel": counts, "total": sum(counts.values())}


# ---------------------------------------------------------------------
# Email log inspector
# ---------------------------------------------------------------------
@api.get("/admin/email/logs")
async def admin_list_email_logs(
    request: Request,
    tag:      Optional[str] = None,   # e.g. "seller-lifecycle" or "audit"
    to:       Optional[str] = None,   # email address (exact match)
    provider: Optional[str] = None,   # "sendgrid" | "mailtrap" | "mailgun"
    status:   Optional[str] = None,   # "sent" | "rejected" | "skipped"
    limit:    int = 100,
):
    """Paginated newest-first email_log rows. Used by the new
    /admin/email-log page to drill into what was delivered, by whom,
    via which provider."""
    await require_admin(request)
    q: dict = {}
    if tag:      q["tags"] = tag
    if to:       q["to"] = to
    if provider: q["provider"] = provider
    if status:   q["status"] = status
    cursor = db.email_log.find(q).sort("created_at", -1).limit(
        min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    return {"logs": [_ser(r) for r in rows], "count": len(rows)}


# ---------------------------------------------------------------------
# SendGrid test-send
# ---------------------------------------------------------------------
class TestSendPayload(BaseModel):
    to: EmailStr
    template: Optional[str] = "welcome"   # welcome | audit | nudge | recovery


@api.post("/admin/email/test-send")
async def admin_email_test_send(payload: TestSendPayload, request: Request):
    """Fires a single lifecycle email so the admin can verify the
    provider chain after pasting `SENDGRID_API_KEY`. Returns the
    provider that ultimately delivered (sendgrid / mailtrap / mailgun)
    OR an error if the whole chain rejected."""
    await require_admin(request)
    sample_lead = {
        "id":            "admin-test-lead",
        "user_id":       "admin-test",
        "business_name": "CortexViral Admin Test",
        "email":         str(payload.to),
        "niche":         "marketing-os",
        "source":        "etsy",
        "stage":         "active",
        "seller_score":  72,
        "socials":       {"instagram": "cortexviral"},
        "website":       "https://cortexviral.com",
        "estimated_activity": "high",
        "created_at":    datetime.now(timezone.utc),
        "updated_at":    datetime.now(timezone.utc),
    }
    sample_artifact = {
        "id":         "admin-test-artifact",
        "title":      "Admin Test · Marketplace Growth Audit",
        "summary":    "This is a sanity-check email from your CortexViral admin panel — confirming the SendGrid lifecycle email pipeline is live and reachable.",
        "score":      82,
        "offer_type": "marketplace_growth",
        "sections":   [{
            "heading": "It works.",
            "body":    "If you're reading this in your inbox, SendGrid → Mailtrap → Mailgun chain is wired correctly.",
            "recommendations": [
                "Continue onboarding live sellers.",
                "Watch /admin/email-log for delivery throughput.",
                "Verify your sender domain on app.sendgrid.com if you haven't yet.",
            ],
        }],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    from routes.seller_emails import (
        send_seller_welcome_email,
        send_seller_audit_email,
        send_seller_nudge_email,
        send_seller_churn_recovery_email,
    )
    tpl = (payload.template or "welcome").lower()
    try:
        if tpl == "audit":
            res = await send_seller_audit_email(sample_lead, sample_artifact)
        elif tpl == "nudge":
            res = await send_seller_nudge_email(sample_lead, churn_score=72)
        elif tpl in ("recovery", "churn", "churn-recovery"):
            res = await send_seller_churn_recovery_email(
                sample_lead, sample_artifact, churn_score=72)
        else:
            res = await send_seller_welcome_email(sample_lead)
    except Exception as e:
        logger.exception("admin test-send failed")
        raise HTTPException(500, f"test-send threw: {e}")

    return {
        "template":  tpl,
        "to":        str(payload.to),
        "sent":      bool(res.get("sent")),
        "provider":  res.get("provider"),
        "message_id": res.get("id"),
        "skipped":   res.get("skipped"),
        "error":     res.get("error"),
        "tried_at":  datetime.now(timezone.utc).isoformat(),
    }
