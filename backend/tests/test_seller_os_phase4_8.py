"""Phase 4 + Phase 8 — Offer artifacts + Churn-risk intelligence regression."""
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
        for c in ("missions", "seller_leads", "seller_outreach_events",
                  "seller_offer_artifacts", "seller_churn_scores",
                  "seller_retention_workflows", "retention_alerts"):
            await db[c].delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


# ---------------------------------------------------------------------
# Phase 4 — AI Offer Artifacts
# ---------------------------------------------------------------------
def _seed_lead(user_id: str, stage: str = "qualified", **extra) -> dict:
    async def go():
        db = _mongo()
        lead = {
            "id":            uuid.uuid4().hex,
            "user_id":       user_id,
            "business_name": "Knot & Grain Woodworks",
            "niche":         "woodworking",
            "source":        "etsy",
            "stage":         stage,
            "seller_score":  72,
            "socials":       {"instagram": "knotgrain"},
            "website":       "https://knotgrain.example.com",
            "estimated_activity": "high",
            "created_at":    datetime.now(timezone.utc),
            "updated_at":    datetime.now(timezone.utc),
            **extra,
        }
        await db.seller_leads.insert_one(lead)
        return lead
    return _run(go())


class TestOfferArtifacts:
    def test_generate_artifact_persists_and_returns_structured_payload(self, user_id):
        lead = _seed_lead(user_id)
        r = requests.post(
            f"{API_URL}/api/seller-offers/generate",
            json={"lead_id": lead["id"], "offer_type": "free_seo_audit"},
            headers=HEADERS, timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["lead_id"] == lead["id"]
        assert body["offer_type"] == "free_seo_audit"
        assert body["title"]
        assert body["sections"] and len(body["sections"]) >= 1
        for s in body["sections"]:
            assert "heading" in s and "body" in s
            assert isinstance(s.get("recommendations", []), list)
        assert 0 <= body["score"] <= 100
        assert body["generated_by"] in ("nova", "fallback")
        assert body["id"]

    def test_download_html_endpoint_serves_styled_artifact(self, user_id):
        lead = _seed_lead(user_id)
        gen = requests.post(
            f"{API_URL}/api/seller-offers/generate",
            json={"lead_id": lead["id"], "offer_type": "marketplace_growth"},
            headers=HEADERS, timeout=90,
        ).json()

        r = requests.get(
            f"{API_URL}/api/seller-offers/{gen['id']}/download.html",
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        # The HTML should contain the artifact title (HTML-escaped) + Cortex header.
        from html import escape as _esc
        assert _esc(gen["title"]) in r.text
        assert "Cortex · Seller Audit" in r.text
        assert "fit score" in r.text

    def test_list_for_lead_returns_recent_artifacts(self, user_id):
        lead = _seed_lead(user_id)
        for ot in ("free_seo_audit", "product_optimization"):
            requests.post(
                f"{API_URL}/api/seller-offers/generate",
                json={"lead_id": lead["id"], "offer_type": ot},
                headers=HEADERS, timeout=90,
            )
        r = requests.get(
            f"{API_URL}/api/seller-offers/lead/{lead['id']}",
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200
        rows = r.json()["artifacts"]
        assert len(rows) >= 2
        # Newest first
        assert rows[0]["generated_at"] >= rows[-1]["generated_at"]

    def test_outreach_attach_artifact_links_event_to_audit(self, user_id):
        lead = _seed_lead(user_id)
        r = requests.post(
            f"{API_URL}/api/seller-outreach/generate",
            json={"lead_id": lead["id"], "attach_artifact": True},
            headers=HEADERS, timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["event_id"]
        assert body.get("artifact"), "outreach should include artifact when attach_artifact=True"
        art_id = body["artifact"]["id"]

        # The sent event should carry artifact_id so the UI can resolve it.
        thread = requests.get(
            f"{API_URL}/api/seller-outreach/events/{lead['id']}",
            headers=HEADERS, timeout=10,
        ).json()
        sent = [e for e in thread["events"] if e["event"] == "sent"][0]
        assert sent.get("artifact_id") == art_id


# ---------------------------------------------------------------------
# Phase 8 — Churn-risk intelligence
# ---------------------------------------------------------------------
class TestChurnRiskScoring:
    def test_score_signals_shape_and_range(self, user_id):
        lead = _seed_lead(user_id, stage="active",
                          updated_at=datetime.now(timezone.utc) - timedelta(days=10))
        r = requests.post(
            f"{API_URL}/api/seller-retention/intel/score",
            json={"lead_id": lead["id"]},
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert 0 <= body["score"] <= 100
        sigs = body["signals"]
        for k in ("inactivity", "activity_drop", "social_silence", "score_trajectory"):
            assert k in sigs
            assert 0 <= sigs[k] <= 100
        assert isinstance(body["reasons"], list)

    def test_healthy_seller_low_score_no_workflow(self, user_id):
        # Recently active, multi-channel, high seller score → low churn risk
        lead = _seed_lead(
            user_id, stage="active",
            updated_at=datetime.now(timezone.utc) - timedelta(days=2),
            onboarded_at=datetime.now(timezone.utc) - timedelta(days=80),
            seller_score=85,
            socials={"instagram": "x", "facebook": "x", "linkedin": "x"},
        )
        r = requests.post(
            f"{API_URL}/api/seller-retention/intel/score",
            json={"lead_id": lead["id"]},
            headers=HEADERS, timeout=10,
        ).json()
        assert r["score"] < 40, f"healthy seller scored too high: {r}"
        assert r.get("workflow") is None

    def test_high_risk_seller_auto_launches_workflow(self, user_id):
        lead = _seed_lead(
            user_id, stage="active",
            updated_at=datetime.now(timezone.utc) - timedelta(days=85),
            onboarded_at=datetime.now(timezone.utc) - timedelta(days=92),
            seller_score=25,
            socials={},
        )
        r = requests.post(
            f"{API_URL}/api/seller-retention/intel/score",
            json={"lead_id": lead["id"]},
            headers=HEADERS, timeout=90,   # send_offer step calls LLM
        ).json()
        assert r["score"] >= 60, f"high-risk seller scored low: {r}"
        wf = r.get("workflow")
        assert wf, "high-risk seller should auto-launch workflow"
        assert wf["status"] == "running"
        # 3 steps in the workflow; first one (send_offer) should be auto-executed.
        steps = wf["steps"]
        assert [s["step"] for s in steps] == ["send_offer", "nudge_message", "operator_alert"]
        # The persisted record (re-fetched) should have step 1 as ok.
        wfs = requests.get(
            f"{API_URL}/api/seller-retention/intel/workflows",
            headers=HEADERS, timeout=10,
        ).json()["workflows"]
        first_step = wfs[0]["steps"][0]
        assert first_step["status"] == "ok"
        assert first_step.get("artifact_id")

    def test_workflow_advance_marks_next_step(self, user_id):
        lead = _seed_lead(
            user_id, stage="active",
            updated_at=datetime.now(timezone.utc) - timedelta(days=85),
            onboarded_at=datetime.now(timezone.utc) - timedelta(days=92),
            seller_score=25, socials={},
        )
        requests.post(
            f"{API_URL}/api/seller-retention/intel/score",
            json={"lead_id": lead["id"]}, headers=HEADERS, timeout=90,
        )
        wfs = requests.get(f"{API_URL}/api/seller-retention/intel/workflows",
                           headers=HEADERS, timeout=10).json()["workflows"]
        wf_id = wfs[0]["id"]
        r = requests.post(
            f"{API_URL}/api/seller-retention/intel/workflows/{wf_id}/advance",
            headers=HEADERS, timeout=10,
        )
        assert r.status_code == 200, r.text
        # Step 2 (nudge_message) should now be ok.
        wf = requests.get(f"{API_URL}/api/seller-retention/intel/workflows",
                          headers=HEADERS, timeout=10).json()["workflows"][0]
        nudge = [s for s in wf["steps"] if s["step"] == "nudge_message"][0]
        assert nudge["status"] == "ok"

    def test_score_idempotency_upserts_same_row(self, user_id):
        lead = _seed_lead(user_id, stage="active",
                          updated_at=datetime.now(timezone.utc) - timedelta(days=5),
                          socials={"instagram": "x", "facebook": "x"})
        for _ in range(3):
            requests.post(
                f"{API_URL}/api/seller-retention/intel/score",
                json={"lead_id": lead["id"]}, headers=HEADERS, timeout=10,
            )
        rows = requests.get(
            f"{API_URL}/api/seller-retention/intel/scores",
            headers=HEADERS, timeout=10,
        ).json()["scores"]
        # Only one row per lead, regardless of how often we score it.
        for_this_lead = [r for r in rows if r["lead_id"] == lead["id"]]
        assert len(for_this_lead) == 1

    def test_bulk_scan_endpoint(self, user_id):
        for i in range(3):
            _seed_lead(
                user_id, stage="active",
                business_name=f"Seller #{i}",
                updated_at=datetime.now(timezone.utc) - timedelta(days=15 + i * 20),
            )
        r = requests.post(
            f"{API_URL}/api/seller-retention/intel/score",
            json={}, headers=HEADERS, timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scanned"] >= 3
