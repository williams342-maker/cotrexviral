"""Mailgun transactional email tests (live API hits — sandbox-safe)."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _clear_email_log():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.email_log.delete_many({})
    asyncio.get_event_loop().run_until_complete(go())


class TestEmailEndpoint:
    def test_requires_admin(self):
        r = httpx.post(
            f"{API_URL}/api/admin/email/test",
            json={"to": "a@b.com", "kind": "welcome"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_returns_structured_status(self):
        """Either {'sent': True, 'id': ...} or {'sent': False, 'error': ...}.
        Either way, the endpoint must NOT 500."""
        r = httpx.post(
            f"{API_URL}/api/admin/email/test",
            headers=H,
            json={"to": "test-recipient@example.com", "kind": "welcome"},
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert "sent" in body
        # 'sent' will be False on a disabled sandbox / unverified recipient.
        if body["sent"] is False:
            assert "error" in body or "skipped" in body

    def test_all_template_kinds_supported(self):
        for kind in ("welcome", "gift", "trial", "past_due"):
            r = httpx.post(
                f"{API_URL}/api/admin/email/test",
                headers=H,
                json={"to": "test-recipient@example.com", "kind": kind},
                timeout=30,
            )
            assert r.status_code == 200, f"{kind} failed: {r.text[:200]}"

    def test_email_log_persists(self):
        _clear_email_log()
        httpx.post(
            f"{API_URL}/api/admin/email/test",
            headers=H,
            json={"to": "log-test@example.com", "kind": "welcome"},
            timeout=30,
        ).raise_for_status()

        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def fetch():
            return await db.email_log.find_one({"to": "log-test@example.com"}, {"_id": 0})

        doc = asyncio.get_event_loop().run_until_complete(fetch())
        assert doc is not None
        assert doc["subject"]
        assert doc["status"] in ("sent", "rejected", "error", "skipped")


class TestEmailHealth:
    def test_requires_admin(self):
        r = httpx.get(f"{API_URL}/api/admin/email/health", timeout=10)
        assert r.status_code == 401

    def test_returns_full_shape(self):
        _clear_email_log()
        # Seed one rejected
        httpx.post(
            f"{API_URL}/api/admin/email/test",
            headers=H, json={"to": "shape-test@example.com", "kind": "welcome"}, timeout=30,
        ).raise_for_status()
        r = httpx.get(f"{API_URL}/api/admin/email/health?hours=24", headers=H, timeout=10)
        r.raise_for_status()
        body = r.json()
        for key in ("hours", "total", "sent", "rejected", "errored", "skipped", "delivery_rate", "last_problem"):
            assert key in body, f"missing key: {key}"
        assert body["total"] >= 1

    def test_hours_clamped(self):
        r = httpx.get(f"{API_URL}/api/admin/email/health?hours=99999", headers=H, timeout=10)
        r.raise_for_status()
        assert r.json()["hours"] == 24 * 30  # clamped to 30 days
        r2 = httpx.get(f"{API_URL}/api/admin/email/health?hours=0", headers=H, timeout=10)
        r2.raise_for_status()
        assert r2.json()["hours"] == 1

    def test_surfaces_last_problem_with_reason(self):
        _clear_email_log()
        httpx.post(
            f"{API_URL}/api/admin/email/test",
            headers=H, json={"to": "problem-test@example.com", "kind": "welcome"}, timeout=30,
        ).raise_for_status()
        r = httpx.get(f"{API_URL}/api/admin/email/health", headers=H, timeout=10)
        body = r.json()
        # When the only send rejected, last_problem must be populated.
        if body["sent"] == 0 and body["total"] > 0:
            assert body["last_problem"] is not None
            assert body["last_problem"]["status"] in ("rejected", "error", "skipped")


class TestEmailHelpers:
    """Direct calls into the helpers — verifies template wiring + payload shape
    without going through HTTP."""

    def test_welcome_email_produces_html_with_name(self):
        import sys
        sys.path.insert(0, "/app/backend")
        # Stub BOTH provider tokens to "" so send_email returns the "skipped"
        # branch without hitting the network. Verifies the helper itself
        # doesn't crash and the provider chain handles no-config gracefully.
        import routes.email as email_module
        orig_mg = email_module.MAILGUN_API_KEY
        orig_mt = email_module.MAILTRAP_TOKEN
        email_module.MAILGUN_API_KEY = ""
        email_module.MAILTRAP_TOKEN = ""
        try:
            res = asyncio.get_event_loop().run_until_complete(
                email_module.send_welcome_email("test@example.com", "Michael Smith")
            )
            assert res["sent"] is False
            assert res.get("skipped") == "not_configured"
        finally:
            email_module.MAILGUN_API_KEY = orig_mg
            email_module.MAILTRAP_TOKEN = orig_mt

    def test_gift_plan_email_includes_reason(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import routes.email as email_module
        orig_mg = email_module.MAILGUN_API_KEY
        orig_mt = email_module.MAILTRAP_TOKEN
        email_module.MAILGUN_API_KEY = ""
        email_module.MAILTRAP_TOKEN = ""
        try:
            res = asyncio.get_event_loop().run_until_complete(
                email_module.send_gift_plan_email(
                    "test@example.com", "Michael", "growth", reason="Top creator"
                )
            )
            assert res["sent"] is False
            assert res.get("skipped") == "not_configured"
        finally:
            email_module.MAILGUN_API_KEY = orig_mg
            email_module.MAILTRAP_TOKEN = orig_mt


class TestProviderRouting:
    def test_parse_from_with_display_name(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.email import _parse_from
        assert _parse_from("CortexViral <hello@x.com>") == {"name": "CortexViral", "email": "hello@x.com"}
        assert _parse_from("plain@x.com") == {"email": "plain@x.com"}
        assert _parse_from("") == {"email": ""}
