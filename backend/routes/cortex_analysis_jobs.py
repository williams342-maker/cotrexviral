"""Cortex Analysis Jobs — durable long-running analysis with visible
status, real job IDs, and conversation integration.

CRITICAL RULE: Cortex must NEVER claim to be running an analysis
without a real `analysis_jobs` row backing it. Every "I'm scanning..."
message references a job_id surfaced in the Active Work rail.

State machine:
    queued → running → completed → reviewed → mission_created
                    ↓
                 failed (Retry available)

Auto-completion: when a job transitions to completed/failed, the
runner appends a Cortex message into the user's current conversation
with kind="analysis_complete" / kind="analysis_failed" + embedded
action buttons so the user never finds out about results by silence.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# Supported job types. Each has a runner registered in
# `cortex.analysis_runner._RUNNERS`.
JOB_TYPES = {
    "seo_scan":         "SEO Scan",
    "seller_discovery": "Seller Discovery",
    "site_scan":        "Site Scan",
    "competitor_audit": "Competitor Audit",
    "content_audit":    "Content Audit",
}

# Statuses ordered for the rail's section grouping.
STATUSES = ("queued", "running", "completed", "failed", "reviewed",
             "mission_created", "cancelled")


# Tone targets for kind-specific completion CTAs in the chat bubble.
# Each entry tells the frontend what action buttons to render.
ACTION_TEMPLATES = {
    "seo_scan": {
        "view_label":     "View Report",
        "create_label":   "Create SEO Fix Mission",
        "optimize_label": "Optimize Automatically",
    },
    "seller_discovery": {
        "view_label":     "View Discovered Sellers",
        "create_label":   "Launch Outreach Mission",
        "optimize_label": "Auto-Qualify Top Tier",
    },
    "site_scan": {
        "view_label":     "View Report",
        "create_label":   "Create Improvement Mission",
        "optimize_label": "Apply Automatically",
    },
    "competitor_audit": {
        "view_label":     "View Audit",
        "create_label":   "Create Counter-Move",
        "optimize_label": "Match Pricing",
    },
    "content_audit": {
        "view_label":     "View Audit",
        "create_label":   "Create Content Mission",
        "optimize_label": "Refresh Top 10",
    },
}


# ----------------------------------------------------------- payloads
class CreateJobPayload(BaseModel):
    job_type:        str
    target:          Optional[str] = Field(None, max_length=500)
    params:          Optional[dict] = None
    conversation_id: Optional[str] = None


# ----------------------------------------------------------- helpers
def _project(j: dict) -> dict:
    """Shape a job row for the frontend. Excludes Mongo internals."""
    template = ACTION_TEMPLATES.get(j.get("job_type") or "", {})
    return {
        "id":              j.get("id"),
        "user_id":         j.get("user_id"),
        "conversation_id": j.get("conversation_id"),
        "job_type":        j.get("job_type"),
        "job_label":       JOB_TYPES.get(j.get("job_type") or "", "Analysis"),
        "target":          j.get("target"),
        "status":          j.get("status"),
        "progress_pct":    int(j.get("progress_pct") or 0),
        "current_step":    j.get("current_step"),
        "next_step":       j.get("next_step"),
        "eta_seconds":     j.get("eta_seconds"),
        "started_at":      _iso(j.get("started_at")),
        "completed_at":    _iso(j.get("completed_at")),
        "queued_at":       _iso(j.get("queued_at")),
        "error_message":   j.get("error_message"),
        "result_summary":  j.get("result_summary"),
        "result_link":     j.get("result_link"),
        "metrics":         j.get("metrics") or {},
        "view_label":      template.get("view_label", "View Results"),
        "create_label":    template.get("create_label", "Create Mission"),
        "optimize_label":  template.get("optimize_label", "Optimize Automatically"),
        "mission_id":      j.get("mission_id"),
    }


def _iso(v) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


# ----------------------------------------------------------- endpoints
@api.post("/cortex/analysis-jobs")
async def create_analysis_job(payload: CreateJobPayload, request: Request):
    """Enqueue a new analysis job. CRITICAL: this is the ONLY way Cortex
    is allowed to claim it's running a scan. Returns the job_id which
    the chat layer references in any "scanning…" message."""
    user = await get_current_user(request)
    if payload.job_type not in JOB_TYPES:
        raise HTTPException(400, f"Unknown job_type: {payload.job_type}. "
                                   f"Allowed: {list(JOB_TYPES)}")

    # Cap concurrent in-flight jobs per user (queued + running). The
    # rail isn't meant to host dozens of items at once and a runaway
    # caller shouldn't be able to swamp the runner.
    active = await db.analysis_jobs.count_documents({
        "user_id": user.user_id,
        "status":  {"$in": ["queued", "running"]},
    })
    if active >= 5:
        raise HTTPException(429, "Too many active jobs (max 5). "
                                   "Wait for current ones to finish or cancel one.")

    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    doc = {
        "id":               job_id,
        "user_id":          user.user_id,
        "conversation_id":  payload.conversation_id,
        "job_type":         payload.job_type,
        "target":           (payload.target or "").strip()[:500] or None,
        "params":           payload.params or {},
        "status":           "queued",
        "progress_pct":     0,
        "current_step":     "Waiting in queue",
        "next_step":        "Starting analysis",
        "eta_seconds":      _estimate_eta(payload.job_type),
        "queued_at":        now,
        "started_at":       None,
        "completed_at":     None,
        "error_message":    None,
        "result_summary":   None,
        "result_link":      None,
        "metrics":          {},
        "mission_id":       None,
    }
    await db.analysis_jobs.insert_one(doc)

    # Fire the runner. asyncio.create_task — survives the response,
    # dies cleanly if process exits (rare). Retry handles that case.
    from cortex.analysis_runner import run_analysis_job
    asyncio.create_task(run_analysis_job(job_id))

    return _project(doc)


@api.get("/cortex/analysis-jobs")
async def list_analysis_jobs(request: Request, hours: int = 24):
    """List the user's recent analysis jobs (last `hours` hours, default
    24). The Active Work rail polls this every 1.5s."""
    user = await get_current_user(request)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(168, hours)))
    cur = db.analysis_jobs.find({
        "user_id":    user.user_id,
        "queued_at":  {"$gte": cutoff},
    }, {"_id": 0}).sort("queued_at", -1).limit(50)
    rows = []
    async for j in cur:
        rows.append(_project(j))
    grouped: dict[str, list] = {s: [] for s in STATUSES}
    for r in rows:
        grouped.setdefault(r["status"], []).append(r)
    return {"jobs": rows, "grouped": grouped}


@api.get("/cortex/analysis-jobs/{job_id}")
async def get_analysis_job(job_id: str, request: Request):
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    return _project(j)


@api.post("/cortex/analysis-jobs/{job_id}/retry")
async def retry_analysis_job(job_id: str, request: Request):
    """Reset a failed job to `queued` and re-fire the runner. No-op for
    non-failed jobs (idempotent)."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] not in ("failed", "cancelled"):
        return _project(j)
    await db.analysis_jobs.update_one(
        {"id": job_id, "user_id": user.user_id},
        {"$set": {"status":        "queued",
                   "progress_pct":  0,
                   "current_step":  "Waiting in queue (retry)",
                   "next_step":     "Starting analysis",
                   "error_message": None,
                   "started_at":    None,
                   "completed_at":  None,
                   "queued_at":     datetime.now(timezone.utc)}},
    )
    from cortex.analysis_runner import run_analysis_job
    asyncio.create_task(run_analysis_job(job_id))
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    return _project(j)


