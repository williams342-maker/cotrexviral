"""Background reminder: nudge users about HITL-paused Marketing OS runs
that have been sitting in `status="awaiting_approval"` for more than
24 hours.

Why this exists
---------------
The LangGraph human-in-the-loop gate (added in part 50) lets users
pause a Marketing OS run before Distribution publishes. If the
reviewer forgets to come back, the campaign silently stalls — Atlas
strategised, Iris researched, Nova drafted, but Kai never wrote the
distribution plan and Angela never synthesised. That's the most
expensive way for a campaign to die.

What it does
------------
Every 6 hours the scheduler ticks `_remind_paused_runs()`. For each
run that is:
    • status="awaiting_approval"
    • requires_approval=True  (defensive — only paused, not other limbo)
    • created_at older than REMINDER_THRESHOLD_HOURS
    • has not already been reminded (`reminder_sent_at` unset)
…we send one email via `routes.email.send_email()` and stamp
`reminder_sent_at` on the run row so the same user doesn't get spammed.

We deliberately send only ONE reminder per paused run — a "death by
email" anti-pattern is worse than a stalled campaign. If the user
ignores the first nudge, the existing activity feed will keep showing
the amber awaiting_approval pill indefinitely.
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from core import db

logger = logging.getLogger(__name__)

# Configurable so we can tighten in tests or relax for early users.
REMINDER_THRESHOLD_HOURS = int(os.environ.get("HITL_REMINDER_HOURS", "24"))


def _build_email(run: dict, user_name: str, brief: str, campaign_name: Optional[str]) -> tuple[str, str, str]:
    """Returns (subject, html, text) tailored to the paused run."""
    # Mongo can hand back naive datetimes — normalise to aware UTC so
    # the arithmetic doesn't blow up.
    created = run["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_hrs = max(
        24,
        int((datetime.now(timezone.utc) - created).total_seconds() / 3600),
    )
    name = (user_name or "there").split()[0]
    where = f" for the “{campaign_name}” campaign" if campaign_name else ""
    preview = (brief or "").strip().replace("\n", " ")
    if len(preview) > 240:
        preview = preview[:237] + "…"

    subject = f"⏸️ Your Marketing OS run{where} is waiting for approval"
    text = (
        f"Hey {name},\n\n"
        f"A Marketing OS run you started{where} has been paused for "
        f"~{age_hrs}h waiting for your review before Distribution "
        f"publishes anything.\n\n"
        f"Brief: {preview}\n\n"
        f"Atlas, Iris and Nova have already done their parts. One click "
        f"on Approve in the Command Center activity feed lets Kai write "
        f"the distribution plan and Angela synthesise the final summary "
        f"— takes ~30 seconds.\n\n"
        f"Or click Reject to skip Distribution and just get Angela's "
        f"executive summary on what the team already produced.\n\n"
        f"→ Review now: https://cortexviral.com/dashboard/command-center\n\n"
        f"— CortexViral"
    )
    html = f"""\
<!doctype html>
<html><body style="margin:0;padding:0;background:#0a0a0b;color:#e4e4e7;font-family:-apple-system,Segoe UI,sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:40px 24px;">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.32em;color:#a78bfa;font-weight:700;margin-bottom:8px;">Awaiting your review</div>
    <h1 style="margin:0 0 24px;font-size:24px;line-height:1.2;color:#fafafa;font-weight:800;">
      Your Marketing OS run{where} is paused
    </h1>
    <p style="margin:0 0 16px;color:#a1a1aa;font-size:14px;line-height:1.6;">
      Hey {name}, the chain has been waiting for ~{age_hrs}h. Atlas,
      Iris and Nova finished their work — Distribution is gated on your
      go-ahead.
    </p>
    <div style="background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px;margin:20px 0;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.2em;color:#71717a;margin-bottom:6px;">Brief</div>
      <div style="color:#d4d4d8;font-size:14px;line-height:1.5;">{preview}</div>
    </div>
    <a href="https://cortexviral.com/dashboard/command-center"
       style="display:inline-block;background:#7c3aed;color:#fff;padding:14px 22px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;">
      Review the run →
    </a>
    <p style="margin:32px 0 0;color:#71717a;font-size:12px;line-height:1.5;">
      You're getting this because you opted into approval gating on a
      Marketing OS run. We only send one reminder per paused run —
      promise we won't nag.
    </p>
  </div>
</body></html>"""
    return subject, html, text


async def _remind_paused_runs() -> dict:
    """Find paused runs older than the threshold that haven't been
    reminded yet, send each owner one email, stamp the row. Returns
    a small dict for log visibility."""
    from routes.email import send_email   # lazy: keeps scheduler boot light

    cutoff = datetime.now(timezone.utc) - timedelta(hours=REMINDER_THRESHOLD_HOURS)
    cursor = db.marketing_os_runs.find({
        "status": "awaiting_approval",
        "requires_approval": True,
        "created_at": {"$lte": cutoff},
        "reminder_sent_at": {"$exists": False},
    }).limit(50)   # cap per tick so a backlog can't spam

    sent = 0
    skipped = 0
    failed = 0
    async for run in cursor:
        try:
            user = await db.users.find_one(
                {"user_id": run.get("user_id")},
                {"_id": 0, "email": 1, "name": 1, "user_id": 1, "status": 1},
            )
            if not user or not user.get("email") or user.get("status") == "deleted":
                skipped += 1
                # Stamp anyway so we don't reconsider this row every tick.
                await db.marketing_os_runs.update_one(
                    {"id": run["id"]},
                    {"$set": {"reminder_sent_at": datetime.now(timezone.utc),
                              "reminder_skipped_reason": "no_email_or_deleted_user"}},
                )
                continue

            campaign_name: Optional[str] = None
            if run.get("campaign_id"):
                camp = await db.campaigns.find_one(
                    {"id": run["campaign_id"]}, {"_id": 0, "name": 1},
                )
                campaign_name = (camp or {}).get("name")

            subject, html, text = _build_email(
                run, user.get("name") or "", run.get("brief") or "", campaign_name,
            )
            result = await send_email(
                to=user["email"], subject=subject, html=html, text=text,
                tags=["hitl-reminder"],
            )
            if result.get("sent"):
                sent += 1
            else:
                failed += 1
                logger.warning(
                    "hitl-reminder failed for run %s user %s: %s",
                    run.get("id"), user.get("user_id"), result.get("error") or result.get("skipped"),
                )

            # Always stamp — successful or failed — so we don't retry
            # forever on a dead email address.
            await db.marketing_os_runs.update_one(
                {"id": run["id"]},
                {"$set": {
                    "reminder_sent_at": datetime.now(timezone.utc),
                    "reminder_status":  "sent" if result.get("sent") else "failed",
                }},
            )
        except Exception:
            failed += 1
            logger.exception("hitl-reminder crashed on run %s", run.get("id"))

    if sent or failed or skipped:
        logger.info("hitl-reminders tick: sent=%d failed=%d skipped=%d", sent, failed, skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped}


def register_hitl_reminder_job(scheduler) -> None:
    """Wires the reminder job onto the existing AsyncIOScheduler. Idempotent."""
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(
        _remind_paused_runs,
        trigger=IntervalTrigger(hours=6),
        id="hitl_paused_run_reminders",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=4),
        replace_existing=True,
    )
