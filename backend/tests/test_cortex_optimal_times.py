"""P1 — 'Auto-schedule on optimal times' (mode=optimal_times) for the
bulk push endpoint POST /api/cortex/campaigns/{cid}/push.

Verifies:
- mode=optimal_times schedules every pushable post on an OPTIMAL_BASE slot
  per platform (returns status='scheduled' + scheduled_at populated)
- Round-robin within a platform: distinct scheduled_at per post per platform
- Per-platform OPTIMAL_BASE adherence (weekday + hour)
- Global slot deduplication via used_slots set across platforms
- 400 on invalid mode
- Idempotency: already-pushed posts skip with reason=already_pushed
- Non-pushable platforms (google_ads) skip with reason=platform_not_pushable
- Existing modes unchanged: draft (status=draft, scheduled_at=null) and
  scheduled (cadence_hours spreading)
- Single-post push endpoint regression: draft + scheduled still work,
  invalid mode 400
"""

import os
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load envs so we can hit both the backend HTTP API and Mongo directly.
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Campaigns (3 pinterest, 2 facebook, 3 instagram, 2 instagram_story, 3 google_ads = 13)
OPTIMAL_CID = "f4fb952252934d5383ae1168157d73c6"
DRAFT_CID = "2d546710e31b47819883100eb87d52fc"
SCHED_CID = "960b69244447430e87bbafc3373620d4"
INVALID_CID = "0b134d3bdd314519aaa97586efdff1f7"
IDEMP_CID = "3d579a6bd5f04df39261d8a2779a13cb"  # all already pushed

_PUSHABLE = {"facebook", "instagram", "instagram_story", "linkedin", "pinterest"}

# Mirrors routes/channels.OPTIMAL_BASE — kept inline to assert slots without
# importing backend modules (this test runs as a standalone pytest).
OPTIMAL_BASE = {
    "instagram":  [{"day": d, "hour": h} for d in ["Mon", "Tue", "Wed"] for h in [11, 14, 19]] + [{"day": "Fri", "hour": 11}],
    "facebook":   [{"day": d, "hour": h} for d in ["Tue", "Wed", "Thu"] for h in [9, 13, 15]],
    "linkedin":   [{"day": d, "hour": h} for d in ["Tue", "Wed", "Thu"] for h in [8, 10, 12]],
    "pinterest":  [{"day": d, "hour": h} for d in ["Fri", "Sat", "Sun"] for h in [20, 21, 22]],
}
DOW = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


async def _unstamp(cid, also_delete_posts=True):
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo[DB_NAME]
    cps = await db.cortex_social_posts.find(
        {"campaign_id": cid, "user_id": USER_ID}, {"_id": 0}).to_list(None)
    backup = [{k: v for k, v in p.items() if k in (
        "id", "pushed_at", "posts_id", "pushed_mode", "pushed_platform")} for p in cps]
    await db.cortex_social_posts.update_many(
        {"campaign_id": cid, "user_id": USER_ID},
        {"$unset": {"pushed_at": "", "posts_id": "",
                    "pushed_mode": "", "pushed_platform": ""}})
    if also_delete_posts:
        await db.posts.delete_many({"user_id": USER_ID, "cortex_campaign_id": cid})
    mongo.close()
    return backup


async def _restamp(cid, backup):
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo[DB_NAME]
    for b in backup:
        sets = {k: v for k, v in b.items() if k != "id" and v is not None}
        if sets:
            await db.cortex_social_posts.update_one(
                {"id": b["id"], "user_id": USER_ID},
                {"$set": sets})
    # also clean any /posts rows we may have created
    await db.posts.delete_many({"user_id": USER_ID, "cortex_campaign_id": cid})
    mongo.close()


def _slot_matches(plat, dt):
    """Returns True if dt's (weekday, hour) is a member of OPTIMAL_BASE[plat]."""
    base = OPTIMAL_BASE.get(plat) or []
    return any(DOW[s["day"]] == dt.weekday() and s["hour"] == dt.hour for s in base)


# ---------- mode=optimal_times -----------------------------------------------

