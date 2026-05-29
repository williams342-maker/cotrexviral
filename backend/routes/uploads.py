"""Uploads — multipart file upload endpoint for Compose (currently: YouTube
video uploads, but the design generalizes to any binary asset).

The browser POSTs a video file → we store it on disk under
`/app/backend/uploads/videos/{uuid}.{ext}` → return a public URL pointing
at our own `GET /api/uploads/videos/{uuid}.{ext}` streaming route.

The publish path (`publish_to_youtube`) then downloads from that URL
(its existing video_url flow) and resumable-uploads to YouTube. Once the
upload succeeds, a daily cleanup job (TBD) sweeps anything older than 24h.

We deliberately serve the file ourselves rather than mounting `StaticFiles`
because Kubernetes ingress only proxies `/api/*` to the backend — anything
else routes to the React app. Keeping the URL under `/api/uploads/...` is
the only way it reaches the backend in production.
"""
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse

from core import db, api, PUBLIC_SITE_URL
from deps import get_current_user

logger = logging.getLogger(__name__)


# Where uploaded video bytes live on disk. Kept inside /app/backend so it
# survives supervisor restarts. Wiped automatically by the cleanup job
# (uploaded_videos older than UPLOAD_TTL_HOURS).
UPLOAD_ROOT = Path("/app/backend/uploads/videos")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# Match `publish_to_youtube.MAX_VIDEO_BYTES` so the cap is uniform.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024  # 256 MiB
UPLOAD_TTL_HOURS = 24

ALLOWED_VIDEO_PREFIXES = ("video/",)


def _safe_ext(filename: str | None, content_type: str | None) -> str:
    """Returns a sanitized extension like '.mp4'. Defaults to '.mp4' when
    we can't infer one — YouTube will sniff the actual file type anyway."""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext and len(ext) <= 6 and ext.replace(".", "").isalnum():
            return ext
    # Fall back to content-type → extension mapping.
    if content_type:
        ct = content_type.lower()
        if "/mp4" in ct:
            return ".mp4"
        if "/quicktime" in ct or "/mov" in ct:
            return ".mov"
        if "/webm" in ct:
            return ".webm"
    return ".mp4"


@api.post("/uploads/video")
async def upload_video(request: Request, file: UploadFile = File(...)):
    """Stream a video to disk. Returns
        {ok, url, asset_id, bytes, content_type, expires_at}
    The caller (Compose form) drops the `url` into the YouTube video_url
    field; publish_to_youtube downloads it and forwards to YouTube."""
    user = await get_current_user(request)

    # Quick content-type sanity. We can't trust the browser entirely,
    # but a wrong content-type is a clear red flag worth blocking early.
    content_type = (file.content_type or "").lower()
    if content_type and not any(content_type.startswith(p) for p in ALLOWED_VIDEO_PREFIXES):
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {content_type}")

    asset_id = uuid.uuid4().hex
    ext = _safe_ext(file.filename, content_type)
    target = UPLOAD_ROOT / f"{asset_id}{ext}"

    # Stream-copy so we don't blow memory on large uploads. Enforce the
    # max-size cap by tracking bytes written — abort + cleanup if exceeded.
    written = 0
    try:
        with open(target, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MiB chunks
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MiB cap",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        logger.exception("video upload failed for user=%s", user.user_id)
        raise HTTPException(status_code=500, detail=f"upload failed: {exc}")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=UPLOAD_TTL_HOURS)
    await db.uploaded_videos.insert_one({
        "asset_id":     asset_id,
        "user_id":      user.user_id,
        "filename":     file.filename or f"{asset_id}{ext}",
        "ext":          ext,
        "content_type": content_type or "video/mp4",
        "size":         written,
        "path":         str(target),
        "created_at":   datetime.now(timezone.utc),
        "expires_at":   expires_at,
    })

    # Public URL the Compose UI / publish path uses. We use PUBLIC_SITE_URL
    # so the URL works from both preview AND production deployments — the
    # publish_to_youtube downloader will hit whichever it points to.
    public_url = f"{PUBLIC_SITE_URL}/api/uploads/videos/{asset_id}{ext}"
    return {
        "ok":           True,
        "asset_id":     asset_id,
        "url":          public_url,
        "bytes":        written,
        "content_type": content_type or "video/mp4",
        "expires_at":   expires_at,
        "filename":     file.filename,
    }


@api.get("/uploads/videos/{filename}")
async def serve_uploaded_video(filename: str):
    """Streams the uploaded video back. No auth — the URL itself is the
    capability token (asset_id is uuid4 = 128 bits of randomness, not
    enumerable). Returns 404 on anything that escapes the upload root."""
    # Defense in depth: reject path traversal up-front. UUIDs are hex +
    # one dot + lowercase extension, so anything with `/` or `..` is
    # plainly malicious.
    if "/" in filename or ".." in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Not found")
    target = UPLOAD_ROOT / filename
    try:
        # `relative_to` raises if `target` escapes UPLOAD_ROOT.
        target.resolve().relative_to(UPLOAD_ROOT.resolve())
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    asset_id = os.path.splitext(filename)[0]
    meta = await db.uploaded_videos.find_one(
        {"asset_id": asset_id}, {"_id": 0, "content_type": 1, "size": 1, "filename": 1},
    ) or {}
    ct = meta.get("content_type") or "video/mp4"
    size = meta.get("size") or target.stat().st_size

    def _stream():
        with open(target, "rb") as fh:
            while True:
                chunk = fh.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Content-Length":       str(size),
        "Cache-Control":        "public, max-age=3600",
        "Content-Disposition":  f'inline; filename="{meta.get("filename") or filename}"',
    }
    return StreamingResponse(_stream(), media_type=ct, headers=headers)


@api.delete("/uploads/videos/{asset_id}")
async def delete_uploaded_video(asset_id: str, request: Request):
    """Operator can manually evict an uploaded video before TTL fires."""
    user = await get_current_user(request)
    meta = await db.uploaded_videos.find_one(
        {"asset_id": asset_id, "user_id": user.user_id}, {"_id": 0, "path": 1},
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        Path(meta["path"]).unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to unlink upload %s", meta.get("path"))
    await db.uploaded_videos.delete_one({"asset_id": asset_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------------------------------------------------------------
# Scheduler hookup — daily cleanup of expired uploads.
# ---------------------------------------------------------------------
async def run_upload_cleanup() -> dict:
    """Removes uploaded videos older than UPLOAD_TTL_HOURS. Idempotent
    and safe to re-run."""
    now = datetime.now(timezone.utc)
    expired = await db.uploaded_videos.find(
        {"expires_at": {"$lt": now}}, {"_id": 0, "asset_id": 1, "path": 1},
    ).to_list(length=500)
    removed = 0
    for doc in expired:
        try:
            Path(doc["path"]).unlink(missing_ok=True)
            await db.uploaded_videos.delete_one({"asset_id": doc["asset_id"]})
            removed += 1
        except Exception:
            logger.warning("Cleanup failed for asset %s", doc.get("asset_id"))
    return {"removed": removed, "ran_at": now}


def register_upload_cleanup_job(scheduler) -> None:
    """Daily 04:00 UTC sweep. Idempotent — only adds when missing."""
    from apscheduler.triggers.cron import CronTrigger
    if scheduler.get_job("uploads_cleanup_daily"):
        return
    scheduler.add_job(
        run_upload_cleanup,
        trigger=CronTrigger(hour=4, minute=0),
        id="uploads_cleanup_daily",
        max_instances=1,
        coalesce=True,
    )
