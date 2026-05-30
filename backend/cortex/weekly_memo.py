"""Weekly Cortex Memo — Monday-morning briefing.

Composes a one-pager retrospective + forward-looking plan per active
user, sends it via SendGrid (Mailgun fallback), and logs to email_log.
Cron entry: Monday 09:00 UTC.

Memo structure:
  · Last week's detections + which improved
  · Strategic memory summary (long-term goals)
  · Top 3 priorities Cortex recommends for THIS week
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


async def _compose_memo_for(user_id: str) -> Optional[dict]:
    """Build the memo payload for one user. Returns None if there's
    nothing meaningful to send (no activity in the past 7 days)."""
    from core import db

    since = datetime.now(timezone.utc) - timedelta(days=7)

    # 1) Detections + learnings
    detections: list[dict] = []
    cur = db.cortex_optimization_log.find(
        {"user_id": user_id, "created_at": {"$gte": since}}, {"_id": 0},
    ).sort("created_at", -1).limit(20)
    async for r in cur:
        detections.append(r)
    if not detections:
        # No detections AND no missions launched → skip the memo.
        miss_count = await db.missions.count_documents(
            {"user_id": user_id, "created_at": {"$gte": since}})
        if miss_count == 0:
            return None

    improved = [d for d in detections if d.get("learning") == "improved"]
    open_ones = [d for d in detections if not d.get("applied_at")][:3]

    # 2) Strategic memory
    strategy = await db.cortex_strategy.find_one({"user_id": user_id}, {"_id": 0}) or {}

    # 3) Forward-looking priorities — use opportunity-feed top 3.
    priorities: list[dict] = []
    try:
        from routes.cortex_recommendations import build_briefing
        briefing = await build_briefing(user_id, max_opportunities=3)
        priorities = (briefing or {}).get("opportunities", [])[:3]
    except Exception:
        logger.exception("memo: build_briefing failed")

    # 4) Missions
    mission_count = await db.missions.count_documents(
        {"user_id": user_id, "created_at": {"$gte": since}})

    return {
        "user_id":       user_id,
        "week_end":      datetime.now(timezone.utc).isoformat(),
        "detections":    detections[:5],
        "improved":      improved[:3],
        "open_actions":  open_ones,
        "strategy":      strategy,
        "priorities":    priorities,
        "missions_launched_7d": mission_count,
    }


def _render_html(name: str, memo: dict) -> str:
    """Render the memo as a self-contained HTML email."""
    strat = memo.get("strategy") or {}
    detections = memo.get("detections") or []
    improved = memo.get("improved") or []
    priorities = memo.get("priorities") or []
    open_actions = memo.get("open_actions") or []
    missions_count = memo.get("missions_launched_7d", 0)

    def li_list(items: list, render):
        return "".join(f"<li style='margin-bottom:6px'>{render(it)}</li>" for it in items)

    return f"""<!doctype html><html><body style="font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0c;color:#e4e4e7;padding:24px;max-width:680px;margin:0 auto">
  <div style="border:1px solid rgba(167,139,250,0.25);background:rgba(167,139,250,0.04);border-radius:14px;padding:24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#a78bfa;font-weight:700;margin-bottom:6px">CORTEX · WEEKLY MEMO</div>
    <h2 style="margin:0 0 16px 0;font-size:22px;color:#fff">Hi {name} — here's what I worked on this week</h2>

    <h3 style="font-size:13px;color:#a78bfa;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 8px">By the numbers</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="padding:8px 0;font-size:11px;color:#71717a">DETECTIONS<br><b style="color:#fff;font-size:18px">{len(detections)}</b></td>
        <td style="padding:8px 0;font-size:11px;color:#71717a">IMPROVED<br><b style="color:#10b981;font-size:18px">{len(improved)}</b></td>
        <td style="padding:8px 0;font-size:11px;color:#71717a">MISSIONS LAUNCHED<br><b style="color:#a78bfa;font-size:18px">{missions_count}</b></td>
      </tr>
    </table>

    {f'''<h3 style="font-size:13px;color:#a78bfa;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 8px">Last week's findings</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#d4d4d8;line-height:1.6">
      {li_list(detections[:5], lambda d: f"<b>{d.get('bottleneck','')}</b><br><span style='color:#a1a1aa;font-size:12px'>{d.get('recommendation','')}</span>")}
    </ul>''' if detections else ''}

    {f'''<h3 style="font-size:13px;color:#a78bfa;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 8px">Where we are</h3>
    <p style="font-size:13px;color:#d4d4d8;line-height:1.5">{strat.get("summary","")}</p>''' if strat.get("summary") else ''}

    {f'''<h3 style="font-size:13px;color:#a78bfa;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 8px">My recommendations for this week</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#d4d4d8;line-height:1.6">
      {li_list(priorities, lambda p: f"<b>{p.get('title','')}</b><br><span style='color:#a1a1aa;font-size:12px'>{p.get('subtitle') or p.get('summary','')}</span>")}
    </ul>''' if priorities else ''}

    {f'''<h3 style="font-size:13px;color:#f59e0b;text-transform:uppercase;letter-spacing:0.08em;margin:18px 0 8px">Awaiting your decision</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#d4d4d8;line-height:1.6">
      {li_list(open_actions, lambda a: f"<b>{a.get('bottleneck','')}</b> — <i>{a.get('recommendation','')}</i>")}
    </ul>''' if open_actions else ''}

    <p style="margin-top:24px;font-size:11px;color:#71717a">
      I'll keep working. Open the Command Center anytime to dive deeper.
    </p>
  </div>
  <p style="font-size:11px;color:#52525b;text-align:center;margin-top:16px">
    Sent by Cortex · CortexViral
  </p>
