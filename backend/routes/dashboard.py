"""Dashboard summary endpoint (stats + recent activity for /dashboard overview)."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import db, api, STRICT_NORMALIZED_READS
from deps import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers
def _looks_failed(report: dict) -> bool:
    """Mirror of the frontend `isFailedReport` heuristic — gates the
    /reports/{id}/retry endpoint and filters bulk-retry. A report is
    failed when its summary starts with a failure phrase OR the findings
    body is empty."""
    body = report.get("report") or {}
    summary = str(body.get("summary") or "").strip().lower()
    if not summary:
        empty = not any(body.get(k) for k in (
            "improvements", "issues", "recommendations",
            "post_ideas", "notable_items"))
        if empty:
            return True
    if re.match(r"^(could not|scan could not|failed to|unable to|scan failed)",
                 summary):
        return True
    if "lacked an http" in summary or "lacked a valid" in summary \
            or "lacked http" in summary:
        return True
    return False


def _fix_url(url: Optional[str]) -> Optional[str]:
    """Heuristic URL repair: prepend https:// when a scheme is missing —
    the root cause of the most common production failure mode."""
    if not url:
        return None
    u = str(url).strip()
    if not u:
        return None
    if re.match(r"^[a-z][a-z0-9+\-.]*://", u, flags=re.IGNORECASE):
        return u
    return "https://" + u.lstrip("/")


async def _rerun_report(report: dict) -> dict:
    """Re-run the original scan with a repaired URL and return the new
    persisted report row. Supports seo_scan and site_scan; other types
    raise 400."""
    rtype = report.get("type")
    url = _fix_url(report.get("url") or report.get("target"))
    if not url:
        raise HTTPException(400, "Original report has no URL — nothing to retry.")
    user_id = report.get("user_id")
    if rtype in ("seo_scan", "seo_review"):
        from cortex.analysis_runner import _fetch_url_snippet, _run_seo_llm
        snippet = await _fetch_url_snippet(url)
        data = await _run_seo_llm(user_id, url, snippet)
        new_type = "seo_scan"
    elif rtype == "site_scan":
        from cortex.analysis_runner import _fetch_url_snippet, _run_site_llm
        snippet = await _fetch_url_snippet(url)
        data = await _run_site_llm(user_id, url, snippet)
        new_type = "site_scan"
    else:
        raise HTTPException(
            400, f"Retry is only supported for URL scans (got type={rtype!r}).")
    new_doc = {
        "id":          uuid.uuid4().hex,
        "user_id":     user_id,
        "type":        new_type,
        "url":         url,
        "report":      data,
        "retried_from": report.get("id"),
        "created_at":  datetime.now(timezone.utc),
    }
    await db.reports.insert_one(new_doc)
    new_doc.pop("_id", None)
    return new_doc


@api.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    """Headline counters for the dashboard overview. Phase 4 reads `posts`
    via the normalized `content_items` layer (one row per platform-agnostic
    intent — the agent-readable source-of-truth). In lenient mode we top
    up with any un-mirrored straggler posts so the number stays
    semantically equivalent to the pre-Phase-4 count during the
    migration window."""
    user = await get_current_user(request)

    posts_count = await db.content_items.count_documents({"user_id": user.user_id})
    if not STRICT_NORMALIZED_READS:
        unmirrored = await db.posts.count_documents({
            "user_id": user.user_id,
            "$or": [{"content_item_id": {"$exists": False}}, {"content_item_id": None}],
        })
        posts_count += unmirrored

    reports_count = await db.reports.count_documents({"user_id": user.user_id})
    channels_count = await db.channels.count_documents({"user_id": user.user_id})
    leads_count = await db.leads.count_documents({"user_id": user.user_id})
    return {
        "posts": posts_count,
        "reports": reports_count,
        "channels": channels_count,
        "leads": leads_count,
    }


@api.get("/reports")
async def list_reports(request: Request):
    user = await get_current_user(request)
    cursor = db.reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(50)


@api.post("/reports/{report_id}/retry")
async def retry_report(report_id: str, request: Request):
    """Retry a failed scan with a repaired URL. The old row is deleted
    once the new one is persisted so the Reports list stays clean."""
    user = await get_current_user(request)
    report = await db.reports.find_one(
        {"id": report_id, "user_id": user.user_id}, {"_id": 0})
    if not report:
        raise HTTPException(404, "Report not found.")
    if not _looks_failed(report):
        raise HTTPException(409,
            "Report doesn't look failed — only failed scans can be retried.")
    new_report = await _rerun_report(report)
    # Drop the original failed row so the list de-noises automatically.
    await db.reports.delete_one({"id": report_id, "user_id": user.user_id})
    return {"ok": True,
             "old_id": report_id,
             "new_id": new_report["id"],
             "report": new_report}


class BulkRetryReportsPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)


@api.post("/reports/bulk-retry")
async def bulk_retry_reports(payload: BulkRetryReportsPayload, request: Request):
    """Bulk-retry the given report ids. Only ids that actually look
    failed AND are URL scans get re-run; others are returned in the
    `skipped` list so the UI can surface why nothing happened.

    Retries run in parallel (capped to RETRY_CONCURRENCY=3 so we don't
    slam the LLM provider or blow past the 60s Cloudflare ingress
    timeout). With this cap, 6 retries finish in ~2×average instead of
    6× — well within the 60s window for any realistic batch."""
    user = await get_current_user(request)
    ids = [i for i in (payload.ids or []) if isinstance(i, str) and i.strip()]
    if not ids:
        return {"ok": True, "retried": 0, "skipped": 0, "items": []}
    # Heavy endpoint (LLM call per row). The 60s Cloudflare edge timeout
    # is the hard ceiling, and one URL+LLM round trip averages ~20-30s.
    # Cap = 5 keeps the 95p comfortably under 60s with concurrency=3.
    # Users with more failures simply press the button again — the list
    # has refreshed by then and only the still-failed rows remain.
    ids = ids[:5]

    cur = db.reports.find(
        {"id": {"$in": ids}, "user_id": user.user_id}, {"_id": 0})
    rows = [r async for r in cur]

    RETRY_CONCURRENCY = 3
    sem = asyncio.Semaphore(RETRY_CONCURRENCY)

    async def _one(row: dict) -> dict:
        if not _looks_failed(row):
            return {"old_id": row["id"], "ok": False,
                     "reason": "not_failed"}
        async with sem:
            try:
                new_report = await _rerun_report(row)
                await db.reports.delete_one(
                    {"id": row["id"], "user_id": user.user_id})
                return {"old_id": row["id"], "ok": True,
                         "new_id": new_report["id"]}
            except HTTPException as e:
                return {"old_id": row["id"], "ok": False,
                         "reason": str(e.detail)}
            except Exception as e:   # noqa: BLE001
                logger.exception("bulk_retry_reports: %s failed",
                                  row.get("id"))
                return {"old_id": row["id"], "ok": False,
                         "reason": f"{type(e).__name__}: {str(e)[:120]}"}

    items = await asyncio.gather(*(_one(r) for r in rows))
    retried = sum(1 for it in items if it.get("ok"))
    skipped = sum(1 for it in items if not it.get("ok"))
    return {"ok": True, "retried": retried, "skipped": skipped,
             "items": items}


@api.delete("/reports/{report_id}")
async def delete_report(report_id: str, request: Request):
    """Hard-delete a report owned by the current user. Used by the
    Reports page card close (X) button so users can dismiss noisy or
    failed scans from their list."""
    user = await get_current_user(request)
    result = await db.reports.delete_one(
        {"id": report_id, "user_id": user.user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Report not found.")
    return {"ok": True, "id": report_id}


class BulkDeleteReportsPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)


@api.post("/reports/bulk-delete")
async def bulk_delete_reports(payload: BulkDeleteReportsPayload, request: Request):
    """Bulk-delete reports owned by the current user. Always scoped to
    the caller's user_id so a malicious client can't wipe other users'
    rows even with a spoofed id list."""
    user = await get_current_user(request)
    ids = [i for i in (payload.ids or []) if isinstance(i, str) and i.strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    # Cap the batch so a runaway client can't issue a huge delete in one shot.
    ids = ids[:500]
    result = await db.reports.delete_many(
        {"id": {"$in": ids}, "user_id": user.user_id})
    return {"ok": True, "deleted": int(result.deleted_count), "requested": len(ids)}
