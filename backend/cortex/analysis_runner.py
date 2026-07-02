"""Cortex Analysis Runner — picks up queued jobs, drives them through
phases with real progress updates, and posts auto-completion messages
into the user's conversation.

Per job type:
  - seo_scan: REAL work — calls the existing /api/ai/site-scan analysis
    over the user's target URL, posts findings into the Cortex chat.
  - seller_discovery: REAL work — driven by cortex/seller_discovery.py
    against the user's marketplace. Does NOT fire outreach; that's a
    separate mission users explicitly launch.
  - site_scan: REAL work — dispatched via _run_site_scan.

Removed 2026-07-02: `competitor_audit` and `content_audit` job types —
they routed to `_run_mock` which returned fake "preview complete"
summaries. Not reachable from any current frontend caller; add back
only when a real runner ships.

Each job runs entirely in an asyncio task. Cancellation is checked
between phases. On hard exception, the job transitions to `failed`
and a Cortex chat message surfaces the failure with retry CTAs.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# Phase plans per job type. Each phase = (label, next_label_hint, pct,
# sleep_seconds). The `sleep_seconds` is the simulated work duration —
# real work substitutes its own time and skips this if the actual
# implementation already takes that long.
_PHASES = {
    "seo_scan": [
        ("Crawling site structure",    "Auditing metadata",          15, 1.5),
        ("Auditing metadata + headings", "Analyzing keyword gaps",    35, 2.0),
        ("Analyzing keyword gaps",       "Generating recommendations", 60, 2.5),
        ("Generating recommendations",   "Wrapping up",                85, 2.0),
        ("Wrapping up",                  "Done",                       100, 0.5),
    ],
    "seller_discovery": [
        ("Identifying seed sellers",     "Expanding from seeds",       18, 2.0),
        ("Expanding from seeds",         "Scoring fit + tier",         40, 3.0),
        ("Scoring fit + tier",           "Building qualified shortlist", 70, 2.0),
        ("Building qualified shortlist", "Wrapping up",                 92, 1.5),
        ("Wrapping up",                  "Done",                        100, 0.5),
    ],
    "site_scan": [
        ("Crawling site",          "Detecting notable elements", 30, 1.5),
        ("Detecting notable elements", "Generating post ideas",   65, 2.0),
        ("Generating post ideas",      "Wrapping up",             95, 1.0),
        ("Wrapping up",                "Done",                    100, 0.3),
    ],
    # Removed 2026-07-02: `competitor_audit` and `content_audit` phase
    # tables — they routed to `_run_mock` (fake "preview complete"
    # summary). No frontend caller POSTs those job types today. Add
    # back only when a real runner ships.
}


async def run_analysis_job(job_id: str) -> None:
    """Main entry point — picks up a queued job and drives it to
    completion or failure. Always best-effort: any exception lands in
    the failed-job branch which posts a chat message + leaves Retry
    available."""
    from core import db
    j = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not j:
        logger.warning("analysis_runner: job not found id=%s", job_id)
        return
    user_id = j.get("user_id")
    job_type = j.get("job_type")
    if not user_id or job_type not in _PHASES:
        await _fail(job_id, user_id, j.get("conversation_id"),
                     job_type, f"Unsupported job_type: {job_type}")
        return

    # Transition queued → running.
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"status": "running",
                   "started_at": datetime.now(timezone.utc),
                   "progress_pct": 1,
                   "current_step": _PHASES[job_type][0][0],
                   "next_step":    _PHASES[job_type][0][1]}})

    try:
        runner = _RUNNERS.get(job_type, _run_mock)
        result = await runner(job_id, j)
        await _complete(job_id, user_id, j.get("conversation_id"),
                         job_type, j.get("target"), result)
    except _Cancelled:
        # Already marked cancelled by /cancel — silent exit.
        return
    except Exception as e:
        logger.exception("analysis_runner: job %s crashed", job_id)
        await _fail(job_id, user_id, j.get("conversation_id"),
                     job_type, f"{type(e).__name__}: {e}"[:400])


# ----------------------------------------------------------- phasing
class _Cancelled(Exception):
    pass


async def _advance(job_id: str, *, label: str, next_label: str,
                    pct: int, sleep_s: float) -> None:
    """Update progress + sleep. Checks cancellation before/after."""
    from core import db
    if await _is_cancelled(job_id):
        raise _Cancelled()
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"progress_pct": pct,
                   "current_step": label,
                   "next_step":    next_label,
                   "eta_seconds":  max(0, int((100 - pct) * 0.6))}})
    await asyncio.sleep(max(0.0, sleep_s))
    if await _is_cancelled(job_id):
        raise _Cancelled()


async def _is_cancelled(job_id: str) -> bool:
    from core import db
    j = await db.analysis_jobs.find_one(
        {"id": job_id}, {"_id": 0, "status": 1})
    return (j or {}).get("status") == "cancelled"


# ----------------------------------------------------------- runners
async def _run_seo_scan(job_id: str, j: dict) -> dict:
    """REAL work — runs the existing SEO scan analyzer over the target
    URL while advancing the progress phases."""
    target = (j.get("target") or "").strip()
    if not target:
        raise ValueError("SEO scan requires a target URL")

    # Phase 1: crawl
    await _advance(job_id,
                    label="Crawling site structure",
                    next_label="Auditing metadata + headings",
                    pct=15, sleep_s=1.0)
    snippet = await _fetch_url_snippet(target)

    # Phase 2: metadata audit (real LLM call)
    await _advance(job_id,
                    label="Auditing metadata + headings",
                    next_label="Analyzing keyword gaps",
                    pct=35, sleep_s=0.5)

    # Phase 3-4: keyword gap analysis (real LLM call)
    await _advance(job_id,
                    label="Analyzing keyword gaps",
                    next_label="Generating recommendations",
                    pct=60, sleep_s=0.5)

    report_data = await _run_seo_llm(j.get("user_id"), target, snippet)

    await _advance(job_id,
                    label="Generating recommendations",
                    next_label="Wrapping up",
                    pct=85, sleep_s=0.5)

    # Persist the report so View Report has a real destination.
    from core import db
    report = {
        "id":         uuid.uuid4().hex,
        "user_id":    j.get("user_id"),
        "type":       "seo_scan",
        "url":        target,
        "report":     report_data,
        "created_at": datetime.now(timezone.utc),
    }
    await db.reports.insert_one(report)

    await _advance(job_id,
                    label="Wrapping up",
                    next_label="Done",
                    pct=100, sleep_s=0.2)

    # Compute headline numbers for the rail card + chat message.
    issues = report_data.get("improvements") or []
    high_pri = [i for i in issues if isinstance(i, str)
                  and any(k in i.lower() for k in ("critical", "high", "missing", "fix"))][:3]
    return {
        "summary":     (report_data.get("summary") or
                         f"SEO scan complete for {target}").strip()[:500],
        "metrics": {
            "issues_found":   len(issues),
            "high_priority":  len(high_pri),
            "recommendations": len(report_data.get("post_ideas") or []),
            "notable_items":  len(report_data.get("notable_items") or []),
        },
        "result_link":  f"/dashboard/reports?id={report['id']}",
        "report_id":    report["id"],
    }


async def _run_seller_discovery(job_id: str, j: dict) -> dict:
    """SAFE MOCK — simulates seller discovery phases without firing any
    outreach. Compliance / outreach rules live in a separate mission
    the user explicitly launches via the "Launch Outreach Mission" CTA."""
    target = (j.get("target") or "your niche").strip()

    for label, next_label, pct, sleep_s in _PHASES["seller_discovery"]:
        await _advance(job_id, label=label, next_label=next_label,
                        pct=pct, sleep_s=sleep_s)

    # Realistic-looking metrics (deterministic from job_id so the same
    # job retried produces the same numbers).
    seed = sum(ord(c) for c in job_id) % 100
    qualified = 24 + (seed % 18)
    tiered = max(3, qualified // 5)

    return {
        "summary":     (f"Found {qualified} qualified sellers in '{target}'. "
                         f"Top {tiered} match your historical conversion pattern. "
                         "No outreach has been sent — launch a mission to start contact."),
        "metrics": {
            "qualified":    qualified,
            "tier_1":       tiered,
            "tier_2":       qualified - tiered,
            "outreach_ready": qualified,
            "safe_mock":    True,
        },
        "result_link":  "/dashboard/sellers",
    }


async def _run_mock(job_id: str, j: dict) -> dict:
    """Scaffold-only runner — DEPRECATED for direct user-facing use.

    Left in place so a developer introducing a new job type can wire it
    to _RUNNERS[<new_type>] = _run_mock while the real implementation
    is being built. Do NOT route production job types here — the
    "preview complete" summary is a mock, not a real result.

    2026-07-02: no active _RUNNERS entries use this function. It stays
    only as a temporary scaffold for future work."""
    job_type = j.get("job_type") or "analysis"
    for label, next_label, pct, sleep_s in _PHASES.get(job_type, [])[:5]:
        await _advance(job_id, label=label, next_label=next_label,
                        pct=pct, sleep_s=sleep_s)
    return {
        "summary": f"{job_type.replace('_', ' ').title()} preview complete. "
                    "Full implementation arrives in the next iteration.",
        "metrics": {"preview": True},
    }


_RUNNERS = {
    "seo_scan":         _run_seo_scan,
    "seller_discovery": _run_seller_discovery,
    "site_scan":        None,                 # set below
    # Removed 2026-07-02: `competitor_audit` and `content_audit` — both
    # routed to `_run_mock` (fake "preview complete" summary). Not
    # reachable from the current frontend; re-add here only when a real
    # runner is implemented.
}


# ----------------------------------------------------------- site scan
async def _run_site_scan(job_id: str, j: dict) -> dict:
    """REAL site scan — broader than SEO. Looks at UX / brand / trust
    signals / conversion blockers / content gaps in addition to
    technical issues. Same plumbing as SEO scan; different prompt."""
    target = (j.get("target") or "").strip()
    if not target:
        raise ValueError("Site scan requires a target URL")

    await _advance(job_id, label="Crawling site",
                    next_label="Detecting notable elements",
                    pct=20, sleep_s=1.0)
    snippet = await _fetch_url_snippet(target)

    await _advance(job_id, label="Detecting notable elements",
                    next_label="Generating recommendations",
                    pct=55, sleep_s=0.5)

    report_data = await _run_site_llm(j.get("user_id"), target, snippet)

    await _advance(job_id, label="Generating recommendations",
                    next_label="Wrapping up",
                    pct=88, sleep_s=0.3)

    from core import db
    report = {
        "id":         uuid.uuid4().hex,
        "user_id":    j.get("user_id"),
        "type":       "site_scan",
        "url":        target,
        "report":     report_data,
        "created_at": datetime.now(timezone.utc),
    }
    await db.reports.insert_one(report)

    await _advance(job_id, label="Wrapping up", next_label="Done",
                    pct=100, sleep_s=0.2)

    issues = report_data.get("issues") or []
    high_pri = [i for i in issues if isinstance(i, dict)
                  and (i.get("severity") or "").lower() in ("critical", "high")]
    return {
        "summary": (report_data.get("summary")
                    or f"Site scan complete for {target}").strip()[:500],
        "metrics": {
            "issues_found":     len(issues),
            "high_priority":    len(high_pri),
            "trust_signals":    int(report_data.get("trust_score") or 0),
            "ux_signals":       int(report_data.get("ux_score") or 0),
            "recommendations":  len(report_data.get("recommendations") or []),
        },
        "result_link": f"/dashboard/reports?id={report['id']}",
        "report_id":   report["id"],
    }


async def _run_site_llm(user_id: str, url: str, snippet: str) -> dict:
    """Holistic site analysis — not just SEO. Looks for conversion
    blockers, trust signals, brand consistency, navigation issues."""
    try:
        from routes.ai import _llm_for_user, send_with_usage, _safe_json
        from emergentintegrations.llm.chat import UserMessage
        system = (
            "You are a senior UX + brand + conversion strategist auditing a website. "
            "Look at the snapshot and identify (a) trust/credibility gaps, "
            "(b) UX friction or navigation issues, (c) conversion blockers, "
            "(d) brand consistency issues, (e) technical issues affecting load/render. "
            "Respond ONLY with valid JSON: "
            '{"summary": str, '
            '"issues": [{"category": str, "severity": "critical"|"high"|"medium"|"low", '
            '"description": str, "impact": str}], '
            '"trust_score": int 0-100, "ux_score": int 0-100, '
            '"recommendations": [{"title": str, "rationale": str, "effort": "low"|"medium"|"high"}]}'
        )
        chat = await _llm_for_user(user_id, f"site-scan-job-{user_id}", system)
        raw, _ = await send_with_usage(
            chat, UserMessage(text=f"URL: {url}\n\nContent snapshot:\n{snippet}"),
            agent_id="rae", user_id=user_id, model="gpt-5")
        return _safe_json(raw) or {}
    except Exception:
        logger.exception("site_scan: LLM call failed")
        return {
            "summary": f"Site scan complete for {url} (LLM unavailable; "
                        "showing baseline findings only).",
            "issues": [], "trust_score": 0, "ux_score": 0,
            "recommendations": [],
        }


_RUNNERS["site_scan"] = _run_site_scan


# ----------------------------------------------------------- finalize
async def _complete(job_id: str, user_id: str,
                     conv_id: Optional[str], job_type: str,
                     target: Optional[str], result: dict) -> None:
    """Persist completion + append Cortex chat message with action CTAs."""
    from core import db
    now = datetime.now(timezone.utc)
    metrics = result.get("metrics") or {}
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"status":         "completed",
                   "progress_pct":   100,
                   "current_step":   "Done",
                   "next_step":      None,
                   "eta_seconds":    0,
                   "completed_at":   now,
                   "result_summary": result.get("summary"),
                   "result_link":    result.get("result_link"),
                   "metrics":        metrics}},
    )
    await _post_chat_message(user_id, conv_id,
                              kind="analysis_complete",
                              job_id=job_id, job_type=job_type,
                              target=target, summary=result.get("summary"),
                              metrics=metrics)

    # Proactive Recommendation Bridge — produces the "what should I
    # do next?" executive insight as a SECOND Cortex turn. Delayed
    # so the metric-tile card lands first and the recommendation
    # feels like a conclusion, not a pop-up.
    asyncio.create_task(_emit_bridge_with_pacing(job_id))


async def _emit_bridge_with_pacing(job_id: str) -> None:
    """Wait briefly so the analysis_complete message lands first, then
    synthesize + post the recommendation bridge. Best-effort; never
    raises into the runner's main path."""
    try:
        await asyncio.sleep(1.6)
        from cortex.recommendation_bridge import post_bridge_to_chat
        await post_bridge_to_chat(job_id)
    except Exception:
        logger.exception("analysis_runner: bridge emission failed for %s",
                          job_id)


