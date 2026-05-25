"""Mailgun transactional email integration.

One helper `send_email(to, subject, html, ...)` and a registry of templates
for our lifecycle emails. Failures are logged but never raised — analytics
shouldn't ever break a user-facing request.

Sandbox limitation: until a real domain is verified in Mailgun, sends to
unauthorised recipients return 400. We log the recipient + reason and move on.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from core import (
    db, api, logger,
    MAILGUN_API_KEY, MAILGUN_DOMAIN, MAILGUN_BASE_URL, MAILGUN_FROM,
    PUBLIC_SITE_URL,
)


# -----------------------------------------------------------------------------
# Low-level send
# -----------------------------------------------------------------------------
async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    from_addr: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Send a single email via Mailgun. Returns a status dict — never raises.

    Status shapes:
      {"sent": True, "id": "<mailgun-id>"}                  → delivered to Mailgun
      {"sent": False, "skipped": "not_configured"}          → no API key
      {"sent": False, "error": "<reason>", "status": <int>} → Mailgun rejected
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN or not MAILGUN_FROM:
        logger.warning("Mailgun not configured — skipping email to %s", to)
        await _log_email(to, subject, status="skipped", reason="not_configured", tags=tags)
        return {"sent": False, "skipped": "not_configured"}

    payload: list[tuple[str, str]] = [
        ("from", from_addr or MAILGUN_FROM),
        ("to", to),
        ("subject", subject),
        ("html", html),
    ]
    if text:
        payload.append(("text", text))
    for tag in (tags or []):
        payload.append(("o:tag", tag))

    url = f"{MAILGUN_BASE_URL}/v3/{MAILGUN_DOMAIN}/messages"
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            transport=httpx.AsyncHTTPTransport(),
        ) as cli:
            # urlencode preserves duplicate keys (multiple o:tag entries).
            # We can't pass data=<list of tuples> because httpx 0.28's
            # AsyncClient interprets that as a sync byte-stream and crashes.
            body = urlencode(payload).encode("utf-8")
            r = await cli.post(
                url,
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=httpx.BasicAuth("api", MAILGUN_API_KEY),
            )
        if r.status_code == 200:
            mg_id = (r.json() or {}).get("id")
            logger.info("Mailgun ✉  sent %s to %s (id=%s)", subject, to, mg_id)
            await _log_email(to, subject, status="sent", mailgun_id=mg_id, tags=tags)
            return {"sent": True, "id": mg_id}
        # Sandbox often returns 400 for unauthorised recipients — log + continue.
        body = (r.text or "")[:300]
        logger.warning("Mailgun ✉  rejected %s to %s: %s %s", subject, to, r.status_code, body)
        await _log_email(to, subject, status="rejected", reason=body, mg_status=r.status_code, tags=tags)
        return {"sent": False, "error": body, "status": r.status_code}
    except Exception as e:  # network / DNS / timeout
        logger.exception("Mailgun ✉  network error sending %s to %s", subject, to)
        await _log_email(to, subject, status="error", reason=str(e)[:300], tags=tags)
        return {"sent": False, "error": str(e)}


async def _log_email(to: str, subject: str, **fields):
    """Best-effort audit row. Never throws."""
    try:
        await db.email_log.insert_one({
            "to": to,
            "subject": subject,
            "created_at": datetime.now(timezone.utc),
            **fields,
        })
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Shared email shell
# -----------------------------------------------------------------------------
def _layout(title: str, body_html: str, cta_label: Optional[str] = None,
            cta_url: Optional[str] = None) -> str:
    """Wrap content in a dark-on-light layout matching the CortexViral brand."""
    cta = ""
    if cta_label and cta_url:
        cta = f"""
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="left" style="margin:24px 0">
          <tr><td style="border-radius:999px;background:linear-gradient(135deg,#7c3aed,#6366f1)">
            <a href="{cta_url}" style="display:inline-block;padding:12px 22px;font-family:Inter,Arial,sans-serif;
               font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:999px">{cta_label} →</a>
          </td></tr>
        </table>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#f5f5f7;font-family:Inter,Arial,sans-serif;color:#18181b">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f5f5f7;padding:32px 0">
    <tr><td align="center">
      <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04)">
        <tr><td style="padding:24px 32px;background:linear-gradient(135deg,#0c0a1f,#1a1442);color:#ffffff">
          <div style="font-size:18px;font-weight:600">Cortex<span style="background:linear-gradient(90deg,#a78bfa,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent">Viral</span></div>
        </td></tr>
        <tr><td style="padding:32px">
          <h1 style="margin:0 0 16px 0;font-size:22px;line-height:1.3;color:#18181b">{title}</h1>
          <div style="font-size:15px;line-height:1.6;color:#404045">{body_html}</div>
          {cta}
        </td></tr>
        <tr><td style="padding:20px 32px;background:#fafafa;border-top:1px solid #e4e4e7;font-size:12px;color:#71717a">
          You're receiving this because you have a CortexViral account.<br>
          <a href="{PUBLIC_SITE_URL}" style="color:#71717a">cortexviral.com</a> · <a href="{PUBLIC_SITE_URL}/privacy" style="color:#71717a">Privacy</a> · <a href="{PUBLIC_SITE_URL}/terms" style="color:#71717a">Terms</a>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# -----------------------------------------------------------------------------
