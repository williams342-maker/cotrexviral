"""Seller-acquisition leads — the pipeline objects for the Seller OS.

A `seller_lead` is a candidate marketplace seller (Etsy maker, Shopify
store, Instagram creator, etc.) that the Discovery Scout has surfaced
for a given Mission. The lead moves through a clear pipeline:

   discovered → qualified → outreached → interested → onboarding → active
                ↘ rejected (low score) ↘ unresponsive ↘ churned

This is the canonical source of truth for Seller-OS funnel KPIs (Mission
Dashboard's 8 stat cards). All Discovery / Qualification / Outreach /
Onboarding / Retention modules write to this single collection.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# Pipeline stages — every lead is in exactly one. Order matters: it
# defines the funnel left→right on the Mission Dashboard.
STAGES = (
    "discovered",
    "qualified",
    "outreached",
    "interested",
    "onboarding",
    "active",
    "rejected",
    "unresponsive",
    "churned",
)
FUNNEL_STAGES = ("discovered", "qualified", "outreached", "interested",
                 "onboarding", "active")

# Supported discovery sources (Phase 1 backs 3; rest stub-return fixtures).
SOURCES = ("etsy", "shopify", "instagram", "pinterest", "facebook",
           "tiktok", "reddit", "google_search", "google_maps")


# ---------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------
class SellerLeadCreate(BaseModel):
    mission_id:    Optional[str] = None
    business_name: str = Field(..., min_length=1, max_length=200)
    website:       Optional[str] = None
    email:         Optional[str] = None    # delivery target for lifecycle emails
    source:        str           # one of SOURCES
    platform:      Optional[str] = None    # the seller's primary platform
    niche:         Optional[str] = None    # "woodworking", "laser-engraving"
    location:      Optional[str] = None    # free-form city/region
    socials:       Optional[dict] = None   # {instagram, facebook, tiktok, …}
    product_categories: Optional[List[str]] = None
    estimated_activity: Optional[str] = None  # "high"/"medium"/"low" or raw string
    raw_signal:    Optional[dict] = None   # source-specific payload


class SellerLeadUpdate(BaseModel):
    stage:    Optional[str] = None
    notes:    Optional[str] = None
    email:    Optional[str] = None
    seller_score: Optional[float] = None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at", "discovered_at", "qualified_at",
              "outreached_at", "responded_at", "onboarded_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def funnel_for_mission(user_id: str, mission_id: Optional[str] = None) -> dict:
    """Aggregate seller_leads counts by stage. Backs the Mission Dashboard's
    8 KPI cards. If `mission_id` is None, returns the user's grand total."""
    match: dict = {"user_id": user_id}
    if mission_id:
        match["mission_id"] = mission_id

    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
    ]
    counts = {s: 0 for s in STAGES}
    async for r in db.seller_leads.aggregate(pipeline):
        if r["_id"] in counts:
            counts[r["_id"]] = r["count"]
    counts["total"] = sum(counts.get(s, 0) for s in FUNNEL_STAGES)
    return counts


# ---------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------
@api.post("/seller-leads")
async def create_lead(payload: SellerLeadCreate, request: Request):
    user = await get_current_user(request)
    if payload.source not in SOURCES:
        raise HTTPException(400, f"Unknown source: {payload.source}")
    now = datetime.now(timezone.utc)
    doc = {
        "id":                  uuid.uuid4().hex,
        "user_id":             user.user_id,
        "mission_id":          payload.mission_id,
        "business_name":       payload.business_name.strip(),
        "website":             (payload.website or "").strip() or None,
        "email":               (payload.email or "").strip() or None,
        "source":              payload.source,
        "platform":            payload.platform,
        "niche":               payload.niche,
        "location":            payload.location,
        "socials":             payload.socials or {},
        "product_categories":  payload.product_categories or [],
        "estimated_activity":  payload.estimated_activity,
        "raw_signal":          payload.raw_signal or {},
        "stage":               "discovered",
        "seller_score":        None,
        "score_breakdown":     None,
        "qualified_at":        None,
        "outreached_at":       None,
        "responded_at":        None,
        "onboarded_at":        None,
        "created_at":          now,
        "updated_at":          now,
        "discovered_at":       now,
    }
    await db.seller_leads.insert_one(doc)
    return _serialize(doc)


@api.get("/seller-leads")
async def list_leads(request: Request,
                     mission_id: Optional[str] = None,
                     stage:      Optional[str] = None,
                     limit:      int = 100):
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id}
    if mission_id:
        q["mission_id"] = mission_id
    if stage:
        if stage not in STAGES:
            raise HTTPException(400, f"Unknown stage: {stage}")
        q["stage"] = stage
    cursor = db.seller_leads.find(q).sort([("seller_score", -1), ("created_at", -1)]).limit(min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    return {"leads": [_serialize(r) for r in rows], "count": len(rows)}


@api.get("/seller-leads/{lead_id}")
async def get_lead(lead_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.seller_leads.find_one({"id": lead_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    return _serialize(doc)


@api.patch("/seller-leads/{lead_id}")
async def update_lead(lead_id: str, payload: SellerLeadUpdate, request: Request):
    user = await get_current_user(request)
    doc = await db.seller_leads.find_one({"id": lead_id, "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.stage is not None:
        if payload.stage not in STAGES:
            raise HTTPException(400, f"Unknown stage: {payload.stage}")
        updates["stage"] = payload.stage
        # Stage transition timestamps — useful for funnel timing analytics.
        stamp_map = {
            "qualified":   "qualified_at",
            "outreached":  "outreached_at",
            "interested":  "responded_at",
            "onboarding":  "onboarded_at",
        }
        if payload.stage in stamp_map and not doc.get(stamp_map[payload.stage]):
            updates[stamp_map[payload.stage]] = datetime.now(timezone.utc)
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if payload.email is not None:
        updates["email"] = payload.email.strip() or None
    if payload.seller_score is not None:
        updates["seller_score"] = float(payload.seller_score)
    await db.seller_leads.update_one({"id": lead_id}, {"$set": updates})
    fresh = await db.seller_leads.find_one({"id": lead_id})
    return _serialize(fresh)


@api.delete("/seller-leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.seller_leads.delete_one({"id": lead_id, "user_id": user.user_id})
    if not res.deleted_count:
        raise HTTPException(404, "Lead not found")
    return {"ok": True, "deleted": lead_id}


@api.get("/seller-leads/funnel/{mission_id}")
async def get_funnel(mission_id: str, request: Request):
    user = await get_current_user(request)
    return await funnel_for_mission(user.user_id, mission_id)


@api.get("/seller-leads/funnel")
async def get_funnel_all(request: Request):
    """Cross-mission funnel — drives the Seller OS Mission Control hero."""
    user = await get_current_user(request)
    return await funnel_for_mission(user.user_id, None)
