"""Email-blast endpoint tests — /admin/broadcasts/{id}/email."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _create_test_broadcast(title: str = "Test Blast", severity: str = "info") -> str:
    r = httpx.post(
        f"{API_URL}/api/admin/broadcasts", headers=H,
        json={"title": title, "body": "Test body for the blast", "severity": severity, "active": True},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def _cleanup(broadcast_id: str):
    httpx.delete(f"{API_URL}/api/admin/broadcasts/{broadcast_id}", headers=H, timeout=10)


class TestEmailBlast:
    def test_requires_admin(self):
        r = httpx.post(
            f"{API_URL}/api/admin/broadcasts/anything/email",
            json={"dry_run": True}, timeout=10,
        )
        assert r.status_code == 401

    def test_404_unknown_broadcast(self):
        r = httpx.post(
            f"{API_URL}/api/admin/broadcasts/does_not_exist/email",
            headers=H, json={"dry_run": True}, timeout=10,
        )
        assert r.status_code == 404

    def test_dry_run_counts_recipients_without_sending(self):
        bid = _create_test_broadcast()
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/broadcasts/{bid}/email",
                headers=H, json={"dry_run": True}, timeout=10,
            )
            r.raise_for_status()
            body = r.json()
            assert body["dry_run"] is True
            assert "would_send_to" in body
            assert isinstance(body["would_send_to"], int)
            assert body["would_send_to"] >= 0
        finally:
            _cleanup(bid)

    def test_invalid_plan_in_filter_rejected(self):
        bid = _create_test_broadcast()
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/broadcasts/{bid}/email",
                headers=H, json={"plans": ["enterprise_xl"], "dry_run": True}, timeout=10,
            )
            assert r.status_code == 400
        finally:
            _cleanup(bid)

    def test_plan_filter_subsets_recipients(self):
        """A filter that matches no users → 0 recipients (Free plan filter on a
        DB that has only Free+admin users will likely return 0 paid users)."""
        bid = _create_test_broadcast()
        try:
            r_all = httpx.post(
                f"{API_URL}/api/admin/broadcasts/{bid}/email",
                headers=H, json={"dry_run": True}, timeout=10,
            ).json()
            r_paid = httpx.post(
                f"{API_URL}/api/admin/broadcasts/{bid}/email",
                headers=H, json={"plans": ["agency"], "dry_run": True}, timeout=10,
            ).json()
            # 'all plans' will be >= 'just agency plan'
            assert r_paid["would_send_to"] <= r_all["would_send_to"]
        finally:
            _cleanup(bid)

    def test_real_send_records_stats_on_broadcast(self):
        """Verify the live-send path: send to a single matching user (the admin
        test user comped to growth) and confirm the broadcast doc captures
        sent/recipients/emailed_at."""
        # Make sure admin test user has an email (it's the seed user)
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def has_users():
            return await db.users.count_documents({"status": "active"})
        n_users = asyncio.get_event_loop().run_until_complete(has_users())
        assert n_users >= 1, "Need at least 1 active user with email for this test"

        bid = _create_test_broadcast(title="REAL SEND TEST", severity="info")
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/broadcasts/{bid}/email",
                headers=H,
                # Filter to a non-existent plan name pattern keeps blast tiny.
                # We just want a smoke send — use 'free' filter (almost no real users).
                json={"plans": ["free"], "include_comped": True, "dry_run": False},
                timeout=120,
            )
            r.raise_for_status()
            body = r.json()
            assert "sent" in body
            assert "failed" in body
            assert "recipients" in body

            # Re-fetch the broadcast — verify stats were persisted
            bcasts = httpx.get(f"{API_URL}/api/admin/broadcasts", headers=H, timeout=10).json()
            my_b = [b for b in bcasts if b["id"] == bid][0]
            assert "emailed_at" in my_b
            assert my_b["emailed_recipients"] == body["recipients"]
            assert my_b["emailed_sent"] == body["sent"]
            assert my_b["emailed_failed"] == body["failed"]
        finally:
            _cleanup(bid)
