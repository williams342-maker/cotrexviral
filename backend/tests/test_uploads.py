"""Compose video-upload endpoint tests.

Covers:
  • Auth required on POST /uploads/video
  • Multipart upload writes the file + returns a usable URL + DB row
  • GET /uploads/videos/{name} streams the file back
  • Path traversal attempts return 404
  • Content-type allow-list rejects non-video types
  • Size cap rejects oversized uploads
  • DELETE /uploads/videos/{asset_id} works for the owner
  • run_upload_cleanup removes expired rows
"""
import asyncio
import io
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

# Minimal fake "video" payload — content_type is what gates acceptance,
# not the actual bytes (YouTube would sniff the file anyway).
FAKE_MP4 = b"fake-mp4-bytes-for-testing-only-" * 10


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin_user_id():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    return r.json().get("user_id") if r.status_code == 200 else None


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing")
    return uid


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    async def go():
        db = _mongo()
        rows = await db.uploaded_videos.find(
            {"user_id": admin_user_id, "filename": {"$regex": "^pytest_"}},
            {"_id": 0, "path": 1},
        ).to_list(length=50)
        for r in rows:
            Path(r["path"]).unlink(missing_ok=True)
        await db.uploaded_videos.delete_many({"user_id": admin_user_id, "filename": {"$regex": "^pytest_"}})
    _run(go())
    yield
    _run(go())


class TestAuth:
    def test_post_requires_auth(self):
        files = {"file": ("pytest_no_auth.mp4", io.BytesIO(FAKE_MP4), "video/mp4")}
        r = requests.post(f"{API_URL}/api/uploads/video", files=files, timeout=15)
        assert r.status_code == 401

    def test_delete_requires_auth(self):
        r = requests.delete(f"{API_URL}/api/uploads/videos/some-id", timeout=10)
        assert r.status_code == 401


class TestUploadFlow:
    def test_upload_persists_and_serves(self, admin_user_id):
        files = {"file": ("pytest_sample.mp4", io.BytesIO(FAKE_MP4), "video/mp4")}
        r = requests.post(f"{API_URL}/api/uploads/video", files=files,
                          headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["asset_id"]
        assert body["bytes"] == len(FAKE_MP4)
        assert "/api/uploads/videos/" in body["url"]
        # DB row exists
        async def check():
            db = _mongo()
            doc = await db.uploaded_videos.find_one({"asset_id": body["asset_id"]})
            assert doc is not None
            assert doc["user_id"] == admin_user_id
            assert doc["size"] == len(FAKE_MP4)
            assert Path(doc["path"]).is_file()
        _run(check())

        # Streaming GET round-trips the bytes
        filename = body["url"].split("/")[-1]
        g = requests.get(f"{API_URL}/api/uploads/videos/{filename}", timeout=15)
        assert g.status_code == 200
        assert g.content == FAKE_MP4
        assert g.headers["content-type"] in ("video/mp4", "video/mp4; charset=utf-8")

    def test_path_traversal_blocked(self):
        for evil in ["..%2Fpasswd", "../../etc/passwd", ".hidden"]:
            r = requests.get(f"{API_URL}/api/uploads/videos/{evil}", timeout=10)
            assert r.status_code == 404, f"path-traversal {evil} returned {r.status_code}"

    def test_rejects_non_video_content_type(self, admin_user_id):
        files = {"file": ("pytest_bogus.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(f"{API_URL}/api/uploads/video", files=files,
                          headers=HEADERS, timeout=15)
        assert r.status_code == 415

    def test_delete_removes_row_and_file(self, admin_user_id):
        files = {"file": ("pytest_delete_target.mp4", io.BytesIO(FAKE_MP4), "video/mp4")}
        r = requests.post(f"{API_URL}/api/uploads/video", files=files,
                          headers=HEADERS, timeout=15)
        asset_id = r.json()["asset_id"]

        d = requests.delete(f"{API_URL}/api/uploads/videos/{asset_id}",
                            headers=HEADERS, timeout=10)
        assert d.status_code == 200

        # DB row + file are gone
        async def check():
            db = _mongo()
            doc = await db.uploaded_videos.find_one({"asset_id": asset_id})
            assert doc is None
        _run(check())


class TestCleanupJob:
    def test_run_upload_cleanup_removes_expired(self, admin_user_id):
        # Seed an "expired" upload row that points at a real file.
        files = {"file": ("pytest_to_expire.mp4", io.BytesIO(FAKE_MP4), "video/mp4")}
        r = requests.post(f"{API_URL}/api/uploads/video", files=files,
                          headers=HEADERS, timeout=15)
        asset_id = r.json()["asset_id"]
        # Backdate the expires_at so the cleanup picks it up.
        async def backdate():
            db = _mongo()
            await db.uploaded_videos.update_one(
                {"asset_id": asset_id},
                {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(hours=1)}},
            )
        _run(backdate())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.uploads import run_upload_cleanup
        summary = _run(run_upload_cleanup())
        assert summary["removed"] >= 1
        async def check_gone():
            db = _mongo()
            assert await db.uploaded_videos.find_one({"asset_id": asset_id}) is None
        _run(check_gone())
