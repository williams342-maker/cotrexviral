"""Experiments — head-to-head content variant testing, owned by Ori.

Lets the operator (or, eventually, Atlas) declare: "I think variant A
will beat variant B on engagements". The system polls live perf metrics,
and on conclude, Ori picks the winner and writes the learning to memory
so future briefs can retrieve it. This is how the team's knowledge
becomes durable — losing variants are forgotten, winning patterns stick.

Status lifecycle:
  running → completed       (clear winner ≥ MIN_MARGIN_PCT)
  running → inconclusive    (margin too small — no memory write)

Metric enum maps to the `performance_rollups.{window}.{field}` shape.
Default window is `all_time` so longer-running experiments accumulate
their full sample. Future: opt-in `last_7d` window.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from routes.memory import remember

logger = logging.getLogger(__name__)


# Supported comparison metrics. Each maps to a rollup field that the
# `recompute_rollup` job already populates (under `windows.all_time.*`).
# `ctr` is a ratio — we compare its rounded value directly.
SUPPORTED_METRICS = {
    "engagements": "Total engagements (likes + comments + shares + saves)",
    "impressions": "Total impressions",
    "clicks":      "Total clicks",
    "reach":       "Unique reach",
    "ctr":         "Click-through rate (clicks / impressions)",
}

# Minimum percentage delta between winner and loser before we call a winner.
# Anything tighter is declared inconclusive — protects the memory layer
# from being polluted with statistical noise that could pollute future
# briefs ("variant A won by 2%" is not a signal worth remembering).
MIN_MARGIN_PCT = 10.0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
async def _variant_live(variant_id: str, metric: str) -> dict:
    """Returns the variant's live metric value + a snapshot of related
    rollup numbers. Missing data → zeroes (so the UI can still render
    a fresh experiment with no traffic yet)."""
    roll = await db.performance_rollups.find_one(
        {"variant_id": variant_id},
        {"_id": 0, "windows.all_time": 1, "platform": 1},
    )
    win = (roll or {}).get("windows", {}).get("all_time", {}) or {}
    value = float(win.get(metric) or 0)
    return {
        "value":       value,
        "impressions": int(win.get("impressions") or 0),
        "engagements": int(win.get("engagements") or 0),
        "clicks":      int(win.get("clicks") or 0),
        "reach":       int(win.get("reach") or 0),
        "ctr":         float(win.get("ctr") or 0),
        "samples":     int(win.get("samples") or 0),
        "platform":    (roll or {}).get("platform"),
    }


async def _variant_label(variant_id: str) -> dict:
    """Returns {id, platform, body_preview, content_item_id} for the
    variant — used in the UI + the memory write so a future read can
    cite which variant won."""
    v = await db.content_variants.find_one(
        {"id": variant_id},
        {"_id": 0, "id": 1, "platform": 1, "body": 1, "content_item_id": 1},
    )
    if not v:
        return {"id": variant_id, "platform": None, "body_preview": None,
                "content_item_id": None, "missing": True}
    body = (v.get("body") or "").strip()
    return {
        "id":              variant_id,
        "platform":        v.get("platform"),
        "body_preview":    (body[:140] + "…") if len(body) > 140 else body,
        "content_item_id": v.get("content_item_id"),
    }


def _margin_pct(winner: float, loser: float) -> float:
    """% by which winner exceeds loser. Returns 0 if loser is 0 (avoid div-by-zero)."""
    if loser <= 0:
        # When the loser has zero baseline, anything > 0 is "infinite" uplift —
        # we cap at 100% for display sanity but still call a winner.
        return 100.0 if winner > 0 else 0.0
    return round((winner - loser) / loser * 100, 1)


async def _hydrate(doc: dict) -> dict:
    """Attach live metric snapshots + variant labels to a stored row."""
    out = dict(doc)
    out.pop("_id", None)
    metric = out["metric"]
    a_live = await _variant_live(out["variant_a_id"], metric)
    b_live = await _variant_live(out["variant_b_id"], metric)
    a_meta = await _variant_label(out["variant_a_id"])
    b_meta = await _variant_label(out["variant_b_id"])
    leader = (
        "a" if a_live["value"] > b_live["value"]
        else "b" if b_live["value"] > a_live["value"]
        else "tie"
    )
    if leader == "tie":
        live_margin = 0.0
    elif leader == "a":
        live_margin = _margin_pct(a_live["value"], b_live["value"])
    else:
        live_margin = _margin_pct(b_live["value"], a_live["value"])
    out["variant_a"] = {**a_meta, **a_live}
    out["variant_b"] = {**b_meta, **b_live}
    out["live_leader"] = leader
    out["live_margin_pct"] = live_margin
    out["can_conclude"] = (out["status"] == "running") and (
        leader != "tie" and live_margin >= MIN_MARGIN_PCT
    )
    return out


# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
class ExperimentIn(BaseModel):
    name:         str = Field(..., min_length=3, max_length=140)
    hypothesis:   Optional[str] = Field(None, max_length=600)
    variant_a_id: str
    variant_b_id: str
    metric:       str = "engagements"


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.get("/experiments/metrics")
async def list_experiment_metrics(request: Request):
    """Metric enum for the create-experiment dropdown."""
    await get_current_user(request)
    return {
        "metrics": [{"id": k, "label": v} for k, v in SUPPORTED_METRICS.items()],
        "min_margin_pct": MIN_MARGIN_PCT,
    }


@api.get("/variants/recent")
async def recent_variants(request: Request, limit: int = 50):
    """Recent content_variants for this user — used to populate the
    variant pickers in the create-experiment modal. Returns the body
    + platform + ids so the UI can render a readable dropdown."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 200))
    docs = await db.content_variants.find(
        {"user_id": user.user_id},
        {"_id": 0, "id": 1, "platform": 1, "body": 1, "status": 1,
         "content_item_id": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(length=limit)
    return {"items": docs, "count": len(docs)}


@api.post("/experiments")
async def create_experiment(payload: ExperimentIn, request: Request):
    user = await get_current_user(request)
    if payload.metric not in SUPPORTED_METRICS:
        raise HTTPException(status_code=400, detail=f"Unknown metric: {payload.metric}")
    if payload.variant_a_id == payload.variant_b_id:
        raise HTTPException(status_code=400, detail="Variants must differ")

    # Verify the variants exist + belong to this user — prevents an
    # operator from comparing variants from a different brand by id.
    found = await db.content_variants.find(
        {"id": {"$in": [payload.variant_a_id, payload.variant_b_id]},
         "user_id": user.user_id},
        {"_id": 0, "id": 1},
    ).to_list(length=4)
    if len({v["id"] for v in found}) != 2:
        raise HTTPException(status_code=404, detail="One or both variants not found for this user")

    now = datetime.now(timezone.utc)
    doc = {
        "id":             uuid.uuid4().hex,
        "user_id":        user.user_id,
        "name":           payload.name.strip(),
        "hypothesis":     (payload.hypothesis or "").strip() or None,
        "variant_a_id":   payload.variant_a_id,
        "variant_b_id":   payload.variant_b_id,
        "metric":         payload.metric,
        "status":         "running",
        "started_at":     now,
        "ended_at":       None,
        "winner_variant_id":  None,
        "winner_margin_pct":  None,
        "conclusion_text":    None,
        "memory_id":          None,
        "owner_agent":    "ori",
        "created_at":     now,
        "updated_at":     now,
    }
    await db.experiments.insert_one(doc)
    return await _hydrate(doc)


@api.get("/experiments")
async def list_experiments(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query: dict = {"user_id": user.user_id}
    if status:
        query["status"] = status
    docs = await db.experiments.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    items = [await _hydrate(d) for d in docs]
    running = [e for e in items if e["status"] == "running"]
    completed = [e for e in items if e["status"] == "completed"]
    inconclusive = [e for e in items if e["status"] == "inconclusive"]
    avg_margin = (
        round(sum(e["winner_margin_pct"] or 0 for e in completed) / len(completed), 1)
        if completed else 0.0
    )
    return {
        "items":             items,
        "count":             len(items),
        "running_count":     len(running),
        "completed_count":   len(completed),
        "inconclusive_count": len(inconclusive),
        "avg_winner_margin_pct": avg_margin,
    }


@api.get("/experiments/{exp_id}")
async def get_experiment(exp_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.experiments.find_one(
        {"id": exp_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return await _hydrate(doc)


@api.post("/experiments/{exp_id}/conclude")
async def conclude_experiment(exp_id: str, request: Request):
    """Ori's moment. Picks a winner if the margin is decisive, writes the
    learning to memory (kind=experiment_winner) so future briefs retrieve
    it, and marks the experiment terminal. Inconclusive when neither
    variant clears the threshold."""
    user = await get_current_user(request)
    doc = await db.experiments.find_one(
        {"id": exp_id, "user_id": user.user_id, "status": "running"},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Running experiment not found")

    metric = doc["metric"]
    a_live = await _variant_live(doc["variant_a_id"], metric)
    b_live = await _variant_live(doc["variant_b_id"], metric)
    a_label = await _variant_label(doc["variant_a_id"])
    b_label = await _variant_label(doc["variant_b_id"])

    now = datetime.now(timezone.utc)
    if a_live["value"] == b_live["value"]:
        # Hard tie. No winner.
        await db.experiments.update_one(
            {"id": exp_id},
            {"$set": {
                "status": "inconclusive", "ended_at": now, "updated_at": now,
                "conclusion_text": f"Tie on {metric} ({a_live['value']:.1f} vs {b_live['value']:.1f}).",
            }},
        )
    else:
        winner_key = "a" if a_live["value"] > b_live["value"] else "b"
        winner_id = doc["variant_a_id"] if winner_key == "a" else doc["variant_b_id"]
        loser_id  = doc["variant_b_id"] if winner_key == "a" else doc["variant_a_id"]
        w_live    = a_live if winner_key == "a" else b_live
        l_live    = b_live if winner_key == "a" else a_live
        w_label   = a_label if winner_key == "a" else b_label
        l_label   = b_label if winner_key == "a" else a_label
        margin    = _margin_pct(w_live["value"], l_live["value"])

        if margin < MIN_MARGIN_PCT:
            await db.experiments.update_one(
                {"id": exp_id},
                {"$set": {
                    "status": "inconclusive", "ended_at": now, "updated_at": now,
                    "winner_margin_pct": margin,
                    "conclusion_text": (
                        f"Margin only {margin:.1f}% on {metric} — below the "
                        f"{MIN_MARGIN_PCT:.0f}% threshold. No winner recorded."
                    ),
                }},
            )
        else:
            # Decisive winner — write learning to memory + mark completed.
            memory_text = (
                f"Experiment '{doc['name']}': {w_label['platform']} variant "
                f"\"{(w_label['body_preview'] or '').strip()}\" beat "
                f"\"{(l_label['body_preview'] or '').strip()}\" on {metric} "
                f"by {margin:.1f}% ({w_live['value']:.0f} vs {l_live['value']:.0f})."
            )
            if doc.get("hypothesis"):
                memory_text += f" Hypothesis: {doc['hypothesis']}"

            mem_id = await remember(
                user.user_id,
                kind="experiment_winner",
                text=memory_text,
                meta={
                    "experiment_id":  exp_id,
                    "winner_variant_id": winner_id,
                    "loser_variant_id":  loser_id,
                    "metric":         metric,
                    "margin_pct":     margin,
                    "winner_value":   w_live["value"],
                    "loser_value":    l_live["value"],
                },
                dedupe_key=f"experiment:{exp_id}",
            )
            await db.experiments.update_one(
                {"id": exp_id},
                {"$set": {
                    "status":            "completed",
                    "ended_at":          now,
                    "updated_at":        now,
                    "winner_variant_id": winner_id,
                    "winner_margin_pct": margin,
                    "conclusion_text":   memory_text,
                    "memory_id":         mem_id,
                }},
            )

    fresh = await db.experiments.find_one({"id": exp_id}, {"_id": 0})
    return await _hydrate(fresh)


@api.delete("/experiments/{exp_id}")
async def delete_experiment(exp_id: str, request: Request):
    """Hard delete. Memory rows written by a prior conclude stay — those
    are the durable learnings and shouldn't disappear because the
    experiment record was archived."""
    user = await get_current_user(request)
    res = await db.experiments.delete_one({"id": exp_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"ok": True}


# ---------------------------------------------------------------------
# Standup integration — Ori cites the latest winners
# ---------------------------------------------------------------------
async def gather_experiment_facts(user_id: str, limit: int = 5) -> dict:
    """Returns a small dict the standup generator can paste into Ori's
    persona prompt. The Monday standup uses this to keep Ori's voice
    grounded in actual learnings instead of speculation."""
    recent = await db.experiments.find(
        {"user_id": user_id, "status": {"$in": ["completed", "inconclusive"]}},
        {"_id": 0, "name": 1, "status": 1, "winner_margin_pct": 1,
         "conclusion_text": 1, "metric": 1, "ended_at": 1},
    ).sort("ended_at", -1).to_list(length=limit)
    running = await db.experiments.count_documents(
        {"user_id": user_id, "status": "running"}
    )
    return {
        "running_experiments": running,
        "recent_results":      recent,
    }
