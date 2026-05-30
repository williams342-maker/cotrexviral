"""Cortex plan-card actions: cancel, dismiss, email-to-inbox.

These complement the existing /api/cortex/console/execute path:
  - cancel:  mark a proposed plan as rejected (won't be re-surfaced)
  - email:   send the plan card as an HTML email to the user's inbox
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


class CancelPayload(BaseModel):
    recommendation: dict
    reason: Optional[str] = Field(None, max_length=400)


class EmailPayload(BaseModel):
    recommendation: dict
    to_email: Optional[str] = None   # default = user's account email


@api.post("/cortex/plan/cancel")
async def cortex_plan_cancel(payload: CancelPayload, request: Request):
    """Mark a Cortex-proposed plan as dismissed. Stored in
    `cortex_dismissed_plans` so the recommendation engine can skip
    re-surfacing the same plan type for ~7 days."""
    user = await get_current_user(request)
    rec = payload.recommendation or {}
    if not rec.get("type"):
        raise HTTPException(400, "Invalid recommendation payload")

    doc = {
        "id":         uuid.uuid4().hex,
        "user_id":    user.user_id,
        "rec_id":     rec.get("id"),
        "rec_type":   rec.get("type"),
        "title":      rec.get("title"),
        "reason":     (payload.reason or "").strip()[:400],
        "created_at": datetime.now(timezone.utc),
    }
    await db.cortex_dismissed_plans.insert_one(doc)
    return {
        "action_taken": "cancelled",
        "message": "Plan dismissed. Cortex won't re-suggest this for the next 7 days.",
        "dismissed_id": doc["id"],
    }


@api.post("/cortex/plan/email")
async def cortex_plan_email(payload: EmailPayload, request: Request):
    """Send the plan card as a readable HTML email to the user's inbox.

    Uses the existing `routes.seller_emails` SendGrid helpers (already
    wired in this app) — if SendGrid is unavailable, falls back to
    Mailgun via `routes.email`. Records the send into `email_log`."""
    user = await get_current_user(request)
    rec = payload.recommendation or {}
    if not rec.get("type"):
        raise HTTPException(400, "Invalid recommendation payload")

    user_doc = await db.users.find_one({"user_id": user.user_id}) or {}
    to_email = (payload.to_email or user_doc.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        raise HTTPException(400, "No destination email on file")

    subject = f"Cortex plan: {rec.get('title','Recommended mission')}"
    html = _render_plan_email_html(rec, user_doc.get("name") or "there")

    sent = await _send_via_any(to_email, subject, html, user_id=user.user_id,
                                 template="cortex_plan_card",
                                 rec_id=rec.get("id"))
    return {
        "action_taken": "emailed",
        "to_email":     to_email,
        "provider":     sent.get("provider", "unknown"),
        "message":      f"Plan sent to {to_email}.",
    }


# ---------------------------------------------------------- helpers
def _render_plan_email_html(rec: dict, recipient_name: str) -> str:
    """Render a self-contained HTML email of the plan card."""
    title = rec.get("title", "Recommended mission")
    summary = rec.get("summary", "")
    reasoning = rec.get("reasoning") or []
    if not isinstance(reasoning, list):
        reasoning = [reasoning]
    confidence_pct = round(float(rec.get("confidence") or 0) * 100)
    cost = rec.get("estimated_cost_usd")
    timeline = rec.get("estimated_timeline_days")
    outcome = rec.get("expected_outcome", "—")
    risk = (rec.get("risk_level") or "medium").upper()

    bullets = "".join(f"<li style='margin-bottom:6px'>{r}</li>" for r in reasoning[:5])
    cost_str = f"${int(cost)}" if cost is not None else "—"
    tl_str = f"{int(timeline)} days" if timeline else "—"

    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0c;color:#e4e4e7;padding:24px;max-width:640px;margin:0 auto">
  <div style="border:1px solid rgba(167,139,250,0.25);background:rgba(167,139,250,0.04);border-radius:14px;padding:24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#a78bfa;font-weight:700;margin-bottom:6px">CORTEX · RECOMMENDED MISSION · {risk} RISK</div>
    <h2 style="margin:0 0 8px 0;font-size:20px;color:#fff">{title}</h2>
    <p style="margin:0 0 16px 0;font-size:13px;color:#a1a1aa;line-height:1.5">{summary}</p>

    <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:14px;margin-bottom:14px">
      <div style="font-size:10px;letter-spacing:0.12em;color:#71717a;font-weight:700;margin-bottom:8px">REASONING</div>
      <ul style="margin:0;padding-left:18px;font-size:13px;color:#d4d4d8;line-height:1.6">{bullets}</ul>
    </div>

    <table style="width:100%;border-collapse:collapse"><tr>
      <td style="padding:8px 0;font-size:11px;color:#71717a">CONFIDENCE<br><b style="color:#fff;font-size:14px">{confidence_pct}%</b></td>
      <td style="padding:8px 0;font-size:11px;color:#71717a">EXPECTED<br><b style="color:#10b981;font-size:14px">{outcome}</b></td>
      <td style="padding:8px 0;font-size:11px;color:#71717a">COST<br><b style="color:#f59e0b;font-size:14px">{cost_str}</b></td>
      <td style="padding:8px 0;font-size:11px;color:#71717a">TIMELINE<br><b style="color:#06b6d4;font-size:14px">{tl_str}</b></td>
    </tr></table>

    <p style="margin-top:18px;font-size:11px;color:#71717a">
      Hi {recipient_name} — this plan is currently in your Cortex Command Center.
      Open the dashboard to launch or queue it via your autonomy level.
    </p>
  </div>
  <p style="font-size:11px;color:#52525b;text-align:center;margin-top:16px">
    Sent by Cortex · CortexViral
  </p>
</body></html>"""


async def _send_via_any(to_email: str, subject: str, html: str,
                          *, user_id: str, template: str,
                          rec_id: Optional[str] = None) -> dict:
    """Try SendGrid first, then Mailgun. Log to `email_log`."""
    provider = None
    error = None

    # SendGrid path (preferred — already used across the app)
    try:
        from routes.email import _send_via_sendgrid
        res = await _send_via_sendgrid(
            to=to_email, subject=subject, html=html, text=None,
            from_addr=None, tags=["cortex_plan_card"],
            custom_args={"user_id": user_id, "template": template,
                          "rec_id": rec_id or ""},
        )
        if res.get("sent"):
            provider = "sendgrid"
        elif res.get("error"):
            error = res.get("error")
    except Exception as e:
        logger.exception("cortex_plan_actions: sendgrid send failed")
        error = str(e)

    # Mailgun fallback
    if provider is None:
        try:
            from routes.email import _send_via_mailgun
            res = await _send_via_mailgun(
                to=to_email, subject=subject, html=html, text=None,
                from_addr=None, tags=["cortex_plan_card"],
            )
            if res.get("sent"):
                provider = "mailgun"
            elif res.get("error"):
                error = res.get("error")
        except Exception as e:
            logger.exception("cortex_plan_actions: mailgun send failed")
            error = str(e)

    await db.email_log.insert_one({
        "id":         uuid.uuid4().hex,
        "provider":   provider or "none",
        "template":   template,
        "to_email":   to_email,
        "subject":    subject,
        "status":     "sent" if provider else "failed",
        "error":      error if not provider else None,
        "user_id":    user_id,
        "rec_id":     rec_id,
        "created_at": datetime.now(timezone.utc),
    })
    if provider is None:
        raise HTTPException(502, f"Email send failed: {error or 'no provider available'}")
    return {"provider": provider}
