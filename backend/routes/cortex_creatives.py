"""Cortex Creatives — generated ad images backed by the image provider
abstraction layer.

Phase B endpoints:
  POST  /api/cortex/briefs/{brief_id}/concepts/{idx}/generate
        body: {size?, platform?, provider?}
        Generate ONE creative for the concept at index `idx` of the
        named brief. Persists bytes via the storage adapter under
        `<user_id>/creatives/<creative_id>.png`. Returns the row.

  POST  /api/cortex/briefs/{brief_id}/generate-all
        body: {size?, platform?}
        Generate creatives for all concepts in parallel. Returns the
        list of created rows. Idempotent on the concept index — re-
        running won't duplicate existing rows.

  GET   /api/cortex/creatives?brief_id=...&asset_id=...
        List creatives, newest first.

  POST  /api/cortex/creatives/{id}/regenerate
        Re-run the same concept (overwrites the existing creative bytes).

  DELETE /api/cortex/creatives/{id}
        Soft delete + storage purge.

Image bytes stream through the existing `/cortex/assets/file/{key:path}`
endpoint since the storage adapter + auth check already work for any
key prefixed with the requesting user_id.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user
from cortex.asset_storage import storage
from cortex.image_provider import (
    generate_for_concept, get_provider, SIZE_PRESETS,
)

logger = logging.getLogger(__name__)


class GeneratePayload(BaseModel):
    size:     Optional[str] = None   # "square" | "story" | "pin" | "landscape"
    platform: Optional[str] = None
    provider: Optional[str] = None   # "gemini" | "openai"


def _isofy(row: dict) -> dict:
    out = dict(row)
    out.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    if out.get("storage_key"):
        out["file_url"] = storage.public_url(out["storage_key"])
    return out


async def _resolve_size(brief: dict, concept: dict, override: Optional[str]) -> str:
    """Default size: derive from concept format / brief platforms.
    `square` is the catch-all when we can't infer."""
    if override and override in SIZE_PRESETS:
        return override
    fmt = (concept.get("format") or "").lower()
    if fmt in ("reel", "short", "story", "shorts"):
        return "story"
    if fmt in ("pin",):
        return "pin"
    # Use the first recommended platform as a tiebreaker.
    plats = [p.lower() for p in (brief.get("recommended_platforms") or [])]
    if "pinterest" in plats:
        return "pin"
    if "instagram_story" in plats or "tiktok" in plats or "youtube_shorts" in plats:
        return "story"
    if "youtube" in plats or "linkedin" in plats:
        return "landscape"
    return "square"


async def _do_generate(*, brief: dict, asset: Optional[dict], concept: dict,
                          concept_idx: int, payload: GeneratePayload,
                          user_id: str, existing_id: Optional[str] = None) -> dict:
    """Shared synthesis path used by generate + regenerate + generate-all."""
    creative_id = existing_id or uuid.uuid4().hex
    size = await _resolve_size(brief, concept, payload.size)

    # Seed the row in `generating` state so the UI can immediately show
    # a pending tile next to the concept.
    base_row = {
        "id":             creative_id,
        "user_id":        user_id,
        "brief_id":       brief.get("id"),
        "asset_id":       brief.get("asset_id"),
        "concept_index":  concept_idx,
        "concept_title":  concept.get("title"),
        "concept_format": concept.get("format"),
        "size":           size,
        "platform":       payload.platform,
        "provider_override": payload.provider,
        "status":         "generating",
        "updated_at":     datetime.now(timezone.utc),
    }
    if not existing_id:
        base_row["created_at"] = datetime.now(timezone.utc)
    await db.cortex_creatives.update_one(
        {"id": creative_id}, {"$set": base_row}, upsert=True)

    try:
        result = await generate_for_concept(
            concept=concept, brief=brief, asset=asset,
            size=size, platform=payload.platform,
            override=payload.provider,
        )
    except Exception as e:
        logger.exception("creative generate failed for %s", creative_id)
        await db.cortex_creatives.update_one(
            {"id": creative_id},
            {"$set": {"status": "failed",
                       "error":  f"{type(e).__name__}: {str(e)[:240]}",
                       "updated_at": datetime.now(timezone.utc)}},
        )
        raise

    storage_key = f"{user_id}/creatives/{creative_id}.png"
    await storage.save(storage_key, result["bytes"])

    update = {
        "status":      "complete",
        "provider":    result["provider"],
        "prompt":      result["prompt"],
        "storage_key": storage_key,
        "width":       result["width"],
        "height":      result["height"],
        "size":        result["size"],
        "error":       None,
        "updated_at":  datetime.now(timezone.utc),
    }
    await db.cortex_creatives.update_one(
        {"id": creative_id}, {"$set": update})

    row = await db.cortex_creatives.find_one({"id": creative_id}, {"_id": 0})
    return _isofy(row)


