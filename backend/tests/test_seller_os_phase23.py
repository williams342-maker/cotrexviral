"""Phase 2 + Phase 3 — Outreach / Onboarding / Retention regression."""
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
        await db.seller_outreach_events.delete_many({"user_id": user_id})
        await db.seller_onboardings.delete_many({"user_id": user_id})
        await db.retention_alerts.delete_many({"user_id": user_id})
        await db.discovery_runs.delete_many({"user_id": user_id})
        await db.qualification_runs.delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


def _seed_qualified_lead() -> tuple:
    """Helper: create mission → discover → qualify → return (mission, lead)."""
    m = requests.post(
        f"{API_URL}/api/missions",
        json={"title": "Recruit 10 woodworking makers", "target": 10,
              "mission_type": "seller_acquisition",
              "seller_target_niche": "woodworking",
              "autonomy_level": 3},
        headers=HEADERS, timeout=10,
    ).json()
    requests.post(
        f"{API_URL}/api/seller-discovery/run",
        json={"mission_id": m["id"], "niche": "woodworking",
              "sources": ["etsy"], "max_per_source": 5},
        headers=HEADERS, timeout=30,
    )
    requests.post(
        f"{API_URL}/api/seller-qualification/run",
        json={"mission_id": m["id"], "threshold": 0},
        headers=HEADERS, timeout=30,
    )
    leads = requests.get(
        f"{API_URL}/api/seller-leads?mission_id={m['id']}&stage=qualified",
        headers=HEADERS, timeout=10,
    ).json()["leads"]
    assert leads, "fixture should produce ≥1 qualified lead"
    return m, leads[0]