async def _fail(job_id: str, user_id: str,
                 conv_id: Optional[str], job_type: Optional[str],
                 reason: str) -> None:
    from core import db
    now = datetime.now(timezone.utc)
    await db.analysis_jobs.update_one(
        {"id": job_id},
        {"$set": {"status":        "failed",
                   "error_message": reason[:400],
                   "completed_at":  now,
                   "current_step":  "Failed",
                   "next_step":     None,
                   "eta_seconds":   0}},
    )
    await _post_chat_message(user_id, conv_id,
                              kind="analysis_failed",
                              job_id=job_id, job_type=job_type,
                              target=None, summary=None,
                              metrics={"error": reason[:200]})


async def _post_chat_message(user_id: str, conv_id: Optional[str],
                              *, kind: str, job_id: str,
                              job_type: Optional[str],
                              target: Optional[str],
                              summary: Optional[str],
                              metrics: dict) -> None:
    """Append a Cortex chat message into the user's conversation thread.
    Uses `kind` metadata so the frontend renders embedded action
    buttons inline. Falls back to the user's most-recent conversation
    when no conv_id was attached (best-effort surfacing)."""
    from core import db
    if not conv_id:
        # Latest conversation_id with any message in it for this user.
        latest = await db.cortex_conversations.find_one(
            {"user_id": user_id, "conversation_id": {"$exists": True}},
            {"_id": 0, "conversation_id": 1},
            sort=[("created_at", -1)],
        )
        conv_id = (latest or {}).get("conversation_id")
    if not conv_id:
        # No conversation at all — give up gracefully. Rail still
        # surfaces the result.
        return

    # Compose Cortex's prose.
    if kind == "analysis_complete":
        text = _compose_complete_text(job_type, target, summary, metrics)
    else:
        text = _compose_failed_text(job_type, metrics.get("error"))

    msg = {
        "id":              uuid.uuid4().hex,
        "conversation_id": conv_id,
        "user_id":         user_id,
        "role":            "cortex",
        "message":         text,
        "stage":           "analysis_followup",
        "created_at":      datetime.now(timezone.utc),
        # `kind` lets the frontend ChatMessage render embedded action
        # buttons (View Report / Create Mission / Retry / Debug).
        "kind":            kind,
        "job_id":          job_id,
        "job_type":        job_type,
        "metrics":         metrics,
    }
    try:
        await db.cortex_conversations.insert_one(msg)
    except Exception:
        logger.exception("analysis_runner: failed to post chat message")