# ----------------------------------------------------------- routes
@api.post("/cortex/briefs/{brief_id}/concepts/{idx}/generate")
async def generate_concept_image(brief_id: str, idx: int,
                                    payload: GeneratePayload,
                                    request: Request):
    user = await get_current_user(request)
    brief = await db.cortex_creative_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id}, {"_id": 0})
    if not brief:
        raise HTTPException(404, "Brief not found.")
    concepts = brief.get("creative_concepts") or []
    if idx < 0 or idx >= len(concepts):
        raise HTTPException(404, f"Concept index {idx} out of range.")
    concept = concepts[idx]

    asset = None
    if brief.get("asset_id"):
        intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})
        asset = intel  # we only need brand/tone for prompt context.

    return await _do_generate(brief=brief, asset=asset, concept=concept,
                                 concept_idx=idx, payload=payload,
                                 user_id=user.user_id)


@api.post("/cortex/briefs/{brief_id}/generate-all")
async def generate_all_concepts(brief_id: str, payload: GeneratePayload,
                                  request: Request):
    """Fire all concepts in parallel — skips concepts that already have
    a completed creative on file (idempotent)."""
    import asyncio
    user = await get_current_user(request)
    brief = await db.cortex_creative_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id}, {"_id": 0})
    if not brief:
        raise HTTPException(404, "Brief not found.")
    concepts = brief.get("creative_concepts") or []
    if not concepts:
        raise HTTPException(409, "Brief has no creative concepts.")

    # Skip concept indexes that already have a complete creative.
    existing = {
        c["concept_index"] async for c in db.cortex_creatives.find(
            {"brief_id": brief_id, "user_id": user.user_id,
              "status":   "complete"},
            {"_id": 0, "concept_index": 1})
    }

    asset = None
    if brief.get("asset_id"):
        intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})
        asset = intel

    pending = [(i, c) for i, c in enumerate(concepts) if i not in existing]

    async def _safe(i, c):
        try:
            return await _do_generate(brief=brief, asset=asset, concept=c,
                                          concept_idx=i, payload=payload,
                                          user_id=user.user_id)
        except Exception:
            return None

    results = await asyncio.gather(*[_safe(i, c) for i, c in pending])
    return {"started": len(pending),
             "results": [r for r in results if r],
             "skipped": len(concepts) - len(pending)}


@api.get("/cortex/creatives")
async def list_creatives(request: Request, brief_id: Optional[str] = None,
                           asset_id: Optional[str] = None, limit: int = 60):
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 60), 200))
    flt: dict = {"user_id": user.user_id, "deleted_at": {"$exists": False}}
    if brief_id:
        flt["brief_id"] = brief_id
    if asset_id:
        flt["asset_id"] = asset_id
    cur = db.cortex_creatives.find(flt, {"_id": 0}) \
                                .sort("created_at", -1).limit(limit)
    rows = [_isofy(r) async for r in cur]
    return {"creatives": rows, "count": len(rows)}


@api.post("/cortex/creatives/{creative_id}/regenerate")
async def regenerate_creative(creative_id: str, payload: GeneratePayload,
                                 request: Request):
    user = await get_current_user(request)
    cr = await db.cortex_creatives.find_one(
        {"id": creative_id, "user_id": user.user_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Creative not found.")
    brief = await db.cortex_creative_briefs.find_one(
        {"id": cr["brief_id"], "user_id": user.user_id}, {"_id": 0})
    if not brief:
        raise HTTPException(404, "Brief not found.")
    concepts = brief.get("creative_concepts") or []
    if cr["concept_index"] >= len(concepts):
        raise HTTPException(409, "Original concept no longer exists.")
    concept = concepts[cr["concept_index"]]
    asset = None
    if brief.get("asset_id"):
        asset = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})

    return await _do_generate(brief=brief, asset=asset, concept=concept,
                                 concept_idx=cr["concept_index"], payload=payload,
                                 user_id=user.user_id, existing_id=creative_id)


@api.delete("/cortex/creatives/{creative_id}")
async def delete_creative(creative_id: str, request: Request):
    user = await get_current_user(request)
    cr = await db.cortex_creatives.find_one(
        {"id": creative_id, "user_id": user.user_id}, {"_id": 0})
    if not cr:
        raise HTTPException(404, "Creative not found.")
    if cr.get("storage_key"):
        await storage.delete(cr["storage_key"])
    await db.cortex_creatives.update_one(
        {"id": creative_id},
        {"$set": {"deleted_at": datetime.now(timezone.utc),
                   "status":     "deleted"}},
    )
    return {"ok": True, "id": creative_id}
