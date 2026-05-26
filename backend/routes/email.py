"""Transactional email integration with provider fallback.

Primary: **Mailtrap** (Email Sending API).
Fallback: **Mailgun** (used only if Mailtrap is unconfigured OR returns a 5xx /
network error — Mailgun is currently sandbox-disabled, so a 403 there should
NOT trigger another fallback; we let the first provider's error bubble up).

One helper `send_email(to, subject, html, ...)`. Failures are logged but never
raised — analytics shouldn't ever break a user-facing request.
"""
from __future__ import annotations

import asyncio
import json as _json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from core import (
    db, api, logger,
    MAILGUN_API_KEY, MAILGUN_DOMAIN, MAILGUN_BASE_URL, MAILGUN_FROM,
    MAILTRAP_TOKEN, MAILTRAP_FROM, MAILTRAP_API_URL,
    PUBLIC_SITE_URL,
)


def _parse_from(addr: str) -> dict:
    """Split 'Name <email@host>' into {'name': ..., 'email': ...} for Mailtrap.
    Falls back to {'email': addr} if no display name is present."""
    if not addr:
        return {"email": ""}
    m = re.match(r"^\s*(.+?)\s*<\s*([^>]+)\s*>\s*$", addr)
    if m:
        return {"name": m.group(1).strip(), "email": m.group(2).strip()}
    return {"email": addr.strip()}


