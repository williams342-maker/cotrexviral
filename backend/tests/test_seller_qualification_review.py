"""Seller Qualification — Manual Review Queue, Confidence Scoring,
Prospect Intel Cards, and Recommended-Action endpoint (iter 28).

Covers the 4-item batch:
  1) score_lead() new fields (confidence, confidence_band, signals,
     prospect_card).
  2) 3-band routing in POST /seller-qualification/run.
  3) Manual review queue + per-lead promote/reject decisions.
  4) Recommended-action endpoint replacing "Found N sellers" framing.
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
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _uid() -> str:
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=30)
    assert r.status_code == 200, f"auth/me failed: {r.status_code} {r.text}"
    return r.json()["user_id"]


@pytest.fixture(scope="module")
def user_id():
    return _uid()


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        for c in ("missions", "seller_leads", "qualification_runs"):
            await db[c].delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


# ------------------------------ seeders ------------------------------
def _seed_mission(user_id: str, threshold: float = 60.0,
                  niche: str = "woodworking") -> str:
    mid = uuid.uuid4().hex
    async def go():
        db = _mongo()
        await db.missions.insert_one({
            "id": mid,
            "user_id": user_id,
            "title": "TEST_seller_acquisition_mission",
            "mission_type": "seller_acquisition",
            "seller_target_niche": niche,
            "qualification_threshold": threshold,
            "created_at": datetime.now(timezone.utc),
        })
    _run(go())
    return mid


def _lead(user_id: str, mission_id: str, **kw) -> str:
    lid = uuid.uuid4().hex
    base = {
        "id": lid,
        "user_id": user_id,
        "mission_id": mission_id,
        "business_name": kw.get("business_name", "TEST_Seller_" + lid[:6]),
        "niche": kw.get("niche", "woodworking"),
        "source": kw.get("source", "etsy"),
        "stage": "discovered",
        "socials": kw.get("socials", {"instagram": "x", "pinterest": "y"}),
        "website": kw.get("website", "https://x.example.com"),
        "estimated_activity": kw.get("estimated_activity", "high"),
        "product_categories": kw.get("product_categories", ["cat1", "cat2", "cat3"]),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    async def go():
        await _mongo().seller_leads.insert_one(base)
    _run(go())
    return lid


# Lead designed to score high (≥60): high activity, woodworking niche, full socials/website.
def _seed_high(user_id, mid):
    return _lead(user_id, mid, niche="woodworking", estimated_activity="high",
                 socials={"instagram": "a", "pinterest": "b", "tiktok": "c"},
                 product_categories=["c1", "c2", "c3", "c4"])


# Medium band 45–59: moderate signals
def _seed_medium(user_id, mid):
    return _lead(user_id, mid, niche="unrelated_topic",
                 business_name="MidBrand Co",
                 estimated_activity="medium",
                 socials={"instagram": "a"},
                 website="",
                 product_categories=["c1"])


# Low band <45: very poor signals
def _seed_low(user_id, mid):
    return _lead(user_id, mid, niche="completely_unrelated",
                 business_name="test demo brand",  # placeholder penalty
                 estimated_activity="low",
                 socials={}, website="",
                 product_categories=[],
                 source="other")


# ---------------------------------------------------------------------
# Scoring + 3-band routing
# ---------------------------------------------------------------------
class TestQualificationRunAndBands:
    def test_run_routes_three_bands_and_persists_fields(self, user_id):
        mid = _seed_mission(user_id)
        hid = _seed_high(user_id, mid)
        mid_lead = _seed_medium(user_id, mid)
        lid = _seed_low(user_id, mid)

        r = requests.post(f"{API_URL}/api/seller-qualification/run",
                          json={"mission_id": mid}, headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Response carries the new fields.
        assert data["threshold"] == 60.0
        assert data["review_floor"] == 45.0
        assert data["accepted"] >= 1
        assert data["review"] >= 1
        assert data["rejected"] >= 1
        # Per-lead results echo bands.
        bands = {row["id"]: row["band"] for row in data["results"]}
        assert bands[hid] == "high"
        assert bands[mid_lead] == "medium"
        assert bands[lid] == "low"

        # Persisted: fetch each lead and verify new fields.
        async def fetch(lid):
            return await _mongo().seller_leads.find_one({"id": lid}, {"_id": 0})

        for lead_id, expected_stage, expected_band in [
            (hid, "qualified", "high"),
            (mid_lead, "review", "medium"),
            (lid, "rejected", "low"),
        ]:
            doc = _run(fetch(lead_id))
            assert doc["stage"] == expected_stage, f"{lead_id} stage={doc['stage']}"
            assert doc["confidence_band"] == expected_band
            assert "confidence" in doc and doc["confidence"] == doc["seller_score"]
            assert isinstance(doc["signals"], list) and len(doc["signals"]) >= 4
            assert isinstance(doc["prospect_card"], dict)
            card = doc["prospect_card"]
            for k in ("why_match", "pain_points", "outreach_angle",
                      "likelihood_to_convert", "confidence_band"):
                assert k in card, f"prospect_card missing {k}"

        # Medium leads should have review_queued_at stamped.
        med_doc = _run(fetch(mid_lead))
        assert med_doc.get("review_queued_at") is not None
        # qualified_at stamped on high.
        hi_doc = _run(fetch(hid))
        assert hi_doc.get("qualified_at") is not None

        # qualification_runs audit row carries review + review_floor.
        async def get_audit():
            return await _mongo().qualification_runs.find_one(
                {"mission_id": mid}, {"_id": 0})
        audit = _run(get_audit())
        assert audit is not None
        assert audit["review"] >= 1
        assert audit["review_floor"] == 45.0


# ---------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------
class TestReviewQueue:
    def test_review_queue_lists_medium_leads_only(self, user_id):
        mid = _seed_mission(user_id)
        _seed_high(user_id, mid)
        mlid = _seed_medium(user_id, mid)
        _seed_low(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)

        r = requests.get(f"{API_URL}/api/seller-qualification/review-queue?mission_id={mid}",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "queue" in body and "count" in body
        ids = [row["id"] for row in body["queue"]]
        assert mlid in ids
        # No qualified or rejected in queue
        for row in body["queue"]:
            assert row["stage"] == "review"
            assert row.get("confidence_band") == "medium"
            assert "prospect_card" in row

    def test_review_queue_unknown_mission_returns_empty(self, user_id):
        # Endpoint accepts arbitrary mission_id filter — should return empty queue (not 404).
        r = requests.get(
            f"{API_URL}/api/seller-qualification/review-queue?mission_id=nope_{uuid.uuid4().hex[:6]}",
            headers=HEADERS, timeout=30)
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ---------------------------------------------------------------------
# Decide review
# ---------------------------------------------------------------------
class TestDecideReview:
    def test_promote_flips_to_qualified(self, user_id):
        mid = _seed_mission(user_id)
        mlid = _seed_medium(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)

        r = requests.post(f"{API_URL}/api/seller-qualification/review/{mlid}",
                          json={"decision": "promote", "note": "looks legit"},
                          headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "qualified"

        async def fetch():
            return await _mongo().seller_leads.find_one({"id": mlid}, {"_id": 0})
        doc = _run(fetch())
        assert doc["stage"] == "qualified"
        assert doc["review_decision"] == "promote"
        assert doc["review_note"] == "looks legit"
        assert doc["reviewed_by"] == user_id
        assert doc.get("reviewed_at") is not None
        assert doc.get("qualified_at") is not None

    def test_reject_flips_to_rejected(self, user_id):
        mid = _seed_mission(user_id)
        mlid = _seed_medium(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        r = requests.post(f"{API_URL}/api/seller-qualification/review/{mlid}",
                          json={"decision": "reject"}, headers=HEADERS, timeout=30)
        assert r.status_code == 200
        assert r.json()["stage"] == "rejected"

    def test_decide_non_review_stage_returns_409(self, user_id):
        mid = _seed_mission(user_id)
        hid = _seed_high(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        # high lead is in 'qualified' — not review
        r = requests.post(f"{API_URL}/api/seller-qualification/review/{hid}",
                          json={"decision": "promote"}, headers=HEADERS, timeout=30)
        assert r.status_code == 409
        assert "stage" in (r.json().get("detail") or "")

    def test_decide_invalid_decision_returns_400(self, user_id):
        mid = _seed_mission(user_id)
        mlid = _seed_medium(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        r = requests.post(f"{API_URL}/api/seller-qualification/review/{mlid}",
                          json={"decision": "maybe"}, headers=HEADERS, timeout=30)
        assert r.status_code == 400

    def test_decide_unknown_lead_returns_404(self, user_id):
        r = requests.post(
            f"{API_URL}/api/seller-qualification/review/nope_{uuid.uuid4().hex}",
            json={"decision": "promote"}, headers=HEADERS, timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------------
# Recommended action
# ---------------------------------------------------------------------
class TestRecommendedAction:
    def test_contact_high_confidence_when_three_or_more_high(self, user_id):
        mid = _seed_mission(user_id)
        for _ in range(3):
            _seed_high(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        r = requests.get(
            f"{API_URL}/api/seller-qualification/recommended-action?mission_id={mid}",
            headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["action"] == "contact_high_confidence"
        assert body["verb"].lower() == "contact"
        assert body["counts"]["high"] >= 3
        assert "summary" in body and "reason" in body

    def test_review_medium_queue_when_under_three_high_but_three_total(self, user_id):
        mid = _seed_mission(user_id)
        _seed_high(user_id, mid)
        _seed_high(user_id, mid)
        _seed_medium(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        r = requests.get(
            f"{API_URL}/api/seller-qualification/recommended-action?mission_id={mid}",
            headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["action"] == "review_medium_queue"
        assert body["counts"]["high"] == 2
        assert body["counts"]["medium"] == 1

    def test_expand_discovery_when_fewer_than_three(self, user_id):
        mid = _seed_mission(user_id)
        _seed_low(user_id, mid)
        _seed_low(user_id, mid)
        requests.post(f"{API_URL}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS, timeout=30)
        r = requests.get(
            f"{API_URL}/api/seller-qualification/recommended-action?mission_id={mid}",
            headers=HEADERS, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["action"] == "expand_discovery"
        assert body["counts"]["high"] == 0
        assert body["counts"]["medium"] == 0

    def test_recommended_action_unknown_mission_returns_404(self, user_id):
        r = requests.get(
            f"{API_URL}/api/seller-qualification/recommended-action?mission_id=nope_xxx",
            headers=HEADERS, timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------------
# Preview uses mission-specific threshold
# ---------------------------------------------------------------------
class TestPreviewUsesMissionThreshold:
    def test_preview_band_reflects_mission_threshold(self, user_id):
        # Mission threshold set to 99 — even the best lead won't clear it.
        mid = _seed_mission(user_id, threshold=99.0)
        hid = _seed_high(user_id, mid)
        r = requests.get(f"{API_URL}/api/seller-qualification/preview/{hid}",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200
        body = r.json()
        # With threshold=99, even the high-quality lead lands medium or low,
        # NOT high (proves preview uses mission threshold, not DEFAULT 60).
        assert body["confidence_band"] in ("medium", "low"), (
            f"Expected medium/low with threshold=99, got {body['confidence_band']} "
            f"score={body['seller_score']}")


# ---------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------
class TestIsolation:
    def test_review_queue_isolates_by_user(self, user_id):
        # Seed a foreign-user lead in review and verify it's not visible.
        foreign_uid = "user_foreign_" + uuid.uuid4().hex[:8]
        mid = uuid.uuid4().hex
        async def seed_foreign():
            db = _mongo()
            await db.missions.insert_one({
                "id": mid, "user_id": foreign_uid,
                "title": "X", "mission_type": "seller_acquisition",
                "qualification_threshold": 60.0,
                "created_at": datetime.now(timezone.utc),
            })
            await db.seller_leads.insert_one({
                "id": uuid.uuid4().hex, "user_id": foreign_uid,
                "mission_id": mid, "business_name": "FOREIGN",
                "stage": "review", "confidence_band": "medium",
                "review_queued_at": datetime.now(timezone.utc),
                "seller_score": 50.0,
                "created_at": datetime.now(timezone.utc),
            })
        _run(seed_foreign())

        r = requests.get(f"{API_URL}/api/seller-qualification/review-queue",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200
        for row in r.json()["queue"]:
            assert row.get("business_name") != "FOREIGN"

        # Cleanup foreign data
        async def cleanup():
            db = _mongo()
            await db.missions.delete_many({"user_id": foreign_uid})
            await db.seller_leads.delete_many({"user_id": foreign_uid})
        _run(cleanup())
