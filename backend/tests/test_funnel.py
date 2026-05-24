"""Marketing funnel: tracking + admin endpoint tests."""
import os
import asyncio
import time
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _clear_pageviews():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.pageviews.delete_many({})
    asyncio.get_event_loop().run_until_complete(go())


class TestVisitTracking:
    def test_anonymous_visit_recorded(self):
        _clear_pageviews()
        r = httpx.post(
            f"{API_URL}/api/track/visit",
            json={"path": "/", "referrer": "https://twitter.com"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_bot_user_agent_skipped(self):
        _clear_pageviews()
        r = httpx.post(
            f"{API_URL}/api/track/visit",
            json={"path": "/"},
            headers={"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"},
            timeout=10,
        )
        assert r.json().get("skipped") == "bot"

    def test_ip_not_persisted_raw(self):
        """The pageview document must store an ip_hash, never a raw IP."""
        _clear_pageviews()
        httpx.post(
            f"{API_URL}/api/track/visit",
            json={"path": "/test"},
            headers={"X-Forwarded-For": "9.9.9.9"},
            timeout=10,
        )
        time.sleep(0.5)
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def go():
            return await db.pageviews.find_one({"path": "/test"})
        doc = asyncio.get_event_loop().run_until_complete(go())
        assert doc is not None
        assert "ip_hash" in doc
        assert "9.9.9.9" not in str(doc)


class TestAdminFunnel:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/admin/funnel", timeout=10)
        assert r.status_code == 401

    def test_returns_full_shape(self):
        _clear_pageviews()
        # Seed two distinct visitors
        httpx.post(f"{API_URL}/api/track/visit", json={"path": "/"},
                   headers={"X-Forwarded-For": "1.1.1.1"}, timeout=10)
        httpx.post(f"{API_URL}/api/track/visit", json={"path": "/pricing"},
                   headers={"X-Forwarded-For": "2.2.2.2"}, timeout=10)

        r = httpx.get(f"{API_URL}/api/admin/funnel?days=30", headers=H, timeout=10)
        r.raise_for_status()
        body = r.json()
        assert body["window_days"] == 30
        for key in ("visitors", "raw_views", "signups", "activated", "paid", "comped"):
            assert key in body["buckets"]
            assert isinstance(body["buckets"][key], int)
        for key in ("visit_to_signup", "signup_to_activated", "activated_to_paid", "visit_to_paid"):
            assert key in body["rates"]
        assert body["buckets"]["visitors"] >= 2
        assert body["buckets"]["raw_views"] >= 2

    def test_days_parameter_clamped(self):
        r = httpx.get(f"{API_URL}/api/admin/funnel?days=99999", headers=H, timeout=10)
        r.raise_for_status()
        assert r.json()["window_days"] == 365  # clamped upper

        r2 = httpx.get(f"{API_URL}/api/admin/funnel?days=0", headers=H, timeout=10)
        r2.raise_for_status()
        assert r2.json()["window_days"] == 1  # clamped lower

    def test_dedupes_visitors_same_ip_same_day(self):
        _clear_pageviews()
        # Three hits from the same IP — should only count as 1 unique visitor.
        for _ in range(3):
            httpx.post(f"{API_URL}/api/track/visit", json={"path": "/"},
                       headers={"X-Forwarded-For": "5.5.5.5"}, timeout=10)
        r = httpx.get(f"{API_URL}/api/admin/funnel?days=7", headers=H, timeout=10)
        r.raise_for_status()
        b = r.json()["buckets"]
        assert b["visitors"] == 1
        assert b["raw_views"] == 3