@api.post("/cortex/analysis-jobs/{job_id}/cancel")
async def cancel_analysis_job(job_id: str, request: Request):
    """Mark queued/running job as cancelled. The runner checks this
    flag on each step and exits early."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] not in ("queued", "running"):
        return _project(j)
    await db.analysis_jobs.update_one(
        {"id": job_id, "user_id": user.user_id},
        {"$set": {"status":       "cancelled",
                   "completed_at": datetime.now(timezone.utc),
                   "current_step": "Cancelled by user"}},
    )
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    return _project(j)


@api.post("/cortex/analysis-jobs/{job_id}/mark-reviewed")
async def mark_analysis_reviewed(job_id: str, request: Request):
    """User clicked View Report — mark reviewed so the card moves out
    of the active rail (still visible in history)."""
    user = await get_current_user(request)
    await db.analysis_jobs.update_one(
        {"id": job_id, "user_id": user.user_id,
         "status": {"$in": ["completed"]}},
        {"$set": {"status": "reviewed",
                   "reviewed_at": datetime.now(timezone.utc)}},
    )
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    return _project(j)


@api.post("/cortex/analysis-jobs/{job_id}/create-mission")
async def create_mission_from_job(job_id: str, request: Request):
    """Spawn a real mission from a completed analysis job. Each
    `job_type` maps to a tailored mission spec — what the user sees on
    the Create Mission button is wired here, not stubbed.

    Mapping:
      seo_scan         → seo_fix mission (autonomy L2; user reviews fixes before execution)
      seller_discovery → seller_acquisition mission (uses qualified target, niche=target, no auto-outreach)
      site_scan        → content_refresh stub mission
      competitor_audit → counter_competitor stub mission
      content_audit    → content_calendar stub mission

    Idempotent: subsequent calls for the same job return the existing
    mission row instead of creating duplicates."""
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] not in ("completed", "reviewed", "mission_created"):
        raise HTTPException(409, f"Job must be completed first (status={j['status']})")

    # Idempotency: if a mission was already created from this job, return it.
    if j.get("mission_id"):
        m = await db.missions.find_one(
            {"id": j["mission_id"], "user_id": user.user_id}, {"_id": 0})
        if m:
            return {"mission_id": m["id"], "title": m.get("title"),
                    "already_created": True}

    spec = _spec_for_job(j)
    from routes.missions import _create_mission_core
    mid = await _create_mission_core(
        user_id=user.user_id,
        title=spec["title"],
        description=spec["description"],
        metric=spec["metric"],
        target=spec["target"],
        autonomy_level=spec["autonomy_level"],
        teams_assigned=spec["teams"],
        mission_type=spec["mission_type"],
        seller_target_niche=spec.get("seller_target_niche"),
        status="running",
    )

    # Stamp the job row with the mission_id so the rail card can link
    # to it + idempotency works on next call.
    await db.analysis_jobs.update_one(
        {"id": job_id, "user_id": user.user_id},
        {"$set": {"mission_id": mid, "status": "mission_created"}},
    )
    return {"mission_id": mid, "title": spec["title"], "already_created": False}


@api.post("/cortex/analysis-jobs/{job_id}/optimize")
async def optimize_automatically(job_id: str, request: Request):
    """Option-A semantics: launch an `seo_auto_fix` mission at L3 that
    drafts ready-to-apply change records from the SEO scan report.

    L3 means Cortex can act without per-step approval — but irreversible
    production changes (i.e., actually deploying the rewrites to the
    user's site) still wait on the CMS connector. Until that ships,
    this endpoint:

      1) Creates a real `missions` row at autonomy_level=3,
         mission_type=seo_auto_fix, target=high_priority count.
      2) Synchronously drafts copy-pasteable change records via
         `cortex.seo_auto_fix.draft_changes_for_job` (~one Claude call,
         <20s). Each record lands in `seo_change_records` with
         status='ready'.
      3) Returns mission_id + draft counts so the UI can deep-link
         straight to the approve-all batch.

    Idempotent — second call returns the existing mission and skips
    redrafting (records persist).

    Only applicable to completed `seo_scan` jobs today; other job
    types are 400.
    """
    user = await get_current_user(request)
    j = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user.user_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    if j.get("job_type") != "seo_scan":
        raise HTTPException(400, "Optimize Automatically is only available for SEO scans today.")
    if j["status"] not in ("completed", "reviewed", "mission_created"):
        raise HTTPException(409, f"Job must be completed first (status={j['status']})")

    # Idempotency: if a mission was already auto-fixed from this job,
    # return it + the existing draft count.
    if j.get("mission_id"):
        m = await db.missions.find_one(
            {"id": j["mission_id"], "user_id": user.user_id}, {"_id": 0})
        if m and m.get("mission_type") == "seo_auto_fix":
            ready = await db.seo_change_records.count_documents({
                "user_id": user.user_id, "mission_id": m["id"],
                "status":  "ready",
            })
            return {"mission_id": m["id"], "title": m.get("title"),
                    "drafted": ready, "ready": ready,
                    "already_created": True}

    # Build an L3 seo_auto_fix mission. Target = high-priority count
    # (or fall back to issues_found / 3) so the bar reflects what's
    # being prepared.
    metrics = j.get("metrics") or {}
    high = int(metrics.get("high_priority", 0)) \
            or max(3, int(metrics.get("issues_found", 0)) // 3)
    title = f"Auto-fix top SEO issues for {j.get('target') or 'site'}"
    description = (
        f"Auto-launched at L3 from SEO scan job #{job_id[:8]}. "
        f"Drafting {high} prioritized fixes for your review. "
        "Cortex acts without per-step approval; the rewrites are staged "
        "in `seo_change_records` ready for batch approve. "
        "Live deployment waits on the CMS connector."
    )
    from routes.missions import _create_mission_core
    mid = await _create_mission_core(
        user_id=user.user_id,
        title=title,
        description=description,
        metric="fixes_ready",
        target=high,
        autonomy_level=3,
        teams_assigned=["intelligence", "creator"],
        mission_type="seo_auto_fix",
        seller_target_niche=None,
        status="running",
    )

    # Drafting happens synchronously so the UI hop lands on a ready
    # batch (good UX). One Claude tool-call covers all findings.
    from cortex.seo_auto_fix import draft_changes_for_job
    result = await draft_changes_for_job(
        job_id=job_id, mission_id=mid, user_id=user.user_id)

    await db.analysis_jobs.update_one(
        {"id": job_id, "user_id": user.user_id},
        {"$set": {"mission_id": mid, "status": "mission_created"}},
    )

    return {
        "mission_id":      mid,
        "title":           title,
        "drafted":         result.get("drafted", 0),
        "ready":           result.get("ready", 0),
        "report_id":       result.get("report_id"),
        "error":           result.get("error"),
        "already_created": False,
    }


@api.get("/cortex/analysis-jobs/missions/{mission_id}/changes")
async def list_seo_change_records(mission_id: str, request: Request):
    """List the ready-to-apply SEO change records drafted by an
    seo_auto_fix mission. Frontend renders this as an Approve-All
    batch on the mission detail page."""
    user = await get_current_user(request)
    cur = db.seo_change_records.find(
        {"user_id": user.user_id, "mission_id": mission_id},
        {"_id": 0},
    ).sort("created_at", 1).limit(200)
    rows = [r async for r in cur]
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    by_status: dict[str, int] = {}
    for r in rows:
        s = r.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    return {"changes": rows, "by_status": by_status,
            "total": len(rows)}


def _spec_for_job(j: dict) -> dict:
    """Build a mission spec from a completed analysis job. Each job
    type has its own translation; metrics from the analysis inform the
    mission target where it makes sense."""
    job_type = j.get("job_type") or "analysis"
    metrics = j.get("metrics") or {}
    target_str = j.get("target") or ""

    if job_type == "seo_scan":
        # Use issues_found as the mission target so progress is tied to
        # the number of fixes shipped vs. the number found.
        issues = int(metrics.get("issues_found", 0)) or 3
        return {
            "title":          f"Fix SEO findings for {target_str or 'site'}",
            "description":    (f"Auto-generated from SEO scan job #{j['id'][:8]}. "
                                f"{issues} improvements detected, "
                                f"{metrics.get('high_priority', 0)} high-priority."),
            "metric":         "issues_resolved",
            "target":         issues,
            "mission_type":   "seo_fix",
            "autonomy_level": 2,   # L2 — Cortex drafts, user approves
            "teams":          ["intelligence", "creator"],
        }

    if job_type == "seller_discovery":
        qualified = int(metrics.get("qualified", 0)) or 25
        return {
            "title":          f"Recruit qualified sellers in {target_str or 'niche'}",
            "description":    (f"Auto-generated from seller-discovery job #{j['id'][:8]}. "
                                f"{qualified} qualified sellers found. "
                                f"Tier 1: {metrics.get('tier_1', 0)}. "
                                "No outreach has been sent yet — this mission will start contact "
                                "under your autonomy settings."),
            "metric":         "sellers_acquired",
            "target":         qualified,
            "mission_type":   "seller_acquisition",
            "autonomy_level": 2,   # L2 — operator drafts outreach, user approves
            "teams":          ["scout", "operator", "creator"],
            "seller_target_niche": target_str or "general",
        }

    # Generic mapping for the scaffold-only job types — creates a real
    # mission row so the user can shepherd it manually until each scan
    # gets its dedicated implementation.
    return {
        "title":          f"{job_type.replace('_', ' ').title()} follow-up",
        "description":    (f"Auto-generated from {job_type} job #{j['id'][:8]}. "
                            "Open the mission to refine scope and launch."),
        "metric":         "actions_completed",
        "target":         5,
        "mission_type":   job_type,
        "autonomy_level": 1,   # L1 — user steers; safer default for stub kinds
        "teams":          ["intelligence"],
    }


def _estimate_eta(job_type: str) -> int:
    """Coarse ETAs displayed before the runner kicks off. Once running,
    the runner updates these per-phase with sharper numbers."""
    return {
        "seo_scan":         45,
        "seller_discovery": 90,
        "site_scan":        30,
        "competitor_audit": 60,
        "content_audit":    50,
    }.get(job_type, 30)
