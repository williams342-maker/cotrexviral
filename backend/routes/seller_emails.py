"""Seller Acquisition OS — lifecycle email senders.

Four typed helpers that compose CortexViral-branded HTML emails and route
them through the unified `send_email()` provider chain
(SendGrid → Mailtrap → Mailgun). Each helper is best-effort: if the lead
has no `email` field, OR the chain has no provider configured, OR the
provider rejects the payload, it logs + returns `{sent: False, …}`. The
caller (Phase 3/4/8 flows) never raises.

Lifecycle stages → helpers:
  Phase 3  · onboarding/start (lead → active)    → send_seller_welcome_email
  Phase 4  · outreach attach_artifact=true       → send_seller_audit_email
  Phase 8  · cron nudge_message step             → send_seller_nudge_email
  Phase 8  · workflow auto-launch (high churn)   → send_seller_churn_recovery_email
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from routes.email import send_email
from routes.seller_offers import _artifact_to_html

logger = logging.getLogger(__name__)


# --- Branding shell -------------------------------------------------
def _shell(headline: str, body_html: str, cta_label: Optional[str] = None,
           cta_url: Optional[str] = None) -> str:
    cta = ""
    if cta_label and cta_url:
        cta = f"""
        <div style="margin:28px 0 8px;">
          <a href="{cta_url}" style="display:inline-block;padding:12px 22px;border-radius:99px;background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;text-decoration:none;font-weight:600;font-size:14px;letter-spacing:.005em;">{cta_label}</a>
        </div>
        """
    return f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0b0b12;font-family:-apple-system,Inter,system-ui,sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:36px 28px;color:#f4f4f5;">
    <div style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#3b82f6);padding:4px 10px;border-radius:99px;font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;">CortexViral</div>
    <h1 style="font-size:24px;line-height:1.25;margin:14px 0 18px;letter-spacing:-.005em;">{headline}</h1>
    <div style="font-size:15px;line-height:1.6;color:#d4d4d8;">{body_html}</div>
    {cta}
    <hr style="border:none;border-top:1px solid #2a2a35;margin:34px 0 12px;">
    <div style="font-size:11.5px;color:#71717a;">
      You're receiving this because we identified your shop as a great fit
      for CortexViral's marketplace network. Reply STOP to opt out.
    </div>
  </div>
</body></html>"""


def _public_url(path: str) -> str:
    from core import PUBLIC_SITE_URL
    base = (PUBLIC_SITE_URL or "").rstrip("/")
    return f"{base}{path}" if base else path


# --- 1. Welcome (lead → active) -------------------------------------
async def send_seller_welcome_email(lead: dict) -> dict:
    """Sent right after `/seller-onboarding/start` flips a lead to `active`.
    Welcomes the seller and points them at their first action."""
    to = (lead.get("email") or "").strip()
    if not to:
        return {"sent": False, "skipped": "no_email", "reason": "lead has no email"}

    name = lead.get("business_name") or "your shop"
    body = f"""
      <p>Welcome aboard, <strong>{name}</strong>.</p>
      <p>You're now an active seller on CortexViral. Here's what happens next:</p>
      <ul style="padding-left:18px;line-height:1.7;">
        <li>Your storefront is live and indexed for discovery.</li>
        <li>Our growth team will surface your first 3 product slots within 24 hours.</li>
        <li>You'll get a weekly performance digest every Monday.</li>
      </ul>
      <p style="color:#a1a1aa;font-size:13.5px;margin-top:18px;">
        Anything we can help with? Just reply to this email — a real human reads every one.
      </p>
    """
    return await send_email(
        to=to,
        subject=f"Welcome to CortexViral, {name}",
        html=_shell(f"You're in, {name} 🎉", body,
                    cta_label="Open your storefront",
                    cta_url=_public_url("/dashboard")),
        tags=["seller-lifecycle", "welcome"],
    )


