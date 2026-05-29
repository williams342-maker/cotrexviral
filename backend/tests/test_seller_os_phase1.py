"""Phase 1 — Seller Acquisition OS regression suite.

Covers Discovery → Qualification → Funnel for a seller-acquisition mission.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

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


def _uid() -> str:
    return requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10).json()["user_id"]


@pytest.fixture
def user_id():
    return _uid()


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        await db.missions.delete_many({"user_id": user_id, "mission_type": "seller_acquisition"})
        await db.seller_leads.delete_many({"user_id": user_id})
        await db.discovery_runs.delete_many({"user_id": user_id})
        await db.qualification_runs.delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


def _mk_mission(niche="woodworking", threshold=None, target=100):
    body = {
        "title": f"Recruit {target} {niche} makers",
        "target": target,
        "mission_type": "seller_acquisition",
        "seller_target_niche": niche,
        "autonomy_level": 3,
    }
    if threshold is not None:
        body["qualification_threshold"] = threshold
    r = requests.post(f"{API_URL}/api/missions", json=body, headers=HEADERS, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


# ----------------------------------------------------------------------
class TestMissionTypeExtension:
    def test_creates_seller_acquisition_mission(self):
        m = _mk_mission()
        assert m["mission_type"] == "seller_acquisition"
        assert m["seller_target_niche"] == "woodworking"

    def test_patch_can_update_niche_and_threshold(self):
        m = _mk_mission()
        r = requests.patch(
            f"{API_URL}/api/missions/{m['id']}",
            json={"seller_target_niche": "laser engraving",
                  "qualification_threshold": 75},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        # PATCH should NOT return these on the response (they're on the doc)
        # but the next GET must.
        g = requests.get(f"{API_URL}/api/missions/{m['id']}",
                         headers=HEADERS, timeout=10).json()
        assert g["seller_target_niche"] == "laser engraving"
        assert g["qualification_threshold"] == 75


# ----------------------------------------------------------------------
class TestDiscovery:
    def test_run_writes_leads(self):
        m = _mk_mission()
        r = requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy", "google_search"], "max_per_source": 10},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] > 0
        assert body["candidates"] >= body["inserted"]
        assert set(body["sources"]) == {"etsy", "google_search"}

        # leads landed
        lst = requests.get(f"{API_URL}/api/seller-leads?mission_id={m['id']}",
                           headers=HEADERS, timeout=10).json()
        assert lst["count"] == body["inserted"]
        assert all(l["stage"] == "discovered" for l in lst["leads"])

    def test_dedupe_skips_existing(self):
        m = _mk_mission()
        r1 = requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy"], "max_per_source": 10},
            headers=HEADERS, timeout=30,
        ).json()
        r2 = requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy"], "max_per_source": 10},
            headers=HEADERS, timeout=30,
        ).json()
        # Second run should see all duplicates
        assert r2["inserted"] == 0
        assert r2["skipped_existing"] == r1["candidates"]

    def test_unknown_source_400(self):
        m = _mk_mission()
        r = requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "x", "sources": ["yelp"]},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 400

    def test_unknown_mission_404(self):
        r = requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": "nope", "niche": "x", "sources": ["etsy"]},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 404

    def test_sources_endpoint_returns_registry(self):
        r = requests.get(f"{API_URL}/api/seller-discovery/sources",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        sources = set(r.json()["sources"])
        assert {"etsy", "shopify", "instagram", "google_search"} <= sources


# ----------------------------------------------------------------------
class TestQualification:
    def _seed(self):
        m = _mk_mission(niche="woodworking", threshold=60)
        requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy", "shopify", "instagram"], "max_per_source": 5},
            headers=HEADERS, timeout=30,
        )
        return m

    def test_qualify_writes_scores_and_advances_stage(self):
        m = self._seed()
        r = requests.post(
            f"{API_URL}/api/seller-qualification/run",
            json={"mission_id": m["id"]},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scored"] > 0
        assert body["accepted"] + body["rejected"] == body["scored"]
        # All results carry a score 0-100
        for r in body["results"]:
            assert 0 <= r["score"] <= 100

        # All leads now have a score + qualified/rejected stage
        lst = requests.get(
            f"{API_URL}/api/seller-leads?mission_id={m['id']}&limit=100",
            headers=HEADERS, timeout=10,
        ).json()
        for l in lst["leads"]:
            assert l["seller_score"] is not None
            assert l["stage"] in ("qualified", "rejected")

    def test_threshold_controls_acceptance(self):
        m = self._seed()
        # Score every lead with a very high threshold → most rejected.
        r_high = requests.post(
            f"{API_URL}/api/seller-qualification/run",
            json={"mission_id": m["id"], "threshold": 95, "requalify": True},
            headers=HEADERS, timeout=30,
        ).json()
        # Score every lead with a very low threshold → all accepted.
        r_low = requests.post(
            f"{API_URL}/api/seller-qualification/run",
            json={"mission_id": m["id"], "threshold": 1, "requalify": True},
            headers=HEADERS, timeout=30,
        ).json()
        assert r_high["accepted"] <= r_low["accepted"]
        assert r_low["accepted"] == r_low["scored"]

    def test_preview_endpoint(self):
        m = self._seed()
        leads = requests.get(
            f"{API_URL}/api/seller-leads?mission_id={m['id']}",
            headers=HEADERS, timeout=10,
        ).json()["leads"]
        lead_id = leads[0]["id"]
        r = requests.get(
            f"{API_URL}/api/seller-qualification/preview/{lead_id}?target_niche=woodworking",
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert 0 <= body["seller_score"] <= 100
        assert set(body["score_breakdown"].keys()) == {
            "quality", "growth", "marketplace_fit", "engagement",
        }


# ----------------------------------------------------------------------
class TestFunnelKPIs:
    def test_funnel_reports_correct_stage_counts(self):
        m = _mk_mission(niche="woodworking", threshold=60)
        requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy", "google_search"], "max_per_source": 6},
            headers=HEADERS, timeout=30,
        )
        # Right after discovery: every lead at stage=discovered
        f = requests.get(f"{API_URL}/api/missions/{m['id']}/seller-funnel",
                         headers=HEADERS, timeout=10).json()
        funnel = f["funnel"]
        assert funnel["discovered"] > 0
        assert funnel["qualified"] == 0

        # After qualification at threshold=1 → all qualified.
        requests.post(
            f"{API_URL}/api/seller-qualification/run",
            json={"mission_id": m["id"], "threshold": 1, "requalify": True},
            headers=HEADERS, timeout=30,
        )
        f2 = requests.get(f"{API_URL}/api/missions/{m['id']}/seller-funnel",
                          headers=HEADERS, timeout=10).json()
        assert f2["funnel"]["qualified"] == funnel["discovered"]
        assert f2["funnel"]["discovered"] == 0

    def test_score_summary_in_funnel(self):
        m = _mk_mission()
        requests.post(
            f"{API_URL}/api/seller-discovery/run",
            json={"mission_id": m["id"], "niche": "woodworking",
                  "sources": ["etsy"], "max_per_source": 5},
            headers=HEADERS, timeout=30,
        )
        requests.post(
            f"{API_URL}/api/seller-qualification/run",
            json={"mission_id": m["id"], "threshold": 0, "requalify": True},
            headers=HEADERS, timeout=30,
        )
        f = requests.get(f"{API_URL}/api/missions/{m['id']}/seller-funnel",
                         headers=HEADERS, timeout=10).json()
        assert f["score_summary"]["n"] > 0
        assert 0 <= f["score_summary"]["average"] <= 100
