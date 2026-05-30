"""Admin · Seller-OS inspector + Email log viewer + Test-send."""
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
    return requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=30).json()["user_id"]


@pytest.fixture
def user_id():
    return _uid()


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        for c in ("seller_leads", "seller_retention_workflows",
                  "seller_offer_artifacts", "missions"):
            await db[c].delete_many({"user_id": user_id})
        await db.email_log.delete_many({"tags": "seller-lifecycle"})
    _run(go())
    yield
    _run(go())


class TestAdminStats:
    def test_stats_includes_seller_os_counts(self, user_id):
        # Seed a couple of leads + a workflow so counts are non-zero.
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            await db.seller_leads.insert_many([
                {"id": uuid.uuid4().hex, "user_id": user_id,
                 "business_name": "Q1", "stage": "qualified",
                 "source": "etsy", "created_at": now, "updated_at": now},
                {"id": uuid.uuid4().hex, "user_id": user_id,
                 "business_name": "A1", "stage": "active",
                 "source": "etsy", "created_at": now, "updated_at": now},
            ])
            await db.seller_retention_workflows.insert_one({
                "id": uuid.uuid4().hex, "user_id": user_id,
                "lead_id": "x", "status": "running", "score": 70,
                "steps": [], "created_at": now,
            })
        _run(seed())

        r = requests.get(f"{API_URL}/api/admin/stats", headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("seller_leads_total", "seller_leads_qualified",
                  "seller_leads_active", "seller_workflows_running",
                  "seller_artifacts_total", "seller_missions_active"):
            assert k in body, f"stats missing key {k}: {body}"
        assert body["seller_leads_total"] >= 2
        assert body["seller_leads_qualified"] >= 1
        assert body["seller_leads_active"] >= 1
        assert body["seller_workflows_running"] >= 1


class TestAdminSellerOS:
    def test_funnel_aggregates_all_users(self, user_id):
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            for stage in ("discovered", "qualified", "qualified", "active"):
                await db.seller_leads.insert_one({
                    "id": uuid.uuid4().hex, "user_id": user_id,
                    "business_name": f"S-{stage}", "stage": stage,
                    "source": "etsy", "created_at": now, "updated_at": now,
                })
        _run(seed())
        r = requests.get(f"{API_URL}/api/admin/seller-os/funnel",
                          headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        funnel = r.json()["funnel"]
        assert funnel.get("qualified", 0) >= 2
        assert funnel.get("active", 0) >= 1

    def test_leads_endpoint_filters_by_stage(self, user_id):
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            for i in range(3):
                await db.seller_leads.insert_one({
                    "id": uuid.uuid4().hex, "user_id": user_id,
                    "business_name": f"Q-{i}", "stage": "qualified",
                    "source": "etsy", "created_at": now, "updated_at": now,
                })
            await db.seller_leads.insert_one({
                "id": uuid.uuid4().hex, "user_id": user_id,
                "business_name": "A-only", "stage": "active",
                "source": "etsy", "created_at": now, "updated_at": now,
            })
        _run(seed())

        r = requests.get(f"{API_URL}/api/admin/seller-os/leads?stage=qualified",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        leads = r.json()["leads"]
        assert all(l["stage"] == "qualified" for l in leads)
        assert len([l for l in leads if l.get("user_id") == user_id]) >= 3

    def test_workflows_endpoint_filters_by_status(self, user_id):
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            await db.seller_retention_workflows.insert_one({
                "id": uuid.uuid4().hex, "user_id": user_id, "lead_id": "x",
                "status": "running", "score": 70, "steps": [],
                "created_at": now,
            })
            await db.seller_retention_workflows.insert_one({
                "id": uuid.uuid4().hex, "user_id": user_id, "lead_id": "y",
                "status": "complete", "score": 80, "steps": [],
                "created_at": now,
            })
        _run(seed())

        r = requests.get(f"{API_URL}/api/admin/seller-os/workflows?status=running",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        wfs = r.json()["workflows"]
        assert all(w["status"] == "running" for w in wfs)


class TestAdminEmailLog:
    def test_logs_endpoint_filters_by_tag_and_provider(self, user_id):
        # The /admin/email/test-send endpoint actually fires a real email
        # through the chain, which inserts an email_log row. Use it as
        # the seeding mechanism — keeps the test honest.
        r = requests.post(
            f"{API_URL}/api/admin/email/test-send",
            json={"to": "admin-log-test@example.com", "template": "welcome"},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        sent = r.json()
        assert sent.get("sent") is True
        provider = sent.get("provider")
        assert provider in ("sendgrid", "mailtrap", "mailgun"), sent

        # Now query the log
        r = requests.get(
            f"{API_URL}/api/admin/email/logs?tag=seller-lifecycle&provider={provider}",
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        logs = r.json()["logs"]
        match = [l for l in logs if l.get("to") == "admin-log-test@example.com"]
        assert len(match) >= 1, f"expected log row for test send, got {logs}"

    def test_health_endpoint_includes_breakdowns(self, user_id):
        # Fire one welcome to ensure non-empty breakdowns.
        requests.post(
            f"{API_URL}/api/admin/email/test-send",
            json={"to": "admin-health-test@example.com", "template": "welcome"},
            headers=HEADERS, timeout=30,
        )
        r = requests.get(f"{API_URL}/api/admin/email/health?hours=72",
                         headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "by_provider" in body
        assert "by_lifecycle" in body
        assert isinstance(body["by_provider"], dict)
        # welcome should be in the lifecycle breakdown after our test send.
        assert body["by_lifecycle"].get("welcome", 0) >= 1


class TestAdminTestSend:
    @pytest.mark.parametrize("tpl", ["welcome", "audit", "nudge", "recovery"])
    def test_test_send_all_4_templates(self, tpl):
        r = requests.post(
            f"{API_URL}/api/admin/email/test-send",
            json={"to": f"admin-{tpl}@example.com", "template": tpl},
            headers=HEADERS, timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["template"] == tpl
        assert body["to"] == f"admin-{tpl}@example.com"
        # In this env Mailtrap is configured, so we expect sent=True. If the
        # env is dry, skipped should be set instead — either is a wire-up pass.
        assert body["sent"] is True or body.get("skipped"), body

    def test_test_send_rejects_bad_email(self):
        r = requests.post(
            f"{API_URL}/api/admin/email/test-send",
            json={"to": "not-a-real-email", "template": "welcome"},
            headers=HEADERS, timeout=30,
        )
        # Pydantic EmailStr rejects with 422.
        assert r.status_code == 422, r.text
