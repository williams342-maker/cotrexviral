"""Experiments — Phase 4 of the Autonomous Growth Team.

Covers the full lifecycle:
  - create requires 2 distinct variants owned by the user
  - hydrated read pulls live perf rollups
  - conclude → completed with memory write when margin clears threshold
  - conclude → inconclusive when margin too small
  - delete cleans up the experiment row but leaves the memory write intact
  - standup integration: gather_experiment_facts returns recent results

All tests run against the live preview backend over HTTP (matches the
pattern used by the rest of the suite).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()

# A real test user with brand_id pre-stamped by the normalize migration.
# Same session token used elsewhere (admin = williams342@gmail.com).
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin_user_id():
    """Resolve the user_id that ADMIN_TOKEN authenticates as. Same approach
    as other tests in the suite — query /api/auth/me, fall back to a
    direct DB lookup on user_sessions if /me changes shape."""
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    if r.status_code == 200:
        return r.json().get("user_id")
    async def go():
        db = _mongo()
        sess = await db.user_sessions.find_one({"session_token": ADMIN_TOKEN}, {"_id": 0, "user_id": 1})
        return (sess or {}).get("user_id")
    return _run(go())


def _seed_variant(user_id: str, brand_id: str, platform: str, body: str,
                  *, rollup_engagements: int = 0, rollup_impressions: int = 0,
                  rollup_ctr: float = 0.0):
    """Create a variant + an optional rollup row so the conclude logic has
    real perf data to compare."""
    vid = uuid.uuid4().hex
    cid = uuid.uuid4().hex
    async def go():
        db = _mongo()
        now = datetime.now(timezone.utc)
        await db.content_variants.insert_one({
            "id": vid, "user_id": user_id, "brand_id": brand_id,
            "content_item_id": cid, "platform": platform, "body": body,
            "status": "published", "created_at": now,
        })
        if rollup_engagements or rollup_impressions:
            await db.performance_rollups.insert_one({
                "variant_id": vid, "user_id": user_id, "brand_id": brand_id,
                "content_item_id": cid, "platform": platform,
                "windows": {
                    "all_time": {
                        "engagements": rollup_engagements,
                        "impressions": rollup_impressions,
                        "clicks": 0, "reach": 0,
                        "ctr": rollup_ctr, "samples": 3,
                    },
                    "last_7d":  {"engagements": 0, "impressions": 0, "clicks": 0,
                                 "reach": 0, "ctr": 0.0, "samples": 0},
                    "last_30d": {"engagements": rollup_engagements, "impressions": rollup_impressions,
                                 "clicks": 0, "reach": 0, "ctr": rollup_ctr, "samples": 3},
                },
                "updated_at": now,
            })
    _run(go())
    return vid


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing in DB")
    return uid


@pytest.fixture
def admin_brand_id(admin_user_id):
    async def go():
        db = _mongo()
        b = await db.brands.find_one({"user_id": admin_user_id}, {"_id": 0, "id": 1})
        if b:
            return b["id"]
        # Mint one on the fly so tests don't depend on the normalize migration.
        bid = uuid.uuid4().hex
        await db.brands.insert_one({
            "id": bid, "user_id": admin_user_id,
            "name": "pytest brand", "created_at": datetime.now(timezone.utc),
        })
        return bid
    return _run(go())


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    """Wipe test-injected rows before AND after each test so order doesn't matter."""
    async def go():
        db = _mongo()
        await db.experiments.delete_many({"user_id": admin_user_id, "name": {"$regex": "^pytest_"}})
        await db.cortex_memory.delete_many({"user_id": admin_user_id, "kind": "experiment_winner",
                                            "text": {"$regex": "pytest_"}})
        # Clean up our seeded variants too (matched by body prefix).
        variant_ids = [v["id"] async for v in db.content_variants.find(
            {"user_id": admin_user_id, "body": {"$regex": "^pytest_"}}, {"_id": 0, "id": 1},
        )]
        if variant_ids:
            await db.content_variants.delete_many({"id": {"$in": variant_ids}})
            await db.performance_rollups.delete_many({"variant_id": {"$in": variant_ids}})
    _run(go())
    yield
    _run(go())


class TestAuth:
    def test_endpoints_require_auth(self):
        for path, method, payload in [
            ("/api/experiments/metrics",       "get",    None),
            ("/api/experiments",               "get",    None),
            ("/api/variants/recent",           "get",    None),
            ("/api/experiments/abc/conclude",  "post",   {}),
            ("/api/experiments/abc",           "delete", None),
        ]:
            kw = {"timeout": 10}
            if payload is not None:
                kw["json"] = payload
            r = getattr(requests, method)(f"{API_URL}{path}", **kw)
            assert r.status_code == 401, f"{method.upper()} {path} → {r.status_code}"