# --- 2. Audit delivery (Phase 4) ------------------------------------
async def send_seller_audit_email(lead: dict, artifact: dict) -> dict:
    """Delivers the personalized audit artifact to the seller. The audit
    HTML is attached AND linked inline so the seller can read it in their
    browser or grab the .html file."""
    to = (lead.get("email") or "").strip()
    if not to:
        return {"sent": False, "skipped": "no_email"}

    name = lead.get("business_name") or "your shop"
    art_title = artifact.get("title") or "Your audit"
    summary = artifact.get("summary") or ""
    score = artifact.get("score") or 0

    body = f"""
      <p>Hi {name} team,</p>
      <p>I'm Nova from CortexViral. I just finished a personalized audit on your
      shop — <strong>{score}/100</strong> on our fit-score model. Quick summary:</p>
      <blockquote style="margin:14px 0;padding:12px 16px;background:#1a1a24;border-left:3px solid #7c3aed;border-radius:6px;color:#e4e4e7;font-size:14px;line-height:1.55;">
        {summary}
      </blockquote>
      <p>The full audit (with section-by-section recommendations) is attached
      and also viewable in your browser via the button below.</p>
    """

    # Attach the rendered HTML so it travels with the email.
    html_payload = _artifact_to_html(artifact, lead).encode("utf-8")
    attachment = {
        "filename": f"{(art_title[:60] or 'audit').replace(' ', '-')}.html",
        "content":  base64.b64encode(html_payload).decode("ascii"),
        "type":     "text/html",
        "disposition": "attachment",
    }

    return await send_email(
        to=to,
        subject=f"{art_title} — your free audit from CortexViral",
        html=_shell(art_title, body,
                    cta_label="Read the full audit",
                    cta_url=_public_url(f"/api/seller-offers/{artifact['id']}/download.html")),
        tags=["seller-lifecycle", "audit", artifact.get("offer_type", "audit")],
        attachments=[attachment],
    )


# --- 3. Nudge (Phase 8 cron — gentle re-engagement) -----------------
async def send_seller_nudge_email(lead: dict,
                                   churn_score: Optional[float] = None) -> dict:
    """Sent by the retention cron when a workflow's `nudge_message` step
    advances. Light, no-CTA pressure — just acknowledges the gap."""
    to = (lead.get("email") or "").strip()
    if not to:
        return {"sent": False, "skipped": "no_email"}

    name = lead.get("business_name") or "your shop"
    severity = ("noticing a pause" if (churn_score or 0) < 70
                else "missing your activity")

    body = f"""
      <p>Hi {name} team,</p>
      <p>Quick note — we've been {severity} on your CortexViral storefront the
      past few weeks and wanted to check in.</p>
      <p>Is there anything blocking you? A listing edit, a payout question, a
      promotion idea? Hit reply with even a single sentence and I'll personally
      help unstick it.</p>
      <p style="color:#a1a1aa;font-size:13px;margin-top:18px;">— Nova, CortexViral</p>
    """
    return await send_email(
        to=to,
        subject=f"Quick check-in, {name}",
        html=_shell("Anything blocking you?", body,
                    cta_label="Reopen your dashboard",
                    cta_url=_public_url("/dashboard")),
        tags=["seller-lifecycle", "nudge"],
    )


# --- 4. Churn recovery (Phase 8 workflow auto-launch) ---------------
async def send_seller_churn_recovery_email(lead: dict, artifact: dict,
                                            churn_score: Optional[float] = None) -> dict:
    """Sent when the retention intel detects high churn risk and the
    workflow's auto-executed `send_offer` step generates an artifact.
    Combines the audit attachment with a stronger 'we'd like to keep you'
    framing."""
    to = (lead.get("email") or "").strip()
    if not to:
        return {"sent": False, "skipped": "no_email"}

    name = lead.get("business_name") or "your shop"
    score_pct = int(churn_score) if churn_score is not None else None

    body = f"""
      <p>Hi {name} team,</p>
      <p>We noticed your CortexViral activity has slowed{f" ({score_pct}/100 churn signal)" if score_pct else ""},
      and rather than just sending another nudge, we built you something
      concrete: a fresh marketplace growth audit, tailored to what we see in
      your category right now.</p>
      <blockquote style="margin:14px 0;padding:12px 16px;background:#1a1a24;border-left:3px solid #ef4444;border-radius:6px;color:#e4e4e7;font-size:14px;line-height:1.55;">
        {artifact.get("summary") or ""}
      </blockquote>
      <p>It's attached. No catch — just our way of saying we'd rather help you
      win than lose you. Reply if you want to jump on a 15-minute call.</p>
    """
    html_payload = _artifact_to_html(artifact, lead).encode("utf-8")
    attachment = {
        "filename": f"{(artifact.get('title') or 'recovery-audit')[:60].replace(' ', '-')}.html",
        "content":  base64.b64encode(html_payload).decode("ascii"),
        "type":     "text/html",
        "disposition": "attachment",
    }
    return await send_email(
        to=to,
        subject=f"A growth audit for {name} (on us)",
        html=_shell("We'd rather help you win.", body,
                    cta_label="Read the recovery audit",
                    cta_url=_public_url(f"/api/seller-offers/{artifact['id']}/download.html")),
        tags=["seller-lifecycle", "churn-recovery"],
        attachments=[attachment],
    )