# Lifecycle email templates
# -----------------------------------------------------------------------------
async def send_welcome_email(to: str, name: str):
    first = (name or "there").split()[0]
    subj = "Welcome to CortexViral — let's make your first viral hook"
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>Your CortexViral account is live. Here's the fastest way to feel the magic:</p>
    <ol style="padding-left:20px;line-height:1.7">
      <li>Open <strong>Content Studio</strong> and try the <em>Video Script</em> generator on something you've been wanting to post.</li>
      <li>Connect <strong>TikTok or Instagram</strong> on the Integrations page (takes 30 seconds).</li>
      <li>Hit <strong>Compose & Publish</strong>, paste the AI's hook, and ship it.</li>
    </ol>
    <p>You're on the <strong>Free plan</strong> — that's 20 generations a month, no card required. When you outgrow it, the Growth tier unlocks unlimited AI + the Trend Engine + A/B Hook Lab.</p>
    <p style="color:#71717a;font-size:13.5px">If anything's confusing, just hit reply — I read every email.<br>— Michael, founder</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["welcome"],
        html=_layout("Welcome to CortexViral 👋", body,
                     cta_label="Open Content Studio",
                     cta_url=f"{PUBLIC_SITE_URL}/dashboard/studio"),
    )


async def send_gift_plan_email(to: str, name: str, plan: str, reason: Optional[str] = None):
    first = (name or "there").split()[0]
    plan_label = plan.capitalize()
    subj = f"You've been gifted {plan_label} on CortexViral 🎁"
    reason_html = f'<p style="color:#404045;background:#f5f3ff;border-left:3px solid #7c3aed;padding:12px 16px;border-radius:6px;margin:18px 0"><em>"{reason}"</em></p>' if reason else ""
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>The CortexViral team just upgraded your account to <strong>{plan_label}</strong> — no card, no renewal, just on us.</p>
    {reason_html}
    <p>What this unlocks:</p>
    <ul style="padding-left:20px;line-height:1.7">
      <li><strong>Unlimited AI generations</strong> (no more weekly cap)</li>
      <li><strong>Trend Engine</strong> — live viral-velocity hooks across TikTok / Reels / Shorts</li>
      <li><strong>A/B Hook Lab</strong> — 5 scored variations per idea</li>
      <li><strong>Unlimited channel connections</strong></li>
    </ul>
    <p>It's already live on your account — just sign in and start creating.</p>
    <p style="color:#71717a;font-size:13.5px">Enjoy 🚀<br>— The CortexViral team</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["gift_plan", f"plan:{plan}"],
        html=_layout(f"You're on {plan_label}, on us.", body,
                     cta_label="Jump in →",
                     cta_url=f"{PUBLIC_SITE_URL}/dashboard"),
    )