class TestMetricsEnum:
    def test_metrics_returned(self):
        r = requests.get(f"{API_URL}/api/experiments/metrics", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        ids = {m["id"] for m in r.json()["metrics"]}
        assert ids == {"engagements", "impressions", "clicks", "reach", "ctr"}
        assert r.json()["min_margin_pct"] == 10.0


class TestCreateAndList:
    def test_create_requires_distinct_variants(self, admin_user_id, admin_brand_id):
        v = _seed_variant(admin_user_id, admin_brand_id, "instagram", "pytest_a", rollup_engagements=10)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_dupe", "variant_a_id": v, "variant_b_id": v,
                                "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        assert r.status_code == 400
        assert "differ" in r.text.lower()

    def test_create_rejects_unknown_metric(self, admin_user_id, admin_brand_id):
        a = _seed_variant(admin_user_id, admin_brand_id, "instagram", "pytest_a")
        b = _seed_variant(admin_user_id, admin_brand_id, "instagram", "pytest_b")
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_bad_metric", "variant_a_id": a,
                                "variant_b_id": b, "metric": "vanity_score"},
                          headers=HEADERS, timeout=10)
        assert r.status_code == 400

    def test_create_and_list_round_trip(self, admin_user_id, admin_brand_id):
        a = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_hook_question?", rollup_engagements=120, rollup_impressions=2000)
        b = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_hook_statement.", rollup_engagements=80, rollup_impressions=2000)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_hook_test", "hypothesis": "Questions win",
                                "variant_a_id": a, "variant_b_id": b, "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "running"
        assert body["live_leader"] == "a"
        # 120 vs 80 → 50% margin
        assert body["live_margin_pct"] >= 49.9
        assert body["variant_a"]["engagements"] == 120
        assert body["variant_b"]["engagements"] == 80

        # List endpoint reflects it
        r = requests.get(f"{API_URL}/api/experiments?status=running", headers=HEADERS, timeout=10)
        names = {e["name"] for e in r.json()["items"]}
        assert "pytest_hook_test" in names


class TestConclude:
    def test_conclude_writes_memory_when_decisive(self, admin_user_id, admin_brand_id):
        a = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_winning_caption", rollup_engagements=200, rollup_impressions=3000)
        b = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_losing_caption",  rollup_engagements=80,  rollup_impressions=3000)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_decisive", "variant_a_id": a,
                                "variant_b_id": b, "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        exp_id = r.json()["id"]

        r = requests.post(f"{API_URL}/api/experiments/{exp_id}/conclude",
                          headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "completed"
        assert body["winner_variant_id"] == a
        assert body["winner_margin_pct"] >= 99.9  # 200 vs 80 → +150%
        assert body["memory_id"]
        # Memory row landed
        async def check():
            db = _mongo()
            mem = await db.cortex_memory.find_one({"id": body["memory_id"]})
            assert mem is not None
            assert mem["kind"] == "experiment_winner"
            assert "pytest_winning_caption" in mem["text"]
            assert mem["meta"]["winner_variant_id"] == a
        _run(check())

    def test_conclude_inconclusive_when_margin_too_small(self, admin_user_id, admin_brand_id):
        a = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_marginal_a", rollup_engagements=105, rollup_impressions=1000)
        b = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_marginal_b", rollup_engagements=100, rollup_impressions=1000)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_marginal", "variant_a_id": a,
                                "variant_b_id": b, "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        exp_id = r.json()["id"]

        r = requests.post(f"{API_URL}/api/experiments/{exp_id}/conclude",
                          headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "inconclusive"
        assert body["winner_variant_id"] is None
        # No memory write for the inconclusive path — protect the signal layer
        async def check():
            db = _mongo()
            count = await db.cortex_memory.count_documents({
                "user_id": admin_user_id,
                "dedupe_key": f"experiment:{exp_id}",
            })
            assert count == 0
        _run(check())

    def test_conclude_404_on_non_running(self, admin_user_id, admin_brand_id):
        a = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_x", rollup_engagements=200, rollup_impressions=1000)
        b = _seed_variant(admin_user_id, admin_brand_id, "instagram",
                          "pytest_y", rollup_engagements=50, rollup_impressions=1000)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_already_done", "variant_a_id": a,
                                "variant_b_id": b, "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        exp_id = r.json()["id"]
        # Conclude once → completed
        requests.post(f"{API_URL}/api/experiments/{exp_id}/conclude",
                      headers=HEADERS, timeout=10)
        # Conclude again → 404 because it's no longer running
        r = requests.post(f"{API_URL}/api/experiments/{exp_id}/conclude",
                          headers=HEADERS, timeout=10)
        assert r.status_code == 404


class TestVariantsRecent:
    def test_recent_returns_seeded(self, admin_user_id, admin_brand_id):
        _seed_variant(admin_user_id, admin_brand_id, "tiktok", "pytest_recent_one")
        r = requests.get(f"{API_URL}/api/variants/recent?limit=20", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        bodies = {v["body"] for v in r.json()["items"]}
        assert "pytest_recent_one" in bodies


class TestStandupIntegration:
    def test_facts_gathered(self, admin_user_id, admin_brand_id):
        """gather_experiment_facts surfaces recent results for Ori."""
        a = _seed_variant(admin_user_id, admin_brand_id, "linkedin",
                          "pytest_standup_a", rollup_engagements=200, rollup_impressions=1000)
        b = _seed_variant(admin_user_id, admin_brand_id, "linkedin",
                          "pytest_standup_b", rollup_engagements=50, rollup_impressions=1000)
        r = requests.post(f"{API_URL}/api/experiments",
                          json={"name": "pytest_for_standup", "variant_a_id": a,
                                "variant_b_id": b, "metric": "engagements"},
                          headers=HEADERS, timeout=10)
        exp_id = r.json()["id"]
        requests.post(f"{API_URL}/api/experiments/{exp_id}/conclude",
                      headers=HEADERS, timeout=10)

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.experiments import gather_experiment_facts
        facts = _run(gather_experiment_facts(admin_user_id))
        names = {r["name"] for r in facts["recent_results"]}
        assert "pytest_for_standup" in names
