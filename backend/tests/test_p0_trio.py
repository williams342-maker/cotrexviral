"""P0 trio — Week in Review digest + 80% headroom alerts + Ori auto-conclude.

Bundled because the three features ship together. Covers:
  • Digest compute + persist; idempotency on re-run within same week
  • Email skipped gracefully without provider config
  • /digests/latest returns computed-on-the-fly when no row exists
  • Headroom alert fires once when usage crosses 80%; dedupes on re-tick
  • 100% threshold is a distinct alert from 80%
  • Mark-read flow
  • auto_conclude_due_experiments writes a winner when margin clears 10%
  • auto_conclude skips experiments with sub-threshold margins
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
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


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
        await db.weekly_digests.delete_many({"user_id": admin_user_id})
        await db.agent_alerts.delete_many({"user_id": admin_user_id})
        await db.agent_usage_ledger.delete_many({"user_id": admin_user_id})
        # Wipe pytest experiments + their cleanup
        async def find_ids(coll, regex):
            return [d["id"] async for d in coll.find({"user_id": admin_user_id, regex[0]: {"$regex": regex[1]}}, {"_id": 0, "id": 1})]
        for d in await db.experiments.find({"user_id": admin_user_id, "name": {"$regex": "^pytest_"}}, {"_id": 0, "id": 1}).to_list(50):
            await db.experiments.delete_one({"id": d["id"]})
        variants = [v["id"] async for v in db.content_variants.find({"user_id": admin_user_id, "body": {"$regex": "^pytest_"}}, {"_id": 0, "id": 1})]
        if variants:
            await db.content_variants.delete_many({"id": {"$in": variants}})
            await db.performance_rollups.delete_many({"variant_id": {"$in": variants}})
    _run(go())
    yield
    _run(go())


# =====================================================================
# A) Week in Review digest
# =====================================================================
class TestDigestEndpoints:
    def test_auth_required(self):
        for path, method in [
            ("/api/digests/latest", "get"),
            ("/api/digests", "get"),
            ("/api/digests/run-now", "post"),
        ]:
            kw = {"timeout": 10}
            if method == "post":
                kw["json"] = {}
            r = getattr(requests, method)(f"{API_URL}{path}", **kw)
            assert r.status_code == 401, f"{path} → {r.status_code}"

    def test_latest_computes_on_fly_when_empty(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/digests/latest",
                         headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("iso_week", "briefs_proposed", "briefs_approved",
                  "experiments_concluded", "posts_published",
                  "signals_captured", "goal_progress_pct",
                  "active_goals", "agent_burns"):
            assert k in body, f"missing {k}"

    def test_run_now_persists_and_dedupes(self, admin_user_id):
        # First run — creates the row
        r = requests.post(f"{API_URL}/api/digests/run-now?email=false",
                          headers=HEADERS, timeout=20)
        assert r.status_code == 200
        iso_wk = r.json()["iso_week"]
        async def count():
            db = _mongo()
            return await db.weekly_digests.count_documents(
                {"user_id": admin_user_id, "iso_week": iso_wk})
        assert _run(count()) == 1

        # Second run same week — UPSERTS (still 1 row)
        r = requests.post(f"{API_URL}/api/digests/run-now?email=false",
                          headers=HEADERS, timeout=20)
        assert r.status_code == 200
        assert _run(count()) == 1


# =====================================================================
# B) Headroom alerts (80% / 100%)
# =====================================================================
class TestHeadroomAlerts:
    def test_alert_fires_at_80_pct(self, admin_user_id):
        """Burn enough Atlas tokens to cross 80% on the tokens axis but
        stay under 100%. Verify ONE alert lands, with threshold=80."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, _iso_week_key
        from routes.agent_personas import PERSONAS

        cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]["max_tokens_per_week"]
        target = int(cap * 0.85)  # 85% — past 80, under 100
        _run(record_usage("atlas", admin_user_id, tokens=target))

        async def fetch():
            db = _mongo()
            return await db.agent_alerts.find(
                {"user_id": admin_user_id, "agent_id": "atlas", "iso_week": _iso_week_key()},
                {"_id": 0},
            ).to_list(length=10)
        alerts = _run(fetch())
        assert len(alerts) == 1, f"expected 1 alert, got {len(alerts)}: {alerts}"
        assert alerts[0]["threshold"] == 80
        assert alerts[0]["headroom_pct"] >= 80

    def test_dedupes_within_same_week_and_threshold(self, admin_user_id):
        """Multiple ticks past 80% only produce ONE 80-tier alert."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, _iso_week_key
        from routes.agent_personas import PERSONAS

        cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]["max_tokens_per_week"]
        # First tick lands in the 80% band
        _run(record_usage("atlas", admin_user_id, tokens=int(cap * 0.85)))
        # Re-tick a few more in the same band — alert should not duplicate
        _run(record_usage("atlas", admin_user_id, tokens=int(cap * 0.02)))
        _run(record_usage("atlas", admin_user_id, tokens=int(cap * 0.02)))

        async def count():
            db = _mongo()
            return await db.agent_alerts.count_documents({
                "user_id": admin_user_id, "agent_id": "atlas",
                "iso_week": _iso_week_key(), "threshold": 80,
            })
        assert _run(count()) == 1

    def test_100_pct_fires_separate_alert(self, admin_user_id):
        """Crossing 100% produces a NEW alert (threshold=100) in addition
        to any 80-tier one already on file."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, _iso_week_key
        from routes.agent_personas import PERSONAS

        cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]["max_tokens_per_week"]
        # Cross 80% then jump past 100%
        _run(record_usage("atlas", admin_user_id, tokens=int(cap * 0.85)))
        _run(record_usage("atlas", admin_user_id, tokens=cap))  # blows past 100%

        async def by_threshold():
            db = _mongo()
            rows = await db.agent_alerts.find(
                {"user_id": admin_user_id, "agent_id": "atlas",
                 "iso_week": _iso_week_key()},
                {"_id": 0, "threshold": 1},
            ).to_list(length=10)
            return {r["threshold"] for r in rows}
        thresholds = _run(by_threshold())
        assert 100 in thresholds
        assert 80 in thresholds  # the earlier 85% tick fired the 80-tier

    def test_mark_read_endpoint(self, admin_user_id):
        # Seed an alert directly
        async def seed():
            db = _mongo()
            aid = uuid.uuid4().hex
            await db.agent_alerts.insert_one({
                "id": aid, "user_id": admin_user_id, "agent_id": "atlas",
                "agent_name": "Atlas", "agent_role": "Strategist",
                "iso_week": "2026-W22", "threshold": 80,
                "headroom_pct": 85, "can_act": True,
                "read": False, "created_at": datetime.now(timezone.utc),
            })
            return aid
        aid = _run(seed())

        # Unread shows up
        r = requests.get(f"{API_URL}/api/agents/alerts?unread_only=true",
                         headers=HEADERS, timeout=10)
        assert any(a["id"] == aid for a in r.json()["items"])
        assert r.json()["unread_count"] >= 1

        # Mark single read
        r = requests.post(f"{API_URL}/api/agents/alerts/{aid}/read",
                          headers=HEADERS, timeout=10)
        assert r.status_code == 200

        # Now it's no longer unread
        r = requests.get(f"{API_URL}/api/agents/alerts?unread_only=true",
                         headers=HEADERS, timeout=10)
        assert not any(a["id"] == aid for a in r.json()["items"])