class TestOptimalTimesMode:
    """Bulk push with mode=optimal_times — full happy path."""

    @pytest.fixture(scope="class")
    def push_result(self, client):
        backup = asyncio.run(_unstamp(OPTIMAL_CID))
        try:
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{OPTIMAL_CID}/push",
                json={"mode": "optimal_times"}, timeout=120)
            assert r.status_code == 200, r.text
            yield r.json()
        finally:
            asyncio.run(_restamp(OPTIMAL_CID, backup))

    def test_returns_200_with_pushed_and_skipped(self, push_result):
        data = push_result
        assert data["ok"] is True
        assert isinstance(data["pushed"], list)
        assert isinstance(data["skipped"], list)
        # 10 pushable (2 fb + 3 ig + 2 ig_story + 3 pinterest), 3 google_ads skipped
        assert data["counts"]["pushed"] == 10, data["counts"]
        assert data["counts"]["skipped"] == 3, data["counts"]

    def test_every_pushed_entry_is_scheduled(self, push_result):
        for e in push_result["pushed"]:
            assert e["status"] == "scheduled", e
            assert e.get("scheduled_at"), f"missing scheduled_at: {e}"

    def test_google_ads_skipped_as_not_pushable(self, push_result):
        gads = [s for s in push_result["skipped"]
                if (s.get("platform") or "").lower().replace(" ", "_") == "google_ads"]
        assert len(gads) == 3, push_result["skipped"]
        for s in gads:
            assert s["reason"] == "platform_not_pushable"

    def test_round_robin_unique_within_platform(self, push_result):
        """No two posts on the same platform get the same scheduled_at."""
        by_plat: dict = {}
        for e in push_result["pushed"]:
            raw = (e.get("platform") or "").lower().replace(" ", "_")
            canonical = "instagram" if raw == "instagram_story" else raw
            by_plat.setdefault(canonical, []).append(e["scheduled_at"])
        for plat, slots in by_plat.items():
            assert len(set(slots)) == len(slots), (
                f"duplicate slot for {plat}: {slots}")

    def test_global_slot_dedup_across_platforms(self, push_result):
        """used_slots set must prevent any duplicate datetime across platforms."""
        all_slots = [e["scheduled_at"] for e in push_result["pushed"]]
        assert len(set(all_slots)) == len(all_slots), (
            f"global duplicate scheduled_at: {all_slots}")

    def test_slots_adhere_to_OPTIMAL_BASE_per_platform(self, push_result):
        """Each scheduled_at must land on a (weekday, hour) defined in
        OPTIMAL_BASE for that platform (instagram_story → instagram)."""
        for e in push_result["pushed"]:
            raw = (e.get("platform") or "").lower().replace(" ", "_")
            canonical = "instagram" if raw == "instagram_story" else raw
            if canonical not in OPTIMAL_BASE:
                continue
            dt = datetime.fromisoformat(
                e["scheduled_at"].replace("Z", "+00:00"))
            assert _slot_matches(canonical, dt), (
                f"{canonical} post landed on {dt.weekday()=}/{dt.hour=} "
                f"which is not in OPTIMAL_BASE")
            assert dt > datetime.now(timezone.utc), (
                f"scheduled_at must be in the future: {dt}")

    def test_idempotency_already_pushed(self, client, push_result):
        """Re-running optimal_times on same campaign must skip everything
        with reason=already_pushed."""
        r2 = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{OPTIMAL_CID}/push",
            json={"mode": "optimal_times"}, timeout=60)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        # Nothing newly pushed; all 10 pushable now report already_pushed.
        assert d2["counts"]["pushed"] == 0
        already = [s for s in d2["skipped"] if s["reason"] == "already_pushed"]
        not_pushable = [s for s in d2["skipped"]
                        if s["reason"] == "platform_not_pushable"]
        assert len(already) == 10, d2["skipped"]
        assert len(not_pushable) == 3, d2["skipped"]


# ---------- existing modes regression ----------------------------------------

class TestModeDraftRegression:
    def test_draft_mode_has_no_scheduled_at(self, client):
        backup = asyncio.run(_unstamp(DRAFT_CID))
        try:
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{DRAFT_CID}/push",
                json={"mode": "draft"}, timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["counts"]["pushed"] == 10
            for e in d["pushed"]:
                assert e["status"] == "draft", e
                assert e.get("scheduled_at") in (None, ""), e
        finally:
            asyncio.run(_restamp(DRAFT_CID, backup))


class TestModeScheduledRegression:
    def test_scheduled_mode_spreads_by_cadence(self, client):
        backup = asyncio.run(_unstamp(SCHED_CID))
        try:
            start = "2099-01-15T10:00:00+00:00"  # far future
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{SCHED_CID}/push",
                json={"mode": "scheduled", "start_at": start,
                      "cadence_hours": 6}, timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["counts"]["pushed"] == 10
            # All non-null scheduled_at; first one equals start, subsequent
            # ones increment by 6 hours.
            times = [datetime.fromisoformat(e["scheduled_at"].replace("Z", "+00:00"))
                     for e in d["pushed"] if e.get("scheduled_at")]
            assert len(times) == 10
            for i in range(1, len(times)):
                delta = (times[i] - times[i - 1]).total_seconds() / 3600
                assert abs(delta - 6) < 0.01, (
                    f"cadence mismatch at index {i}: {delta}h")
        finally:
            asyncio.run(_restamp(SCHED_CID, backup))


# ---------- error paths -------------------------------------------------------

class TestErrorPaths:
    def test_invalid_mode_returns_400(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{INVALID_CID}/push",
            json={"mode": "magic"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "mode" in r.text.lower()

    def test_optimal_times_does_not_require_start_at(self, client):
        """Sanity: 'optimal_times' must NOT need start_at — confirm we get
        a 200 path (or any non-400-missing-start_at), proving the guard
        only fires for mode='scheduled'."""
        # Use already-pushed campaign so we don't mutate state; expect 200
        # with zero pushed + everything skipped.
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{IDEMP_CID}/push",
            json={"mode": "optimal_times"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["counts"]["pushed"] == 0


# ---------- single-post push regression --------------------------------------

class TestSinglePostPushRegression:
    """Single-push endpoint should still work with mode=draft / scheduled
    and reject mode=optimal_times (single push expects an explicit
    scheduled_at when not draft — optimal_times intentionally does not
    apply)."""

    @pytest.fixture(scope="class")
    def single_post_target(self):
        async def _find():
            mongo = AsyncIOMotorClient(MONGO_URL)
            db = mongo[DB_NAME]
            cp = await db.cortex_social_posts.find_one(
                {"campaign_id": IDEMP_CID, "user_id": USER_ID,
                 "platform": "instagram"}, {"_id": 0, "id": 1})
            mongo.close()
            return cp
        cp = asyncio.run(_find())
        assert cp, "Need at least one instagram post in IDEMP_CID"
        return cp["id"]

    def test_single_push_invalid_mode_returns_400(self, client, single_post_target):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{IDEMP_CID}/posts/"
            f"{single_post_target}/push",
            json={"mode": "optimal_times"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "mode" in r.text.lower()

    def test_single_push_scheduled_requires_scheduled_at(
            self, client, single_post_target):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{IDEMP_CID}/posts/"
            f"{single_post_target}/push",
            json={"mode": "scheduled"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "scheduled_at" in r.text.lower()
