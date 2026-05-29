"""Week in Review — Sunday digest summarizing the autonomous team's week.

Compiles a single concise snapshot from the existing collections:
  • briefs proposed/approved/auto-approved this week
  • experiments concluded with winners
  • top listening signal
  • goal progress (% to target)
  • per-agent ledger snapshot

Stored in `weekly_digests` so the operator can review historical weeks.
Optionally emailed when SENDGRID/MAILGUN is configured (best-effort, never blocks).

Sunday 18:00 UTC cron iterates active users and persists one row per user.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request

from core import api, db
from deps import get_current_user
from routes.autonomy import check_budget, _iso_week_key, _week_bounds
from routes.agent_personas import PERSONAS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Compute helper
# ---------------------------------------------------------------------
async def compute_week_in_review(user_id: str) -> dict:
    """Compiles the full digest for `user_id` for the CURRENT ISO week.
    Pure read — never writes anywhere. Safe to call from the UI."""
    week_start, week_end = await _week_bounds()
    import asyncio as _aio
    (briefs_week, exps_week, posts_week, signals_week,
     standups_week, goals_active) = await _aio.gather(
        db.proposed_briefs.find(
            {"user_id": user_id, "created_at": {"$gte": week_start}},
            {"_id": 0, "title": 1, "status": 1, "auto_approved": 1, "decided_by": 1},
        ).sort("created_at", -1).to_list(length=200),
        db.experiments.find(
            {"user_id": user_id, "ended_at": {"$gte": week_start}, "status": "completed"},
            {"_id": 0, "name": 1, "winner_margin_pct": 1, "metric": 1, "conclusion_text": 1},
        ).sort("ended_at", -1).to_list(length=50),
        db.posts.count_documents(
            {"user_id": user_id, "status": "published", "published_at": {"$gte": week_start}}),
        db.social_listening_signals.find(
            {"user_id": user_id, "detected_at": {"$gte": week_start}},
            {"_id": 0, "text": 1, "urgency": 1, "sentiment": 1, "topic": 1},
        ).sort("urgency", -1).to_list(length=10),
        db.weekly_standups.count_documents(
            {"user_id": user_id, "generated_at": {"$gte": week_start}}),
        db.growth_goals.find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0, "title": 1, "current": 1, "target": 1, "metric": 1},
        ).to_list(length=50),
    )

    # Derived stats — keep numbers honest, not aspirational.
    briefs_proposed = len(briefs_week)
    briefs_approved = sum(1 for b in briefs_week if b["status"] == "approved")
    briefs_auto     = sum(1 for b in briefs_week if b.get("auto_approved"))
    briefs_rejected = sum(1 for b in briefs_week if b["status"] == "rejected")
    top_signal = signals_week[0] if signals_week else None

    # Goal progress — avg % to target across active goals.
    goal_pct = 0.0
    if goals_active:
        valid = [
            min(100.0, ((g.get("current") or 0) / g["target"]) * 100)
            for g in goals_active
            if isinstance(g.get("target"), (int, float)) and g["target"] > 0
        ]
        goal_pct = round(sum(valid) / len(valid), 1) if valid else 0.0

    # Per-agent budget snapshot — only agents that BURNED something this
    # week (filters out the noise of every agent always being on the list).
    agent_snapshots = []
    for p in PERSONAS:
        snap = await check_budget(p["id"], user_id)
        if snap.get("tokens_used") or snap.get("irreversible_used"):
            agent_snapshots.append({
                "agent_id":         p["id"],
                "name":             p["name"],
                "tokens_used":      snap.get("tokens_used", 0),
                "usd_used":         snap.get("usd_used", 0.0),
                "headroom_pct":     snap.get("headroom_pct", 0),
                "can_act":          snap.get("can_act", True),
            })

    return {
        "iso_week":             _iso_week_key(),
        "week_started_at":      week_start,
        "week_ended_at":        week_end,
        "briefs_proposed":      briefs_proposed,
        "briefs_approved":      briefs_approved,
        "briefs_auto_approved": briefs_auto,
        "briefs_rejected":      briefs_rejected,
        "experiments_concluded": len(exps_week),
        "experiment_winners":   [{
            "name":       e["name"],
            "metric":     e.get("metric"),
            "margin_pct": e.get("winner_margin_pct"),
        } for e in exps_week[:5]],
        "posts_published":      posts_week,
        "signals_captured":     len(signals_week),
        "top_signal":           top_signal,
        "standups_generated":   standups_week,
        "goal_progress_pct":    goal_pct,
        "active_goals":         len(goals_active),
        "agent_burns":          agent_snapshots,
    }


# ---------------------------------------------------------------------
# HTML email template
# ---------------------------------------------------------------------
def _digest_html(name: str, d: dict) -> str:
    """Renders the digest as a minimal HTML email. Inline styles —
    most email clients strip <style> blocks."""
    winners_html = ""
    for w in d.get("experiment_winners") or []:
        winners_html += (
            f"<li><b>{w['name']}</b> won on {w['metric']} "
            f"(+{(w.get('margin_pct') or 0):.0f}%)</li>"
        )
    if not winners_html:
        winners_html = "<li style='color:#888;'>No experiments concluded this week.</li>"

    sig = d.get("top_signal") or {}
    sig_html = (f'<div style="background:#fef9c3;padding:12px;border-radius:8px;'
                f'margin:8px 0;color:#713f12;">'
                f'<b>Top signal:</b> "{(sig.get("text") or "")[:200]}" '
                f'(urgency {sig.get("urgency", 1)}/5)</div>') if sig else ""

    agents_html = ""
    for a in d.get("agent_burns") or []:
        tone = "#ef4444" if a["headroom_pct"] >= 80 else "#0ea5e9"
        agents_html += (
            f"<tr><td style='padding:6px 12px 6px 0;'><b>{a['name']}</b></td>"
            f"<td style='padding:6px 12px;color:{tone};text-align:right;'>"
            f"{a['headroom_pct']:.0f}% used</td>"
            f"<td style='padding:6px 0;color:#666;text-align:right;'>"
            f"${a['usd_used']:.2f}</td></tr>"
        )
    if not agents_html:
        agents_html = ("<tr><td colspan='3' style='color:#888;padding:6px 0;'>"
                       "No LLM burn recorded this week.</td></tr>")

    return f"""
    <h2 style="color:#0f172a;margin-bottom:4px;">Your team's week — {d['iso_week']}</h2>
    <p style="color:#64748b;margin-top:0;">Here's what your autonomous Growth Team shipped this week, {name}.</p>

    <div style="background:#f8fafc;padding:16px;border-radius:12px;margin:16px 0;">
      <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <div><span style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Briefs proposed</span><br>
          <b style="font-size:24px;">{d['briefs_proposed']}</b>
          <span style="color:#10b981;">· {d['briefs_approved']} approved</span>
          {f"<span style='color:#a855f7;'>· {d['briefs_auto_approved']} auto-approved</span>" if d['briefs_auto_approved'] else ""}
        </div>
      </div>
      <div style="margin-top:12px;display:flex;gap:24px;flex-wrap:wrap;color:#475569;">
        <div><b>{d['experiments_concluded']}</b> experiments concluded</div>
        <div><b>{d['posts_published']}</b> posts published</div>
        <div><b>{d['signals_captured']}</b> signals captured</div>
        <div><b>{d['goal_progress_pct']:.0f}%</b> avg goal progress</div>
      </div>
    </div>

    {sig_html}

    <h3 style="color:#0f172a;margin-bottom:4px;">🧪 Experiment winners</h3>
    <ul style="color:#475569;">{winners_html}</ul>

    <h3 style="color:#0f172a;margin-bottom:4px;">🔋 Agent burn this week</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      {agents_html}
    </table>
    """


# ---------------------------------------------------------------------
# Persistence + email
# ---------------------------------------------------------------------
async def generate_and_persist_digest(user_id: str, *, send_email_too: bool = True) -> dict:
    """Computes + persists a `weekly_digests` row + optionally emails it."""
    d = await compute_week_in_review(user_id)

    now = datetime.now(timezone.utc)
    doc = {
        **d,
        "user_id":      user_id,
        "generated_at": now,
        "emailed":      False,
    }
    # Dedupe per (user, iso_week) — re-running the cron in the same week
    # OVERWRITES the previous snapshot instead of double-writing.
    await db.weekly_digests.update_one(
        {"user_id": user_id, "iso_week": d["iso_week"]},
        {"$set": doc},
        upsert=True,
    )

    if send_email_too:
        try:
            from routes.email import send_email
            user = await db.users.find_one(
                {"user_id": user_id}, {"_id": 0, "email": 1, "name": 1, "username": 1},
            ) or {}
            email = user.get("email")
            if email:
                name = user.get("name") or user.get("username") or email.split("@")[0]
                subject = f"Week in Review — {d['iso_week']}"
                html = _digest_html(name, d)
                res = await send_email(email, subject, html, tags=["weekly-digest"])
                if res.get("sent"):
                    await db.weekly_digests.update_one(
                        {"user_id": user_id, "iso_week": d["iso_week"]},
                        {"$set": {"emailed": True, "emailed_at": now}},
                    )
        except Exception:
            logger.exception("digest email failed for user=%s", user_id)

    return doc


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.get("/digests/latest")
async def get_latest_digest(request: Request):
    """Returns the most recent digest for the current user, or a freshly
    computed one when none exists yet. Never emails on this path —
    operator browsing shouldn't trigger inbox traffic."""
    user = await get_current_user(request)
    doc = await db.weekly_digests.find_one(
        {"user_id": user.user_id}, {"_id": 0},
        sort=[("generated_at", -1)],
    )
    if doc:
        return doc
    # Compute on-the-fly for first-time callers.
    return await compute_week_in_review(user.user_id)


