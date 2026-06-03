#!/usr/bin/env python3
"""One-shot migration: pull every active asset from Emergent obj store
and push it to the active S3-compatible backend (R2 in our case).

After this script runs successfully you can flip
`ASSET_STORAGE_BACKEND=s3` (already set) and Emergent obj store
becomes truly unused — `_HybridStorage`'s legacy fallback only checks
the local disk, not Emergent, so once everything is in R2 the
Emergent client is never called again.

Behavior:
  • Reads every `cortex_assets` row where `storage_key` is set and
    `deleted_at` is absent.
  • For each, reads bytes from EmergentObjStorage and writes to
    S3Storage under the SAME storage_key (no key rewrite — DB rows
    stay valid).
  • Idempotent: re-running is safe (R2 PutObject just overwrites).
  • Verifies each migrated file by reading it back from S3 and
    comparing byte-length + first/last 64 bytes (full byte compare
    on small files).

Usage:
    python3 -m scripts.migrate_emergent_to_r2 [--dry-run] [--verbose]
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

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from dotenv import load_dotenv   # noqa: E402

load_dotenv(HERE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient   # noqa: E402

from cortex.asset_storage import (   # noqa: E402
    EmergentObjStorage, S3Storage,
)

logger = logging.getLogger("migrate_emergent_to_r2")


def _bytes_match(a: bytes, b: bytes) -> bool:
    """Fast equality check. Full compare on small files, head+tail on
    large ones — this guards against silent corruption on transit
    without paying for a full 50 MiB compare."""
    if len(a) != len(b):
        return False
    if len(a) <= 256 * 1024:
        return a == b
    return a[:1024] == b[:1024] and a[-1024:] == b[-1024:]


async def migrate(*, dry_run: bool, verbose: bool) -> dict:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    rows = await db.cortex_assets.find({
        "storage_key": {"$exists": True, "$ne": None},
        "deleted_at": {"$exists": False},
    }, {"_id": 0, "id": 1, "storage_key": 1,
        "user_id": 1, "filename": 1}).to_list(None)
    total = len(rows)
    if total == 0:
        print("No assets to migrate.")
        return {"total": 0, "moved": 0, "failed": 0, "skipped": 0}

    src = EmergentObjStorage()
    dst = S3Storage()
    print(f"Migrating {total} asset(s): Emergent → R2 (bucket={dst._bucket})"
          + (" [DRY RUN]" if dry_run else ""))
    print()

    moved = 0
    failed = 0
    skipped = 0
    bytes_moved = 0
    failures: list[tuple[str, str]] = []
    started = time.monotonic()

    for i, row in enumerate(rows, 1):
        key = row["storage_key"]
        rid = row["id"]
        prefix = f"[{i}/{total}]"

        # 1. Read from Emergent.
        try:
            data = await src.read(key)
        except FileNotFoundError:
            print(f"{prefix} SKIP (not in Emergent): {key}")
            skipped += 1
            continue
        except Exception as e:   # noqa: BLE001
            print(f"{prefix} READ FAIL {key} — {type(e).__name__}: {e}")
            failures.append((key, f"read: {e}"))
            failed += 1
            continue

        if verbose:
            print(f"{prefix} {key}  ({len(data):>10,} B)")
        if dry_run:
            moved += 1
            bytes_moved += len(data)
            continue

        # 2. Write to R2.
        try:
            await dst.save(key, data, max_bytes=max(len(data), 50 * 1024 * 1024))
        except Exception as e:   # noqa: BLE001
            print(f"{prefix} WRITE FAIL {key} — {type(e).__name__}: {e}")
            failures.append((key, f"write: {e}"))
            failed += 1
            continue

        # 3. Verify round-trip (read back from R2 + compare).
        try:
            verify = await dst.read(key)
        except Exception as e:   # noqa: BLE001
            print(f"{prefix} VERIFY READ FAIL {key} — {e}")
            failures.append((key, f"verify-read: {e}"))
            failed += 1
            continue
        if not _bytes_match(data, verify):
            print(f"{prefix} BYTES DIFFER for {key} "
                  f"(src={len(data)} dst={len(verify)})")
            failures.append((key, "byte mismatch"))
            failed += 1
            continue

        moved += 1
        bytes_moved += len(data)
        logger.info("migrated %s id=%s size=%dB", key, rid, len(data))

    elapsed = time.monotonic() - started
    mb = bytes_moved / (1024 * 1024)
    print()
    print(f"Done in {elapsed:.1f}s — {moved}/{total} migrated "
          f"({mb:.1f} MiB), {skipped} skipped, {failed} failed.")
    if failures:
        print()
        print("Failures:")
        for k, err in failures[:20]:
            print(f"  - {k}: {err}")

    return {"total": total, "moved": moved, "failed": failed,
             "skipped": skipped, "bytes": bytes_moved}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                          help="List what would be migrated; touch nothing in R2.")
    parser.add_argument("--verbose", "-v", action="store_true",
                          help="Print every asset as it's processed.")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Sanity: refuse to run if R2 isn't configured (the script writes
    # bytes — if the destination is misconfigured we'd silently lose them).
    for var in ("AWS_S3_BUCKET", "AWS_REGION",
                  "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        if not os.environ.get(var):
            print(f"Refusing to run: env var {var} is not set.")
            return 2

    result = asyncio.run(migrate(dry_run=args.dry_run,
                                  verbose=args.verbose))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
