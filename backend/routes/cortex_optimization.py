"""Cortex Autonomous Optimization endpoints.

UI surfaces the OODA loop's findings as 'Cortex detected …' panels in
the Command Center. These endpoints read from cortex_optimization_log
and optionally trigger a fresh iteration on demand."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import Request

from core import api, db
from deps import get_current_user
from cortex.optimization_loop import run_for_user, _serialize

logger = logging.getLogger(__name__)


@api.get("/cortex/optimization/log")
async def optimization_log(request: Request, limit: int = 8):
    """Recent OODA-loop findings for this user, newest first."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 30))
    cur = db.cortex_optimization_log.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("created_at", -1).limit(limit)
    items = [_serialize(d) async for d in cur]
    return {"items": items, "count": len(items)}


@api.get("/cortex/optimization/status")
async def optimization_status(request: Request):
    """Headline status for the right-rail 'Cortex is monitoring' card."""
    user = await get_current_user(request)
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d  = now - timedelta(days=7)

    # Newest finding still considered 'active' (<24h old).
    latest = await db.cortex_optimization_log.find_one(
        {"user_id": user.user_id, "created_at": {"$gte": since_24h}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    detections_24h = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "created_at": {"$gte": since_24h}})
    detections_7d  = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "created_at": {"$gte": since_7d}})

    improved = await db.cortex_optimization_log.count_documents(
        {"user_id": user.user_id, "learning": "improved",
         "created_at": {"$gte": since_7d}})

    return {
        "active":              latest is not None,
        "latest":              _serialize(latest) if latest else None,
        "detections_24h":      detections_24h,
        "detections_7d":       detections_7d,
        "improved_7d":         improved,
        "monitoring_since":    None,  # placeholder for future onboarding ts
    }


@api.post("/cortex/optimization/run-now")
async def optimization_run_now(request: Request):
    """Trigger a fresh OODA iteration immediately for this user.
    Useful for the 'Scan now' button in the UI."""
    user = await get_current_user(request)
    try:
        doc = await run_for_user(user.user_id)
    except Exception:
        logger.exception("optimization_run_now failed")
        doc = None
    return {"ran": True, "fired": doc is not None, "finding": doc}


# Map of finding-kind → concrete autonomous action. Each entry is a
# tuple (label, mission_type, target_params, autonomy_required).
# These actions are intentionally conservative — they queue rather than
# instantly mutate sensitive things.
APPLY_ACTIONS: dict = {
    "discovery_stall": {
        "label":          "Broaden Scout sources",
        "mission_type":   "seller_acquisition",
        "title":          "Cortex: broaden Scout sources",
        "summary":        "Adds Pinterest + Shopify Public to Scout's source list and relaxes niche filters by one notch.",
    },
    "qualification_bottleneck": {
        "label":          "Lower qualification threshold",
        "mission_type":   "seller_acquisition",
        "title":          "Cortex: lower qualification threshold by 10pt for 7 days",
        "summary":        "Temporarily lowers seller_score gate to 65 (from 75) for a 7-day test window. Auto-reverts after.",
    },
    "deliverability_risk": {
        "label":          "Throttle outreach + warm secondary",
        "mission_type":   "campaign",
        "title":          "Cortex: throttle outreach + warm secondary sending domain",
        "summary":        "Caps sends at 40/hour for 48h and queues a 3-variant subject-line A/B test.",
    },
    "copy_conversion_gap": {
        "label":          "Auto-attach audit + tighten CTA",
        "mission_type":   "campaign",
        "title":          "Cortex: tighten outreach CTA + auto-attach audit PDF",
        "summary":        "Switches outreach template to auto-attach personalized audit PDF and rewrites the CTA paragraph.",
    },
    "onboarding_stall": {
        "label":          "Add onboarding nudge sequence",
        "mission_type":   "campaign",
        "title":          "Cortex: nudge sequence for interested sellers (h2 + d1 + d3)",
        "summary":        "Sends a 3-touch onboarding nudge sequence to interested leads who haven't onboarded yet.",
    },
}


@api.post("/cortex/optimization/{finding_id}/apply")
async def optimization_apply(finding_id: str, request: Request):
    """Apply Cortex's recommended action for a detected bottleneck.
    Looks up the finding, maps `kind` → a concrete action via
    APPLY_ACTIONS, and routes through the autonomy engine (drafts,
    queues, or launches per user's autonomy_level).

    Stamps `applied_at` + `applied_action_id` back onto the finding so
    the UI can hide / dim the Apply button after the click."""
    user = await get_current_user(request)

    doc = await db.cortex_optimization_log.find_one(
        {"id": finding_id, "user_id": user.user_id}, {"_id": 0})
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(404, "Finding not found")
    if doc.get("applied_at"):
        return {"already_applied": True,
                "applied_at": doc["applied_at"]
                  if isinstance(doc["applied_at"], str)
                  else doc["applied_at"].isoformat()}

    kind = doc.get("kind")
    spec = APPLY_ACTIONS.get(kind)
    if not spec:
        from fastapi import HTTPException
        raise HTTPException(400, f"No automatic action mapped for kind={kind!r}")

    # Build a recommendation payload that the existing autonomy engine
    # already knows how to execute. We piggy-back on the find_opportunities
    # intent so the action is queued in the cortex_approval_queue at L≤2
    # and launched at L≥3 — same gate as user-initiated plan cards.
    from routes.cortex_console import _execute_queue, _execute_launch
    autonomy = int(doc.get("autonomy_level") or 2)
    rec = {
        "id":              uuid.uuid4().hex,
        "type":            "apply_optimization",
        "title":           spec["title"],
        "summary":         spec["summary"],
        "expected_outcome": doc.get("recommendation") or spec["summary"],
        "estimated_cost_usd":      0,
        "estimated_timeline_days": 7,
        "risk_level":      "low",
        "confidence":      float(doc.get("confidence") or 0.7),
        "autonomy_level":  autonomy,
        "source_finding":  {
            "id": finding_id, "kind": kind,
            "bottleneck": doc.get("bottleneck"),
            "hypothesis": doc.get("hypothesis"),
        },
        "action_payload":  {"finding_id": finding_id, "kind": kind},
    }

    if autonomy >= 3:
        result = await _execute_launch(user.user_id, rec, autonomy)
        action_taken = "launched"
    else:
        result = await _execute_queue(user.user_id, rec, autonomy)
        action_taken = "queued"

    now = datetime.now(timezone.utc)
    await db.cortex_optimization_log.update_one(
        {"id": finding_id, "user_id": user.user_id},
        {"$set": {"applied_at":        now,
                   "applied_action_id": result.get("mission_id") or result.get("queue_id"),
                   "applied_action_taken": action_taken}},
    )
    return {
        "applied":       True,
        "action_taken":  action_taken,
        "label":         spec["label"],
        "result":        result,
    }