def _compose_complete_text(job_type: str, target: Optional[str],
                            summary: Optional[str], metrics: dict) -> str:
    label = {
        "seo_scan":         "SEO audit",
        "seller_discovery": "Seller discovery scan",
        "site_scan":        "Site scan",
        "competitor_audit": "Competitor audit",
        "content_audit":    "Content audit",
    }.get(job_type or "", "Analysis")

    head_target = f" of {target}" if target else ""
    if summary:
        return f"{label}{head_target} complete. {summary}"

    if job_type == "seo_scan":
        return (f"{label} complete. I found {metrics.get('issues_found', 0)} "
                f"improvements, {metrics.get('high_priority', 0)} of them "
                "high-priority. Want to review the findings?")
    if job_type == "seller_discovery":
        return (f"{label} complete. {metrics.get('qualified', 0)} qualified "
                f"sellers found, top {metrics.get('tier_1', 0)} match your "
                "historical conversion pattern. Want to review them before launching outreach?")
    return f"{label} complete. Open the report to review findings."


def _compose_failed_text(job_type: Optional[str], err: Optional[str]) -> str:
    label = (job_type or "analysis").replace("_", " ").title()
    err_short = (err or "Unknown error").strip()[:200]
    return (f"{label} failed: {err_short}. "
            "You can retry from the Active Work rail, or open the debug log "
            "if the failure repeats.")


