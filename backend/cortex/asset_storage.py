"""Asset storage adapter — local disk implementation with an interface
ready to swap for S3/R2 without changing the asset pipeline.

Layout: /app/backend/uploads/assets/<user_id>/<asset_id>.<ext>

The adapter is the ONLY component that knows about filesystem paths.
Everything else passes around `storage_key` strings (e.g.
`assets/u-abc/x123.pdf`) which the adapter resolves to bytes on read.

Future: drop in `S3Storage(bucket=...)` that implements the same
protocol and the rest of the codebase is unchanged.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


# 20 MiB hard limit per asset (Phase A spec). Easy to raise per-tier later.
MAX_ASSET_BYTES = 20 * 1024 * 1024

# MIME → extension whitelist. Anything else is rejected at the route layer.
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg":      ".jpg",
    "image/jpg":       ".jpg",
    "image/png":       ".png",
    "image/webp":      ".webp",
}


class AssetStorage(Protocol):
    """The contract every storage backend implements."""
    async def save(self, key: str, data: bytes) -> str: ...
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

    async def save(self, key: str, data: bytes) -> str:
        if len(data) > MAX_ASSET_BYTES:
            raise ValueError(f"asset exceeds {MAX_ASSET_BYTES} byte cap")
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write synchronously — file sizes are bounded ≤ 20 MiB so this
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


# Default singleton used throughout the app. Swap implementation here
# (e.g., S3Storage) and the entire pipeline switches.
storage: AssetStorage = LocalDiskStorage()