# =====================================================================
# C) Auto-conclude experiments cron
# =====================================================================
class TestAutoConcludeCron:
    def _seed_variant_and_rollup(self, user_id, body, engagements):
        vid = uuid.uuid4().hex
        async def go():
            db = _mongo()
            now = datetime.now(timezone.utc)
            await db.content_variants.insert_one({
                "id": vid, "user_id": user_id, "brand_id": "pytest-brand",
                "content_item_id": uuid.uuid4().hex, "platform": "instagram",
                "body": body, "status": "published", "created_at": now,
            })
            await db.performance_rollups.insert_one({
                "variant_id": vid, "user_id": user_id, "platform": "instagram",
                "windows": {
                    "all_time": {"engagements": engagements, "impressions": 1000,
                                  "clicks": 0, "reach": 0, "ctr": 0.0, "samples": 3},
                    "last_7d":  {"engagements": 0, "impressions": 0, "clicks": 0, "reach": 0, "ctr": 0.0, "samples": 0},
                    "last_30d": {"engagements": engagements, "impressions": 1000,
                                  "clicks": 0, "reach": 0, "ctr": 0.0, "samples": 3},
                },
                "updated_at": now,
            })
        _run(go())
        return vid

    def test_auto_concludes_winner(self, admin_user_id):
        va = self._seed_variant_and_rollup(admin_user_id, "pytest_auto_a", engagements=200)
        vb = self._seed_variant_and_rollup(admin_user_id, "pytest_auto_b", engagements=80)
        # Create the experiment directly (skipping the propose API)
        async def seed_exp():
            db = _mongo()
            eid = uuid.uuid4().hex
            await db.experiments.insert_one({
                "id": eid, "user_id": admin_user_id,
                "name": "pytest_auto_decisive", "hypothesis": "A wins",
                "variant_a_id": va, "variant_b_id": vb,
                "metric": "engagements", "status": "running",
                "started_at": datetime.now(timezone.utc),
                "ended_at": None, "winner_variant_id": None,
                "winner_margin_pct": None, "conclusion_text": None,
                "memory_id": None, "owner_agent": "ori",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            return eid
        eid = _run(seed_exp())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.experiments import auto_conclude_due_experiments
        summary = _run(auto_conclude_due_experiments())
        assert summary["concluded"] >= 1

        async def check():
            db = _mongo()
            doc = await db.experiments.find_one({"id": eid})
            assert doc["status"] == "completed"
            assert doc["winner_variant_id"] == va
            assert doc.get("auto_concluded") is True
            assert doc["memory_id"]
            mem = await db.cortex_memory.find_one({"id": doc["memory_id"]})
            assert mem is not None
            assert mem["meta"].get("auto_concluded") is True
        _run(check())

    def test_skips_sub_threshold_margin(self, admin_user_id):
        va = self._seed_variant_and_rollup(admin_user_id, "pytest_marginal_a", engagements=105)
        vb = self._seed_variant_and_rollup(admin_user_id, "pytest_marginal_b", engagements=100)
        async def seed_exp():
            db = _mongo()
            eid = uuid.uuid4().hex
            await db.experiments.insert_one({
                "id": eid, "user_id": admin_user_id,
                "name": "pytest_auto_marginal", "hypothesis": "A barely wins",
                "variant_a_id": va, "variant_b_id": vb,
                "metric": "engagements", "status": "running",
                "started_at": datetime.now(timezone.utc),
                "ended_at": None, "winner_variant_id": None,
                "winner_margin_pct": None, "conclusion_text": None,
                "memory_id": None, "owner_agent": "ori",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            return eid
        eid = _run(seed_exp())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.experiments import auto_conclude_due_experiments
        summary = _run(auto_conclude_due_experiments())
        async def check():
            db = _mongo()
            doc = await db.experiments.find_one({"id": eid})
            assert doc["status"] == "running"  # left alone
        _run(check())
        assert summary["skipped"] >= 1
