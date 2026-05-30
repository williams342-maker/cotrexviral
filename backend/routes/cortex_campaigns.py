"""Campaigns — Phase C orchestrator endpoints.

Routes:
  POST   /api/cortex/campaigns                  body: {brief_id}
         Kick off a full campaign build from an existing brief.

  GET    /api/cortex/campaigns                  ?status=...&limit=...
         List the user's campaigns, newest first.

  GET    /api/cortex/campaigns/{id}             ?include=posts,emails,landing_page,creatives
         Hydrate full campaign with related artifacts.

  DELETE /api/cortex/campaigns/{id}             soft delete
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user
from cortex.campaign_builder import build_campaign
from cortex.asset_storage import storage

logger = logging.getLogger(__name__)


class CampaignCreatePayload(BaseModel):
    brief_id: str


def _iso(row: dict) -> dict:
    out = dict(row); out.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@api.post("/cortex/campaigns")
async def create_campaign(payload: CampaignCreatePayload, request: Request):
    user = await get_current_user(request)
    brief = await db.cortex_creative_briefs.find_one(
        {"id": payload.brief_id, "user_id": user.user_id}, {"_id": 0})
    if not brief:
        raise HTTPException(404, "Brief not found.")

    asset_intel = None
    if brief.get("asset_id"):
        asset_intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})

    row = await build_campaign(brief=brief, asset_intel=asset_intel,
                                  user_id=user.user_id)
    return _iso(row)


@api.get("/cortex/campaigns")
async def list_campaigns(request: Request, limit: int = 30,
                           status: Optional[str] = None):
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 30), 100))
    flt: dict = {"user_id": user.user_id, "deleted_at": {"$exists": False}}
    if status:
        flt["status"] = status
    cur = db.cortex_campaigns.find(flt, {"_id": 0}) \
                              .sort("created_at", -1).limit(limit)
    rows = [_iso(r) async for r in cur]
    return {"campaigns": rows, "count": len(rows)}


@api.get("/cortex/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request,
                         include: str = "posts,emails,landing_page,creatives,brief"):
    user = await get_current_user(request)
    row = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not row or row.get("deleted_at"):
        raise HTTPException(404, "Campaign not found.")
    out = _iso(row)
    wanted = {p.strip() for p in (include or "").split(",") if p.strip()}

    if "brief" in wanted and out.get("brief_id"):
        brief = await db.cortex_creative_briefs.find_one(
            {"id": out["brief_id"], "user_id": user.user_id}, {"_id": 0})
        if brief:
            out["brief"] = _iso(brief)

    if "posts" in wanted:
        posts = []
        async for p in db.cortex_social_posts.find(
                {"campaign_id": campaign_id, "user_id": user.user_id},
                {"_id": 0}).sort("platform", 1):
            posts.append(_iso(p))
        out["social_posts"] = posts

    if "emails" in wanted:
        emails = []
        async for e in db.cortex_email_drafts.find(
                {"campaign_id": campaign_id, "user_id": user.user_id},
                {"_id": 0}).sort("step", 1):
            emails.append(_iso(e))
        out["email_sequence"] = emails

    if "landing_page" in wanted:
        lp = await db.cortex_landing_pages.find_one(
            {"campaign_id": campaign_id, "user_id": user.user_id}, {"_id": 0})
        if lp:
            out["landing_page"] = _iso(lp)

    if "creatives" in wanted:
        creatives = []
        async for c in db.cortex_creatives.find(
                {"campaign_id": campaign_id, "user_id": user.user_id,
                  "deleted_at": {"$exists": False}}, {"_id": 0}) \
                  .sort("concept_index", 1):
            row = _iso(c)
            if row.get("storage_key"):
                row["file_url"] = storage.public_url(row["storage_key"])
            creatives.append(row)
        out["creatives"] = creatives

    return out


@api.delete("/cortex/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, request: Request):
    user = await get_current_user(request)
    row = await db.cortex_campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Campaign not found.")
    await db.cortex_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"deleted_at": datetime.now(timezone.utc),
                   "status":     "deleted"}})
    return {"ok": True, "id": campaign_id}
