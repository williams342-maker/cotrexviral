"""Cortex Autonomous Optimization Loop — the OODA cycle.

Runs continuously in the background per user. Each iteration:

  1. OBSERVE  — pull current funnel/mission/campaign metrics
  2. ANALYZE  — detect bottlenecks (where is the conversion stuck?)
  3. HYPOTHESIZE — generate a testable explanation
  4. RECOMMEND — produce an action proposal
  5. EXECUTE  — per autonomy (L3+ auto-executes; L0-L2 queues)
  6. MEASURE  — compare follow-up metrics to baseline
  7. LEARN    — record outcome confidence into cortex_optimization_log

This makes Cortex actively improve business performance rather than
waiting for the user to ask. It's the difference between a chatbot and
a Chief Growth Officer.

Storage:
    cortex_optimization_log    one row per loop iteration per user
        { id, user_id, kind, observations, bottleneck, hypothesis,
          recommendation, autonomy_taken, result, learning,
          confidence, created_at }
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------- detectors
async def _observe(user_id: str) -> dict:
    """Pull current signal snapshot for the user. Cheap, single-pass."""
    from core import db

    snap: dict = {"user_id": user_id, "at": datetime.now(timezone.utc).isoformat()}

    # Lead funnel (seller acquisition).
    stage_counts: dict[str, int] = {}
    try:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
        ]
        async for r in db.seller_leads.aggregate(pipeline):
            stage_counts[r["_id"] or "unknown"] = int(r["n"] or 0)
    except Exception:
        pass
    snap["funnel"] = stage_counts
    snap["funnel_total"] = sum(stage_counts.values())

    # Mission activity.
    try:
        running = await db.missions.count_documents(
            {"user_id": user_id, "status": {"$in": ["running", "active"]}})
        paused  = await db.missions.count_documents(
            {"user_id": user_id, "status": "paused"})
        snap["missions"] = {"running": running, "paused": paused}
    except Exception:
        snap["missions"] = {"running": 0, "paused": 0}

    # Recent outreach engagement (last 24h).
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        sent     = await db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": "sent",      "created_at": {"$gte": since}})
        opened   = await db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": "opened",    "created_at": {"$gte": since}})
        replied  = await db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": {"$in": ["replied", "interested"]},
             "created_at": {"$gte": since}})
        snap["outreach_24h"] = {"sent": sent, "opened": opened, "replied": replied}
        snap["open_rate"]  = (opened / sent) if sent else None
        snap["reply_rate"] = (replied / sent) if sent else None
    except Exception:
        snap["outreach_24h"] = {"sent": 0, "opened": 0, "replied": 0}

    # User's autonomy level.
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "autonomy_level": 1})
        snap["autonomy_level"] = int((u or {}).get("autonomy_level", 2))
    except Exception:
        snap["autonomy_level"] = 2

    return snap


# Bottleneck detection heuristics. Each rule returns a (bottleneck, hypothesis,
# recommendation, confidence, kind) tuple if it fires, or None.
def _rules(snap: dict) -> list[dict]:
    out: list[dict] = []
    funnel = snap.get("funnel") or {}
    discovered = funnel.get("discovered", 0)
    qualified  = funnel.get("qualified",  0)
    outreached = funnel.get("outreached", 0)
    interested = funnel.get("interested", 0)
    onboarded  = funnel.get("onboarded",  0)
    sent     = snap.get("outreach_24h", {}).get("sent",    0)
    opened   = snap.get("outreach_24h", {}).get("opened",  0)
    replied  = snap.get("outreach_24h", {}).get("replied", 0)
    open_rate  = snap.get("open_rate")
    reply_rate = snap.get("reply_rate")

    # 1) Discovery stall — running missions but no leads after 24h.
    if (snap.get("missions", {}).get("running", 0) > 0
            and snap.get("funnel_total", 0) == 0):
        out.append({
            "kind":           "discovery_stall",
            "bottleneck":     "Mission is running but Scout has surfaced 0 candidate sellers.",
            "hypothesis":     "Scout's source list or niche filters may be too narrow, or the niche has limited public supply.",
            "recommendation": "Broaden Scout's source set (add Pinterest + Shopify Public) or relax niche filters by one notch.",
            "confidence":     0.78,
        })

    # 2) Qualification bottleneck — many discovered, few qualified.
    if discovered >= 20 and qualified <= discovered * 0.25:
        out.append({
            "kind":           "qualification_bottleneck",
            "bottleneck":     f"Only {qualified}/{discovered} discovered leads passed qualification ({100*qualified//max(discovered,1)}%).",
            "hypothesis":     "Qualification threshold may be too strict, OR Scout's discovery is bringing in low-quality sources.",
            "recommendation": "Lower the seller_score threshold by 10 points for 7 days and measure conversion — OR refine Scout sources.",
            "confidence":     0.72,
        })

    # 3) Outreach silent — sent but no opens (deliverability problem).
    if sent >= 15 and (open_rate is None or open_rate < 0.05):
        out.append({
            "kind":           "deliverability_risk",
            "bottleneck":     f"{sent} emails sent in 24h but open rate is {round((open_rate or 0)*100,1)}% (target 25%+).",
            "hypothesis":     "Possible deliverability / spam-folder issue — domain reputation, subject lines, or sending volume too aggressive.",
            "recommendation": "Throttle to <40 sends/hour, warm a secondary sending domain, and A/B test 3 new subject lines.",
            "confidence":     0.81,
        })

    # 4) Engagement without conversion — many opens, no replies.
    if opened >= 12 and replied <= max(1, int(opened * 0.05)):
        out.append({
            "kind":           "copy_conversion_gap",
            "bottleneck":     f"{opened} opens in 24h but only {replied} replies — your copy is read but not converting.",
            "hypothesis":     "The CTA is too soft, the value prop is unclear, or the audit PDF isn't being attached.",
            "recommendation": "Add a direct CTA + auto-attach the personalized audit PDF to every outreach message.",
            "confidence":     0.74,
        })

    # 5) Reply stall — replies but no onboards.
    if interested >= 5 and onboarded <= 1:
        out.append({
            "kind":           "onboarding_stall",
            "bottleneck":     f"{interested} interested sellers but only {onboarded} onboarded — handoff is leaking.",
            "hypothesis":     "Onboarding workflow may be slow or the activation step is too manual.",
            "recommendation": "Send a 'getting started' nudge sequence at hour 2 + day 1 + day 3 to interested leads.",
            "confidence":     0.69,
        })

    return out


# --------------------------------------------------------- per-user run
async def run_for_user(user_id: str, *, dry_run: bool = False) -> Optional[dict]:
    """Run one OODA iteration for the given user. Returns the log
    document (already persisted) or None if no bottleneck fired."""
    from core import db

    snap = await _observe(user_id)
    if not snap.get("user_id"):
        return None
    detections = _rules(snap)
    if not detections:
        return None

    # Pick the highest-confidence finding this round (we surface one at
    # a time so the user isn't bombarded).
    top = max(detections, key=lambda d: d.get("confidence", 0))

    # De-dupe: don't surface the same `kind` more than once per 12h.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    try:
        recent = await db.cortex_optimization_log.find_one(
            {"user_id": user_id, "kind": top["kind"],
             "created_at": {"$gte": cutoff}}, {"_id": 0, "id": 1})
        if recent:
            return None
    except Exception:
        pass

    autonomy = snap.get("autonomy_level", 2)
    # L0-L2 → propose only (drops into opportunity feed). L3+ → could
    # auto-act, but we DO NOT auto-execute strategic loop suggestions
    # yet — they go to the opportunity rail so the user can decide.
    # (Auto-execute reserved for mission ticks already wired elsewhere.)
    autonomy_taken = "proposed" if autonomy < 3 else "proposed_auto_eligible"

    doc = {
        "id":              uuid.uuid4().hex,
        "user_id":         user_id,
        "kind":            top["kind"],
        "observations":    snap,
        "bottleneck":      top["bottleneck"],
        "hypothesis":      top["hypothesis"],
        "recommendation":  top["recommendation"],
        "confidence":      float(top["confidence"]),
        "autonomy_level":  autonomy,
        "autonomy_taken":  autonomy_taken,
        "result":          None,    # filled by the next iteration's measure step
        "learning":        None,
        "created_at":      datetime.now(timezone.utc),
    }
    if not dry_run:
        try:
            await db.cortex_optimization_log.insert_one(doc)
        except Exception:
            logger.exception("optimization_loop: failed to persist log")

    # Try the MEASURE step on prior detections of any kind for this user —
    # if a prior detection is >24h old and still has result=None, mark
    # its result based on whether the metric improved.
    if not dry_run:
        try:
            await _measure_prior(user_id, snap)
        except Exception:
            logger.exception("optimization_loop: _measure_prior failed")

    return _serialize(doc)


async def _measure_prior(user_id: str, current_snap: dict) -> None:
    """Compare a prior detection's metrics to the current snapshot and
    write back a learning. Simple heuristic per `kind`."""
    from core import db

    cutoff_min = datetime.now(timezone.utc) - timedelta(hours=72)
    cutoff_max = datetime.now(timezone.utc) - timedelta(hours=24)
    cur = db.cortex_optimization_log.find({
        "user_id":    user_id,
        "result":     None,
        "created_at": {"$gte": cutoff_min, "$lte": cutoff_max},
    }, {"_id": 0}).limit(5)

    async for prior in cur:
        kind = prior.get("kind")
        learning = "neutral"
        result = {}
        prev = prior.get("observations") or {}
        if kind == "deliverability_risk":
            prev_or = prev.get("open_rate") or 0
            now_or  = current_snap.get("open_rate") or 0
            result = {"prev_open_rate": prev_or, "now_open_rate": now_or}
            learning = "improved" if now_or > prev_or + 0.05 else (
                "regressed" if now_or < prev_or - 0.02 else "neutral")
        elif kind == "copy_conversion_gap":
            prev_rr = prev.get("reply_rate") or 0
            now_rr  = current_snap.get("reply_rate") or 0
            result = {"prev_reply_rate": prev_rr, "now_reply_rate": now_rr}
            learning = "improved" if now_rr > prev_rr + 0.03 else (
                "regressed" if now_rr < prev_rr - 0.01 else "neutral")
        elif kind == "qualification_bottleneck":
            prev_q = (prev.get("funnel") or {}).get("qualified", 0)
            now_q  = (current_snap.get("funnel") or {}).get("qualified", 0)
            result = {"prev_qualified": prev_q, "now_qualified": now_q}
            learning = "improved" if now_q > prev_q else (
                "regressed" if now_q < prev_q else "neutral")
        else:
            now_total  = current_snap.get("funnel_total", 0)
            prev_total = prev.get("funnel_total", 0)
            result = {"prev_total": prev_total, "now_total": now_total}
            learning = "improved" if now_total > prev_total else "neutral"

        try:
            await db.cortex_optimization_log.update_one(
                {"id": prior["id"]},
                {"$set": {"result": result, "learning": learning}},
            )
        except Exception:
            logger.exception("optimization_loop: failed to write learning")


# ---------------------------------------------------------- scheduler
async def run_loop_all_users() -> dict:
    """Scheduler entry point — sweeps all users with recent activity
    and runs one OODA iteration per user."""
    from core import db

    seen: set[str] = set()
    horizon = datetime.now(timezone.utc) - timedelta(days=14)
    cur = db.missions.find(
        {"created_at": {"$gte": horizon}, "user_id": {"$ne": None}},
        {"_id": 0, "user_id": 1},
    ).limit(500)
    async for row in cur:
        uid = row.get("user_id")
        if uid:
            seen.add(uid)

    summary = {"total_users": len(seen), "fired": 0, "users_with_findings": []}
    for uid in seen:
        try:
            doc = await run_for_user(uid)
            if doc:
                summary["fired"] += 1
                summary["users_with_findings"].append(uid)
        except Exception:
            logger.exception("optimization_loop: run_for_user failed for %s", uid)
    summary["ran_at"] = datetime.now(timezone.utc).isoformat()
    return summary


# ---------------------------------------------------------- helpers
def _serialize(doc: dict) -> dict:
    """Strip Mongo ObjectId + ISO-ify timestamps for API responses."""
    out = dict(doc)
    out.pop("_id", None)
    v = out.get("created_at")
    if isinstance(v, datetime):
        out["created_at"] = v.isoformat()
    return out
