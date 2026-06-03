"""Asset storage adapter — pluggable backend (local disk OR Emergent
managed object storage) behind one Protocol.

Layout (local disk):   /app/backend/uploads/assets/<user_id>/<asset_id>.<ext>
Layout (Emergent obj): cortexviral/assets/<user_id>/<asset_id>.<ext>

The adapter is the ONLY component that knows where bytes live.
Everything else passes around `storage_key` strings (e.g.
`assets/u-abc/x123.pdf`) which the adapter resolves to bytes on read.

Backend selection is driven by the env var `ASSET_STORAGE_BACKEND`:
  • "local"     (default)  — `LocalDiskStorage`
  • "emergent"             — `EmergentObjStorage` (production)

The Emergent backend has a few quirks the protocol absorbs:
  • No native delete API — `delete()` is a soft-delete no-op (the DB row's
    `deleted_at` field is the source of truth and any orphaned bytes
    are reaped server-side by Emergent).
  • No presigned URLs — `public_url()` keeps returning our backend's
    proxy route, which then streams via `read()`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Protocol

import requests

logger = logging.getLogger(__name__)


# 20 MiB hard limit per asset (Phase A spec). Videos get a higher cap
# below since a 5-minute clip can easily exceed 20 MiB; everything else
# stays at 20.
MAX_ASSET_BYTES        = 20 * 1024 * 1024
MAX_VIDEO_ASSET_BYTES  = 50 * 1024 * 1024

# MIME → extension whitelist. Anything else is rejected at the route layer.
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg":      ".jpg",
    "image/jpg":       ".jpg",
    "image/png":       ".png",
    "image/webp":      ".webp",
    # Phase A expansion — PPTX presentations.
    "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        ".pptx",
    # Phase A expansion — Short videos (≤ 50 MiB, ≤ 5 min handled later).
    "video/mp4":        ".mp4",
    "video/quicktime":  ".mov",
    "video/webm":       ".webm",
}

# Per-MIME size override. Falls back to MAX_ASSET_BYTES when unset.
MAX_BYTES_BY_MIME = {
    "video/mp4":        MAX_VIDEO_ASSET_BYTES,
    "video/quicktime":  MAX_VIDEO_ASSET_BYTES,
    "video/webm":       MAX_VIDEO_ASSET_BYTES,
}


class AssetStorage(Protocol):
    """The contract every storage backend implements."""
    async def save(self, key: str, data: bytes,
                     max_bytes: int = MAX_ASSET_BYTES) -> str: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def public_url(self, key: str) -> str: ...


class LocalDiskStorage:
    """Disk-backed adapter. Files live under `root/<key>`. `public_url`
    points at the backend's own `/api/cortex/assets/file/{key}` route
    so kubernetes ingress (which only proxies /api/*) reaches it."""

    def __init__(self, root: str = "/app/backend/uploads/assets"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Guard against path traversal — keys are server-generated, but
        # belt-and-braces on user input that flows in via API.
        safe = Path(key).as_posix().lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError(f"unsafe asset key: {key!r}")
        return self.root / safe

    async def save(self, key: str, data: bytes,
                     max_bytes: int = MAX_ASSET_BYTES) -> str:
        if len(data) > max_bytes:
            raise ValueError(f"asset exceeds {max_bytes} byte cap")
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write synchronously — file sizes are bounded ≤ 50 MiB so this
        # is microseconds. async file I/O via aiofiles is unnecessary
        # overhead here.
        target.write_bytes(data)
        return key

    async def read(self, key: str) -> bytes:
        target = self._path(key)
        if not target.exists():
            raise FileNotFoundError(key)
        return target.read_bytes()

    async def delete(self, key: str) -> None:
        target = self._path(key)
        try:
            if target.exists():
                target.unlink()
        except Exception:
            logger.exception("asset_storage: delete failed for %s", key)

    def public_url(self, key: str) -> str:
        # The route handler streams from disk.
        return f"/api/cortex/assets/file/{key}"

    # --- maintenance ----------------------------------------------------
    def total_bytes(self, user_id: str | None = None) -> int:
        """Total disk usage in bytes — used for per-user quota dashboards."""
        scope = self.root / user_id if user_id else self.root
        if not scope.exists():
            return 0
        total = 0
        for p in scope.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def purge_user(self, user_id: str) -> int:
        """Wipe a user's entire asset tree — for account deletion."""
        scope = self.root / user_id
        if not scope.exists():
            return 0
        n = sum(1 for _ in scope.rglob("*") if _.is_file())
        shutil.rmtree(scope, ignore_errors=True)
        return n


# --------------------------------------------------------------------------
# Emergent managed object storage backend.
# --------------------------------------------------------------------------
class EmergentObjStorage:
    """Stores asset bytes in Emergent's managed object store
    (`https://integrations.emergentagent.com/objstore/api/v1/storage`).

    Auth is a two-step handshake:
      1) POST /init with `EMERGENT_LLM_KEY` → returns a session
         `storage_key` (cached at process level for the duration of the
         process; re-init on 403 is handled lazily).
      2) PUT  /objects/<path>  with header `X-Storage-Key: <sk>`
         GET  /objects/<path>  with header `X-Storage-Key: <sk>`

    Quirks:
      • No delete API. `delete()` is a no-op — the DB row's `deleted_at`
        flag is the source of truth and orphan bytes are reaped server
        side by Emergent. Cortex's pipeline already soft-deletes, so
        nothing else needs to change.
      • No presigned GET URLs. `public_url()` returns the backend's own
        proxy route — clients still talk to /api/cortex/assets/file/{key}.

    Network I/O is sync `requests` calls; we offload to a thread executor
    via `asyncio.to_thread` so we never block the FastAPI event loop.
    """

    BASE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
    PATH_PREFIX = "cortexviral/assets"  # all keys live under this prefix

    def __init__(self, emergent_key: Optional[str] = None):
        self._emergent_key = emergent_key or os.environ.get("EMERGENT_LLM_KEY")
        if not self._emergent_key:
            raise RuntimeError(
                "EmergentObjStorage requires EMERGENT_LLM_KEY in the environment."
            )
        # Session storage key — cached, refreshed on 403.
        self._sk: Optional[str] = None
        self._lock = asyncio.Lock()

    # ----- internal: storage_key lifecycle --------------------------------
    async def _ensure_sk(self, *, force: bool = False) -> str:
        if self._sk and not force:
            return self._sk
        async with self._lock:
            if self._sk and not force:
                return self._sk
            self._sk = await asyncio.to_thread(self._init_sync)
            return self._sk

    def _init_sync(self) -> str:
        r = requests.post(
            f"{self.BASE_URL}/init",
            json={"emergent_key": self._emergent_key},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["storage_key"]

    # ----- key path helpers ----------------------------------------------
    def _remote_path(self, key: str) -> str:
        """Map an internal storage_key (e.g. 'assets/u-abc/x.pdf') to its
        remote object path. We never expose the prefix to callers."""
        safe = key.lstrip("/").replace("..", "_")
        if safe.startswith(self.PATH_PREFIX + "/"):
            return safe  # already prefixed
        if safe.startswith("assets/"):
            return f"cortexviral/{safe}"
        return f"{self.PATH_PREFIX}/{safe}"

    # ----- protocol surface ----------------------------------------------
    async def save(self, key: str, data: bytes,
                     max_bytes: int = MAX_ASSET_BYTES) -> str:
        if len(data) > max_bytes:
            raise ValueError(f"asset exceeds {max_bytes} byte cap")
        remote = self._remote_path(key)
        sk = await self._ensure_sk()
        # PUT with auto-retry on 403 (sk expired) or 409 (already exists →
        # treat as success since our keys are uuid-based).
        for attempt in (0, 1):
            r = await asyncio.to_thread(
                requests.put,
                f"{self.BASE_URL}/objects/{remote}",
                headers={"X-Storage-Key": sk,
                          "Content-Type": "application/octet-stream"},
                data=data, timeout=120,
            )
            if r.status_code == 403 and attempt == 0:
                sk = await self._ensure_sk(force=True)
                continue
            if r.status_code == 409:
                # Object already exists at that path. Our keys are uuid
                # based so this is benign — treat as success.
                logger.info("emergent_obj: PUT 409 (already exists) for %s",
                            remote)
                return key
            r.raise_for_status()
            return key
        return key  # unreachable; raise_for_status above will fire

    async def read(self, key: str) -> bytes:
        remote = self._remote_path(key)
        sk = await self._ensure_sk()
        for attempt in (0, 1):
            r = await asyncio.to_thread(
                requests.get,
                f"{self.BASE_URL}/objects/{remote}",
                headers={"X-Storage-Key": sk},
                timeout=60,
            )
            if r.status_code == 403 and attempt == 0:
                sk = await self._ensure_sk(force=True)
                continue
            if r.status_code == 404:
                raise FileNotFoundError(key)
            # Defensive: the Emergent service currently returns 500 for
            # missing objects instead of 404 (documented quirk). The body
            # shape — `{"code": "internal_server_error"}` with no further
            # detail — is indistinguishable from "object not found",
            # so we treat 500 as "not found" too. The HybridStorage
            # fallback then gets a chance to serve the legacy disk copy.
            if r.status_code == 500:
                logger.info("emergent_obj: read %s returned 500 — "
                            "treating as not-found", remote)
                raise FileNotFoundError(key)
            r.raise_for_status()
            return r.content
        raise FileNotFoundError(key)

    async def delete(self, key: str) -> None:
        # Emergent's API has no delete endpoint. The pipeline already
        # soft-deletes the DB row (status='deleted', deleted_at=<ts>) so
        # the orphan bytes are unreachable from our app surface. Emergent
        # reaps them server-side.
        logger.debug("emergent_obj: delete is a no-op for key=%s", key)
        return None

    def public_url(self, key: str) -> str:
        # We always proxy through our backend so the session cookie's
        # per-user ACL check runs before bytes go out. No direct-S3 URL.
        return f"/api/cortex/assets/file/{key}"

    # ----- maintenance ----------------------------------------------------
    def total_bytes(self, user_id: str | None = None) -> int:
        # Not tracked locally; Emergent has no usage endpoint exposed here.
        return 0

    def purge_user(self, user_id: str) -> int:
        # No bulk-delete API. The DB rows are removed by the caller, and
        # the orphaned object bytes will be reaped on Emergent's side.
        logger.info("emergent_obj: purge_user no-op for user_id=%s", user_id)
        return 0


# --------------------------------------------------------------------------
# S3-compatible backend (AWS S3, Cloudflare R2, Backblaze B2 — anything
# that speaks the S3 API). Activated by ASSET_STORAGE_BACKEND=s3.
# --------------------------------------------------------------------------
class S3Storage:
    """S3-compatible adapter. boto3 client is constructed lazily on first
    use so importing this module never costs an HTTP HEAD against an
    unreachable bucket (tests + dev keep working with no AWS creds).

    Env vars (all required when activated):
      • AWS_S3_BUCKET       — bucket name
      • AWS_REGION          — bucket region (e.g. us-east-1)
      • AWS_ACCESS_KEY_ID   — IAM access key with PutObject/GetObject/DeleteObject
      • AWS_SECRET_ACCESS_KEY
    Optional:
      • AWS_S3_ENDPOINT_URL — override for R2 / B2 / MinIO
                              (e.g. https://<account>.r2.cloudflarestorage.com)
      • S3_KEY_PREFIX       — extra prefix applied to every object (default empty)

    boto3 calls are sync — we offload to a thread executor via
    `asyncio.to_thread` so the FastAPI event loop never blocks.
    """

    def __init__(self,
                  bucket: Optional[str] = None,
                  region: Optional[str] = None,
                  endpoint_url: Optional[str] = None,
                  key_prefix: Optional[str] = None):
        self._bucket = bucket or os.environ.get("AWS_S3_BUCKET")
        self._region = region or os.environ.get("AWS_REGION")
        self._endpoint_url = (endpoint_url
                              or os.environ.get("AWS_S3_ENDPOINT_URL")
                              or None)
        self._key_prefix = (key_prefix
                            or os.environ.get("S3_KEY_PREFIX")
                            or "").strip("/")
        if not self._bucket or not self._region:
            raise RuntimeError(
                "S3Storage requires AWS_S3_BUCKET + AWS_REGION env vars.")
        self._client = None  # lazy

    def _get_client(self):
        if self._client is None:
            try:
                import boto3   # local import keeps boto3 optional at import time
            except ImportError as e:
                raise RuntimeError(
                    "boto3 is required for S3Storage; install with "
                    "`pip install boto3`") from e
            self._client = boto3.client(
                "s3",
                region_name=self._region,
                endpoint_url=self._endpoint_url,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            )
        return self._client

    def _remote_key(self, key: str) -> str:
        """Map an internal storage_key to its remote object key. We
        guard against path traversal and apply the optional prefix."""
        safe = key.lstrip("/").replace("..", "_")
        if self._key_prefix:
            return f"{self._key_prefix}/{safe}"
        return safe

    async def save(self, key: str, data: bytes,
                     max_bytes: int = MAX_ASSET_BYTES) -> str:
        if len(data) > max_bytes:
            raise ValueError(f"asset exceeds {max_bytes} byte cap")
        client = self._get_client()
        remote = self._remote_key(key)

        def _put():
            client.put_object(Bucket=self._bucket, Key=remote, Body=data)
        await asyncio.to_thread(_put)
        return key

    async def read(self, key: str) -> bytes:
        from botocore.exceptions import ClientError   # local import
        client = self._get_client()
        remote = self._remote_key(key)

        def _get() -> bytes:
            try:
                resp = client.get_object(Bucket=self._bucket, Key=remote)
                return resp["Body"].read()
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404", "NotFound"):
                    raise FileNotFoundError(key)
                raise
        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        from botocore.exceptions import ClientError   # local import
        client = self._get_client()
        remote = self._remote_key(key)

        def _del():
            try:
                client.delete_object(Bucket=self._bucket, Key=remote)
            except ClientError:
                logger.exception("s3: delete failed for %s", remote)
        await asyncio.to_thread(_del)

    def public_url(self, key: str) -> str:
        # Keep auth checks in front of every byte — always proxy.
        return f"/api/cortex/assets/file/{key}"

    def presigned_get_url(self, key: str, *, ttl_seconds: int = 3600) -> str:
        """Optional escape hatch for very large videos: short-lived
        direct-from-S3 download URL. Not used by the default pipeline."""
        client = self._get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._remote_key(key)},
            ExpiresIn=max(60, min(ttl_seconds, 7 * 86400)),
        )

    def total_bytes(self, user_id: str | None = None) -> int:
        # Not cheap to compute server-side (would need ListObjects). Skip.
        return 0

    def purge_user(self, user_id: str) -> int:
        # Bulk delete by prefix — use sparingly.
        client = self._get_client()
        prefix = self._remote_key(f"assets/{user_id}/")
        deleted = 0
        token = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            objs = resp.get("Contents") or []
            if objs:
                client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": o["Key"]} for o in objs]},
                )
                deleted += len(objs)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return deleted


# --------------------------------------------------------------------------
# Singleton — selected at import time via ASSET_STORAGE_BACKEND.
# --------------------------------------------------------------------------
class _HybridStorage:
    """Wraps a primary backend (Emergent obj store) with a read-only local
    disk fallback. New uploads go to the primary; legacy files that still
    live under `/app/backend/uploads/assets/` keep serving correctly until
    a migration sweep moves them. Once the disk tree is empty the
    fallback simply never fires.

    Only `read()` is hybrid — writes, deletes, and URLs go through the
    primary so the system has one source of truth for new state."""

    def __init__(self, primary: "AssetStorage", legacy_disk: LocalDiskStorage):
        self._primary = primary
        self._legacy = legacy_disk

    async def save(self, key: str, data: bytes,
                     max_bytes: int = MAX_ASSET_BYTES) -> str:
        return await self._primary.save(key, data, max_bytes=max_bytes)

    async def read(self, key: str) -> bytes:
        try:
            return await self._primary.read(key)
        except FileNotFoundError:
            # Legacy file might still be on disk from before the migration.
            return await self._legacy.read(key)

    async def delete(self, key: str) -> None:
        # Best-effort: tell both backends. Either may no-op (Emergent has
        # no delete API; local disk just unlinks if present).
        await self._primary.delete(key)
        try:
            await self._legacy.delete(key)
        except Exception:
            logger.exception("hybrid: legacy delete failed for %s", key)

    def public_url(self, key: str) -> str:
        return self._primary.public_url(key)

    def total_bytes(self, user_id: str | None = None) -> int:
        # Sum both — useful for ops dashboards during migration.
        n = 0
        try:
            n += self._primary.total_bytes(user_id)   # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            n += self._legacy.total_bytes(user_id)
        except Exception:
            pass
        return n

    def purge_user(self, user_id: str) -> int:
        n = 0
        try:
            n += self._primary.purge_user(user_id)    # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            n += self._legacy.purge_user(user_id)
        except Exception:
            pass
        return n


def _build_storage() -> "AssetStorage":
    """Factory: choose backend based on env var. Default = local disk so
    nothing in dev/test changes unless explicitly opted in."""
    backend = (os.environ.get("ASSET_STORAGE_BACKEND") or "local").lower().strip()
    if backend in ("emergent", "emergent_obj", "emergent-obj"):
        try:
            primary = EmergentObjStorage()
            legacy = LocalDiskStorage()
            logger.info("asset_storage: backend=emergent_obj (with disk fallback)")
            return _HybridStorage(primary, legacy)
        except Exception:
            logger.exception(
                "asset_storage: emergent backend init failed, "
                "falling back to local disk")
    elif backend in ("s3", "aws", "r2", "b2", "s3_compatible"):
        try:
            primary = S3Storage()
            legacy = LocalDiskStorage()
            logger.info("asset_storage: backend=s3_compatible (with disk fallback)")
            return _HybridStorage(primary, legacy)
        except Exception:
            logger.exception(
                "asset_storage: s3 backend init failed, "
                "falling back to local disk")
    logger.info("asset_storage: backend=local (disk)")
    return LocalDiskStorage()


storage: AssetStorage = _build_storage()
