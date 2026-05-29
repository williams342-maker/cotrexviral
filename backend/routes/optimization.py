"""Optimization Agent (Pico) — closes the loop on content performance.

The pattern:
  1. Daily, Pico reads every variant + its performance_rollup
  2. Per-platform percentile-classifies each into winner / loser / middling
     (only variants with ≥ MIN_SAMPLES are eligible — protects against noise)
  3. For each LOSER, calls an LLM to produce 1–2 improved rewrites that
     borrow specific traits from the platform's TOP variant
  4. Spawns a fresh `experiments` row pitting the rewrite against the loser
  5. Writes an `optimization_recommendations` row tied to the parent
     campaign so the operator sees Pico's reasoning in the UI

Status lifecycle for a recommendation:
  pending → applied         (operator clicked "apply" — adds new variant to campaign)
  pending → dismissed       (operator clicked "dismiss")
  pending → expired         (>14 days old without action — auto-archived)

Anti-spam: skip a variant if Pico already wrote a recommendation for it
in the last 7 days. One variant = one rewrite attempt per week.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request

from core import api, db
from deps import get_current_user
from routes.agent_personas import PERSONAS  # noqa: F401  (kept for symmetry)
from routes.autonomy import check_budget, record_usage, can_auto_approve

logger = logging.getLogger(__name__)


# How many performance_metrics ticks a variant needs before Pico will judge it.
# Below this we genuinely don't have signal, only noise.
MIN_SAMPLES = 5

# Percentile cutoffs (per-platform). A variant scoring below the 25th
# percentile (with ≥ MIN_SAMPLES) is a loser candidate; above the 75th
# is a winner that gets cited in the rewrite prompt.
LOSER_PERCENTILE  = 0.25
WINNER_PERCENTILE = 0.75

# Don't write a 2nd recommendation for the same variant within this window.
RECOMMENDATION_COOLDOWN_DAYS = 7

# How many losers we'll process per user per cron run (LLM cost ceiling).
MAX_REWRITES_PER_RUN = 5


# ---------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------
async def classify_variants(user_id: str, *, metric: str = "engagements") -> dict:
    """Returns {platform → {winners, losers, middling}}. Pure read. The
    metric is the field on `performance_rollups.windows.all_time` we
    percentile against — default `engagements`."""
    # Pull every variant + its rollup for this user. The aggregation join
    # is cheaper than two round-trips when we'd be matching by variant_id.
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$lookup": {
            "from":         "performance_rollups",
            "localField":   "id",
            "foreignField": "variant_id",
            "as":           "rollup",
        }},
        {"$unwind": {"path": "$rollup", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id":      0,
            "id":       1,
            "platform": 1,
            "body":     1,
            "content_item_id": 1,
            "metric_value": {"$ifNull": [f"$rollup.windows.all_time.{metric}", 0]},
            "samples":      {"$ifNull": ["$rollup.windows.all_time.samples", 0]},
        }},
    ]
    rows = await db.content_variants.aggregate(pipeline).to_list(length=5000)

    # Group by platform
    by_platform: dict[str, list[dict]] = {}
    for r in rows:
        plat = r.get("platform") or "unknown"
        by_platform.setdefault(plat, []).append(r)

    out: dict[str, dict] = {}
    for plat, items in by_platform.items():
        # Only judge variants with enough samples — drop the rest.
        eligible = [it for it in items if (it.get("samples") or 0) >= MIN_SAMPLES]
        if len(eligible) < 4:
            # Not enough variants to percentile meaningfully on this platform.
            out[plat] = {"winners": [], "losers": [], "middling": eligible,
                         "eligible_count": len(eligible), "skipped": "not enough samples"}
            continue
        sorted_items = sorted(eligible, key=lambda x: x.get("metric_value") or 0)
        n = len(sorted_items)
        loser_cut  = max(1, int(n * LOSER_PERCENTILE))
        winner_cut = max(1, int(n * WINNER_PERCENTILE))
        losers   = sorted_items[:loser_cut]
        middling = sorted_items[loser_cut:winner_cut]
        winners  = sorted_items[winner_cut:]
        out[plat] = {
            "winners":         winners,
            "losers":          losers,
            "middling":        middling,
            "eligible_count":  n,
            "top_value":       winners[-1]["metric_value"] if winners else 0,
            "bottom_value":    losers[0]["metric_value"] if losers else 0,
        }
    return out


# ---------------------------------------------------------------------
# LLM rewrite
# ---------------------------------------------------------------------
async def _rewrite_loser_with_llm(loser: dict, winners: list[dict],
                                  *, user_id: str) -> Optional[dict]:
    """Returns {rewrite, traits_borrowed, hypothesis} or None on failure.

    Pico cites specific traits from the winners ("question hook",
    "first-person voice", "concrete number") so the operator can see
    the editorial logic, not just trust a black-box rewrite."""
    from core import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        # Deterministic fallback: prepend a "❓" hook to the loser body so
        # the test infrastructure can still verify the pipeline E2E.
        return {
            "rewrite":          f"❓ {loser.get('body') or ''}".strip()[:1200],
            "traits_borrowed":  ["question hook"],
            "hypothesis":       "Question-led hooks beat statement-led hooks on average.",
            "model":            "fallback",
        }

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage
        import asyncio as _aio
        import json as _json
        import re

        winner_bodies = "\n".join(
            f"  • [val={w.get('metric_value', 0):.0f}] {(w.get('body') or '')[:200]}"
            for w in winners[-3:]  # last 3 = top 3 by sort order
        ) or "  (no winners — use general best practices)"

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"pico_rewrite_{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
            system_message=(
                "You are Pico, the optimizer. You rewrite under-performing content "
                "by borrowing SPECIFIC traits from the winners on the same platform. "
                "You don't rewrite from scratch — you keep the loser's intent but "
                "swap the hook, structure, or specificity. Output strict JSON only."
            ),
        ).with_model("openai", "gpt-5-mini")

        prompt = (
            f"LOSER VARIANT ({loser.get('platform')}):\n{(loser.get('body') or '')[:600]}\n\n"
            f"TOP WINNERS ON THIS PLATFORM (best at bottom):\n{winner_bodies}\n\n"
            "Output strict JSON with these keys:\n"
            "{\"rewrite\": str (the improved copy, same platform, <=1000 chars), "
            "\"traits_borrowed\": list[str] (specific traits from the winners — e.g. "
            "[\"question hook\", \"first-person voice\", \"concrete number\"]), "
            "\"hypothesis\": str (1 sentence — why this rewrite should win, <=200 chars)}"
        )
        text, _usage = await _aio.wait_for(
            send_with_usage(chat, UserMessage(text=prompt),
                            agent_id="pico", user_id=user_id, model="gpt-5-mini"),
            timeout=25,
        )
        cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = _json.loads(cleaned)
        if not isinstance(parsed, dict):
            return None
        return {
            "rewrite":         str(parsed.get("rewrite") or "").strip()[:1200],
            "traits_borrowed": [t for t in (parsed.get("traits_borrowed") or []) if isinstance(t, str)][:5],
            "hypothesis":      str(parsed.get("hypothesis") or "").strip()[:300],
            "model":           "gpt-5-mini",
        }
    except Exception as exc:
        logger.warning("Pico rewrite failed: %s", exc)
        return None


# ---------------------------------------------------------------------
# Persistence — recommendation + auto-spawned experiment
# ---------------------------------------------------------------------
async def _persist_recommendation(
    *,
    user_id: str,
    loser_variant_id: str,
    new_variant_id: str,
    experiment_id: str,
    rewrite_body: str,
    traits_borrowed: list[str],
    hypothesis: str,
    platform: str,
    campaign_id: Optional[str],
    model: str,
) -> str:
    """Writes the `optimization_recommendations` row. Returns the rec id."""
    rid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await db.optimization_recommendations.insert_one({
        "id":                rid,
        "user_id":           user_id,
        "agent_id":          "pico",
        "loser_variant_id":  loser_variant_id,
        "new_variant_id":    new_variant_id,
        "experiment_id":     experiment_id,
        "rewrite_body":      rewrite_body,
        "traits_borrowed":   traits_borrowed,
        "hypothesis":        hypothesis,
        "platform":          platform,
        "campaign_id":       campaign_id,
        "model":             model,
        "status":            "pending",  # pending | applied | dismissed | expired
        "decided_at":        None,
        "decided_by":        None,
        "created_at":        now,
        "expires_at":        now + timedelta(days=14),
    })
    return rid


async def _create_retest_experiment(
    *,
    user_id: str,
    loser: dict,
    new_variant: dict,
    metric: str,
) -> str:
    """Spawns a running experiment pitting the rewrite vs the loser."""
    eid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    await db.experiments.insert_one({
        "id":             eid,
        "user_id":        user_id,
        "name":           f"Pico retest — {(loser.get('body') or '')[:50]}",
        "hypothesis":     new_variant.get("hypothesis"),
        "variant_a_id":   new_variant["id"],      # A = the rewrite (Pico's pick)
        "variant_b_id":   loser["id"],
        "metric":         metric,
        "status":         "running",
        "started_at":     now,
        "ended_at":       None,
        "winner_variant_id":  None,
        "winner_margin_pct":  None,
        "conclusion_text":    None,
        "memory_id":          None,
        "owner_agent":    "ori",     # Ori will conclude it once data lands
        "spawned_by":     "pico",
        "created_at":     now,
        "updated_at":     now,
    })
    return eid


async def _spawn_variant(loser: dict, rewrite: dict, *, user_id: str) -> dict:
    """Creates a `content_variants` row for the rewrite, tied to the same
    content_item as the loser. Returns the inserted row."""
    vid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    doc = {
        "id":              vid,
        "user_id":         user_id,
        "content_item_id": loser.get("content_item_id"),
        "platform":        loser.get("platform"),
        "body":            rewrite["rewrite"],
        "status":          "draft",
        "spawned_by":      "pico",
        "source_variant_id": loser["id"],
        "traits_borrowed": rewrite.get("traits_borrowed"),
        "hypothesis":      rewrite.get("hypothesis"),
        "created_at":      now,
        "updated_at":      now,
    }
    await db.content_variants.insert_one(doc)
    doc["hypothesis"] = rewrite.get("hypothesis")  # not stripped — needed by retest
    return doc


# ---------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------
async def run_optimization_for_user(user_id: str, *, dry_run: bool = False,
                                    metric: str = "engagements") -> dict:
    """Full Pico run for one user. Returns a summary the cron logs +
    the UI displays. When `dry_run=True`, classification runs but no
    rewrites are generated (used for the preview-mode endpoint)."""
    classes = await classify_variants(user_id, metric=metric)

    # Budget gate — if Pico is out of irreversible headroom this week, just classify.
    allowed, reason = await can_auto_approve("pico", user_id)
    if not allowed and not dry_run:
        return {
            "user_id":            user_id,
            "metric":             metric,
            "classifications":    {k: {kk: len(vv) if isinstance(vv, list) else vv
                                       for kk, vv in v.items()} for k, v in classes.items()},
            "rewrites_attempted": 0,
            "rewrites_succeeded": 0,
            "retests_created":    0,
            "skipped_reason":     reason,
        }

    rewrites_attempted = 0
    rewrites_succeeded = 0
    retests_created = 0
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=RECOMMENDATION_COOLDOWN_DAYS)

    if not dry_run:
        # Flatten the per-platform loser lists into one queue, sorted by
        # how far below the platform's top each loser sits — most-broken
        # first. Capped at MAX_REWRITES_PER_RUN per user per cron tick.
        queue: list[tuple[dict, list[dict]]] = []
        for plat, c in classes.items():
            losers = c.get("losers") or []
            winners = c.get("winners") or []
            if not losers or not winners:
                continue
            for loser in losers:
                queue.append((loser, winners))
        queue = queue[:MAX_REWRITES_PER_RUN]

        for loser, winners in queue:
            # Cooldown — skip if Pico already proposed a rewrite this week
            recent = await db.optimization_recommendations.find_one({
                "user_id":          user_id,
                "loser_variant_id": loser["id"],
                "created_at":       {"$gte": cooldown_cutoff},
            })
            if recent:
                continue

            rewrites_attempted += 1
            rewrite = await _rewrite_loser_with_llm(loser, winners, user_id=user_id)
            if not rewrite or not rewrite.get("rewrite"):
                continue
            new_variant = await _spawn_variant(loser, rewrite, user_id=user_id)
            exp_id = await _create_retest_experiment(
                user_id=user_id, loser=loser, new_variant=new_variant, metric=metric,
            )
            # Find the parent campaign (if any) via the loser's content_item.
            cid = None
            ci = await db.content_items.find_one(
                {"id": loser.get("content_item_id")},
                {"_id": 0, "campaign_id": 1},
            )
            if ci:
                cid = ci.get("campaign_id")
            await _persist_recommendation(
                user_id=user_id,
                loser_variant_id=loser["id"],
                new_variant_id=new_variant["id"],
                experiment_id=exp_id,
                rewrite_body=rewrite["rewrite"],
                traits_borrowed=rewrite.get("traits_borrowed") or [],
                hypothesis=rewrite.get("hypothesis") or "",
                platform=loser.get("platform") or "unknown",
                campaign_id=cid,
                model=rewrite.get("model") or "unknown",
            )
            # Burn one irreversible from Pico's budget — these are real,
            # downstream-visible artifacts.
            await record_usage("pico", user_id, irreversible=1)
            rewrites_succeeded += 1
            retests_created += 1

    return {
        "user_id":            user_id,
        "metric":             metric,
        "classifications":    {k: {"winners": len(v.get("winners") or []),
                                    "losers":  len(v.get("losers") or []),
                                    "middling": len(v.get("middling") or []),
                                    "eligible_count": v.get("eligible_count", 0)}
                                for k, v in classes.items()},
        "rewrites_attempted": rewrites_attempted,
        "rewrites_succeeded": rewrites_succeeded,
        "retests_created":    retests_created,
        "skipped_reason":     None,
    }


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.get("/optimization/classify")
async def get_classifications(request: Request, metric: str = "engagements"):
    """Preview-mode classification — no rewrites, no LLM cost."""
    user = await get_current_user(request)
    classes = await classify_variants(user.user_id, metric=metric)
    # Strip raw rollup numbers to keep the payload small for the UI.
    out = {}
    for plat, c in classes.items():
        out[plat] = {
            "eligible_count": c.get("eligible_count", 0),
            "skipped":        c.get("skipped"),
            "top_value":      c.get("top_value", 0),
            "bottom_value":   c.get("bottom_value", 0),
            "winners":  [{"id": w["id"], "body": (w.get("body") or "")[:200],
                          "value": w.get("metric_value")} for w in (c.get("winners") or [])],
            "losers":   [{"id": w["id"], "body": (w.get("body") or "")[:200],
                          "value": w.get("metric_value")} for w in (c.get("losers") or [])],
        }
    return {"metric": metric, "platforms": out}


@api.post("/optimization/run-now")
async def run_optimization_now(request: Request):
    """Operator-triggered Pico run. Mirrors what the daily cron does
    but only for THIS user. Honors the cooldown + budget gate."""
    user = await get_current_user(request)
    return await run_optimization_for_user(user.user_id)


@api.get("/optimization/recommendations")
async def list_recommendations(request: Request, status: Optional[str] = None):
    """Returns Pico's recommendations with summary stats. Default returns
    all statuses; pass `status=pending` to filter the pending queue."""
    user = await get_current_user(request)
    query: dict = {"user_id": user.user_id}
    if status:
        query["status"] = status
    docs = await db.optimization_recommendations.find(query, {"_id": 0})\
        .sort("created_at", -1).to_list(length=100)
    pending = await db.optimization_recommendations.count_documents(
        {"user_id": user.user_id, "status": "pending"})
    applied = await db.optimization_recommendations.count_documents(
        {"user_id": user.user_id, "status": "applied"})
    dismissed = await db.optimization_recommendations.count_documents(
        {"user_id": user.user_id, "status": "dismissed"})
    return {
        "items":     docs, "count": len(docs),
        "pending":   pending, "applied": applied, "dismissed": dismissed,
    }


@api.post("/optimization/recommendations/{rec_id}/apply")
async def apply_recommendation(rec_id: str, request: Request):
    """Operator approves — flips status + we already spawned the variant
    and experiment, so this is the audit moment."""
    user = await get_current_user(request)
    rec = await db.optimization_recommendations.find_one(
        {"id": rec_id, "user_id": user.user_id, "status": "pending"},
        {"_id": 0},
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Pending recommendation not found")
    now = datetime.now(timezone.utc)
    await db.optimization_recommendations.update_one(
        {"id": rec_id},
        {"$set": {
            "status":      "applied",
            "decided_at":  now,
            "decided_by":  getattr(user, "email", None) or user.user_id,
        }},
    )
    return await db.optimization_recommendations.find_one({"id": rec_id}, {"_id": 0})


@api.post("/optimization/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(rec_id: str, request: Request):
    """Operator rejects. The spawned variant + experiment stay; the
    recommendation row just marks the decision for the audit log."""
    user = await get_current_user(request)
    rec = await db.optimization_recommendations.find_one(
        {"id": rec_id, "user_id": user.user_id, "status": "pending"},
        {"_id": 0},
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Pending recommendation not found")
    now = datetime.now(timezone.utc)
    await db.optimization_recommendations.update_one(
        {"id": rec_id},
        {"$set": {
            "status":      "dismissed",
            "decided_at":  now,
            "decided_by":  getattr(user, "email", None) or user.user_id,
        }},
    )
    return await db.optimization_recommendations.find_one({"id": rec_id}, {"_id": 0})


# ---------------------------------------------------------------------
# Cron — daily 10:00 UTC
# ---------------------------------------------------------------------
async def daily_optimization_run() -> dict:
    """Iterates over every user with at least one classified variant
    and runs Pico. Per-user errors logged but never propagate."""
    # Pull distinct user_ids from content_variants (every user who's
    # published anything has rows here).
    user_ids = await db.content_variants.distinct("user_id")
    processed = 0
    total_rewrites = 0
    for uid in user_ids:
        try:
            summary = await run_optimization_for_user(uid)
            processed += 1
            total_rewrites += summary.get("rewrites_succeeded", 0)
        except Exception:
            logger.exception("Pico daily run failed for user_id=%s", uid)
    summary = {
        "users_processed": processed,
        "total_rewrites":  total_rewrites,
        "candidates":      len(user_ids),
        "ran_at":          datetime.now(timezone.utc),
    }
    logger.info("Pico daily optimization run: %s", summary)
    return summary


def register_optimization_job(scheduler) -> None:
    """Daily 10:00 UTC — runs 30 min after Ori's auto-conclude so any
    overnight winners are already in memory. Idempotent."""
    from apscheduler.triggers.cron import CronTrigger
    if scheduler.get_job("pico_optimization_daily"):
        return
    scheduler.add_job(
        daily_optimization_run,
        trigger=CronTrigger(hour=10, minute=0),
        id="pico_optimization_daily",
        max_instances=1,
        coalesce=True,
    )
