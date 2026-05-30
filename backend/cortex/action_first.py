"""Cortex Action-First router.

Senior consultants don't conduct intake interviews — they look at the
data first and surface insight. This module short-circuits the
discovery-first conversation funnel when the user asks for something
concrete that ALREADY EXISTS in the system (leads / reports / scan
results / opportunities / candidates), or asks Cortex to DO something
concrete (scan a URL / run an audit / analyze a domain).

Two responsibilities:

1. `match_action_intent(message) → ActionIntent | None`
   Deterministic regex pre-classifier. Catches `show me the leads`,
   `list opportunities`, `scan craftersmarket.org`, `audit my SEO`,
   `analyze cortexviral.com`, etc. Returns None when the message is
   genuinely conversational (the LLM stage classifier handles those).

2. `execute_action(intent, user_id, conv_id) → dict`
   For `show_*` intents: pulls a real summary from the appropriate
   collection and renders Cortex's consultative response (data + 1-line
   assessment + a next-step CTA).
   For `run_scan_*` intents: enqueues a real `analysis_jobs` row and
   returns an acknowledgement that references the job_id (visible on
   the Active Work rail).

CRITICAL: Cortex must NEVER claim to be running a scan without an
analysis_jobs row backing it (see iter23 mandate). This module is the
ONLY path that creates jobs from chat — it always inserts the row
BEFORE building the response message.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------- intent matchers
# These are deliberately specific to avoid false positives on
# conversational messages that happen to contain these verbs.

# "show me the leads", "list leads", "export the leads", "view leads"
_SHOW_LEADS = re.compile(
    r"\b(?:show|list|view|see|open|export|display)\s+(?:me\s+(?:the\s+)?|the\s+|my\s+)?"
    r"(?:qualified\s+)?(leads|sellers|candidates|prospects)\b",
    re.IGNORECASE,
)

# "show me the report", "view scan results", "show the SEO report"
_SHOW_REPORTS = re.compile(
    r"\b(?:show|list|view|see|open|export|display)\s+(?:me\s+(?:the\s+)?|the\s+|my\s+)?"
    r"(?:seo\s+)?(reports?|scan\s+results?|audit\s+results?|seo\s+results?)\b",
    re.IGNORECASE,
)

# "show opportunities", "view opportunities", "show me the growth opportunities"
_SHOW_OPPS = re.compile(
    r"\b(?:show|list|view|see|open|display)\s+(?:me\s+(?:the\s+)?|the\s+|my\s+)?"
    r"(?:growth\s+|new\s+)?(opportunit\w+)\b",
    re.IGNORECASE,
)

# "show missions", "list active missions"
_SHOW_MISSIONS = re.compile(
    r"\b(?:show|list|view|see|open|display)\s+(?:me\s+(?:the\s+)?|the\s+|my\s+)?"
    r"(?:active\s+|running\s+)?(missions?)\b",
    re.IGNORECASE,
)

# "scan craftersmarket.org", "audit my site", "review cortexviral.com",
# "analyze example.com", "check my SEO on https://...", "do an SEO audit of..."
_RUN_SCAN = re.compile(
    r"\b(?:scan|audit|analyze|review|check|do\s+(?:an?\s+)?(?:seo\s+)?(?:scan|audit)\s+(?:of|on)?)"
    r"\s+(?:my\s+(?:site|website|seo)|"
    r"(?:https?://)?(?:www\.)?([a-z0-9][-a-z0-9.]*\.[a-z]{2,}(?:/\S*)?))",
    re.IGNORECASE,
)

# URL detector — fallback after a scan/audit verb when the URL is
# separated from the verb by other words.
_URL = re.compile(
    r"\b((?:https?://)?(?:www\.)?[a-z0-9][-a-z0-9.]*\.[a-z]{2,}(?:/\S*)?)",
    re.IGNORECASE,
)

# Generic "scan" verb without context — needs a URL nearby to be valid.
_SCAN_VERB = re.compile(
    r"\b(scan|audit|analyze|review|check|crawl)\b",
    re.IGNORECASE,
)


def match_action_intent(message: str) -> Optional[dict]:
    """Return an action intent dict iff the message is unambiguously
    a concrete data-pull or scan request. None otherwise (caller falls
    through to the LLM stage classifier)."""
    text = (message or "").strip()
    if not text or len(text) > 500:   # don't run on essays
        return None

    # Order matters: more specific patterns first to avoid leads-vs-
    # opportunities collisions on words like "show".
    if _SHOW_LEADS.search(text):
        return {"kind": "show_leads"}
    if _SHOW_REPORTS.search(text):
        return {"kind": "show_reports"}
    if _SHOW_OPPS.search(text):
        return {"kind": "show_opportunities"}
    if _SHOW_MISSIONS.search(text):
        return {"kind": "show_missions"}

    # Scan / audit / analyze intents — must have a URL or "my site/SEO".
    m = _RUN_SCAN.search(text)
    if m:
        url = (m.group(1) or "").strip()
        if not url and re.search(r"\bmy\s+(site|website|seo)\b", text, re.IGNORECASE):
            # User said "scan my site" without a URL — we'll prompt
            # for it in the response (no job created yet).
            return {"kind": "run_scan", "url": None, "needs_url": True}
        if url:
            return {"kind": "run_scan", "url": _normalize_url(url)}

    # Loose pattern: "scan" verb + URL anywhere in message.
    if _SCAN_VERB.search(text):
        urls = [u for u in _URL.findall(text) if _looks_like_domain(u)]
        if urls:
            return {"kind": "run_scan", "url": _normalize_url(urls[0])}

    return None


def _looks_like_domain(s: str) -> bool:
    """Reject false-positive URL matches that aren't real domains
    (e.g. "i.e." or version strings)."""
    s = (s or "").strip().lower()
    if not s:
        return False
    if s in ("i.e.", "e.g.", "etc.", "vs.", "n.b."):
        return False
    if re.match(r"^\d+\.\d+", s):    # version like 1.2.3
        return False
    return "." in s and not s.startswith(".") and not s.endswith(".")


def _normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s
    return s[:500]


# ----------------------------------------------------- action executor
async def execute_action(intent: dict, *, user_id: str,
                          conversation_id: Optional[str]) -> dict:
    """Execute an Action-First intent. Returns a dict shaped like the
    stage_data the rest of the chat pipeline expects, so existing
    persistence + response code paths work unchanged.

    Output shape:
      {
        "stage":  "action",                     # new bypass stage
        "ack":    "<consultative response>",
        "data":   {<kind-specific summary>},    # rendered as a card
        "action_kind": "show_leads"|...,
        ...standard stage_data zeroes
      }
    """
    kind = intent.get("kind")

    if kind == "show_leads":
        return await _show_leads(user_id)
    if kind == "show_reports":
        return await _show_reports(user_id)
    if kind == "show_opportunities":
        return await _show_opportunities(user_id)
    if kind == "show_missions":
        return await _show_missions(user_id)
    if kind == "run_scan":
        return await _run_scan(user_id, conversation_id,
                                url=intent.get("url"),
                                needs_url=intent.get("needs_url"))

    return _empty_stage_data(
        "I didn't understand that action — could you rephrase?")


# ------------------------------------------------- data summaries
async def _show_leads(user_id: str) -> dict:
    from core import db
    cur = db.seller_leads.find({"user_id": user_id}, {"_id": 0})
    leads = [r async for r in cur.limit(500)]
    if not leads:
        return _empty_stage_data(
            "You don't have any leads yet. Want me to launch a scout mission "
            "to find sellers in a specific niche?",
            data={"kind": "leads_summary", "total": 0, "categories": [],
                   "quality": {"high": 0, "review": 0, "low": 0}})

    # Group by niche for the consultative summary.
    from collections import Counter
    niches = Counter((ld.get("niche") or "Other").strip() or "Other" for ld in leads)
    top_cats = [{"name": k, "count": v} for k, v in niches.most_common(5)]

    # Quality buckets based on score / qualification status.
    high = sum(1 for ld in leads if (ld.get("score") or 0) >= 70 or ld.get("status") == "qualified")
    low  = sum(1 for ld in leads if (ld.get("score") or 0) < 35)
    rev  = max(0, len(leads) - high - low)

    summary = (
        f"Here are the {len(leads)} leads.\n\n"
        + ("Top categories: " + ", ".join(f"{c['count']} {c['name']}" for c in top_cats[:4]) + ".\n\n"
            if top_cats else "")
        + "Initial assessment:\n"
        f"• {high} look highly relevant\n"
        f"• {rev} may need manual review\n"
        f"• {low} appear lower quality\n\n"
        "Want me to score and rank them, or filter to the top tier?"
    )
    return _stage_data(summary, action_kind="show_leads", data={
        "kind":  "leads_summary",
        "total": len(leads),
        "categories": top_cats,
        "quality":    {"high": high, "review": rev, "low": low},
        "deep_link":  "/dashboard/seller-os/leads",
    })


async def _show_reports(user_id: str) -> dict:
    from core import db
    cur = db.reports.find({"user_id": user_id}, {"_id": 0}) \
                     .sort("created_at", -1).limit(20)
    rows = [r async for r in cur]
    if not rows:
        return _empty_stage_data(
            "No reports yet. Want me to run an SEO scan or competitor "
            "audit? Just send the URL.",
            data={"kind": "reports_summary", "total": 0, "recent": []})

    by_type: dict[str, int] = {}
    for r in rows:
        t = r.get("type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
    recent = [{
        "id":         r.get("id"),
        "type":       r.get("type"),
        "url":        r.get("url"),
        "created_at": _iso(r.get("created_at")),
    } for r in rows[:5]]
    summary = (
        f"You have {len(rows)} reports on file. "
        + ("Mix: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in by_type.items()) + ". "
            if by_type else "")
        + f"Most recent: {recent[0]['type']} on {recent[0]['url']} "
        f"({recent[0]['created_at'] or 'just now'}).\n\n"
        "Open one or run a fresh scan?"
    )
    return _stage_data(summary, action_kind="show_reports", data={
        "kind":   "reports_summary",
        "total":  len(rows),
        "by_type": by_type,
        "recent": recent,
        "deep_link": "/dashboard/reports",
    })


async def _show_opportunities(user_id: str) -> dict:
    """Reuse the existing briefing engine to surface top opportunities."""
    try:
        from routes.cortex_recommendations import build_briefing
        brief = await build_briefing(user_id, max_opportunities=10)
        opps = brief.get("opportunities", [])
    except Exception:
        logger.exception("show_opportunities: build_briefing failed")
        opps = []
    if not opps:
        return _empty_stage_data(
            "No active opportunities right now. Cortex's monitoring loop "
            "will surface them as they emerge — usually 1-3 per day.",
            data={"kind": "opportunities_summary", "total": 0, "top": []})

    top = [{
        "title":    o.get("title"),
        "type":     o.get("type"),
        "urgency":  o.get("urgency") or "monitor",
        "subtitle": o.get("subtitle"),
    } for o in opps[:5]]

    lines = "\n".join(f"• {o['title']}" for o in top)
    summary = (
        f"{len(opps)} opportunities surfaced. Top picks:\n\n{lines}\n\n"
        "Want me to dive into one, or shall I score them by impact-to-effort?"
    )
    return _stage_data(summary, action_kind="show_opportunities", data={
        "kind":  "opportunities_summary",
        "total": len(opps),
        "top":   top,
        "deep_link": "/dashboard",
    })


async def _show_missions(user_id: str) -> dict:
    from core import db
    cur = db.missions.find(
        {"user_id": user_id, "status": {"$in": ["running", "paused"]}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10)
    rows = [r async for r in cur]
    if not rows:
        return _empty_stage_data(
            "No active missions. Want me to draft one? Tell me the outcome "
            "you want, like 'recruit 50 woodworking sellers'.",
            data={"kind": "missions_summary", "total": 0, "missions": []})

    items = [{
        "id":             r.get("id"),
        "title":          r.get("title"),
        "status":         r.get("status"),
        "mission_type":   r.get("mission_type"),
        "autonomy_level": r.get("autonomy_level"),
    } for r in rows]
    summary = (
        f"You have {len(rows)} active missions:\n\n"
        + "\n".join(f"• {m['title']} (L{m.get('autonomy_level', 2)})" for m in items[:6])
        + "\n\nOpen one for details, or want me to surface what's blocked?"
    )
    return _stage_data(summary, action_kind="show_missions", data={
        "kind":  "missions_summary",
        "total": len(rows),
        "missions": items,
        "deep_link": "/dashboard/missions",
    })


# ------------------------------------------------ run-scan executor
async def _run_scan(user_id: str, conv_id: Optional[str],
                     *, url: Optional[str], needs_url: bool) -> dict:
    """Enqueue an SEO scan analysis_jobs row, then return Cortex's
    acknowledgement that references the job_id."""
    if needs_url and not url:
        return _stage_data(
            "Got it — I'll run an SEO scan. Which URL? "
            "(e.g., `cortexviral.com` or `https://example.com/category/x`)",
            action_kind="run_scan_needs_url",
            data={"kind": "needs_url"})

    from core import db
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    doc = {
        "id":               job_id,
        "user_id":          user_id,
        "conversation_id":  conv_id,
        "job_type":         "seo_scan",
        "target":           url,
        "params":           {},
        "status":           "queued",
        "progress_pct":     0,
        "current_step":     "Waiting in queue",
        "next_step":        "Crawling site structure",
        "eta_seconds":      45,
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

    # Fire the runner.
    from cortex.analysis_runner import run_analysis_job
    asyncio.create_task(run_analysis_job(job_id))

    summary = (
        f"Starting SEO scan of {url}. "
        f"Job #{job_id[:8]} — track progress on the Active Work rail (right side). "
        "I'll post the findings here when it completes (~45 seconds)."
    )
    return _stage_data(summary, action_kind="run_scan_started",
                        data={"kind": "scan_started",
                               "job_id": job_id, "url": url})


# --------------------------------------------------------- helpers
def _stage_data(ack: str, *, action_kind: str, data: dict) -> dict:
    """Wrap into the stage_data shape the chat pipeline expects.
    `stage='action'` is the new bypass marker that downstream code
    treats as terminal (no plan card, no further classification)."""
    return {
        "stage":                    "action",
        "discovery_complete":       True,
        "analysis_complete":        True,
        "recommendation_accepted":  False,
        "explicit_execution_request": False,
        "ack":                      ack,
        "clarifying_questions":     [],
        "answer_shortcuts":         [],
        "findings":                 [],
        "recommendation_summary":   "",
        "alternatives":             [],
        "intent":                   None,
        "params":                   {},
        "action_kind":              action_kind,
        "action_data":              data,
    }


def _empty_stage_data(ack: str, *, data: dict | None = None) -> dict:
    out = _stage_data(ack, action_kind="empty", data=data or {})
    return out


def _iso(v) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)
