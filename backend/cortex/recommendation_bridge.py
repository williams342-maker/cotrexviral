"""Cortex Recommendation Bridge — the missing layer between analysis
and action.

Every completed analysis job (SEO scan, site scan, competitor audit,
seller discovery, content audit) flows through this module to produce
a STRUCTURED executive recommendation:

  • finding         — one-line headline of what stands out
  • root_cause      — *why* it's happening (1–2 sentences)
  • recommendation  — *what to do about it* (action-oriented)
  • expected_impact — projected outcome ("+15-25% organic visibility")
  • confidence      — 0–100 score (how sure Cortex is)
  • reasoning       — conversational paragraph Cortex says before the
                      card renders ("Mission Timing" rule)
  • mission_intent  — proposed mission_type for one-click creation
  • mission_params  — pre-filled mission params (target, niche, etc.)

The bridge is the single source of truth that downstream features
consume:
  • Optimize Automatically  → reads mission_intent + mission_params
  • Mission Suggestions     → lists bridges with confidence ≥ X
  • Autonomous Optimization → OODA loop generates bridges from
                              detected bottlenecks
  • Executive Insights      → cross-bridge trend visualization

`build_bridge_from_job(job_id)` is idempotent — the second call for the
same job returns the existing row instead of regenerating.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# Per-job-type prompt templates. The LLM reads the report payload and
# produces a structured recommendation tailored to the analysis kind.
_PROMPTS = {
    "seo_scan": (
        "You are Cortex, an executive growth consultant. An SEO scan just "
        "completed. Read the report and produce ONE high-impact "
        "recommendation that answers 'What should the operator do next?'\n\n"
        "Focus on category/intent gaps, indexable content opportunities, or "
        "structural fixes that move organic visibility — NOT generic 'add "
        "alt text' boilerplate."
    ),
    "site_scan": (
        "You are Cortex, an executive growth consultant. A site scan just "
        "completed (UX + brand + trust + conversion). Read the report and "
        "produce ONE high-impact recommendation that moves conversion or "
        "positioning.\n\n"
        "Examples: 'Founding Maker Program' for unclear seller value-prop, "
        "'Add social proof above fold' for trust deficit. Focus on the "
        "single biggest unlock."
    ),
    "competitor_audit": (
        "You are Cortex, an executive growth consultant. A competitor audit "
        "just completed. Read the findings and produce ONE recommendation "
        "that targets the largest competitor gap or positioning advantage."
    ),
    "content_audit": (
        "You are Cortex, an executive growth consultant. A content audit "
        "just completed. Produce ONE high-impact recommendation — usually "
        "either a refresh-existing strategy or a net-new content bet."
    ),
    "seller_discovery": (
        "You are Cortex, an executive growth consultant. A seller discovery "
        "scan just completed. Read the qualified sellers + tier distribution "
        "and produce ONE recommendation for converting them into active "
        "sellers — focusing on outreach sequencing or onboarding incentives."
    ),
}


# Map job_type → recommended mission_intent (used as default if the LLM
# doesn't propose one). Keeps the Create Mission CTA always clickable.
_DEFAULT_INTENT = {
    "seo_scan":         "improve_conversions",
    "site_scan":        "improve_conversions",
    "competitor_audit": "analyze_competitors",
    "content_audit":    "generate_content_plan",
    "seller_discovery": "launch_seller_mission",
}


async def build_bridge_from_job(job_id: str, *, pushback: Optional[str] = None) -> Optional[dict]:
    """Idempotent — returns existing bridge if one is already on file
    for this job, otherwise generates a new one via the LLM and
    persists it. Returns None when the job doesn't exist or isn't
    completed.

    When `pushback` is supplied, the existing bridge is bypassed and a
    fresh one is synthesized that explicitly factors in the user's
    feedback. The previous bridge row is replaced (not appended) so
    the conversation surface always reflects the latest take.
    """
    from core import db
    j = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not j:
        return None
    if j.get("status") not in ("completed", "reviewed", "mission_created"):
        return None
    # Idempotency: return existing bridge if present (only when no
    # pushback — pushback forces re-synthesis).
    if not (pushback and pushback.strip()):
        existing = await db.cortex_recommendation_bridges.find_one(
            {"job_id": job_id}, {"_id": 0})
        if existing:
            return existing

    bridge = await _synthesize_bridge(j, pushback=pushback)
    bridge["id"] = uuid.uuid4().hex
    bridge["job_id"] = job_id
    bridge["user_id"] = j.get("user_id")
    bridge["job_type"] = j.get("job_type")
    bridge["target"] = j.get("target")
    bridge["created_at"] = datetime.now(timezone.utc)
    if pushback and pushback.strip():
        bridge["pushback"] = pushback.strip()[:800]
    try:
        # On pushback, replace any prior row so a single bridge always
        # reflects Cortex's CURRENT take.
        if pushback and pushback.strip():
            await db.cortex_recommendation_bridges.delete_many(
                {"job_id": job_id})
        await db.cortex_recommendation_bridges.insert_one(bridge)
    except Exception:
        logger.exception("recommendation_bridge: persist failed for job %s",
                          job_id)
    # Strip Mongo's _id if it survived the insert.
    bridge.pop("_id", None)
    return bridge


async def _synthesize_bridge(job: dict, *, pushback: Optional[str] = None) -> dict:
    """Call the LLM to produce a strict-JSON bridge. Falls back to a
    deterministic synthesizer (no LLM) so the bridge always renders
    even when the LLM is offline.

    When `pushback` is provided (user disagreed with the previous
    recommendation), it's injected into the prompt as direct user
    feedback so the LLM re-thinks rather than restating its first take.
    """
    job_type = job.get("job_type") or "site_scan"
    target = job.get("target") or "your asset"
    metrics = job.get("metrics") or {}

    # Pull the full report (if any) for context.
    report = await _load_report(job)
    report_excerpt = _format_report_for_prompt(report)

    sys_prompt = _PROMPTS.get(job_type) or _PROMPTS["site_scan"]

    pushback_block = ""
    if pushback and pushback.strip():
        pushback_block = (
            "\n\n=== USER PUSHBACK ON YOUR PREVIOUS RECOMMENDATION ===\n"
            f"{pushback.strip()[:800]}\n"
            "\nRe-think the recommendation in light of this feedback. "
            "Do NOT restate your earlier take — adjust the approach, "
            "address the user's concern explicitly in `reasoning`, and "
            "produce a genuinely different recommendation that respects "
            "their input."
        )

    user_text = (
        f"Analysis job type: {job_type}\n"
        f"Target: {target}\n"
        f"Metrics: {json.dumps(metrics, default=str)[:600]}\n\n"
        f"Report excerpt:\n{report_excerpt[:3500]}"
        f"{pushback_block}"
    )

    # Native tool-calling — forces the LLM to emit exactly the bridge
    # shape via the `synthesize_recommendation` tool. Tool-calling has
    # a 95%+ success rate over the last 24h (promotion_ready=true).
    bridge_tool = {
        "name": "synthesize_recommendation",
        "description": (
            "Produce ONE high-impact executive recommendation from the "
            "analysis report. Every field is required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "finding":         {"type": "string",
                                     "description": "One-sentence headline of what stands out."},
                "root_cause":      {"type": "string",
                                     "description": "1-2 sentence explanation of WHY this is happening."},
                "recommendation":  {"type": "string",
                                     "description": "Single action-oriented sentence."},
                "expected_impact": {"type": "string",
                                     "description": "Projected outcome (e.g. '+15-25% organic visibility')."},
                "confidence":      {"type": "integer", "minimum": 0, "maximum": 100,
                                     "description": "Cortex's confidence in this recommendation, 0-100."},
                "reasoning":       {"type": "string",
                                     "description": "2-3 sentence consultative paragraph Cortex says BEFORE the card. The 'explain THEN recommend' bridge text."},
                "mission_intent":  {"type": "string",
                                     "enum": ["launch_seller_mission", "run_bulk_outreach",
                                               "launch_retention_workflow", "generate_content_plan",
                                               "launch_ads_campaign", "analyze_competitors",
                                               "find_opportunities", "improve_conversions"]},
                "mission_params":  {"type": "object",
                                     "description": "Pre-filled mission parameters (target, niche, etc.). Empty object if none."},
            },
            "required": ["finding", "root_cause", "recommendation",
                          "expected_impact", "confidence", "reasoning",
                          "mission_intent"],
        },
    }

    try:
        from cortex.llm_provider import cortex_tool_call
        from core import EMERGENT_LLM_KEY
        if not EMERGENT_LLM_KEY:
            raise RuntimeError("no LLM key")
        args, label, mode = await cortex_tool_call(
            system=sys_prompt,
            user_text=user_text,
            tool=bridge_tool,
            session_id=f"recbridge-{job.get('id')}",
            user_id=job.get("user_id") or "anonymous",
            prefer="claude",
            required=["finding", "recommendation", "confidence", "reasoning",
                       "mission_intent"],
        )
        if args:
            normalized = _normalize_bridge(args, job_type)
            normalized["source"] = f"llm:{label}:{mode}"
            return normalized
        logger.warning("recommendation_bridge: cortex_tool_call returned None "
                        "for job %s — falling back to heuristic.",
                        job.get("id"))
    except Exception:
        logger.exception("recommendation_bridge: tool-call failed for job %s",
                          job.get("id"))

    # Heuristic fallback — keeps the bridge always renderable.
    return _heuristic_bridge(job, report)


# ----------------------------------------------------------- helpers
async def _load_report(job: dict) -> dict:
    """If the job persisted a `reports` row, hydrate it so the LLM can
    read the actual findings (not just the metrics)."""
    try:
        from core import db
        # SEO + site scan runners persist a report and store report_id
        # implicitly via the result_link. We re-fetch by url+user+type.
        if not job.get("target"):
            return {}
        r = await db.reports.find_one({
            "user_id": job.get("user_id"),
            "type":    job.get("job_type"),
            "url":     job.get("target"),
        }, {"_id": 0}, sort=[("created_at", -1)])
        if not r:
            return {}
        return r.get("report") or {}
    except Exception:
        logger.exception("recommendation_bridge: report load failed")
        return {}


def _format_report_for_prompt(report: dict) -> str:
    """Render a report dict into a compact prompt-friendly string."""
    if not report:
        return "(no report payload — synthesize from job type alone)"
    parts = []
    if report.get("summary"):
        parts.append(f"Summary: {report['summary']}")
    for k in ("improvements", "issues", "notable_items", "recommendations",
              "post_ideas", "gaps", "findings"):
        v = report.get(k)
        if not v:
            continue
        if isinstance(v, list):
            sample = []
            for item in v[:8]:
                if isinstance(item, str):
                    sample.append(item)
                elif isinstance(item, dict):
                    sample.append(item.get("title")
                                  or item.get("description")
                                  or json.dumps(item, default=str)[:200])
            if sample:
                parts.append(f"{k}:\n  - " + "\n  - ".join(sample))
    return "\n\n".join(parts) or "(empty report)"


def _parse_strict_json(text: str) -> Optional[dict]:
    """Robust JSON extraction — handles code fences and accidental
    prose. Returns None if parsing fails."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip ```json ... ``` fences.
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Try to extract the first JSON object substring.
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _normalize_bridge(data: dict, job_type: str) -> dict:
    """Clamp fields + apply sensible defaults."""
    conf = data.get("confidence")
    try:
        conf = int(conf)
    except Exception:
        conf = 70
    conf = max(0, min(100, conf))

    intent = data.get("mission_intent")
    from routes.cortex_recommendations import INTENT_TYPES
    if intent not in INTENT_TYPES:
        intent = _DEFAULT_INTENT.get(job_type, "find_opportunities")

    params = data.get("mission_params")
    if not isinstance(params, dict):
        params = {}

    return {
        "finding":         _trim(data.get("finding"), 220),
        "root_cause":      _trim(data.get("root_cause"), 400),
        "recommendation":  _trim(data.get("recommendation"), 220),
        "expected_impact": _trim(data.get("expected_impact"), 160),
        "confidence":      conf,
        "reasoning":       _trim(data.get("reasoning"), 700),
        "mission_intent":  intent,
        "mission_params":  params,
        "source":          "llm",
    }


