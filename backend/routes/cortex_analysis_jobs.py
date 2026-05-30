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
