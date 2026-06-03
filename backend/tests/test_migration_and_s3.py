"""Tests for the legacy-disk → object-storage migration script and the
new S3Storage adapter.

The migration script tests use a temp directory + the *live* Emergent
backend (same as test_asset_storage.py) — that's the only way to verify
the full round trip actually works. They never touch the real
`/app/backend/uploads/assets/` tree.

The S3Storage tests are pure-unit (boto3 patched out). Live S3 tests
would require user-supplied AWS keys, so they're left to ops to run
manually against a real bucket once credentials are configured.
"""
from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from cortex.asset_storage import (  # noqa: E402
    EmergentObjStorage, LocalDiskStorage, S3Storage, _build_storage,
)
from scripts.migrate_legacy_assets import (  # noqa: E402
    _iter_files, _storage_key, migrate,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ==========================================================================
# Migration script — pure helpers
# ==========================================================================
def test_iter_files_returns_only_regular_files(tmp_path):
    (tmp_path / "u1").mkdir()
    (tmp_path / "u1" / "a.pdf").write_bytes(b"a")
    (tmp_path / "u1" / "sub").mkdir()
    (tmp_path / "u1" / "sub" / "b.png").write_bytes(b"b")
    files = list(_iter_files(tmp_path))
    # Directories are excluded, files are sorted.
    rels = [p.relative_to(tmp_path).as_posix() for p in files]
    assert rels == ["u1/a.pdf", "u1/sub/b.png"]


def test_iter_files_missing_root_is_empty(tmp_path):
    """The script must not crash when the legacy tree was already removed
    (e.g. after a prior successful migration + manual rm -rf)."""
    assert list(_iter_files(tmp_path / "does-not-exist")) == []


def test_storage_key_mirrors_upload_route_convention(tmp_path):
    """The script must produce the SAME storage_key shape the upload route
    uses today, otherwise the DB rows pointing at these objects break."""
    fp = tmp_path / "user_abc" / "creatives" / "x.png"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(b"x")
    assert _storage_key(fp, tmp_path) == "assets/user_abc/creatives/x.png"


# ==========================================================================
# Migration script — end-to-end with the live Emergent backend
# ==========================================================================
def test_migrate_dry_run_uploads_nothing(tmp_path):
    """Dry run must not touch the network and must keep local files."""
    fp = tmp_path / "user_dry" / f"{uuid.uuid4().hex}.txt"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(b"would-be-migrated")
    result = _run(migrate(root=tmp_path, dry_run=True,
                            delete_after=False, verbose=False))
    # Reports the file as "uploaded" even though no network call ran —
    # this is the dry-run semantic and matches what the script prints.
    assert result["total"] == 1
    assert result["uploaded"] == 1
    assert result["failed"] == 0
    # The local file is still on disk.
    assert fp.exists()


def test_migrate_uploads_to_destination_and_keeps_local_by_default(tmp_path):
    """Default mode: upload, do NOT delete local copy. Verify the bytes
    are actually retrievable from the destination backend (whichever
    one ASSET_STORAGE_BACKEND resolves to — Emergent or S3-compatible
    like R2)."""
    payload = b"migration-roundtrip-" + uuid.uuid4().hex.encode()
    fp = (tmp_path / "user_mig" /
          f"{uuid.uuid4().hex}.bin")
    fp.parent.mkdir(parents=True)
    fp.write_bytes(payload)

    result = _run(migrate(root=tmp_path, dry_run=False,
                            delete_after=False, verbose=False))
    assert result["uploaded"] == 1
    assert result["failed"] == 0
    # Local copy preserved unless --delete-after is passed.
    assert fp.exists()
    # Bytes are retrievable from whichever destination backend the env
    # var selected. We don't hard-code EmergentObjStorage here because
    # the script honors ASSET_STORAGE_BACKEND.
    from scripts.migrate_legacy_assets import _resolve_destination
    dest, _label = _resolve_destination()
    key = _storage_key(fp, tmp_path)
    got = _run(dest.read(key))
    assert got == payload


def test_migrate_delete_after_removes_local_only_on_success(tmp_path):
    payload = b"migration-delete-after-" + uuid.uuid4().hex.encode()
    fp = tmp_path / "user_del" / f"{uuid.uuid4().hex}.bin"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(payload)

    result = _run(migrate(root=tmp_path, dry_run=False,
                            delete_after=True, verbose=False))
    assert result["uploaded"] == 1
    assert result["failed"] == 0
    # Local file is gone.
    assert not fp.exists()


def test_migrate_idempotent_on_rerun(tmp_path):
    """Running the script twice in a row must not fail — the EmergentObj
    backend treats 409 (already exists) as success. This guards against
    a re-run after a partial failure."""
    fp = tmp_path / "user_idempotent" / f"{uuid.uuid4().hex}.bin"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(b"idempotent-" + uuid.uuid4().hex.encode())

    r1 = _run(migrate(root=tmp_path, dry_run=False,
                        delete_after=False, verbose=False))
    r2 = _run(migrate(root=tmp_path, dry_run=False,
                        delete_after=False, verbose=False))
    assert r1["failed"] == 0 and r2["failed"] == 0
    assert r1["uploaded"] == 1 and r2["uploaded"] == 1


def test_migrate_refuses_local_only_backend(monkeypatch, tmp_path):
    """Safety: refuse to "migrate" into a local-disk backend (would
    just copy files around). Operator must set
    ASSET_STORAGE_BACKEND=emergent first."""
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "local")
    (tmp_path / "u" / "f.txt").parent.mkdir(parents=True)
    (tmp_path / "u" / "f.txt").write_bytes(b"x")
    with pytest.raises(SystemExit):
        _run(migrate(root=tmp_path, dry_run=False,
                       delete_after=False, verbose=False))