def _heuristic_bridge(job: dict, report: dict) -> dict:
    """LLM-offline fallback. Produces a non-empty bridge so the chat
    UX still has something useful to render."""
    job_type = job.get("job_type") or "site_scan"
    target = job.get("target") or "your site"
    metrics = job.get("metrics") or {}

    if job_type == "seo_scan":
        issues = metrics.get("issues_found", 0)
        high = metrics.get("high_priority", 0)
        finding = (f"{high} high-priority SEO issues detected"
                    if high else f"{issues} SEO improvements detected"
                    if issues else "Baseline SEO audit complete")
        return {
            "finding": finding,
            "root_cause": "The site's discoverability is constrained by "
                          "missing on-page signals search engines use to "
                          "rank intent-driven queries.",
            "recommendation": "Prioritize the top-3 high-impact fixes "
                              "(meta, headings, internal linking) before "
                              "broader rewrites.",
            "expected_impact": "+10-20% organic visibility within 4-6 weeks",
            "confidence": 75,
            "reasoning": (f"I scanned {target} and surfaced {issues} "
                          f"improvements, {high} high-priority. Fixing "
                          "the high-priority bucket first compounds — "
                          "those signals influence how the rest of the "
                          "site is crawled and ranked."),
            "mission_intent": "improve_conversions",
            "mission_params": {"focus": "seo"},
            "source": "heuristic",
        }
    if job_type == "seller_discovery":
        qualified = metrics.get("qualified", 0)
        tier_1 = metrics.get("tier_1", 0)
        return {
            "finding": f"{qualified} qualified sellers found — {tier_1} match historical conversion patterns",
            "root_cause": "Sellers that match your existing conversion "
                          "pattern convert faster and onboard with less "
                          "support overhead.",
            "recommendation": f"Launch tiered outreach starting with the "
                              f"top {tier_1} tier-1 matches; sequence "
                              "tier-2 two weeks behind.",
            "expected_impact": f"Estimated {max(tier_1 // 3, 3)}-{tier_1 // 2 or 5} new active sellers",
            "confidence": 78,
            "reasoning": (f"The discovery scan returned {qualified} "
                          f"qualified sellers in '{target}'. The "
                          f"{tier_1} top-tier ones look like your best "
                          "historical conversions — sequencing them "
                          "first maximizes early wins."),
            "mission_intent": "launch_seller_mission",
            "mission_params": {"niche": target, "target": qualified},
            "source": "heuristic",
        }
    if job_type == "site_scan":
        ux = metrics.get("ux_signals", 0)
        return {
            "finding": "Conversion clarity gap detected on primary "
                       "landing experience",
            "root_cause": "The page explains what the platform IS but "
                          "doesn't make the visitor-specific value "
                          "proposition unmistakable in the first scroll.",
            "recommendation": "Add a clear single-purpose CTA + social "
                              "proof above the fold; defer secondary nav "
                              "below.",
            "expected_impact": "Higher visitor-to-action conversion rate",
            "confidence": 72,
            "reasoning": (f"The scan of {target} flagged signals around "
                          f"clarity and trust (ux score {ux}/100). "
                          "Visitors decide within seconds — leading with "
                          "specificity usually outperforms generic "
                          "feature lists."),
            "mission_intent": "improve_conversions",
            "mission_params": {"focus": "homepage"},
            "source": "heuristic",
        }
    # Generic fallback.
    return {
        "finding": f"{job_type.replace('_', ' ').title()} complete with findings worth reviewing",
        "root_cause": "Several patterns emerged that point to specific "
                      "operational levers.",
        "recommendation": "Open the report to choose the highest-leverage "
                          "follow-up.",
        "expected_impact": "Depends on which lever you pull",
        "confidence": 60,
        "reasoning": "I've packaged the findings — let's pick the most "
                     "impactful one to act on together.",
        "mission_intent": _DEFAULT_INTENT.get(job_type, "find_opportunities"),
        "mission_params": {},
        "source": "heuristic",
    }


