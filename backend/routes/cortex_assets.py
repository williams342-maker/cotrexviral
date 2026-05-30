"""Asset Upload Center — REST endpoints.

Pipeline per upload:
  1. validate (mime + size) → write to disk via asset_storage adapter
  2. extract text/meta via asset_extraction dispatcher (per kind)
  3. run LLM intelligence + review via asset_intelligence (background)
  4. persist asset row (cortex_assets) + intelligence + review

Status lifecycle (cortex_assets.status):
  queued → extracting → analyzing → complete
                                  ↘ failed (with error field)

Frontend polls GET /assets/{id} until status='complete'.

Routes:
  POST   /api/cortex/assets/upload            multipart file OR {url}
  GET    /api/cortex/assets                   list (newest first)
  GET    /api/cortex/assets/{id}              detail (asset + intel + review)
  DELETE /api/cortex/assets/{id}              soft delete + storage purge
  POST   /api/cortex/assets/{id}/reanalyze    force re-run intelligence/review
  GET    /api/cortex/assets/file/{key:path}   stream the stored file
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

from cortex.asset_storage import storage, MAX_ASSET_BYTES, ALLOWED_MIME
from cortex.asset_extraction import extract, kind_from_mime
from cortex.asset_intelligence import analyze_asset
from cortex.creative_brief import generate_brief

logger = logging.getLogger(__name__)


# -------------------------------------------------------- shared helpers
async def _serialize(asset: dict) -> dict:
    """Hydrate the asset row with its intelligence + review (if present)
    and ISO-ify datetimes for the API response."""
    out = dict(asset)
    out.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()

    aid = out.get("id")
    if aid:
        intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": aid}, {"_id": 0})
        if intel:
            for k in ("created_at",):
                v = intel.get(k)
                if isinstance(v, datetime):
                    intel[k] = v.isoformat()
            out["intelligence"] = intel
        review = await db.cortex_asset_reviews.find_one(
            {"asset_id": aid}, {"_id": 0})
        if review:
            for k in ("created_at",):
                v = review.get(k)
                if isinstance(v, datetime):
                    review[k] = v.isoformat()
            out["review"] = review
        brief = await db.cortex_creative_briefs.find_one(
            {"asset_id": aid}, {"_id": 0})
        if brief:
            for k in ("created_at",):
                v = brief.get(k)
                if isinstance(v, datetime):
                    brief[k] = v.isoformat()
            out["brief"] = brief

    # Public URL (file streaming) — only for stored binaries.
    if out.get("storage_key"):
        out["file_url"] = storage.public_url(out["storage_key"])

    return out


async def _run_pipeline(asset_id: str) -> None:
    """Background worker: extract → analyze → persist → flip status.
    Best-effort; failures write a `failed` status with a reason so the
    UI can offer a Retry CTA."""
    try:
        asset = await db.cortex_assets.find_one({"id": asset_id}, {"_id": 0})
        if not asset:
            return

        await db.cortex_assets.update_one(
            {"id": asset_id}, {"$set": {"status": "extracting"}})

        # 1. Extract
        kind = asset.get("kind")
        data: Optional[bytes] = None
        if kind in ("pdf", "image") and asset.get("storage_key"):
            data = await storage.read(asset["storage_key"])
        extracted = await extract(kind=kind, data=data,
                                     url=asset.get("source_url"))

        # Stash extraction metadata back onto the asset for diagnostics.
        await db.cortex_assets.update_one(
            {"id": asset_id},
            {"$set": {"status": "analyzing",
                       "extraction_meta": extracted.get("meta") or {},
                       "thumb_b64": extracted.get("thumb_b64")}},
        )

        # 2. Analyze (LLM tool-calls — intelligence + review + memory write)
        result = await analyze_asset(asset, extracted)
        intel = result.get("intelligence")
        review = result.get("review")

        # 3. Persist intelligence + review
        if intel:
            await db.cortex_asset_intelligence.update_one(
                {"asset_id": asset_id},
                {"$set": {**intel, "asset_id": asset_id,
                           "user_id": asset.get("user_id")}},
                upsert=True,
            )
        if review:
            await db.cortex_asset_reviews.update_one(
                {"asset_id": asset_id},
                {"$set": {**review, "asset_id": asset_id,
                           "user_id": asset.get("user_id")}},
                upsert=True,
            )

        # 3b. Creative Brief — synthesize the executable campaign brief
        # on top of the intelligence + review. Phase-A2 layer. Best-effort:
        # if the LLM is down we skip rather than fail the whole pipeline.
        try:
            brief = await generate_brief(asset, intel, review)
            if brief:
                await db.cortex_creative_briefs.update_one(
                    {"asset_id": asset_id},
                    {"$set": {**brief, "asset_id": asset_id,
                               "user_id": asset.get("user_id")}},
                    upsert=True,
                )
        except Exception:
            logger.exception("asset pipeline: creative brief failed for %s",
                              asset_id)

        # 4. Flip status → complete
        await db.cortex_assets.update_one(
            {"id": asset_id},
            {"$set": {"status": "complete",
                       "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.exception("asset pipeline failed for %s", asset_id)
        try:
            await db.cortex_assets.update_one(
                {"id": asset_id},
                {"$set": {"status": "failed",
                           "error":  f"{type(e).__name__}: {str(e)[:240]}"}},
            )
        except Exception:
            pass


# --------------------------------------------------------------- routes
class UrlUploadPayload(BaseModel):
    url:  str
    name: Optional[str] = None


@api.post("/cortex/assets/upload")
async def upload_asset(request: Request,
                        file: Optional[UploadFile] = File(None),
                        url:  Optional[str] = Form(None),
                        name: Optional[str] = Form(None)):
    """Accept either a multipart file OR a URL string. Returns the new
    asset row immediately (status='queued'); the analysis pipeline
    fires in the background."""
    user = await get_current_user(request)

    # ---- URL path -----------------------------------------------------
    if url and not file:
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url.lstrip('/')}"
        asset_id = uuid.uuid4().hex
        row = {
            "id":          asset_id,
            "user_id":     user.user_id,
            "kind":        "url",
            "name":        (name or url)[:200],
            "source_url":  url,
            "storage_key": None,
            "size":        0,
            "mime_type":   "text/html",
            "status":      "queued",
            "created_at":  datetime.now(timezone.utc),
            "updated_at":  datetime.now(timezone.utc),
        }
        await db.cortex_assets.insert_one(row)
        asyncio.create_task(_run_pipeline(asset_id))
        return await _serialize(row)

    # ---- File path ----------------------------------------------------
    if not file:
        raise HTTPException(400, "Provide either a file or a url.")

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported file type: {content_type or 'unknown'}. "
                                    "Allowed: PDF, JPG, PNG, WebP.")

    # Read into memory (≤ 20 MiB cap) — small enough that streaming to
    # disk isn't worth the complexity.
    data = await file.read()
    if len(data) > MAX_ASSET_BYTES:
        raise HTTPException(413, f"File too large ({len(data)} bytes). "
                                    f"Max {MAX_ASSET_BYTES} bytes (20 MiB).")
    if not data:
        raise HTTPException(400, "Empty file.")

    asset_id = uuid.uuid4().hex
    ext = ALLOWED_MIME[content_type]
    storage_key = f"{user.user_id}/{asset_id}{ext}"
    try:
        await storage.save(storage_key, data)
    except ValueError as e:
        raise HTTPException(413, str(e))

    kind = kind_from_mime(content_type) or "image"
    row = {
        "id":           asset_id,
        "user_id":      user.user_id,
        "kind":         kind,
        "name":         (name or file.filename or f"upload{ext}")[:200],
        "source_url":   None,
        "storage_key":  storage_key,
        "size":         len(data),
        "mime_type":    content_type,
        "status":       "queued",
        "created_at":   datetime.now(timezone.utc),
        "updated_at":   datetime.now(timezone.utc),
    }
    await db.cortex_assets.insert_one(row)
    asyncio.create_task(_run_pipeline(asset_id))
    return await _serialize(row)


@api.get("/cortex/assets")
async def list_assets(request: Request, limit: int = 50, skip: int = 0,
                        kind: Optional[str] = None):
    """List the user's assets (newest first)."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))
    flt: dict = {"user_id": user.user_id, "deleted_at": {"$exists": False}}
    if kind:
        flt["kind"] = kind
    cur = db.cortex_assets.find(flt, {"_id": 0}) \
                            .sort("created_at", -1).skip(skip).limit(limit)
    rows = [await _serialize(r) async for r in cur]
    total = await db.cortex_assets.count_documents(flt)
    return {"assets": rows, "count": len(rows), "total": total}


