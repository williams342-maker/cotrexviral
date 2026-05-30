"""PDF rendering + SendGrid webhook + Dynamic Template wiring tests."""
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
    return requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=30).json()["user_id"]


@pytest.fixture
def user_id():
    return _uid()


@pytest.fixture(autouse=True)
def _wipe(user_id):
    async def go():
        db = _mongo()
        for c in ("seller_leads", "seller_outreach_events",
                  "seller_offer_artifacts"):
            await db[c].delete_many({"user_id": user_id})
    _run(go())
    yield
    _run(go())


def _seed_lead(user_id: str, **extra) -> dict:
    async def go():
        db = _mongo()
        lead = {
            "id":            uuid.uuid4().hex,
            "user_id":       user_id,
            "business_name": "PDF Probe Co.",
            "email":         "pdf@probe.dev",
            "niche":         "woodworking",
            "source":        "etsy",
            "stage":         "qualified",
            "seller_score":  72,
            "socials":       {"instagram": "x"},
            "estimated_activity": "high",
            "created_at":    datetime.now(timezone.utc),
            "updated_at":    datetime.now(timezone.utc),
            **extra,
        }
        await db.seller_leads.insert_one(lead)
        return lead
    return _run(go())


# ---------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------
class TestPdfRendering:
    def test_render_html_to_pdf_returns_real_pdf_bytes(self):
        from routes.audit_pdf import render_html_to_pdf
        html = "<html><body><h1>Probe</h1></body></html>"
        out = _run(render_html_to_pdf(html))
        assert out, "PDF rendering returned None"
        # PDF magic header: 25 50 44 46 2d  ("%PDF-")
        assert out[:5] == b"%PDF-", f"Not a PDF: {out[:5]!r}"
        assert len(out) > 500   # not a 1-byte empty file

    def test_download_pdf_endpoint_serves_pdf(self, user_id):
        # Create artifact via the public route then GET the .pdf
        lead = _seed_lead(user_id)
        gen = requests.post(
            f"{API_URL}/api/seller-offers/generate",
            json={"lead_id": lead["id"], "offer_type": "free_seo_audit"},
            headers=HEADERS, timeout=120,
        )
        assert gen.status_code == 200, gen.text
        art_id = gen.json()["id"]
        r = requests.get(f"{API_URL}/api/seller-offers/{art_id}/download.pdf",
                         headers=HEADERS, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000

    def test_audit_email_attaches_pdf_when_renderer_available(self, user_id):
        """Direct-invoke the helper and check the SendGrid send_email
        call would carry a `.pdf` attachment when the renderer works."""
        from unittest import mock
        from routes import seller_emails
        captured = {}

        async def fake_send_email(**kwargs):
            captured.update(kwargs)
            return {"sent": True, "provider": "sendgrid", "id": "x"}

        lead = _seed_lead(user_id)
        artifact = {
            "id":         uuid.uuid4().hex,
            "title":      "Free SEO Audit · PDF Probe",
            "summary":    "Test summary.",
            "score":      78,
            "offer_type": "free_seo_audit",
            "sections":   [{"heading": "H", "body": "B", "recommendations": ["R"]}],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with mock.patch.object(seller_emails, "send_email", side_effect=fake_send_email):
            _run(seller_emails.send_seller_audit_email(lead, artifact))
        atts = captured.get("attachments") or []
        assert len(atts) == 1
        # PDF rendering succeeds in this env → expect application/pdf
        assert atts[0]["type"] == "application/pdf"
        assert atts[0]["filename"].endswith(".pdf")
        import base64
        decoded = base64.b64decode(atts[0]["content"])
        assert decoded[:5] == b"%PDF-"


# ---------------------------------------------------------------------
# SendGrid webhook → seller_outreach_events
# ---------------------------------------------------------------------
class TestSendGridWebhook:
    def test_webhook_projects_delivered_event(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event":         "delivered",
            "email":         "pdf@probe.dev",
            "timestamp":     int(datetime.now(timezone.utc).timestamp()),
            "sg_event_id":   f"sg-evt-{uuid.uuid4().hex[:8]}",
            "sg_message_id": f"sg-msg-{uuid.uuid4().hex[:8]}",
            "lead_id":       lead["id"],
            "lifecycle":     "audit",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["received"] == 1
        assert body["projected"] == 1

        async def check():
            db = _mongo()
            evt = await db.seller_outreach_events.find_one(
                {"lead_id": lead["id"], "event": "delivered"})
            assert evt is not None
            assert evt["channel"] == "email"
            assert evt["offer_type"] == "audit"
            assert evt["sg_event_id"] == payload[0]["sg_event_id"]
        _run(check())

    def test_webhook_idempotent_on_sg_event_id(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event": "open",   # SendGrid uses 'open', which maps to 'opened'
            "email": "pdf@probe.dev",
            "sg_event_id": "sg-evt-dedup",
            "sg_message_id": "sg-msg-dedup",
            "lead_id": lead["id"], "lifecycle": "audit",
        }]
        # Fire 3 times.
        for _ in range(3):
            r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                              json=payload, timeout=30)
            assert r.status_code == 200

        async def count():
            db = _mongo()
            return await db.seller_outreach_events.count_documents(
                {"lead_id": lead["id"], "event": "opened"})
        n = _run(count())
        assert n == 1, f"expected 1 event after 3 fires, got {n}"

    def test_webhook_clicked_records_url(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event": "click", "email": "pdf@probe.dev",
            "sg_event_id": "sg-evt-click",
            "sg_message_id": "sg-msg-click",
            "url":   "https://cortexviral.com/dashboard",
            "lead_id": lead["id"], "lifecycle": "audit",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200
        async def check():
            db = _mongo()
            evt = await db.seller_outreach_events.find_one(
                {"lead_id": lead["id"], "event": "clicked"})
            assert evt is not None
            assert evt["url"] == "https://cortexviral.com/dashboard"
        _run(check())

    def test_webhook_bounce_advances_lead_to_unresponsive(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event": "bounce", "email": "pdf@probe.dev",
            "sg_event_id": "sg-evt-bounce",
            "sg_message_id": "sg-msg-bounce",
            "reason": "550 Mailbox does not exist",
            "lead_id": lead["id"], "lifecycle": "audit",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200
        async def check():
            db = _mongo()
            l = await db.seller_leads.find_one({"id": lead["id"]})
            assert l["stage"] == "unresponsive", l
        _run(check())

    def test_webhook_unsubscribe_marks_lead_not_interested(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event": "unsubscribe", "email": "pdf@probe.dev",
            "sg_event_id": "sg-evt-unsub",
            "sg_message_id": "sg-msg-unsub",
            "lead_id": lead["id"], "lifecycle": "nudge",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200
        async def check():
            db = _mongo()
            l = await db.seller_leads.find_one({"id": lead["id"]})
            assert l["stage"] == "not_interested"
            assert l.get("unsubscribed") is True
        _run(check())

    def test_webhook_skips_events_without_lead_id(self):
        # Pure SendGrid events with no custom_args should be skipped
        # (the webhook is shared with other email types too).
        payload = [{
            "event": "delivered", "email": "x@y.com",
            "sg_event_id": "sg-no-lead",
            "sg_message_id": "sg-no-lead",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["projected"] == 0
        assert body["skipped"] == 1

    def test_webhook_unknown_event_skipped(self, user_id):
        lead = _seed_lead(user_id)
        payload = [{
            "event": "processed",   # intermediate; ignored
            "sg_event_id": "sg-processed",
            "lead_id": lead["id"], "lifecycle": "audit",
        }]
        r = requests.post(f"{API_URL}/api/sendgrid/webhook",
                          json=payload, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["projected"] == 0
        # processed is mapped to None → counted as skipped.
        assert body["skipped"] == 1


# ---------------------------------------------------------------------
# Dynamic Templates wiring
# ---------------------------------------------------------------------
class TestDynamicTemplates:
    def test_helper_passes_template_id_when_env_set(self, user_id, monkeypatch):
        """When `SENDGRID_TEMPLATE_WELCOME` is set, the helper should
        forward it + dynamic_data to send_email."""
        from unittest import mock
        from routes import seller_emails
        monkeypatch.setenv("SENDGRID_TEMPLATE_WELCOME", "d-test-tpl-welcome-123")
        captured = {}

        async def fake_send_email(**kwargs):
            captured.update(kwargs)
            return {"sent": True, "provider": "sendgrid"}

        lead = _seed_lead(user_id)
        with mock.patch.object(seller_emails, "send_email", side_effect=fake_send_email):
            _run(seller_emails.send_seller_welcome_email(lead))
        assert captured.get("template_id") == "d-test-tpl-welcome-123"
        assert captured.get("dynamic_data", {}).get("business_name") == "PDF Probe Co."

    def test_helper_omits_template_id_when_env_blank(self, user_id, monkeypatch):
        from unittest import mock
        from routes import seller_emails
        monkeypatch.delenv("SENDGRID_TEMPLATE_WELCOME", raising=False)
        captured = {}

        async def fake_send_email(**kwargs):
            captured.update(kwargs)
            return {"sent": True, "provider": "sendgrid"}

        lead = _seed_lead(user_id)
        with mock.patch.object(seller_emails, "send_email", side_effect=fake_send_email):
            _run(seller_emails.send_seller_welcome_email(lead))
        assert captured.get("template_id") is None
        # dynamic_data is still passed (cheap; SendGrid only uses it when
        # template_id is set), so other providers fall back to html as
        # before.
        assert "dynamic_data" in captured