def _trim(s, limit: int) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    return s[:limit]


# ----------------------------------------------------------- chat post
async def post_bridge_to_chat(job_id: str) -> Optional[dict]:
    """After an analysis job completes, post a SECOND Cortex turn into
    the user's conversation thread carrying the recommendation bridge.

    Timing: this runs AFTER the analysis_complete metric-tile message,
    so the user sees:

        [analysis_complete card — metrics + View Report]
        ↓ ~1.5s
        Cortex: "<reasoning paragraph>"
        [RecommendationBridgeCard — finding, root_cause, recommendation,
         expected_impact, confidence + 3 CTAs]

    The card pauses for the reasoning to land first so the recommendation
    feels like a CONCLUSION, not a pop-up.
    """
    from core import db

    bridge = await build_bridge_from_job(job_id)
    if not bridge:
        return None

    j = await db.analysis_jobs.find_one({"id": job_id}, {"_id": 0})
    if not j:
        return None

    user_id = j.get("user_id")
    conv_id = j.get("conversation_id")
    if not conv_id:
        latest = await db.cortex_conversations.find_one(
            {"user_id": user_id, "conversation_id": {"$exists": True}},
            {"_id": 0, "conversation_id": 1},
            sort=[("created_at", -1)],
        )
        conv_id = (latest or {}).get("conversation_id")
    if not conv_id:
        return bridge   # no conversation thread to surface in — bridge
                        # is still on file for the rail / Optimize loop.

    msg = {
        "id":              uuid.uuid4().hex,
        "conversation_id": conv_id,
        "user_id":         user_id,
        "role":            "cortex",
        "message":         bridge.get("reasoning") or "",
        "stage":           "recommendation",
        "created_at":      datetime.now(timezone.utc),
        "kind":            "recommendation_bridge",
        "job_id":          job_id,
        "job_type":        j.get("job_type"),
        # Embed the bridge payload directly so the frontend renders
        # without a round-trip.
        "bridge":          {
            "id":              bridge.get("id"),
            "finding":         bridge.get("finding"),
            "root_cause":      bridge.get("root_cause"),
            "recommendation":  bridge.get("recommendation"),
            "expected_impact": bridge.get("expected_impact"),
            "confidence":      bridge.get("confidence"),
            "mission_intent":  bridge.get("mission_intent"),
            "mission_params":  bridge.get("mission_params"),
            "source":          bridge.get("source"),
        },
    }
    try:
        await db.cortex_conversations.insert_one(msg)
    except Exception:
        logger.exception("recommendation_bridge: chat post failed")
    return bridge