@api.get("/digests")
async def list_digests(request: Request, limit: int = 12):
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 52))
    docs = await db.weekly_digests.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("generated_at", -1).to_list(length=limit)
    return {"items": docs, "count": len(docs)}


@api.post("/digests/run-now")
async def run_digest_now(request: Request, email: Optional[bool] = True):
    """Manual trigger — useful for previewing the email + populating the
    operator's first digest before the Sunday cron runs."""
    user = await get_current_user(request)
    doc = await generate_and_persist_digest(user.user_id, send_email_too=bool(email))
    return doc


# ---------------------------------------------------------------------
# Cron — Sunday 18:00 UTC
# ---------------------------------------------------------------------
async def run_weekly_digest() -> dict:
    """Iterates over every user that did SOMETHING this week and persists
    a digest. Users with zero activity are skipped — no point spamming
    them with an empty recap."""
    week_start, _ = await _week_bounds()
    # "Active this week" = had any LLM burn OR any brief/experiment/post.
    active_ids: set[str] = set()
    async for r in db.agent_usage_ledger.find(
        {"iso_week": _iso_week_key()}, {"_id": 0, "user_id": 1},
    ):
        active_ids.add(r["user_id"])
    async for r in db.proposed_briefs.find(
        {"created_at": {"$gte": week_start}}, {"_id": 0, "user_id": 1},
    ):
        active_ids.add(r["user_id"])
    async for r in db.posts.find(
        {"published_at": {"$gte": week_start}, "status": "published"},
        {"_id": 0, "user_id": 1},
    ):
        active_ids.add(r["user_id"])

    processed = 0
    for uid in active_ids:
        try:
            await generate_and_persist_digest(uid, send_email_too=True)
            processed += 1
        except Exception:
            logger.exception("weekly digest failed for user_id=%s", uid)
    return {"users_processed": processed, "candidates": len(active_ids)}


def register_weekly_digest_job(scheduler) -> None:
    """Sunday 18:00 UTC. Idempotent — only adds when missing."""
    from apscheduler.triggers.cron import CronTrigger
    if scheduler.get_job("weekly_digest_sunday"):
        return
    scheduler.add_job(
        run_weekly_digest,
        trigger=CronTrigger(day_of_week="sun", hour=18, minute=0),
        id="weekly_digest_sunday",
        max_instances=1,
        coalesce=True,
    )
