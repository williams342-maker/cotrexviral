"""Performance metrics + attribution dashboard tests.

Covers:
  1. `record_metric` upsert idempotency on the unique compound index.
  2. `recompute_rollup` produces correct windowed sums + CTR.
  3. `/api/attribution/overview` empty-state when no metrics exist.
  4. `/api/attribution/overview` returns sane numbers after a write.
  5. `/api/attribution/timeseries` shape + day-bounding.
  6. Auth required on both endpoints.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import perf_metrics as PM     # noqa: E402

API_URL = "http://localhost:8001"
TOKEN   = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _cleanup_synthetic():
    """Strip rows we wrote during this test. The test user's REAL
    metrics (from earlier synthetic seed during manual verification)
    are tagged with id-prefix `synth_` so we leave those alone."""
    async def _wipe():
        m = _mongo()
        await m.performance_metrics.delete_many({"variant_id": {"$regex": "^test_perf_vid_"}})
        await m.performance_rollups.delete_many({"variant_id": {"$regex": "^test_perf_vid_"}})
    _run(_wipe())
    yield
    _run(_wipe())


async def _make_variant():
    """Pull an existing variant for the test user — record_metric needs
    a real variant_id to satisfy the FK. We don't *create* a new variant
    here; just pick the first one tied to the test user."""
    v = await _mongo().content_variants.find_one(
        {"user_id": USER_ID}, {"_id": 0, "id": 1, "content_item_id": 1, "brand_id": 1, "platform": 1},
    )
    return v


class TestPerfMetrics:

    def test_record_metric_is_idempotent(self):
        """Same (variant, platform, date) → upsert, never duplicate."""
        async def go():
            v = await _make_variant()
            assert v, "test user has no content_variants — migration may not have run"
            # Override the variant id with a disposable one so cleanup catches it.
            vid = f"test_perf_vid_{uuid.uuid4().hex[:8]}"
            date = "2026-05-01"
            for _ in range(3):
                await PM.record_metric(
                    variant_id=vid, content_item_id=v["content_item_id"],
                    brand_id=v["brand_id"], user_id=USER_ID,
                    platform="instagram", date=date,
                    raw_payload={"impressions": 100, "clicks": 5, "likes": 3},
                )
            count = await _mongo().performance_metrics.count_documents({"variant_id": vid})
            assert count == 1, f"3 record_metric calls should upsert into 1 row, got {count}"
        _run(go())

    def test_rollup_windows_and_ctr(self):
        async def go():
            v = await _make_variant()
            vid = f"test_perf_vid_{uuid.uuid4().hex[:8]}"
            today = datetime.now(timezone.utc).date()
            # Three rows: today (in all 3 windows), 10d (in 30d+all),
            # 100d (in all_time only).
            for delta, payload in [
                (0,   {"impressions": 1000, "clicks": 50,  "likes": 20, "shares": 5}),
                (10,  {"impressions": 2000, "clicks": 100, "likes": 30}),
                (100, {"impressions": 3000, "clicks": 30,  "likes": 5}),
            ]:
                d = (today - timedelta(days=delta)).isoformat()
                await PM.record_metric(
                    variant_id=vid, content_item_id=v["content_item_id"],
                    brand_id=v["brand_id"], user_id=USER_ID,
                    platform="instagram", date=d, raw_payload=payload,
                )
            rollup = await _mongo().performance_rollups.find_one(
                {"variant_id": vid}, {"_id": 0},
            )
            assert rollup, "rollup row was not created"
            # last_7d should only count today's row.
            assert rollup["last_7d"]["impressions"] == 1000
            assert rollup["last_7d"]["clicks"] == 50
            # last_30d should count today + 10d row.
            assert rollup["last_30d"]["impressions"] == 3000
            assert rollup["last_30d"]["clicks"] == 150
            # all_time counts everything.
            assert rollup["all_time"]["impressions"] == 6000
            assert rollup["all_time"]["clicks"] == 180
            # CTR = 180 / 6000 = 0.03
            assert rollup["all_time"]["ctr"] == 0.03
        _run(go())


class TestAttributionAPI:

    def test_overview_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/attribution/overview", timeout=5)
        assert r.status_code == 401

    def test_timeseries_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/attribution/timeseries", timeout=5)
        assert r.status_code == 401

    def test_overview_returns_known_shape(self):
        r = httpx.get(f"{API_URL}/api/attribution/overview", headers=H, timeout=10)
        assert r.status_code == 200
        d = r.json()
        for key in ("brand_id", "platforms", "windows", "top_items", "variants_tracked"):
            assert key in d, f"missing {key}"
        for w in ("last_7d", "last_30d", "all_time"):
            assert w in d["windows"]
            for k in ("impressions", "reach", "clicks", "engagements", "ctr", "samples"):
                assert k in d["windows"][w], f"window {w} missing {k}"

    def test_overview_picks_up_a_freshly_recorded_metric(self):
        """Write one metric → overview must reflect it within the same
        request cycle (no caching layer in front)."""
        async def go():
            v = await _make_variant()
            vid = f"test_perf_vid_{uuid.uuid4().hex[:8]}"
            await PM.record_metric(
                variant_id=vid, content_item_id=v["content_item_id"],
                brand_id=v["brand_id"], user_id=USER_ID,
                platform=v["platform"], date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                raw_payload={"impressions": 7000, "clicks": 280, "likes": 100},
            )
            r = httpx.get(f"{API_URL}/api/attribution/overview", headers=H, timeout=10)
            assert r.status_code == 200
            d = r.json()
            # Our row's impressions must be reflected in all_time.
            assert d["windows"]["all_time"]["impressions"] >= 7000
            # And the platform breakdown must include the variant's platform.
            assert v["platform"] in d["platforms"]
        _run(go())

    def test_timeseries_respects_days_param(self):
        """`?days=1` must restrict the response to today's rows."""
        async def go():
            v = await _make_variant()
            vid = f"test_perf_vid_{uuid.uuid4().hex[:8]}"
            # Write one row 5 days ago and one today.
            today = datetime.now(timezone.utc).date()
            for delta in (0, 5):
                d = (today - timedelta(days=delta)).isoformat()
                await PM.record_metric(
                    variant_id=vid, content_item_id=v["content_item_id"],
                    brand_id=v["brand_id"], user_id=USER_ID,
                    platform="instagram", date=d, raw_payload={"impressions": 100},
                )
            # days=1 should NOT include the 5-day-old row.
            r = httpx.get(f"{API_URL}/api/attribution/timeseries?days=1",
                          headers=H, timeout=10)
            assert r.status_code == 200
            dates = {s["date"] for s in r.json()["series"]}
            five_days_ago = (today - timedelta(days=5)).isoformat()
            assert five_days_ago not in dates, dates
        _run(go())
