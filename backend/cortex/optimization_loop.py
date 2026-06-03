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

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# LLM-augmented detector cadence — Claude is consulted at most once per
# user per this many hours to bound cost. The deterministic rules still
# run every tick (free + fast); the LLM only fires when they're silent.
_LLM_DETECTOR_INTERVAL_HOURS = 6
_LLM_DETECTOR_ENABLED = (os.environ.get("CORTEX_LLM_DETECTOR_ENABLED", "true").strip().lower()
                          not in ("0", "false", "no", "off"))


# ---------------------------------------------------------- detectors
async def _observe(user_id: str) -> dict:
    """Pull current signal snapshot for the user. All Mongo reads run
    concurrently — each tick was previously 6 sequential round-trips
    (~150-300ms). With `asyncio.gather` it collapses to one network
    round-trip's worth of latency. At the scheduler-sweep level (100s
    of users) this is the difference between minutes and seconds."""
    from core import db

    snap: dict = {"user_id": user_id, "at": datetime.now(timezone.utc).isoformat()}

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$stage", "n": {"$sum": 1}}},
    ]

    async def _stage_counts():
        out: dict[str, int] = {}
        try:
            async for r in db.seller_leads.aggregate(pipeline):
                out[r["_id"] or "unknown"] = int(r["n"] or 0)
        except Exception:
            pass
        return out

    async def _safe(coro, default):
        try:
            return await coro
        except Exception:
            return default

    (stage_counts, running, paused,
        sent, opened, replied, user_doc) = await asyncio.gather(
        _stage_counts(),
        _safe(db.missions.count_documents(
            {"user_id": user_id, "status": {"$in": ["running", "active"]}}), 0),
        _safe(db.missions.count_documents(
            {"user_id": user_id, "status": "paused"}), 0),
        _safe(db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": "sent",
             "created_at": {"$gte": since}}), 0),
        _safe(db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": "opened",
             "created_at": {"$gte": since}}), 0),
        _safe(db.seller_outreach_events.count_documents(
            {"user_id": user_id, "event": {"$in": ["replied", "interested"]},
             "created_at": {"$gte": since}}), 0),
        _safe(db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "autonomy_level": 1}), None),
    )

    snap["funnel"]       = stage_counts
    snap["funnel_total"] = sum(stage_counts.values())
    snap["missions"]     = {"running": running, "paused": paused}
    snap["outreach_24h"] = {"sent": sent, "opened": opened, "replied": replied}
    snap["open_rate"]    = (opened / sent) if sent else None
    snap["reply_rate"]   = (replied / sent) if sent else None
    snap["autonomy_level"] = int((user_doc or {}).get("autonomy_level", 2))

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


