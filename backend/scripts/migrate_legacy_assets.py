#!/usr/bin/env python3
"""One-shot migration: push legacy `/app/backend/uploads/assets/<user>/<file>`
files into the configured asset storage backend (Emergent obj store by
default, but works with any backend the adapter selects).

Why: when we flipped `ASSET_STORAGE_BACKEND=emergent` for new uploads,
existing files stayed on disk. `_HybridStorage.read()` falls back to
disk so users don't notice — but until everything is in the object
store we can't run the backend on a stateless pod. This script closes
that gap.

Idempotency: each file is uploaded under its existing storage_key. The
EmergentObjStorage adapter treats 409 (already exists) as success, so
re-running the script is safe.

Safety: by default the local disk copy is kept after a successful
upload. Pass `--delete-after` once you've confirmed the new backend
serves correctly, OR just `rm -rf /app/backend/uploads/assets/` once
the script reports 0 failures.

Usage:
    python3 -m scripts.migrate_legacy_assets [--dry-run] [--delete-after]
                                              [--verbose]
                                              [--root /custom/path]

Run from the backend dir (or anywhere — paths are absolute by default).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Make the script runnable from any CWD.
HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE / ".env")

from cortex.asset_storage import (   # noqa: E402
    EmergentObjStorage, LocalDiskStorage, S3Storage, _HybridStorage,
)

DEFAULT_ROOT = "/app/backend/uploads/assets"

logger = logging.getLogger("migrate_assets")


# --------------------------------------------------------------------------
# Migration core
# --------------------------------------------------------------------------
def _iter_files(root: Path):
    """Yield every regular file under `root`. Sorted for stable progress
    output across re-runs."""
    if not root.exists():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p


def _storage_key(file_path: Path, root: Path) -> str:
    """Map a disk file to its canonical storage_key — the path RELATIVE
    to the assets root, with `assets/` prefix so the key matches what
    `cortex_assets.upload` produces today."""
    rel = file_path.relative_to(root).as_posix()
    return f"assets/{rel}"


def _resolve_destination():
    """Pick the destination backend. Honours ASSET_STORAGE_BACKEND so
    the script writes to whatever the running app reads from."""
    backend = (os.environ.get("ASSET_STORAGE_BACKEND")
               or "emergent").lower().strip()
    if backend in ("emergent", "emergent_obj", "emergent-obj"):
        return EmergentObjStorage(), "emergent_obj"
    if backend in ("s3", "aws", "r2", "b2", "s3_compatible"):
        return S3Storage(), "s3_compatible"
    raise SystemExit(
        f"Refusing to migrate to backend={backend!r} — set "
        f"ASSET_STORAGE_BACKEND=emergent (or s3) before running this script."
    )


async def migrate(*, root: Path, dry_run: bool, delete_after: bool,
                    verbose: bool) -> dict:
    dest, dest_label = _resolve_destination()
    files = list(_iter_files(root))
    total = len(files)
    if total == 0:
        print(f"No files found under {root}. Nothing to migrate.")
        return {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0}

    print(f"Migrating {total} file(s) from {root} → {dest_label}"
          + (" [DRY RUN]" if dry_run else ""))
    print()

    uploaded = 0
    failed = 0
    bytes_moved = 0
    failures: list[tuple[str, str]] = []
    started = time.monotonic()

    for i, fp in enumerate(files, 1):
        key = _storage_key(fp, root)
        size = fp.stat().st_size
        prefix = f"[{i}/{total}]"
        if verbose:
            print(f"{prefix} {key}  ({size:>10,} B)")
        if dry_run:
            uploaded += 1
            bytes_moved += size
            continue
        try:
            data = fp.read_bytes()
            # Allow up to 50 MiB per file (matches MAX_VIDEO_ASSET_BYTES);
            # the adapter's own cap is the source of truth for new uploads.
            await dest.save(key, data, max_bytes=max(size, 50 * 1024 * 1024))
            uploaded += 1
            bytes_moved += size
            if delete_after:
                fp.unlink()
        except Exception as e:   # noqa: BLE001
            failed += 1
            failures.append((key, f"{type(e).__name__}: {e}"))
            logger.exception("migrate failed for %s", key)

    elapsed = time.monotonic() - started
    mb = bytes_moved / (1024 * 1024)
    print()
    print(f"Done in {elapsed:.1f}s — {uploaded}/{total} uploaded "
          f"({mb:.1f} MiB), {failed} failed.")
    if failures:
        print()
        print("Failures:")
        for k, err in failures[:20]:
            print(f"  - {k}: {err}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

    if delete_after and not dry_run and failed == 0:
        # Best-effort cleanup of empty directories left behind.
        for d in sorted(root.rglob("*"), reverse=True):
            if d.is_dir():
                try:
                    d.rmdir()
                except OSError:
                    pass

    return {"total": total, "uploaded": uploaded, "skipped": 0,
             "failed": failed, "bytes": bytes_moved}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=DEFAULT_ROOT,
                          help=f"Legacy assets root (default: {DEFAULT_ROOT})")
    parser.add_argument("--dry-run", action="store_true",
                          help="List what would be uploaded; touch nothing.")
    parser.add_argument("--delete-after", action="store_true",
                          help="Delete each local file after a successful "
                                "upload. Use after a successful dry-run.")
    parser.add_argument("--verbose", "-v", action="store_true",
                          help="Print every file as it's processed.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    result = asyncio.run(
        migrate(root=Path(args.root),
                dry_run=args.dry_run,
                delete_after=args.delete_after,
                verbose=args.verbose),
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
