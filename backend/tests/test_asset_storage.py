"""Asset storage adapter tests — exercises the live Emergent Object
Storage backend through the production code path (no mocks).

Covers:
  • Adapter selection via env var (`ASSET_STORAGE_BACKEND=emergent`).
  • EmergentObjStorage save → read round-trip (real network call).
  • read() raises FileNotFoundError for unknown keys.
  • delete() is a no-op (the Emergent service has no delete API).
  • HybridStorage falls back to local disk on read miss.
  • End-to-end upload via POST /api/cortex/assets/upload and download
    via GET /api/cortex/assets/file/{key} actually round-trip through
    object storage.

These tests hit the live `integrations.emergentagent.com` service. If
that service is down the network-dependent tests will fail loudly —
that's intentional, we want to know.
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from cortex.asset_storage import (   # noqa: E402
    EmergentObjStorage, LocalDiskStorage, _HybridStorage, _build_storage,
)

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TEST_TOKEN = "test_session_1779636592168"
TEST_USER_ID = "user_test1779636592168"
HEADERS_JSON = {"Authorization": f"Bearer {TEST_TOKEN}",
                "Content-Type": "application/json"}
HEADERS_AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------
# Adapter selection
# --------------------------------------------------------------------------
def test_build_storage_selects_emergent_when_env_set(monkeypatch):
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "emergent")
    s = _build_storage()
    # Hybrid wraps the primary; primary should be Emergent.
    assert isinstance(s, _HybridStorage)
    assert isinstance(s._primary, EmergentObjStorage)
    assert isinstance(s._legacy, LocalDiskStorage)


def test_build_storage_defaults_to_local(monkeypatch):
    monkeypatch.delenv("ASSET_STORAGE_BACKEND", raising=False)
    s = _build_storage()
    assert isinstance(s, LocalDiskStorage)


def test_build_storage_unknown_value_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "snowflake")
    s = _build_storage()
    assert isinstance(s, LocalDiskStorage)


# --------------------------------------------------------------------------
# EmergentObjStorage (live network)
# --------------------------------------------------------------------------
@pytest.fixture
def emergent_storage():
    return EmergentObjStorage()


def test_emergent_save_then_read_round_trip(emergent_storage):
    """The contract we care about: bytes in == bytes out."""
    key = f"assets/{TEST_USER_ID}/regression-{uuid.uuid4().hex}.txt"
    payload = b"cortexviral regression test payload " * 30
    returned_key = _run(emergent_storage.save(key, payload))
    assert returned_key == key
    got = _run(emergent_storage.read(key))
    assert got == payload


def test_emergent_read_missing_raises_file_not_found(emergent_storage):
    """The route layer turns FileNotFoundError into HTTP 404. This is
    the contract the entire pipeline relies on."""
    missing = f"assets/{TEST_USER_ID}/does-not-exist-{uuid.uuid4().hex}.txt"
    with pytest.raises(FileNotFoundError):
        _run(emergent_storage.read(missing))


def test_emergent_delete_is_a_noop(emergent_storage):
    """The Emergent service has no delete API. delete() must succeed
    without erroring even though the bytes remain on the server side —
    cleanup is handled by the DB row's `deleted_at` flag."""
    key = f"assets/{TEST_USER_ID}/delete-noop-{uuid.uuid4().hex}.bin"
    _run(emergent_storage.save(key, b"abc"))
    # Should not raise.
    _run(emergent_storage.delete(key))
    # And the bytes are still there — we documented this behaviour.
    got = _run(emergent_storage.read(key))
    assert got == b"abc"


def test_emergent_public_url_uses_backend_proxy(emergent_storage):
    """We never expose direct object-store URLs to clients. The proxy
    keeps per-user ACL checks in front of every byte."""
    url = emergent_storage.public_url("assets/u-abc/x.pdf")
    assert url == "/api/cortex/assets/file/assets/u-abc/x.pdf"