# ----------------------------------------------------------------------
# Phase 2 — Outreach
# ----------------------------------------------------------------------
class TestOutreach:
    def test_generate_dry_run_no_event_record(self):
        m, lead = _seed_qualified_lead()
        r = requests.post(
            f"{API_URL}/api/seller-outreach/generate",
            json={"lead_id": lead["id"], "dry_run": True},
            headers=HEADERS, timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["offer_type"] in (
            "free_seo_audit", "marketplace_growth", "product_optimization",
            "free_onboarding", "featured_invite",
        )
        assert body["channel"] in (
            "email", "instagram_dm", "facebook_message",
            "linkedin_inmail", "contact_form",
        )
        # Body length sanity check — fallback template is well >50 chars.
        assert len(body["body"]) > 40
        # Lead stage should remain `qualified` (no event recorded)
        fresh = requests.get(f"{API_URL}/api/seller-leads/{lead['id']}",
                             headers=HEADERS, timeout=10).json()
        assert fresh["stage"] == "qualified"

    def test_generate_live_records_event_and_advances_stage(self):
        m, lead = _seed_qualified_lead()
        r = requests.post(
            f"{API_URL}/api/seller-outreach/generate",
            json={"lead_id": lead["id"], "dry_run": False},
            headers=HEADERS, timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["event_id"]

        fresh = requests.get(f"{API_URL}/api/seller-leads/{lead['id']}",
                             headers=HEADERS, timeout=10).json()
        assert fresh["stage"] == "outreached"
        assert fresh["outreached_at"]
        assert fresh["last_outreach_offer"]
        assert fresh["last_outreach_channel"]

    def test_bulk_outreach_only_processes_qualified(self):
        m, _lead = _seed_qualified_lead()
        # The fixture left N qualified leads
        before = requests.get(
            f"{API_URL}/api/seller-leads?mission_id={m['id']}&stage=qualified",
            headers=HEADERS, timeout=10,
        ).json()["count"]
        r = requests.post(
            f"{API_URL}/api/seller-outreach/bulk",
            json={"mission_id": m["id"], "limit": 100},
            headers=HEADERS, timeout=120,
        )
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == before
        # All those leads should now be `outreached`.
        after_q = requests.get(
            f"{API_URL}/api/seller-leads?mission_id={m['id']}&stage=qualified",
            headers=HEADERS, timeout=10,
        ).json()["count"]
        assert after_q == 0

    def test_post_event_advances_to_interested(self):
        m, lead = _seed_qualified_lead()
        # Move to outreached first
        requests.post(
            f"{API_URL}/api/seller-outreach/generate",
            json={"lead_id": lead["id"]},
            headers=HEADERS, timeout=90,
        )
        r = requests.post(
            f"{API_URL}/api/seller-outreach/events",
            json={"lead_id": lead["id"], "event": "replied",
                  "channel": "email", "body": "Tell me more."},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200
        fresh = requests.get(f"{API_URL}/api/seller-leads/{lead['id']}",
                             headers=HEADERS, timeout=10).json()
        assert fresh["stage"] == "interested"
        assert fresh["responded_at"]

    def test_thread_endpoint_returns_chronological(self):
        m, lead = _seed_qualified_lead()
        requests.post(f"{API_URL}/api/seller-outreach/generate",
                      json={"lead_id": lead["id"]}, headers=HEADERS, timeout=60)
        requests.post(f"{API_URL}/api/seller-outreach/events",
                      json={"lead_id": lead["id"], "event": "opened"},
                      headers=HEADERS, timeout=10)
        requests.post(f"{API_URL}/api/seller-outreach/events",
                      json={"lead_id": lead["id"], "event": "replied"},
                      headers=HEADERS, timeout=10)
        r = requests.get(f"{API_URL}/api/seller-outreach/events/{lead['id']}",
                         headers=HEADERS, timeout=10).json()
        evs = r["events"]
        assert len(evs) >= 3
        for i in range(1, len(evs)):
            assert evs[i - 1]["created_at"] <= evs[i]["created_at"]
        types = [e["event"] for e in evs]
        assert types[0] == "sent"
        assert "replied" in types

    def test_cannot_outreach_non_qualified_lead(self):
        m, lead = _seed_qualified_lead()
        # Manually downgrade to rejected
        requests.patch(f"{API_URL}/api/seller-leads/{lead['id']}",
                       json={"stage": "rejected"}, headers=HEADERS, timeout=10)
        r = requests.post(
            f"{API_URL}/api/seller-outreach/generate",
            json={"lead_id": lead["id"]},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 400


# ----------------------------------------------------------------------
# Phase 3 — Onboarding
# ----------------------------------------------------------------------
class TestOnboarding:
    def test_start_runs_5_steps_and_advances_to_active(self):
        m, lead = _seed_qualified_lead()
        # Need to push to `interested` first
        requests.post(f"{API_URL}/api/seller-outreach/generate",
                      json={"lead_id": lead["id"]}, headers=HEADERS, timeout=60)
        requests.post(f"{API_URL}/api/seller-outreach/events",
                      json={"lead_id": lead["id"], "event": "replied"},
                      headers=HEADERS, timeout=10)

        r = requests.post(f"{API_URL}/api/seller-onboarding/start",
                          json={"lead_id": lead["id"]},
                          headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "complete"
        assert len(body["steps"]) == 5
        step_names = [s["step"] for s in body["steps"]]
        assert step_names == ["create_account", "create_storefront",
                              "import_products", "generate_seo", "send_welcome"]
        # Lead is now active
        fresh = requests.get(f"{API_URL}/api/seller-leads/{lead['id']}",
                             headers=HEADERS, timeout=10).json()
        assert fresh["stage"] == "active"
        assert fresh["onboarded_at"]

    def test_onboarding_is_idempotent(self):
        m, lead = _seed_qualified_lead()
        requests.post(f"{API_URL}/api/seller-onboarding/start",
                      json={"lead_id": lead["id"]}, headers=HEADERS, timeout=30)
        r2 = requests.post(f"{API_URL}/api/seller-onboarding/start",
                           json={"lead_id": lead["id"]}, headers=HEADERS, timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("reused") is True

    def test_cannot_onboard_below_qualified(self):
        m, lead = _seed_qualified_lead()
        requests.patch(f"{API_URL}/api/seller-leads/{lead['id']}",
                       json={"stage": "discovered"}, headers=HEADERS, timeout=10)
        r = requests.post(f"{API_URL}/api/seller-onboarding/start",
                          json={"lead_id": lead["id"]},
                          headers=HEADERS, timeout=10)
        assert r.status_code == 400


# ----------------------------------------------------------------------
# Phase 3 — Retention
# ----------------------------------------------------------------------
class TestRetention:
    def test_scan_flags_inactive_and_churned(self, user_id):
        # Seed an active seller manually
        async def seed():
            db = _mongo()
            await db.seller_leads.insert_many([
                {  # inactive (35 days since updated_at)
                    "id":            uuid.uuid4().hex,
                    "user_id":       user_id,
                    "stage":         "active",
                    "business_name": "Inactive Seller",
                    "source":        "etsy",
                    "created_at":    datetime.now(timezone.utc) - timedelta(days=90),
                    "updated_at":    datetime.now(timezone.utc) - timedelta(days=35),
                    "onboarded_at":  datetime.now(timezone.utc) - timedelta(days=40),
                },
                {  # churned (70 days)
                    "id":            uuid.uuid4().hex,
                    "user_id":       user_id,
                    "stage":         "active",
                    "business_name": "Churned Seller",
                    "source":        "etsy",
                    "created_at":    datetime.now(timezone.utc) - timedelta(days=120),
                    "updated_at":    datetime.now(timezone.utc) - timedelta(days=70),
                    "onboarded_at":  datetime.now(timezone.utc) - timedelta(days=75),
                },
                {  # healthy (5 days)
                    "id":            uuid.uuid4().hex,
                    "user_id":       user_id,
                    "stage":         "active",
                    "business_name": "Healthy Seller",
                    "source":        "etsy",
                    "created_at":    datetime.now(timezone.utc) - timedelta(days=15),
                    "updated_at":    datetime.now(timezone.utc) - timedelta(days=5),
                    "onboarded_at":  datetime.now(timezone.utc) - timedelta(days=10),
                },
            ])
        _run(seed())

        r = requests.post(f"{API_URL}/api/seller-retention/scan",
                          headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # Should flag inactive=1 + churn=1 for THIS user's leads.
        # (Other users' rows may also be flagged in the global scan but
        # we only assert on THIS user's count via the alerts endpoint.)
        alerts = requests.get(f"{API_URL}/api/seller-retention/alerts",
                              headers=HEADERS, timeout=10).json()["alerts"]
        sev = {a["severity"] for a in alerts}
        assert "inactive" in sev
        assert "churn" in sev

        # The churned seller's stage should now be 'churned'
        async def check():
            db = _mongo()
            churned = await db.seller_leads.find_one(
                {"user_id": user_id, "business_name": "Churned Seller"})
            inactive = await db.seller_leads.find_one(
                {"user_id": user_id, "business_name": "Inactive Seller"})
            healthy = await db.seller_leads.find_one(
                {"user_id": user_id, "business_name": "Healthy Seller"})
            assert churned["stage"] == "churned"
            assert inactive["stage"] == "active"   # alert raised, stage preserved
            assert healthy["stage"] == "active"
        _run(check())