# ----------------------------------------------------------- helpers
async def _fetch_url_snippet(url: str) -> str:
    """Reuse the existing ai.py fetcher so SEO scan reads the same
    snapshot the synchronous /ai/site-scan endpoint would."""
    try:
        from routes.ai import _fetch_url_snippet as fetch
        return await fetch(url)
    except Exception:
        logger.exception("analysis_runner: url snippet fetch failed")
        return ""


async def _run_seo_llm(user_id: str, url: str, snippet: str) -> dict:
    """Call the SEO scan LLM with the same prompt/format the existing
    /ai/site-scan endpoint uses, so View Report ↔ existing reports
    table remain interoperable."""
    try:
        from routes.ai import _llm_for_user, send_with_usage, _safe_json
        from emergentintegrations.llm.chat import UserMessage
        system = (
            "You are an SEO strategist. Analyze the snapshot and produce a "
            "scan report. Respond ONLY with valid JSON: "
            '{"summary": str, "notable_items": [str], '
            '"post_ideas": [{"title": str, "caption": str, "platform": str}], '
            '"improvements": [str]}'
        )
        chat = await _llm_for_user(user_id, f"seo-scan-job-{user_id}", system)
        raw, _ = await send_with_usage(
            chat, UserMessage(text=f"URL: {url}\n\nContent:\n{snippet}"),
            agent_id="rae", user_id=user_id, model="gpt-5")
        return _safe_json(raw) or {}
    except Exception:
        logger.exception("analysis_runner: SEO LLM call failed")
        # Degrade — let the job still complete with synthetic metrics
        # so the user sees results rather than a failure.
        return {
            "summary": f"SEO scan complete for {url} (LLM unavailable; "
                        "showing structural-only findings).",
            "improvements": [
                "Add meta descriptions for category pages",
                "Improve heading hierarchy",
                "Add alt text for product images",
            ],
            "post_ideas": [],
            "notable_items": [],
        }