def test_emergent_save_enforces_max_bytes(emergent_storage):
    key = f"assets/{TEST_USER_ID}/too-big-{uuid.uuid4().hex}.bin"
    with pytest.raises(ValueError):
        _run(emergent_storage.save(key, b"x" * 100, max_bytes=50))


# --------------------------------------------------------------------------
# HybridStorage (read fallback)
# --------------------------------------------------------------------------
def test_hybrid_falls_back_to_local_on_read_miss(tmp_path):
    """Legacy files that still live on local disk (pre-migration) must
    keep serving after we flip the env var to emergent."""
    legacy = LocalDiskStorage(root=str(tmp_path))
    legacy_key = f"assets/legacy-{uuid.uuid4().hex}.txt"
    _run(legacy.save(legacy_key, b"legacy bytes"))

    primary = EmergentObjStorage()
    hybrid = _HybridStorage(primary, legacy)
    # Primary won't have this key; hybrid must fall back.
    got = _run(hybrid.read(legacy_key))
    assert got == b"legacy bytes"


def test_hybrid_writes_go_only_to_primary(tmp_path):
    """If save() ever leaked to the local disk in hybrid mode we'd have
    two sources of truth — guard against that."""
    legacy = LocalDiskStorage(root=str(tmp_path))
    primary = EmergentObjStorage()
    hybrid = _HybridStorage(primary, legacy)
    key = f"assets/{TEST_USER_ID}/hybrid-write-{uuid.uuid4().hex}.txt"
    _run(hybrid.save(key, b"new bytes via hybrid"))
    # The legacy disk must NOT have this file.
    assert not (Path(tmp_path) / key).exists()
    # The primary DOES have it — read via the primary directly.
    got = _run(primary.read(key))
    assert got == b"new bytes via hybrid"


# --------------------------------------------------------------------------
# End-to-end via HTTP API — proves the entire pipeline (route → adapter
# → Emergent → adapter → route) actually returns the same bytes the
# user uploaded. This is the test that would have caught a misconfigured
# backend swap on a deploy.
# --------------------------------------------------------------------------
def test_e2e_upload_then_download_via_api():
    """Hit /api/cortex/assets/upload with a small PDF, then GET it back
    via /api/cortex/assets/file/{key} and verify byte identity."""
    # Minimal valid-ish PDF header + body so the pipeline mime sniff
    # accepts it (real upload route validates content_type).
    pdf_bytes = b"%PDF-1.4\n%%EOF\n" + (b"x" * 500)
    files = {"file": (f"regression-{uuid.uuid4().hex}.pdf",
                       pdf_bytes, "application/pdf")}
    r = requests.post(f"{API_URL}/api/cortex/assets/upload",
                      files=files, headers=HEADERS_AUTH, timeout=60)
    assert r.status_code in (200, 201), f"upload failed: {r.status_code} {r.text}"
    asset = r.json()
    asset_id = asset.get("id") or asset.get("asset_id") or (
        asset.get("asset") or {}).get("id")
    storage_key = (asset.get("storage_key")
                   or (asset.get("asset") or {}).get("storage_key"))
    assert asset_id, f"no asset id in upload response: {asset}"
    assert storage_key, f"no storage_key in upload response: {asset}"

    try:
        # Stream it back via the backend proxy. This proves the proxy
        # reads through the Emergent adapter correctly.
        r2 = requests.get(
            f"{API_URL}/api/cortex/assets/file/{storage_key}",
            headers=HEADERS_AUTH, timeout=30,
        )
        assert r2.status_code == 200, r2.text
        # Byte identity end-to-end.
        assert r2.content == pdf_bytes
    finally:
        # Clean up — soft-delete via the bulk endpoint.
        requests.post(f"{API_URL}/api/cortex/assets/bulk-delete",
                      json={"ids": [asset_id]}, headers=HEADERS_JSON, timeout=15)