# -----------------------------------------------------------------------------
# Provider: Mailtrap (Email Sending API)
# -----------------------------------------------------------------------------
async def _send_via_mailtrap(
    to: str, subject: str, html: str, text: Optional[str],
    from_addr: Optional[str], tags: Optional[list[str]],
) -> dict:
    if not MAILTRAP_TOKEN or not MAILTRAP_FROM:
        return {"sent": False, "skipped": "not_configured", "provider": "mailtrap"}

    payload = {
        "from": _parse_from(from_addr or MAILTRAP_FROM),
        "to": [{"email": to}],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    if tags:
        # Mailtrap supports a single 'category' string (not multiple tags),
        # so we pick the first/primary tag as category.
        payload["category"] = tags[0][:255]

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            transport=httpx.AsyncHTTPTransport(),
        ) as cli:
            r = await cli.post(
                MAILTRAP_API_URL,
                content=_json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {MAILTRAP_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        if 200 <= r.status_code < 300:
            data = r.json() if r.text else {}
            mid = ((data.get("message_ids") or [None])[0]
                   if isinstance(data.get("message_ids"), list)
                   else data.get("message_id"))
            logger.info("Mailtrap ✉  sent %s to %s (id=%s)", subject, to, mid)
            return {"sent": True, "id": mid, "provider": "mailtrap"}
        body = (r.text or "")[:300]
        logger.warning("Mailtrap ✉  rejected %s to %s: %s %s", subject, to, r.status_code, body)
        return {
            "sent": False, "error": body, "status": r.status_code,
            "provider": "mailtrap",
            # 5xx → worth falling back. 4xx (bad payload / invalid sender) → don't
            # fall back because Mailgun will reject the same payload too.
            "transient": r.status_code >= 500,
        }
    except Exception as e:
        logger.exception("Mailtrap ✉  network error to %s", to)
        return {
            "sent": False, "error": str(e)[:300],
            "provider": "mailtrap", "transient": True,
        }


# -----------------------------------------------------------------------------
# Provider: Mailgun (fallback)
# -----------------------------------------------------------------------------
async def _send_via_mailgun(
    to: str, subject: str, html: str, text: Optional[str],
    from_addr: Optional[str], tags: Optional[list[str]],
) -> dict:
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN or not MAILGUN_FROM:
        return {"sent": False, "skipped": "not_configured", "provider": "mailgun"}

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
            return {"sent": True, "id": mg_id, "provider": "mailgun"}
        body = (r.text or "")[:300]
        logger.warning("Mailgun ✉  rejected %s to %s: %s %s", subject, to, r.status_code, body)
        return {"sent": False, "error": body, "status": r.status_code, "provider": "mailgun"}
    except Exception as e:
        logger.exception("Mailgun ✉  network error to %s", to)
        return {"sent": False, "error": str(e)[:300], "provider": "mailgun"}


# -----------------------------------------------------------------------------
# Public send_email — provider chain with fallback.
# -----------------------------------------------------------------------------
async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    from_addr: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Try Mailtrap first; fall back to Mailgun if Mailtrap is unconfigured
    or returns a transient (5xx / network) failure. Final status is logged to
    `email_log` with the provider field so admins can see which path delivered."""
    # 1. Try Mailtrap (primary)
    result = await _send_via_mailtrap(to, subject, html, text, from_addr, tags)

    # 2. Mailgun fallback for: not-configured, transient network/5xx errors.
    #    Skip fallback for 4xx (Mailgun would reject the same payload).
    should_fallback = (
        result.get("skipped") == "not_configured"
        or result.get("transient") is True
    )
    if not result.get("sent") and should_fallback:
        logger.info("Falling back to Mailgun for %s (mailtrap result: %s)", to,
                    result.get("error") or result.get("skipped"))
        mg_result = await _send_via_mailgun(to, subject, html, text, from_addr, tags)
        # Persist a row capturing both attempts.
        await _log_email(
            to, subject,
            status="sent" if mg_result.get("sent") else (
                "skipped" if mg_result.get("skipped") else "rejected"
            ),
            provider=mg_result.get("provider"),
            mailgun_id=mg_result.get("id"),
            mg_status=mg_result.get("status"),
            reason=mg_result.get("error") or mg_result.get("skipped"),
            fallback_from="mailtrap",
            primary_error=result.get("error") or result.get("skipped"),
            tags=tags,
        )
        # Strip the internal transient flag from the response.
        mg_result.pop("transient", None)
        return mg_result

    # No fallback needed — log the Mailtrap outcome (success OR 4xx rejection).
    await _log_email(
        to, subject,
        status="sent" if result.get("sent") else (
            "skipped" if result.get("skipped") else "rejected"
        ),
        provider=result.get("provider"),
        mailgun_id=result.get("id"),
        mg_status=result.get("status"),
        reason=result.get("error") or result.get("skipped"),
        tags=tags,
    )
    result.pop("transient", None)
    return result


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


async def send_account_invite_email(to: str, name: str, magic_link: str,
                                     inviter_name: str = "the CortexViral team"):
    """Sent when an admin creates an account (or the lead form auto-creates one).
    Contains a single-use magic-link URL so the user can claim their account
    WITHOUT needing Google Auth."""
    first = (name or "there").split()[0]
    subj = "Your CortexViral account is ready — claim it in one click"
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>{inviter_name} just created a CortexViral account for you. No password needed — click the button below and you're in.</p>
    <p style="background:#f5f3ff;border:1px solid #ddd6fe;padding:14px 18px;border-radius:8px;margin:18px 0;color:#404045;font-size:13.5px">
      <strong>Heads up:</strong> This link works once and expires in 7 days. If it stops working, just reply and we'll send a fresh one.
    </p>
    <p style="color:#71717a;font-size:13.5px">If the button doesn't work, copy &amp; paste this URL into your browser:<br>
      <a href="{magic_link}" style="color:#7c3aed;word-break:break-all;font-size:12px">{magic_link}</a>
    </p>
    <p style="color:#71717a;font-size:13.5px">Welcome aboard 🚀<br>— The CortexViral team</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["account_invite"],
        html=_layout("Claim your CortexViral account →", body,
                     cta_label="Sign in & get started",
                     cta_url=magic_link),
    )


async def send_onboarding_admin_notification(
    user_email: str, user_name: str, profile: dict, recipients: list,
):
    """Heads-up email to the support team when a new user finishes onboarding.
    Sent only on FIRST completion (re-edits don't fire)."""
    first = (user_name or "they").split()[0]
    goals = ", ".join(profile.get("goals") or []) or "—"
    platforms = ", ".join(profile.get("platforms") or []) or "—"
    challenge = profile.get("challenge") or ""
    challenge_block = (
        f'<tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px;vertical-align:top">Challenge</td>'
        f'<td style="padding:6px 12px;color:#18181b;font-size:13.5px;font-style:italic">"{challenge.replace("<","&lt;")}"</td></tr>'
        if challenge else ""
    )

    rows = f"""
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Name</td><td style="padding:6px 12px;font-size:13.5px;font-weight:600">{user_name or "(unnamed)"}</td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Email</td><td style="padding:6px 12px;font-size:13.5px"><a href="mailto:{user_email}" style="color:#7c3aed">{user_email}</a></td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Website</td><td style="padding:6px 12px;font-size:13.5px"><a href="{profile.get('website','')}" style="color:#7c3aed">{profile.get('website','')}</a></td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Brand</td><td style="padding:6px 12px;font-size:13.5px;font-weight:500">{profile.get('brand_name','')}</td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Niche</td><td style="padding:6px 12px;font-size:13.5px;font-weight:500">{profile.get('niche','')}</td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Goals</td><td style="padding:6px 12px;font-size:13.5px">{goals}</td></tr>
      <tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px">Platforms</td><td style="padding:6px 12px;font-size:13.5px">{platforms}</td></tr>
      {challenge_block}
    """
    body = f"""
    <p>{first} just completed onboarding on CortexViral. Here's their context — good time to reach out with niche-specific help.</p>
    <table cellspacing="0" cellpadding="0" border="0" style="margin:18px 0;background:#fafafa;border:1px solid #e4e4e7;border-radius:10px;width:100%">
      {rows}
    </table>
    """
    results = []
    for rcpt in recipients:
        results.append(await send_email(
            to=rcpt,
            subject=f"✨ New onboarding: {user_name or user_email} ({profile.get('brand_name','')})",
            tags=["onboarding_complete", f"niche:{profile.get('niche','').lower()}"],
            html=_layout(f"✨ New onboarding: {profile.get('brand_name') or user_name}", body,
                         cta_label="Open admin → users",
                         cta_url=f"{PUBLIC_SITE_URL}/admin/users"),
        ))
    return results




_SEVERITY_STYLES = {
    "info": ("📣", "#6366f1", "#eef2ff"),
    "warning": ("⚠️", "#d97706", "#fffbeb"),
    "critical": ("🚨", "#dc2626", "#fef2f2"),
    "success": ("🎉", "#10b981", "#ecfdf5"),
}


async def send_broadcast_email(to: str, name: str, title: str, body: str,
                                severity: str = "info"):
    """Email version of an admin broadcast. Used by the 'Email blast' button on
    /admin/broadcasts — converts the broadcast title+body into a styled message."""
    icon, accent, bg = _SEVERITY_STYLES.get(severity, _SEVERITY_STYLES["info"])
    first = (name or "there").split()[0]
    subj = title if len(title) < 90 else title[:87] + "…"
    # body may contain newlines from the broadcast composer — render them as <p>.
    paragraphs = "\n".join(
        f"<p>{p.strip()}</p>" for p in (body or "").split("\n") if p.strip()
    ) or "<p></p>"
    html_body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <div style="background:{bg};border-left:3px solid {accent};padding:14px 18px;border-radius:8px;margin:18px 0">
      <div style="font-size:18px;margin-bottom:6px">{icon} <strong>{title}</strong></div>
      <div style="color:#404045;font-size:14.5px;line-height:1.55">{paragraphs}</div>
    </div>
    <p style="color:#71717a;font-size:13.5px">If you have questions, just reply — we read every email.<br>— The CortexViral team</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["broadcast", f"severity:{severity}"],
        html=_layout(title, html_body,
                     cta_label="Open dashboard",
                     cta_url=f"{PUBLIC_SITE_URL}/dashboard"),
    )


# -----------------------------------------------------------------------------
# Lead-capture lifecycle (when a visitor submits the "Choose Your Specialist" form)
# -----------------------------------------------------------------------------
_AGENT_INTROS = {
    "nova":   ("Nova",   "your SEO & content strategist"),
    "sam":    ("Sam",    "your SEO & content marketing specialist"),
    "kai":    ("Kai",    "your social media specialist"),
    "angela": ("Angela", "your email marketing specialist"),
}


def _lead_field_row(label: str, value: Optional[str]) -> str:
    if not value:
        return ""
    safe = str(value).replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<tr><td style="padding:6px 12px;color:#71717a;font-size:12.5px;white-space:nowrap;vertical-align:top">{label}</td>'
        f'<td style="padding:6px 12px;color:#18181b;font-size:13.5px;font-weight:500">{safe}</td></tr>'
    )


async def send_lead_admin_notification(lead: dict, recipients: list[str]):
    """Notify the CortexViral team that a new lead just submitted the form.
    Fans out to every address in recipients (sequentially, all logged)."""
    agent_id = lead.get("agent_id") or ""
    agent_name, agent_role = _AGENT_INTROS.get(agent_id, ("an agent", ""))
    lead_email = lead.get("email") or "(no email)"
    lead_name = lead.get("name") or "(unnamed)"
    platforms = lead.get("platforms") or []
    platforms_str = ", ".join(platforms) if platforms else None

    subj = f"🔥 New lead for {agent_name}: {lead_name} ({lead_email})"
    table_rows = "".join([
        _lead_field_row("Agent", f"{agent_name} — {agent_role}"),
        _lead_field_row("Name", lead.get("name")),
        _lead_field_row("Email", lead.get("email")),
        _lead_field_row("Website", lead.get("website")),
        _lead_field_row("Platforms", platforms_str),
        _lead_field_row("Pain points", lead.get("pain_points")),
        _lead_field_row("Competitors", lead.get("competitors")),
        _lead_field_row("Keywords", lead.get("keywords")),
        _lead_field_row("Email platform", lead.get("email_platform")),
    ])
    body = f"""
    <p>A new lead just submitted the "Choose Your Specialist" form on cortexviral.com.</p>
    <table cellspacing="0" cellpadding="0" border="0" style="margin:18px 0;background:#fafafa;border:1px solid #e4e4e7;border-radius:10px;width:100%">
      {table_rows}
    </table>
    <p style="color:#71717a;font-size:13px">Reply to this email or hit the button to view the full lead in your admin dashboard.</p>
    """
    results = []
    for rcpt in recipients:
        results.append(await send_email(
            to=rcpt, subject=subj, tags=["lead_notification", f"agent:{agent_id}"],
            html=_layout(f"🔥 New lead for {agent_name}", body,
                         cta_label="Open admin → users",
                         cta_url=f"{PUBLIC_SITE_URL}/admin/users"),
        ))
    return results


async def send_lead_auto_reply(lead: dict, magic_link: Optional[str] = None):
    """Friendly auto-reply to the lead, written as if from the chosen agent.
    Sets expectation that a human will follow up within 24h."""
    if not lead.get("email"):
        return {"sent": False, "skipped": "no_email"}
    agent_id = lead.get("agent_id") or ""
    agent_name, agent_role = _AGENT_INTROS.get(agent_id, ("the CortexViral team", ""))
    first = (lead.get("name") or "there").split()[0]
    subj = f"Got your message — {agent_name} here 👋"

    # Per-agent intros mirror the in-product copy so it feels consistent.
    agent_intros = {
        "nova":   "If you need more traffic but struggle to rank or stay consistent, I can build the engine that delivers it.",
        "sam":    "I handle SEO and content marketing end-to-end — keyword research through AI-search-optimised publishing.",
        "kai":    "I'll monitor your platforms, find the patterns your audience actually responds to, and turn them into shippable hooks.",
        "angela": "I'll write, design, and schedule your email campaigns — no new dashboards, you'll manage me from your inbox.",
    }
    intro = agent_intros.get(agent_id, "We're excited to learn more about your business.")
    pain = lead.get("pain_points")
    pain_block = (
        f'<p style="color:#404045;background:#f5f3ff;border-left:3px solid #7c3aed;padding:12px 16px;border-radius:6px;margin:18px 0"><em>"{pain}"</em></p>'
        if pain else ""
    )
    instant_access = (
        '<p>In the meantime, your CortexViral account is already set up — '
        'click the button below to sign in instantly (no password needed). '
        'Most leads find their first viral hook within the first 5 minutes inside.</p>'
        if magic_link else
        '<p>In the meantime, if you want to skip the wait and explore the platform yourself, you can sign in any time — your account is already created.</p>'
    )
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>Thanks for reaching out — {intro}</p>
    {pain_block}
    <p>I've got the details you sent. I'll dig into your site, draft a quick plan, and follow up <strong>within 24 hours</strong> with the first 2-3 things I'd ship for you.</p>
    {instant_access}
    <p style="color:#71717a;font-size:13.5px">Talk soon,<br>— {agent_name}</p>
    """
    return await send_email(
        to=lead["email"], subject=subj, tags=["lead_auto_reply", f"agent:{agent_id}"],
        html=_layout(f"{agent_name} here 👋", body,
                     cta_label="Sign in to CortexViral" if magic_link else None,
                     cta_url=magic_link or None),
    )

async def send_temp_password_email(to: str, name: str, temp_password: str,
                                   reason: str = "lead_form"):
    """Sent when a user is auto-created from the lead form (or requests a
    password reset). Contains the plaintext temp password + a CTA to /login.

    The `reason` parameter controls the headline copy:
      • "lead_form" → "Welcome to CortexViral — your account is ready"
      • "reset"     → "Your CortexViral password has been reset"
      • "admin"     → "Your CortexViral account has been created by an admin"
    """
    first = (name or "there").split()[0]
    login_url = f"{PUBLIC_SITE_URL}/login"
    is_reset = reason == "reset"
    headline = (
        "Your CortexViral password has been reset"
        if is_reset
        else "Welcome to CortexViral — your account is ready"
    )
    subj = headline
    body = f"""
    <p>Hey <strong>{first}</strong>,</p>
    <p>{
        'You requested a password reset. Use the temporary credentials below to sign in.'
        if is_reset
        else "Thanks for reaching out — we've set up your CortexViral account so you can dive right in."
    }</p>
    <table style="margin:18px 0;border-collapse:collapse;background:#f5f3ff;border:1px solid #ddd6fe;border-radius:8px;padding:14px;font-size:13.5px">
      <tr><td style="padding:8px 14px;color:#52525b">Username (email):</td>
          <td style="padding:8px 14px;color:#18181b;font-family:monospace"><strong>{to}</strong></td></tr>
      <tr><td style="padding:8px 14px;color:#52525b">Temporary password:</td>
          <td style="padding:8px 14px;color:#7c3aed;font-family:monospace;font-size:15px"><strong>{temp_password}</strong></td></tr>
    </table>
    <p style="background:#fff7ed;border:1px solid #fed7aa;padding:12px 16px;border-radius:8px;color:#9a3412;font-size:13px">
      🔒 <strong>For security</strong>, you'll be asked to set your own password the first time you log in. This temporary password works only for that initial sign-in.
    </p>
    <p style="color:#71717a;font-size:13.5px">Prefer one-click sign-in? You can use your Google account with the same email from the login page.</p>
    <p style="color:#71717a;font-size:13.5px">— The CortexViral team</p>
    """
    return await send_email(
        to=to, subject=subj, tags=["temp_password", reason],
        html=_layout(
            "Sign in to your account",
            body,
            cta_label="Sign in to CortexViral",
            cta_url=login_url,
        ),
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