# ----------------------------------------------------------- LLM rules
async def _llm_rules(snap: dict, *, user_id: str,
                      already_detected_kinds: set[str]) -> list[dict]:
    """LLM-augmented detector — surfaces *non-obvious* bottlenecks the
    deterministic heuristics miss (cross-stage patterns, ratios outside
    rule thresholds, leading indicators of decay, etc.).

    Cost guard: at most one Claude consultation per user per
    _LLM_DETECTOR_INTERVAL_HOURS. Heuristics already run every tick;
    this only fills the gap when they're silent or when the patterns
    are subtler than any single rule could catch.

    Each finding is tagged `source="llm_augmented"` and uses an
    `llm_<slug>` kind so it doesn't collide with deterministic kinds
    in the dedupe / Apply-action maps.
    """
    if not _LLM_DETECTOR_ENABLED:
        return []
    from core import db

    # Skip if we'd just call the LLM with an empty signal — saves cost
    # and avoids hallucinated bottlenecks on brand-new accounts.
    if (snap.get("funnel_total", 0) == 0
            and snap.get("outreach_24h", {}).get("sent", 0) == 0
            and snap.get("missions", {}).get("running", 0) == 0):
        return []

    # Rate limit per user (any prior LLM-augmented call within window
    # blocks a fresh one).
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_LLM_DETECTOR_INTERVAL_HOURS)
    try:
        recent_llm = await db.cortex_optimization_log.find_one(
            {"user_id": user_id, "source": "llm_augmented",
             "created_at": {"$gte": cutoff}}, {"_id": 0, "id": 1})
        if recent_llm:
            return []
    except Exception:
        pass

    system = (
        "You are Cortex's reasoning brain — a Chief Growth Officer for an "
        "AI marketing operating system. Inspect the metrics snapshot of a "
        "user's business and surface NON-OBVIOUS bottlenecks the heuristic "
        "rules miss. Things to look for:\n"
        "  • Compounding ratios across funnel stages (e.g., qualified→outreached drop-off).\n"
        "  • Volume vs. velocity mismatches (e.g., paused missions hoarding capacity).\n"
        "  • Early decay signals before the heuristics' thresholds fire.\n"
        "  • Cross-signal patterns (low opens + many running missions ⇒ overload).\n"
        "Be conservative — only flag a bottleneck if there's clear evidence in the snapshot. "
        "Never duplicate kinds already detected by deterministic rules (listed below). "
        "Limit to 2 findings max, ranked by importance. If no bottleneck is found, return an empty list."
    )
    user_text = (
        "Snapshot:\n"
        f"{json.dumps(_compact_snap(snap), indent=2)}\n\n"
        f"Kinds already detected this tick (do not duplicate): "
        f"{sorted(already_detected_kinds) or '[]'}"
    )

    detector_tool = {
        "name": "surface_bottlenecks",
        "description": (
            "Surface 0-2 non-obvious bottlenecks the deterministic rules missed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind":           {"type": "string",
                                                "description": "Short slug like 'llm_paused_mission_overload'. Prefix with llm_."},
                            "bottleneck":     {"type": "string"},
                            "hypothesis":     {"type": "string"},
                            "recommendation": {"type": "string"},
                            "confidence":     {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["kind", "bottleneck", "recommendation", "confidence"],
                    },
                },
            },
            "required": ["findings"],
        },
    }

    try:
        from cortex.llm_provider import cortex_tool_call
        args, _label, _mode = await cortex_tool_call(
            system=system,
            user_text=user_text,
            tool=detector_tool,
            session_id=f"cortex-llm-detector-{user_id}",
            user_id=user_id,
            # Detector output is a 0-2 element structured array — Haiku
            # 4.5 handles this fine and is ~3× faster + cheaper than
            # Sonnet. Failover chain (haiku → claude → gpt) preserved.
            prefer="haiku",
            required=["findings"],
        )
    except Exception:
        logger.exception("optimization_loop: LLM detector tool-call failed")
        return []
    if not args:
        return []

    findings = _normalize_findings(args.get("findings") or [], already_detected_kinds)
    for f in findings:
        f["source"] = "llm_augmented"
    return findings


def _normalize_findings(items: list, already_detected_kinds: set[str]) -> list[dict]:
    """Tool-call shape is already structured; just clamp + de-dupe."""
    out: list[dict] = []
    for f in (items or [])[:2]:
        if not isinstance(f, dict):
            continue
        kind = str(f.get("kind") or "").strip().lower()
        bottleneck = str(f.get("bottleneck") or "").strip()
        rec = str(f.get("recommendation") or "").strip()
        if not kind or not bottleneck or not rec:
            continue
        raw_kind = kind[4:] if kind.startswith("llm_") else kind
        if raw_kind in already_detected_kinds:
            continue
        if not kind.startswith("llm_"):
            kind = f"llm_{kind}"
        kind = kind[:64]
        if kind in already_detected_kinds:
            continue
        try:
            conf = float(f.get("confidence") or 0.6)
        except Exception:
            conf = 0.6
        conf = max(0.0, min(1.0, conf))
        out.append({
            "kind":           kind,
            "bottleneck":     bottleneck[:400],
            "hypothesis":     str(f.get("hypothesis") or "")[:600],
            "recommendation": rec[:600],
            "confidence":     conf,
        })
    return out


def _compact_snap(snap: dict) -> dict:
    """Trim snapshot to the fields the LLM actually needs — keeps the
    prompt small and prevents leaking irrelevant context."""
    return {
        "funnel":          snap.get("funnel") or {},
        "funnel_total":    snap.get("funnel_total", 0),
        "missions":        snap.get("missions") or {},
        "outreach_24h":    snap.get("outreach_24h") or {},
        "open_rate":       snap.get("open_rate"),
        "reply_rate":      snap.get("reply_rate"),
        "autonomy_level":  snap.get("autonomy_level", 2),
    }