def test_migrate_script_runnable_as_module(tmp_path, monkeypatch):
    """Smoke-test the CLI shim — argparse, exit code, dry run. We run
    it as a subprocess to mirror how an operator would actually invoke
    it on the box."""
    fp = tmp_path / "user_cli" / f"{uuid.uuid4().hex}.txt"
    fp.parent.mkdir(parents=True)
    fp.write_bytes(b"cli-smoke")
    env = os.environ.copy()
    env["ASSET_STORAGE_BACKEND"] = "emergent"
    p = subprocess.run(
        [sys.executable, "-m", "scripts.migrate_legacy_assets",
         "--dry-run", "--root", str(tmp_path)],
        cwd="/app/backend", env=env, capture_output=True, text=True,
        timeout=30,
    )
    assert p.returncode == 0, p.stderr
    assert "1/1 uploaded" in p.stdout
    assert "DRY RUN" in p.stdout
    # Real file untouched.
    assert fp.exists()


# ==========================================================================
# S3Storage adapter (unit — boto3 patched out)
# ==========================================================================
def test_s3_storage_requires_bucket_and_region(monkeypatch):
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_S3_BUCKET"):
        S3Storage()


def test_s3_storage_save_calls_put_object(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    fake_client = MagicMock()
    s._client = fake_client
    _run(s.save("assets/u/x.pdf", b"hello"))
    fake_client.put_object.assert_called_once()
    kwargs = fake_client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "assets/u/x.pdf"
    assert kwargs["Body"] == b"hello"


def test_s3_storage_save_applies_prefix(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("S3_KEY_PREFIX", "cortexviral")
    s = S3Storage()
    fake_client = MagicMock()
    s._client = fake_client
    _run(s.save("assets/u/x.pdf", b"x"))
    assert fake_client.put_object.call_args.kwargs["Key"] == \
        "cortexviral/assets/u/x.pdf"


def test_s3_storage_save_enforces_max_bytes(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    s._client = MagicMock()
    with pytest.raises(ValueError):
        _run(s.save("k", b"x" * 100, max_bytes=10))


def test_s3_storage_read_returns_bytes(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    fake_client = MagicMock()
    fake_body = MagicMock()
    fake_body.read.return_value = b"the-bytes"
    fake_client.get_object.return_value = {"Body": fake_body}
    s._client = fake_client
    got = _run(s.read("assets/u/x.pdf"))
    assert got == b"the-bytes"


def test_s3_storage_read_missing_raises_file_not_found(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    fake_client = MagicMock()
    from botocore.exceptions import ClientError
    fake_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "nope"}}, "GetObject")
    s._client = fake_client
    with pytest.raises(FileNotFoundError):
        _run(s.read("assets/u/missing.pdf"))


def test_s3_storage_delete_calls_delete_object(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    fake_client = MagicMock()
    s._client = fake_client
    _run(s.delete("assets/u/x.pdf"))
    fake_client.delete_object.assert_called_once_with(
        Bucket="b", Key="assets/u/x.pdf")


def test_s3_storage_public_url_uses_backend_proxy(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    # public_url must NEVER leak the bucket name — auth runs in our backend.
    url = s.public_url("assets/u/x.pdf")
    assert url == "/api/cortex/assets/file/assets/u/x.pdf"
    assert "amazonaws" not in url and "r2" not in url


def test_s3_storage_presigned_url(monkeypatch):
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = S3Storage()
    fake_client = MagicMock()
    fake_client.generate_presigned_url.return_value = "https://signed.example/x"
    s._client = fake_client
    url = s.presigned_get_url("assets/u/x.pdf", ttl_seconds=600)
    assert url == "https://signed.example/x"
    kwargs = fake_client.generate_presigned_url.call_args.kwargs
    assert kwargs["Params"]["Bucket"] == "b"
    assert kwargs["Params"]["Key"] == "assets/u/x.pdf"
    assert kwargs["ExpiresIn"] == 600


def test_build_storage_selects_s3_when_env_set(monkeypatch):
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("AWS_S3_BUCKET", "b")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    s = _build_storage()
    # Hybrid wraps the primary; primary should be S3Storage.
    from cortex.asset_storage import _HybridStorage
    assert isinstance(s, _HybridStorage)
    assert isinstance(s._primary, S3Storage)


def test_build_storage_s3_missing_creds_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "s3")
    monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    s = _build_storage()
    # Missing creds → defensive fallback to LocalDiskStorage instead of
    # crashing the import.
    assert isinstance(s, LocalDiskStorage)