async def send_trial_ending_email(to: str, name: str, plan: str, days_left: int):
    first = (name or "there").split()[0]
    plan_label = plan.capitalize()
    subj = f"Your {plan_label} trial ends in {days_left} days"
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>Quick heads-up — your <strong>{plan_label}</strong> 14-day trial ends in <strong>{days_left} {'day' if days_left == 1 else 'days'}</strong>. After that, your card will be charged for the first month.</p>
    <p>Nothing to do if you're happy. But if you'd like to switch plans, cancel, or update your card, just open the billing portal:</p>
    <p style="color:#71717a;font-size:13.5px">Questions? Just reply.<br>— Michael, founder</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["trial_ending", f"plan:{plan}"],
        html=_layout(f"Your {plan_label} trial ends in {days_left} days", body,
                     cta_label="Manage billing",
                     cta_url=f"{PUBLIC_SITE_URL}/dashboard"),
    )


async def send_past_due_email(to: str, name: str, plan: str):
    first = (name or "there").split()[0]
    plan_label = plan.capitalize()
    subj = "We couldn't charge your card — your CortexViral access is at risk"
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>Your latest <strong>{plan_label}</strong> payment didn't go through — usually because the card on file expired or has a hold on it.</p>
    <p>To keep your premium features, update your card in the billing portal. We'll automatically retry over the next few days, but if it keeps failing we'll downgrade you to Free to avoid stacking charges.</p>
    <p style="color:#71717a;font-size:13.5px">If something's wrong with the charge, reply to this email and I'll fix it personally.<br>— Michael, founder</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["past_due", f"plan:{plan}"],
        html=_layout("Quick payment hiccup", body,
                     cta_label="Update card",
                     cta_url=f"{PUBLIC_SITE_URL}/dashboard"),
    )


# -----------------------------------------------------------------------------
# Background-task wrappers — for fire-and-forget from sync code paths.
# -----------------------------------------------------------------------------
def fire(coro):
    """Schedule an email coroutine without awaiting (fire-and-forget)."""
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(coro)
    except Exception:
        logger.exception("Failed to schedule email coroutine")


# -----------------------------------------------------------------------------
# Admin debug — send a test email to verify Mailgun config.
# -----------------------------------------------------------------------------
from fastapi import Request
from pydantic import BaseModel


class _TestEmail(BaseModel):
    to: str
    kind: str = "welcome"  # welcome | gift | trial | past_due


@api.post("/admin/email/test")
async def admin_email_test(payload: _TestEmail, request: Request):
    """Send a sample of any lifecycle email to verify Mailgun configuration."""
    from deps import require_admin
    admin = await require_admin(request)
    name = admin.name or "tester"
    if payload.kind == "gift":
        return await send_gift_plan_email(payload.to, name, "growth", reason="Test send from admin")
    if payload.kind == "trial":
        return await send_trial_ending_email(payload.to, name, "growth", days_left=2)
    if payload.kind == "past_due":
        return await send_past_due_email(payload.to, name, "growth")
    return await send_welcome_email(payload.to, name)


@api.get("/admin/email/health")
async def admin_email_health(request: Request, hours: int = 24):
    """Email delivery health for the last `hours` (default 24).

    Returns per-status counts + the most recent error reason so a glance at
    /admin/overview tells you if Mailgun has stopped delivering."""
    from deps import require_admin
    await require_admin(request)
    hours = max(1, min(hours, 24 * 30))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    pipe = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]
    by_status = {row["_id"]: row["n"] async for row in db.email_log.aggregate(pipe)}

    # Most recent non-success row (rejected / errored / skipped) for an at-a-glance reason.
    last_problem = await db.email_log.find_one(
        {"status": {"$ne": "sent"}, "created_at": {"$gte": since}},
        {"_id": 0, "status": 1, "reason": 1, "to": 1, "subject": 1, "created_at": 1, "mg_status": 1},
        sort=[("created_at", -1)],
    )
    if last_problem and isinstance(last_problem.get("created_at"), datetime):
        last_problem["created_at"] = last_problem["created_at"].isoformat()

    total = sum(by_status.values())
    sent = by_status.get("sent", 0)
    return {
        "hours": hours,
        "total": total,
        "sent": sent,
        "rejected": by_status.get("rejected", 0),
        "errored": by_status.get("error", 0),
        "skipped": by_status.get("skipped", 0),
        "delivery_rate": round(sent / total, 4) if total else None,
        "last_problem": last_problem,
    }