def _parse_llm_findings(text: str, already_detected_kinds: set[str]) -> list[dict]:
    """Robust JSON parsing — strips fences, drops malformed entries."""
    if not text:
        return []
    t = text.strip()
    # Defensive fence strip (cortex_chat already strips, but belt-and-braces).
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?|```\s*$", "", t, flags=re.MULTILINE).strip()
    try:
        data = json.loads(t)
    except Exception:
        # Some models wrap with prose despite instructions — try extracting
        # the first {...} JSON object.
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for f in items[:2]:
        if not isinstance(f, dict):
            continue
        kind = str(f.get("kind") or "").strip().lower()
        bottleneck = str(f.get("bottleneck") or "").strip()
        rec = str(f.get("recommendation") or "").strip()
        if not kind or not bottleneck or not rec:
            continue
        # Reject if the LLM tried to duplicate a deterministic kind
        # (either with or without the llm_ prefix).
        raw_kind = kind[4:] if kind.startswith("llm_") else kind
        if raw_kind in already_detected_kinds:
            continue
        if not kind.startswith("llm_"):
            kind = f"llm_{kind}"
        # Truncate so a misbehaving model can't bloat the doc.
        kind = kind[:64]
        if kind in already_detected_kinds:
            continue
        try:
            conf = float(f.get("confidence") or 0.6)
        except Exception:
            conf = 0.6
        conf = max(0.0, min(1.0, conf))
        out.append({
            "kind":           kind,
            "bottleneck":     bottleneck[:400],
            "hypothesis":     str(f.get("hypothesis") or "")[:600],
            "recommendation": rec[:600],
            "confidence":     conf,
        })
    return out
async def run_for_user(user_id: str, *, dry_run: bool = False) -> Optional[dict]:
    """Run one OODA iteration for the given user. Returns the log
    document (already persisted) or None if no bottleneck fired."""
    from core import db

    snap = await _observe(user_id)
    if not snap.get("user_id"):
        return None
    detections = _rules(snap)

    # LLM augmentation — only consulted when the deterministic rules
    # are silent (saves cost; heuristics handle the obvious cases).
    if not detections:
        try:
            llm_detections = await _llm_rules(
                snap, user_id=user_id,
                already_detected_kinds=set())
            detections.extend(llm_detections)
        except Exception:
            logger.exception("optimization_loop: _llm_rules failed (non-fatal)")
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
        "source":          top.get("source", "heuristic"),
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

# Bounded concurrency for the per-user OODA sweep. 8 is a good balance
# between making the scheduler tick fast (10× faster than sequential at
# scale) and not flooding Mongo/Claude with concurrent requests.
_SCHEDULER_CONCURRENCY = int(os.environ.get("CORTEX_LOOP_CONCURRENCY", "8"))


async def run_loop_all_users() -> dict:
    """Scheduler entry point — sweeps all users with recent activity
    and runs one OODA iteration per user.

    Runs up to `_SCHEDULER_CONCURRENCY` users concurrently. Each per-user
    tick is independent (different snapshot, different log doc) so this
    parallelizes cleanly. At 100 users + 8-way parallel that's a ~10×
    wall-clock improvement on every scheduler tick."""
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

    summary = {"total_users": len(seen), "fired": 0, "users_with_findings": [],
                "learnings_written": 0}
    sem = asyncio.Semaphore(max(1, _SCHEDULER_CONCURRENCY))

    async def _per_user(uid: str) -> tuple[str, Optional[dict], int]:
        """Run one user's OODA tick (bounded by `sem`). Returns
        `(uid, doc_or_None, learnings_delta)`."""
        async with sem:
            try:
                doc = await run_for_user(uid)
                if doc:
                    return (uid, doc, 0)
                # Even on detection-free ticks, write learnings for any
                # prior detections that are 24-72h old. Keeps the
                # learning step accruing across quiet periods.
                try:
                    from core import db as _db
                    snap = await _observe(uid)
                    before = await _db.cortex_optimization_log.count_documents(
                        {"user_id": uid, "result": None})
                    await _measure_prior(uid, snap)
                    after = await _db.cortex_optimization_log.count_documents(
                        {"user_id": uid, "result": None})
                    return (uid, None, max(0, before - after))
                except Exception:
                    logger.exception(
                        "optimization_loop: measure-only step failed for %s", uid)
                    return (uid, None, 0)
            except Exception:
                logger.exception(
                    "optimization_loop: run_for_user failed for %s", uid)
                return (uid, None, 0)

    results = await asyncio.gather(*(_per_user(uid) for uid in seen))
    for uid, doc, delta in results:
        if doc:
            summary["fired"] += 1
            summary["users_with_findings"].append(uid)
        summary["learnings_written"] += delta

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