</body></html>"""


async def send_memo_for_user(user_id: str) -> dict:
    """Compose + send one user's weekly memo."""
    from core import db
    memo = await _compose_memo_for(user_id)
    if memo is None:
        return {"sent": False, "reason": "no_activity"}

    user_doc = await db.users.find_one({"user_id": user_id}) or {}
    to_email = (user_doc.get("email") or "").strip()
    if not to_email or "@" not in to_email:
        return {"sent": False, "reason": "no_email"}

    name = user_doc.get("name") or "there"
    html = _render_html(name, memo)
    subject = f"Cortex weekly memo — {len(memo['detections'])} findings, {memo['missions_launched_7d']} missions"

    provider = None; error = None
    try:
        from routes.email import _send_via_sendgrid
        res = await _send_via_sendgrid(
            to=to_email, subject=subject, html=html, text=None,
            from_addr=None, tags=["cortex_weekly_memo"],
            custom_args={"user_id": user_id, "template": "cortex_weekly_memo"},
        )
        if res.get("sent"): provider = "sendgrid"
        else: error = res.get("error")
    except Exception as e:
        logger.exception("memo: sendgrid failed")
        error = str(e)
    if provider is None:
        try:
            from routes.email import _send_via_mailgun
            res = await _send_via_mailgun(
                to=to_email, subject=subject, html=html, text=None,
                from_addr=None, tags=["cortex_weekly_memo"])
            if res.get("sent"): provider = "mailgun"
            else: error = res.get("error")
        except Exception as e:
            logger.exception("memo: mailgun failed")
            error = str(e)

    await db.email_log.insert_one({
        "id":         uuid.uuid4().hex,
        "provider":   provider or "none",
        "template":   "cortex_weekly_memo",
        "to_email":   to_email,
        "subject":    subject,
        "status":     "sent" if provider else "failed",
        "error":      error if not provider else None,
        "user_id":    user_id,
        "created_at": datetime.now(timezone.utc),
    })
    return {"sent": provider is not None, "provider": provider, "to": to_email,
            "error": error if not provider else None}


async def run_weekly_memo_sweep() -> dict:
    """Scheduler entry — sweep all active users and send memos."""
    from core import db
    seen: set[str] = set()
    horizon = datetime.now(timezone.utc) - timedelta(days=30)
    cur = db.missions.find(
        {"created_at": {"$gte": horizon}, "user_id": {"$ne": None}},
        {"_id": 0, "user_id": 1}).limit(500)
    async for row in cur:
        uid = row.get("user_id")
        if uid: seen.add(uid)
    summary = {"total_users": len(seen), "sent": 0, "skipped": 0, "failed": 0}
    for uid in seen:
        try:
            res = await send_memo_for_user(uid)
            if res.get("sent"): summary["sent"] += 1
            elif res.get("reason"): summary["skipped"] += 1
            else: summary["failed"] += 1
        except Exception:
            logger.exception("memo sweep: failed for %s", uid)
            summary["failed"] += 1
    summary["ran_at"] = datetime.now(timezone.utc).isoformat()
    return summary
