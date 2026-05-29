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
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


DEFAULT_THRESHOLD = 60.0

ACTIVITY_SCORES = {"high": 95, "medium": 65, "low": 35}


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


def score_lead(lead: dict, target_niche: Optional[str] = None) -> dict:
    q = _score_quality(lead)
    g = _score_growth(lead)
    f = _score_fit(lead, target_niche)
    e = _score_engagement(lead)
    # Weighted composite — sums to 1.0
    composite = round(0.30 * q + 0.30 * g + 0.25 * f + 0.15 * e, 1)
    return {
        "seller_score":   composite,
        "score_breakdown": {
            "quality":      q,
            "growth":       g,
            "marketplace_fit": f,
            "engagement":   e,
        },
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
    rejected = 0
    for lead in leads:
        s = score_lead(lead, target_niche)
        new_stage = "qualified" if s["seller_score"] >= threshold else "rejected"
        updates = {
            "seller_score":    s["seller_score"],
            "score_breakdown": s["score_breakdown"],
            "stage":           new_stage,
            "updated_at":      datetime.now(timezone.utc),
        }
        if new_stage == "qualified" and not lead.get("qualified_at"):
            updates["qualified_at"] = datetime.now(timezone.utc)
        await db.seller_leads.update_one({"id": lead["id"]}, {"$set": updates})
        scored.append({"id": lead["id"], "score": s["seller_score"], "stage": new_stage})
        if new_stage == "qualified":
            accepted += 1
        else:
            rejected += 1

    # Audit
    await db.qualification_runs.insert_one({
        "id":          uuid.uuid4().hex,
        "user_id":     user.user_id,
        "mission_id":  payload.mission_id,
        "threshold":   threshold,
        "target_niche": target_niche,
        "scored":      len(scored),
        "accepted":    accepted,
        "rejected":    rejected,
        "created_at":  datetime.now(timezone.utc),
    })

    return {
        "mission_id": payload.mission_id,
        "scored":     len(scored),
        "accepted":   accepted,
        "rejected":   rejected,
        "threshold":  threshold,
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
    return {"lead_id": lead_id, **score_lead(doc, target)}
