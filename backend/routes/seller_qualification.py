"""Qualification Engine — scores discovered leads + advances stage.

Computes 4 sub-scores per seller_lead:

  Quality Score       (0-100): branding signals — has website, has socials,
                                product photos OK, plausible business name.
  Growth Potential    (0-100): activity hints — estimated_activity bucket,
                                product category breadth, market signals.
  Marketplace Fit     (0-100): niche-match — does this seller's niche
                                align with target niche from mission?
  Engagement Score    (0-100): platform mix — multi-platform sellers score
                                higher (more channels to reach).

`seller_score` = weighted average (Quality 30% / Growth 30% / Fit 25% /
Engagement 15%).

Leads with score ≥ `accept_threshold` advance to stage='qualified'.
Below → stage='rejected'. Threshold defaults to 60 and is overridable
per Mission via `mission.qualification_threshold`.

The engine is deterministic + fast (no LLM call). LLM enrichment is an
optional Phase-2 polish; the current scoring is enough to make the rest
of the pipeline (Outreach → Onboarding → Retention) testable.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


DEFAULT_THRESHOLD = 60.0
# Below DEFAULT_THRESHOLD but ≥ this → routed to manual review queue.
REVIEW_THRESHOLD  = 45.0

ACTIVITY_SCORES = {"high": 95, "medium": 65, "low": 35}


def _confidence_band(score: float, threshold: float,
                       review_floor: float = REVIEW_THRESHOLD) -> str:
    """Three-band routing:
        score ≥ threshold              → 'high'   (auto-qualified)
        review_floor ≤ score < thresh  → 'medium' (manual review queue)
        score < review_floor           → 'low'    (auto-rejected)
    """
    if score >= threshold:
        return "high"
    if score >= review_floor:
        return "medium"
    return "low"


_BAND_STAGE = {"high": "qualified", "medium": "review", "low": "rejected"}


def _collect_signals(lead: dict, target_niche: Optional[str],
                       breakdown: dict) -> list[dict]:
    """Itemized why-this-score signals for the Prospect Intelligence
    Card. Each entry: {label, weight, verdict ('positive'|'neutral'|
    'negative'), value}. Used by the UI to render the 'Signals' list."""
    socials = lead.get("socials") or {}
    cats    = lead.get("product_categories") or []
    activity = (lead.get("estimated_activity") or "").lower()
    signals: list[dict] = []

    signals.append({
        "label":   "Activity",
        "weight":  30,
        "verdict": "positive" if activity == "high"
                    else "neutral" if activity == "medium"
                    else "negative",
        "value":   activity or "unknown",
    })
    signals.append({
        "label":   "Product breadth",
        "weight":  10,
        "verdict": "positive" if len(cats) >= 4
                    else "neutral" if len(cats) >= 2 else "negative",
        "value":   f"{len(cats)} categories",
    })
    signals.append({
        "label":   "Website",
        "weight":  15,
        "verdict": "positive" if lead.get("website") else "negative",
        "value":   lead.get("website") or "missing",
    })
    signals.append({
        "label":   "Social presence",
        "weight":  20,
        "verdict": "positive" if len(socials) >= 2
                    else "neutral" if len(socials) >= 1 else "negative",
        "value":   ", ".join(socials.keys()) if socials else "none",
    })
    if target_niche:
        signals.append({
            "label":   "Niche match",
            "weight":  25,
            "verdict": "positive" if breakdown["marketplace_fit"] >= 70
                        else "neutral" if breakdown["marketplace_fit"] >= 40
                        else "negative",
            "value":   f"{breakdown['marketplace_fit']}/100",
        })
    return signals


_PAIN_POINTS = {
    "etsy":     ["High platform fees (6.5% + ads)",
                  "Algorithmic visibility throttling",
                  "Limited brand recognition"],
    "shopify":  ["High monthly app stack costs",
                  "Marketing spend pressure"],
    "instagram":["Algorithm reach decline",
                  "Conversion-to-sale leakage"],
    "pinterest":["Slow audience growth without paid push"],
    "tiktok":   ["Inconsistent organic reach"],
}


def _build_prospect_card(lead: dict, target_niche: Optional[str],
                           breakdown: dict, composite: float,
                           band: str) -> dict:
    """Build the Prospect Intelligence Card fields: why_match,
    pain_points, outreach_angle, likelihood_to_convert. Pure-heuristic
    so this stays cheap + deterministic (no LLM dependency)."""
    source = (lead.get("source") or "").lower()
    activity = (lead.get("estimated_activity") or "").lower()
    cats     = lead.get("product_categories") or []

    why_match: list[str] = []
    if breakdown.get("marketplace_fit", 0) >= 70 and target_niche:
        why_match.append(f"Niche aligns with '{target_niche}'")
    if activity in ("high", "medium"):
        why_match.append(f"{activity.title()} activity (estimated revenue match)")
    if breakdown.get("quality", 0) >= 70:
        why_match.append("Strong branding signals (website + socials present)")
    if len(cats) >= 2:
        why_match.append(f"Product breadth across {len(cats)} categories")
    if breakdown.get("engagement", 0) >= 70:
        why_match.append("Multi-channel presence — multiple touch surfaces")

    pain_points = _PAIN_POINTS.get(source, [])[:2] or [
        "Marketing operations fragmentation across tools",
    ]
    if activity == "high":
        pain_points = pain_points[:1] + [
            "Scaling content production without losing brand voice",
        ]

    # Outreach angle: pick the strongest signal.
    if breakdown.get("marketplace_fit", 0) >= 80 and target_niche:
        outreach_angle = (
            f"Lead with the {target_niche} niche match — show one campaign "
            "asset you've already produced for a similar seller.")
    elif activity == "high":
        outreach_angle = (
            "Lead with scale — '95% of our $5k/mo Etsy customers cut "
            "campaign-build time from 14 days to 1 day'.")
    elif breakdown.get("quality", 0) < 50:
        outreach_angle = (
            "Lead with brand setup — offer free brand voice extraction "
            "+ a starter campaign in exchange for a 15-min intro.")
    else:
        outreach_angle = (
            "Lead with platform-fee pain — quantify $X saved per month "
            "vs Etsy ad spend using your existing case study.")

    # Likelihood-to-convert: composite + activity + niche fit.
    base = composite / 100.0
    if activity == "high":
        base += 0.05
    if breakdown.get("marketplace_fit", 0) >= 80:
        base += 0.05
    likelihood = max(0.0, min(1.0, base))

    return {
        "why_match":              why_match[:4],
        "pain_points":            pain_points[:3],
        "outreach_angle":         outreach_angle,
        "likelihood_to_convert":  round(likelihood, 2),
        "confidence_band":        band,
    }


# ---------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------
class QualifyRun(BaseModel):
    mission_id:        str
    threshold:         Optional[float] = None
    limit:             int = 200    # max leads to score in this pass
    requalify:         bool = False  # if False, only score stage='discovered'


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------
def _score_quality(lead: dict) -> int:
    """Branding completeness signals."""
    s = 40  # base
    if lead.get("website"):
        s += 20
    socials = lead.get("socials") or {}
    if len(socials) >= 1:
        s += 10
    if len(socials) >= 2:
        s += 10
    name = (lead.get("business_name") or "").strip()
    # Plausible business names are >=3 chars + contain a word + not all caps.
    if len(name) >= 3 and re.search(r"[A-Za-z]", name):
        s += 10
    # Heuristic penalty for "test"/"sample" placeholder names.
    if re.search(r"\b(test|sample|fixture|demo)\b", name, re.I):
        s -= 15
    return max(0, min(100, s))


def _score_growth(lead: dict) -> int:
    activity = (lead.get("estimated_activity") or "").lower()
    s = ACTIVITY_SCORES.get(activity, 50)
    cats = lead.get("product_categories") or []
    # Sellers with 2+ product categories show breadth → growth potential.
    if len(cats) >= 2:
        s += 8
    if len(cats) >= 4:
        s += 7
    return max(0, min(100, s))


def _score_fit(lead: dict, target_niche: Optional[str]) -> int:
    if not target_niche:
        return 50  # neutral when no target niche on the mission
    target = target_niche.lower().strip()
    niche  = (lead.get("niche") or "").lower().strip()
    cats   = " ".join(lead.get("product_categories") or []).lower()
    haystack = f"{niche} {cats}"

    # Exact match → strong fit.
    if niche == target:
        return 95
    if target in haystack:
        return 85
    # Token-level overlap → partial fit.
    target_tokens = {t for t in re.split(r"\W+", target) if len(t) >= 3}
    hay_tokens    = {t for t in re.split(r"\W+", haystack) if len(t) >= 3}
    if target_tokens and hay_tokens:
        overlap = len(target_tokens & hay_tokens) / max(1, len(target_tokens))
        return int(round(20 + overlap * 60))
    return 25


def _score_engagement(lead: dict) -> int:
    """Multi-platform presence + source diversity."""
    socials = lead.get("socials") or {}
    s = 30 + min(50, len(socials) * 15)
    # Bonus if discovered on a high-trust platform.
    if lead.get("source") in ("etsy", "shopify"):
        s += 10
    return max(0, min(100, s))


def score_lead(lead: dict, target_niche: Optional[str] = None,
                 threshold: float = DEFAULT_THRESHOLD) -> dict:
    q = _score_quality(lead)
    g = _score_growth(lead)
    f = _score_fit(lead, target_niche)
    e = _score_engagement(lead)
    # Weighted composite — sums to 1.0
    composite = round(0.30 * q + 0.30 * g + 0.25 * f + 0.15 * e, 1)
    breakdown = {
        "quality":           q,
        "growth":            g,
        "marketplace_fit":   f,
        "engagement":        e,
    }
    band = _confidence_band(composite, threshold)
    signals = _collect_signals(lead, target_niche, breakdown)
    card = _build_prospect_card(lead, target_niche, breakdown, composite, band)
    # Confidence percentage: composite gives the raw 0–100 score. Convert
    # to a friendlier "Qualification Confidence: 87%" representation by
    # showing the composite directly (already a 0–100 normalized number).
    return {
        "seller_score":     composite,
        "score_breakdown":  breakdown,
        "confidence":       composite,        # alias for UI clarity
        "confidence_band":  band,
        "signals":          signals,
        "prospect_card":    card,
    }


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@api.post("/seller-qualification/run")
async def run_qualification(payload: QualifyRun, request: Request):
    """Score every `discovered` lead for the mission. Above-threshold
    flips to `qualified`, below to `rejected`. Idempotent — pass
    `requalify=True` to re-score already-scored leads (useful when the
    target niche or threshold changes)."""
    user = await get_current_user(request)
    mission = await db.missions.find_one(
        {"id": payload.mission_id, "user_id": user.user_id})
    if not mission:
        raise HTTPException(404, "Mission not found")

    threshold = payload.threshold
    if threshold is None:
        threshold = float(mission.get("qualification_threshold") or DEFAULT_THRESHOLD)

    target_niche = mission.get("seller_target_niche") or mission.get("metric")

    # Pull candidates
    q: dict = {"user_id": user.user_id, "mission_id": payload.mission_id}
    if not payload.requalify:
        q["stage"] = "discovered"
    cursor = db.seller_leads.find(q).limit(min(1000, max(1, payload.limit)))
    leads = await cursor.to_list(length=payload.limit)

    scored: List[dict] = []
    accepted = 0
    review   = 0
    rejected = 0
    for lead in leads:
        s = score_lead(lead, target_niche, threshold=threshold)
        new_stage = _BAND_STAGE[s["confidence_band"]]
        updates = {
            "seller_score":      s["seller_score"],
            "score_breakdown":   s["score_breakdown"],
            "confidence":        s["confidence"],
            "confidence_band":   s["confidence_band"],
            "signals":           s["signals"],
            "prospect_card":     s["prospect_card"],
            "stage":             new_stage,
            "updated_at":        datetime.now(timezone.utc),
        }
        if new_stage == "qualified" and not lead.get("qualified_at"):
            updates["qualified_at"] = datetime.now(timezone.utc)
        if new_stage == "review" and not lead.get("review_queued_at"):
            updates["review_queued_at"] = datetime.now(timezone.utc)
        await db.seller_leads.update_one({"id": lead["id"]}, {"$set": updates})
        scored.append({"id":     lead["id"],
                        "score":  s["seller_score"],
                        "band":   s["confidence_band"],
                        "stage":  new_stage})
        if new_stage == "qualified":
            accepted += 1
        elif new_stage == "review":
            review += 1
        else:
            rejected += 1

    # Audit
    await db.qualification_runs.insert_one({
        "id":           uuid.uuid4().hex,
        "user_id":      user.user_id,
        "mission_id":   payload.mission_id,
        "threshold":    threshold,
        "review_floor": REVIEW_THRESHOLD,
        "target_niche": target_niche,
        "scored":       len(scored),
        "accepted":     accepted,
        "review":       review,
        "rejected":     rejected,
        "created_at":   datetime.now(timezone.utc),
    })

    return {
        "mission_id": payload.mission_id,
        "scored":     len(scored),
        "accepted":   accepted,
        "review":     review,
        "rejected":   rejected,
        "threshold":  threshold,
        "review_floor": REVIEW_THRESHOLD,
        "results":    scored,
    }


@api.get("/seller-qualification/preview/{lead_id}")
async def preview_lead_score(lead_id: str, request: Request,
                              target_niche: Optional[str] = None):
    """Returns the current score breakdown for a lead — used by the
    Qualified Sellers UI to render a per-lead scoring tooltip."""
    user = await get_current_user(request)
    doc = await db.seller_leads.find_one({"id": lead_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    target = target_niche
    if not target and doc.get("mission_id"):
        m = await db.missions.find_one({"id": doc["mission_id"]})
        if m:
            target = m.get("seller_target_niche") or m.get("metric")
    threshold = DEFAULT_THRESHOLD
    if doc.get("mission_id"):
        m = await db.missions.find_one({"id": doc["mission_id"]})
        if m:
            threshold = float(m.get("qualification_threshold") or DEFAULT_THRESHOLD)
    return {"lead_id": lead_id, **score_lead(doc, target, threshold=threshold)}


# ---------------------------------------------------------------------
# Review queue + Recommended Actions
# ---------------------------------------------------------------------
class ReviewDecision(BaseModel):
    decision: str        # 'promote' | 'reject'
    note:     Optional[str] = Field(default=None, max_length=2000)


@api.get("/seller-qualification/review-queue")
async def review_queue(request: Request, mission_id: Optional[str] = None,
                          limit: int = 100):
    """List leads currently in the manual review queue (stage='review').
    Newest first; filtered by mission when supplied."""
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id, "stage": "review"}
    if mission_id:
        q["mission_id"] = mission_id
    cursor = db.seller_leads.find(q, {"_id": 0}) \
                            .sort("review_queued_at", -1) \
                            .limit(max(1, min(int(limit or 100), 500)))
    rows = await cursor.to_list(length=limit)
    return {"queue": rows, "count": len(rows)}


@api.post("/seller-qualification/review/{lead_id}")
async def decide_review(lead_id: str, payload: ReviewDecision,
                          request: Request):
    """Operator decision on a review-queued lead — promote → qualified
    (will enter outreach), reject → rejected. Records the operator's
    note so the next training pass can use it for confidence-tuning."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one(
        {"id": lead_id, "user_id": user.user_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.get("stage") != "review":
        raise HTTPException(409, f"Lead is not in review (stage={lead.get('stage')}).")
    if payload.decision not in ("promote", "reject"):
        raise HTTPException(400, "decision must be 'promote' or 'reject'.")
    new_stage = "qualified" if payload.decision == "promote" else "rejected"
    now = datetime.now(timezone.utc)
    updates = {
        "stage":            new_stage,
        "review_decision":  payload.decision,
        "review_note":      payload.note,
        "reviewed_at":      now,
        "reviewed_by":      user.user_id,
        "updated_at":       now,
    }
    if new_stage == "qualified" and not lead.get("qualified_at"):
        updates["qualified_at"] = now
    await db.seller_leads.update_one({"id": lead_id}, {"$set": updates})
    return {"ok": True, "id": lead_id, "stage": new_stage}


@api.get("/seller-qualification/recommended-action")
async def recommended_action(request: Request, mission_id: str):
    """Returns the executive-summary 'Recommended Action' for a mission:
    'Contact N immediately · Reason: …' framing instead of a raw count.
    Picks from the highest-confidence band only and explains why."""
    user = await get_current_user(request)
    mission = await db.missions.find_one(
        {"id": mission_id, "user_id": user.user_id})
    if not mission:
        raise HTTPException(404, "Mission not found")

    # Counts per band among NOT-yet-contacted qualified leads.
    pipeline = [
        {"$match": {"user_id": user.user_id, "mission_id": mission_id,
                     "stage":   {"$in": ["qualified", "review", "rejected"]}}},
        {"$group": {"_id": "$confidence_band", "count": {"$sum": 1},
                      "top_score": {"$max": "$seller_score"}}},
    ]
    counts = {r["_id"]: r async for r in db.seller_leads.aggregate(pipeline)}
    high   = counts.get("high",   {"count": 0, "top_score": 0})
    medium = counts.get("medium", {"count": 0, "top_score": 0})
    low    = counts.get("low",    {"count": 0, "top_score": 0})

    target_niche = mission.get("seller_target_niche") or mission.get("metric") or "your target niche"

    # Choose the strongest call-to-action available.
    if high["count"] >= 3:
        action  = "contact_high_confidence"
        verb    = "Contact"
        n       = high["count"]
        what    = f"{n} high-confidence sellers immediately"
        reason  = (f"They cleared the auto-qualification threshold with "
                    f"top score {high['top_score']:.0f}/100 and match "
                    f"the {target_niche} segment most likely to convert.")
    elif (high["count"] + medium["count"]) >= 3:
        action  = "review_medium_queue"
        verb    = "Review"
        n       = medium["count"]
        what    = f"{n} medium-confidence leads in the review queue"
        reason  = (f"Only {high['count']} hit auto-qualify — promoting "
                    f"the best medium-confidence prospects will widen "
                    f"outreach volume without sacrificing quality.")
    else:
        action  = "expand_discovery"
        verb    = "Expand"
        n       = 0
        what    = "discovery sources to widen the funnel"
        reason  = (f"Only {high['count'] + medium['count']} qualified/"
                    "review-stage leads available; add a new source or "
                    "loosen the target niche to surface more candidates.")

    return {
        "mission_id": mission_id,
        "action":     action,
        "verb":       verb,
        "count":      n,
        "summary":    f"{verb} {what}",
        "reason":     reason,
        "counts":     {"high":   high["count"],
                        "medium": medium["count"],
                        "low":    low["count"]},
    }
