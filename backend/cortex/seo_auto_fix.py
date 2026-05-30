"""Cortex SEO Auto-Fix drafter — Option-A semantics.

When the user clicks "Optimize Automatically" on a completed SEO scan,
we DO NOT push live changes to their site (no CMS connector yet —
WordPress Connect is P3). Instead Cortex:

  1. Reads the scan report's improvements list.
  2. Drafts concrete rewrites (titles, meta descriptions, heading
     hierarchy fixes, alt-text suggestions) via Claude tool-call.
  3. Persists each rewrite as a `seo_change_records` row tagged
     status="ready", source_job_id, source_report_id, mission_id.
  4. Updates the parent seo_auto_fix mission's progress as drafts
     accumulate.

The user gets a single Accept-All batch to approve once. When the
WordPress connector lands, these `ready` records become the input
queue for the deploy step. Until then they're exportable JSON the
user can paste into their CMS manually.

Runs synchronously inside the optimize endpoint (bounded — one Claude
call covers all findings at once, <20s end-to-end). For very large
reports we cap to top-15 findings.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Cap drafting volume to keep latency / cost bounded.
_MAX_FINDINGS_PER_RUN = 15


async def draft_changes_for_job(*, job_id: str, mission_id: str,
                                  user_id: str) -> dict:
    """Read the SEO scan's report, draft change records, persist.
    Returns a summary the caller can include in its response.

    Returns:
      {
        "drafted":   int,
        "ready":     int,
        "report_id": Optional[str],
        "error":     Optional[str],
      }
    """
    from core import db
    job = await db.analysis_jobs.find_one(
        {"id": job_id, "user_id": user_id}, {"_id": 0})
    if not job:
        return {"drafted": 0, "ready": 0, "report_id": None,
                "error": "job_not_found"}
    if job.get("job_type") != "seo_scan":
        return {"drafted": 0, "ready": 0, "report_id": None,
                "error": "wrong_job_type"}

    # Find the report this job produced. `result_link` carries an
    # `?id=` we can use; otherwise look up the most recent SEO report
    # for the same URL.
    rid = _extract_report_id(job.get("result_link") or "")
    report = None
    if rid:
        report = await db.reports.find_one(
            {"id": rid, "user_id": user_id}, {"_id": 0})
    if not report:
        report = await db.reports.find_one(
            {"user_id": user_id, "type": "seo_scan",
             "url": job.get("target")},
            {"_id": 0}, sort=[("created_at", -1)],
        )
    if not report:
        return {"drafted": 0, "ready": 0, "report_id": None,
                "error": "report_not_found"}

    findings = ((report.get("report") or {}).get("improvements") or [])[:_MAX_FINDINGS_PER_RUN]
    if not findings:
        return {"drafted": 0, "ready": 0, "report_id": report.get("id"),
                "error": "no_findings"}

    # Draft via Claude with a tool call so we get structured output.
    drafts = await _llm_draft(user_id=user_id, url=job.get("target"),
                                findings=findings)
    if not drafts:
        return {"drafted": 0, "ready": 0, "report_id": report.get("id"),
                "error": "draft_failed"}

    # Persist each draft as a ready-to-apply change record.
    now = datetime.now(timezone.utc)
    rows = []
    for d in drafts:
        rows.append({
            "id":               uuid.uuid4().hex,
            "user_id":          user_id,
            "mission_id":       mission_id,
            "source_job_id":    job_id,
            "source_report_id": report.get("id"),
            "url":              job.get("target"),
            "category":         d.get("category", "general"),
            "selector":         d.get("selector"),  # XPath/CSS hint when applicable
            "current":          d.get("current", ""),
            "proposed":         d.get("proposed", ""),
            "rationale":        d.get("rationale", ""),
            "impact":           d.get("impact", "medium"),   # low|medium|high
            "status":           "ready",
            "created_at":       now,
        })
    if rows:
        await db.seo_change_records.insert_many(rows)

    # Stamp the mission with progress so the rail/missions UI shows
    # something useful (current=drafted, target=total findings).
    try:
        await db.missions.update_one(
            {"id": mission_id, "user_id": user_id},
            {"$set": {"current":       len(rows),
                       "target":        len(findings),
                       "progress_pct":  int(round(100 * len(rows) / max(len(findings), 1))),
                       "status":        "ready_for_review",
                       "ready_count":   len(rows),
                       "drafted_at":    now}},
        )
    except Exception:
        logger.exception("draft_changes_for_job: mission update failed")

    return {
        "drafted":   len(rows),
        "ready":     len(rows),
        "report_id": report.get("id"),
        "error":     None,
    }


# ------------------------------------------------------------- LLM
async def _llm_draft(*, user_id: str, url: str, findings: list) -> list[dict]:
    """One Claude tool-call to draft all change records. Bounded so a
    20-finding report still completes in ~15-20s."""
    try:
        from cortex.llm_provider import cortex_tool_call
        system = (
            "You are a senior SEO engineer. For each improvement listed, draft a "
            "concrete, copy-pasteable change the user (or a downstream CMS connector) "
            "could apply. Be specific — never vague. Each change must include: "
            "category (title|meta_description|heading|alt_text|schema|other), "
            "current (best-guess of the existing value or '—' if unknown), "
            "proposed (the exact new value), rationale (1-line why), impact (low|medium|high)."
        )
        user_text = (
            f"URL: {url}\n\nImprovements to address:\n"
            + "\n".join(f"- {f}" for f in findings)
            + "\n\nProduce one draft per improvement."
        )
        tool = {
            "name":        "draft_seo_changes",
            "description": "Produce a list of concrete, copy-pasteable SEO fixes ready for review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "changes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category":  {"type": "string",
                                                "enum": ["title", "meta_description",
                                                          "heading", "alt_text",
                                                          "schema", "other"]},
                                "selector":  {"type": ["string", "null"]},
                                "current":   {"type": "string"},
                                "proposed":  {"type": "string"},
                                "rationale": {"type": "string"},
                                "impact":    {"type": "string",
                                                "enum": ["low", "medium", "high"]},
                            },
                            "required": ["category", "proposed", "rationale", "impact"],
                        },
                    },
                },
                "required": ["changes"],
            },
        }
        args, _label, _mode = await cortex_tool_call(
            system=system, user_text=user_text, tool=tool,
            session_id=f"cortex-autofix-{user_id}", user_id=user_id,
            prefer="claude", required=["changes"],
        )
        if not args:
            return []
        changes = args.get("changes") or []
        # Sanitize: cap length, drop oversized rows so a misbehaving
        # model can't bloat the collection.
        out = []
        for c in changes[:_MAX_FINDINGS_PER_RUN]:
            if not isinstance(c, dict):
                continue
            if len(str(c.get("proposed") or "")) < 3:
                continue
            out.append({
                "category":  str(c.get("category") or "other")[:32],
                "selector":  (str(c.get("selector")) if c.get("selector") else None),
                "current":   str(c.get("current") or "")[:600],
                "proposed":  str(c.get("proposed") or "")[:600],
                "rationale": str(c.get("rationale") or "")[:400],
                "impact":    str(c.get("impact") or "medium")[:16],
            })
        return out
    except Exception:
        logger.exception("seo_auto_fix._llm_draft failed")
        return []


def _extract_report_id(link: str) -> str:
    """Pull `?id=<hex>` from a result_link."""
    m = re.search(r"[?&]id=([a-f0-9]+)", link or "", re.IGNORECASE)
    return m.group(1) if m else ""