@api.get("/cortex/assets/{asset_id}")
async def get_asset(asset_id: str, request: Request):
    """Asset detail — includes intelligence + review when ready."""
    user = await get_current_user(request)
    asset = await db.cortex_assets.find_one(
        {"id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if not asset or asset.get("deleted_at"):
        raise HTTPException(404, "Asset not found.")
    return await _serialize(asset)


@api.delete("/cortex/assets/{asset_id}")
async def delete_asset(asset_id: str, request: Request):
    """Soft-delete + purge stored bytes. Intelligence + review rows
    remain for analytics/audit."""
    user = await get_current_user(request)
    asset = await db.cortex_assets.find_one(
        {"id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Asset not found.")
    if asset.get("storage_key"):
        await storage.delete(asset["storage_key"])
    await db.cortex_assets.update_one(
        {"id": asset_id},
        {"$set": {"deleted_at": datetime.now(timezone.utc),
                   "status":     "deleted"}},
    )
    return {"ok": True, "id": asset_id}


@api.post("/cortex/assets/{asset_id}/reanalyze")
async def reanalyze_asset(asset_id: str, request: Request):
    """Force a fresh extraction + LLM pass. Useful after a model
    upgrade or when the user wants a second opinion."""
    user = await get_current_user(request)
    asset = await db.cortex_assets.find_one(
        {"id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if not asset or asset.get("deleted_at"):
        raise HTTPException(404, "Asset not found.")
    await db.cortex_assets.update_one(
        {"id": asset_id}, {"$set": {"status": "queued", "error": None}})
    asyncio.create_task(_run_pipeline(asset_id))
    return {"ok": True, "id": asset_id, "status": "queued"}


@api.get("/cortex/assets/file/{key:path}")
async def stream_asset_file(key: str, request: Request):
    """Stream a stored asset's bytes. Auth-scoped: the leading path
    segment must match the requesting user_id so other users can't
    enumerate files."""
    user = await get_current_user(request)
    parts = key.split("/", 1)
    if len(parts) < 2 or parts[0] != user.user_id:
        raise HTTPException(403, "Not your asset.")
    try:
        data = await storage.read(key)
    except FileNotFoundError:
        raise HTTPException(404, "File not found.")
    # Best-effort mime sniff from extension.
    ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
    mime = {"."+v.lstrip("."): k for k, v in ALLOWED_MIME.items()}.get(ext, "application/octet-stream")
    return StreamingResponse(iter([data]), media_type=mime)


# ---------------------------------------------------------- briefs (A2)
@api.post("/cortex/assets/{asset_id}/brief")
async def regenerate_brief(asset_id: str, request: Request):
    """Force a fresh Creative Brief synthesis. Useful when the asset's
    first brief is too vague or the user wants a second take."""
    user = await get_current_user(request)
    asset = await db.cortex_assets.find_one(
        {"id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if not asset or asset.get("deleted_at"):
        raise HTTPException(404, "Asset not found.")
    if asset.get("status") != "complete":
        raise HTTPException(409,
                            f"Asset must be fully analyzed first (status={asset.get('status')}).")

    intel = await db.cortex_asset_intelligence.find_one(
        {"asset_id": asset_id}, {"_id": 0})
    review = await db.cortex_asset_reviews.find_one(
        {"asset_id": asset_id}, {"_id": 0})

    brief = await generate_brief(asset, intel, review)
    if not brief:
        raise HTTPException(500, "Brief synthesis failed.")
    await db.cortex_creative_briefs.update_one(
        {"asset_id": asset_id},
        {"$set": {**brief, "asset_id": asset_id, "user_id": user.user_id}},
        upsert=True,
    )
    brief.pop("_id", None)
    return brief


@api.get("/cortex/assets/{asset_id}/brief")
async def get_brief(asset_id: str, request: Request):
    """Fetch the Creative Brief for an asset. Lazily generates one if
    missing (older assets created before Phase A2 shipped)."""
    user = await get_current_user(request)
    asset = await db.cortex_assets.find_one(
        {"id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if not asset or asset.get("deleted_at"):
        raise HTTPException(404, "Asset not found.")
    brief = await db.cortex_creative_briefs.find_one(
        {"asset_id": asset_id, "user_id": user.user_id}, {"_id": 0})
    if brief:
        return brief
    # Lazy backfill for legacy assets.
    if asset.get("status") != "complete":
        raise HTTPException(409,
                            f"Asset still {asset.get('status')} — brief is generated when analysis completes.")
    intel = await db.cortex_asset_intelligence.find_one(
        {"asset_id": asset_id}, {"_id": 0})
    review = await db.cortex_asset_reviews.find_one(
        {"asset_id": asset_id}, {"_id": 0})
    brief = await generate_brief(asset, intel, review)
    if not brief:
        raise HTTPException(500, "Brief synthesis failed.")
    await db.cortex_creative_briefs.update_one(
        {"asset_id": asset_id},
        {"$set": {**brief, "asset_id": asset_id, "user_id": user.user_id}},
        upsert=True,
    )
    brief.pop("_id", None)
    return brief


@api.get("/cortex/briefs")
async def list_briefs(request: Request, limit: int = 30):
    """List the user's most recent Creative Briefs (newest first) —
    feeds the future 'Campaign Library' panel."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit or 30), 100))
    cur = db.cortex_creative_briefs.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    rows = [r async for r in cur]
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    return {"briefs": rows, "count": len(rows)}
