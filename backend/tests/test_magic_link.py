"""Magic-link auth + admin-create user tests."""
import os
import asyncio
import httpx
import secrets

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
H_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _unique_email(prefix="invite"):
    return f"{prefix}_{secrets.token_hex(4)}@magic-test.dev"


def _cleanup_user(email: str):
    """Remove a test user + their magic links + sessions."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        u = await db.users.find_one({"email": email.lower()}, {"_id": 0})
        if u:
            uid = u["user_id"]
            await db.users.delete_one({"user_id": uid})
            await db.user_sessions.delete_many({"user_id": uid})
            await db.magic_links.delete_many({"user_id": uid})

    asyncio.get_event_loop().run_until_complete(go())


class TestAdminCreateUser:
    def test_requires_admin(self):
        r = httpx.post(
            f"{API_URL}/api/admin/users/create",
            json={"email": "foo@bar.com", "name": "Foo"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_creates_new_user_returns_magic_link(self):
        email = _unique_email("new")
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "Test Lead", "plan": "free",
                      "comped": False, "send_email": False},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["new_user"] is True
            assert body["email"] == email.lower()
            assert body["magic_link"].startswith("http")
            assert "token=" in body["magic_link"]
            # email_sent is False because send_email=False
            assert body["email_sent"] is False
        finally:
            _cleanup_user(email)

    def test_idempotent_on_existing_email_returns_fresh_link(self):
        email = _unique_email("exists")
        try:
            r1 = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "First", "send_email": False},
                timeout=15,
            )
            assert r1.status_code == 200
            assert r1.json()["new_user"] is True
            link1 = r1.json()["magic_link"]

            r2 = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "First", "send_email": False},
                timeout=15,
            )
            assert r2.status_code == 200
            assert r2.json()["new_user"] is False
            link2 = r2.json()["magic_link"]
            assert link1 != link2  # fresh token each time
        finally:
            _cleanup_user(email)

    def test_rejects_unknown_plan(self):
        email = _unique_email("badplan")
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "X", "plan": "platinum",
                      "send_email": False},
                timeout=10,
            )
            assert r.status_code == 400
            assert "platinum" in r.text.lower()
        finally:
            _cleanup_user(email)

    def test_creates_user_with_plan_and_comped(self):
        email = _unique_email("comped")
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "VIP", "plan": "growth",
                      "comped": True, "send_email": False},
                timeout=15,
            )
            assert r.status_code == 200
            uid = r.json()["user_id"]

            # Verify in DB
            detail = httpx.get(f"{API_URL}/api/admin/users/{uid}",
                               headers=H_ADMIN, timeout=10)
            assert detail.status_code == 200
            assert detail.json()["user"]["plan"] == "growth"
            assert detail.json()["user"]["comped"] is True
        finally:
            _cleanup_user(email)


class TestMagicLinkClaim:
    def test_rejects_missing_token(self):
        r = httpx.get(f"{API_URL}/api/auth/claim", params={"token": ""}, timeout=10)
        # FastAPI returns 422 when required query param is empty? Let's just check 4xx.
        assert 400 <= r.status_code < 500

    def test_rejects_invalid_token(self):
        r = httpx.get(f"{API_URL}/api/auth/claim",
                      params={"token": "a" * 50}, timeout=10)
        assert r.status_code == 400

    def test_full_claim_flow_sets_session_cookie(self):
        email = _unique_email("claim")
        try:
            # 1. Admin creates user
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "Claimer", "send_email": False},
                timeout=15,
            )
            assert r.status_code == 200
            link = r.json()["magic_link"]
            token = link.split("token=")[1]

            # 2. User clicks the magic link
            with httpx.Client(timeout=15) as cli:
                claim = cli.get(f"{API_URL}/api/auth/claim",
                                params={"token": token})
                assert claim.status_code == 200, claim.text
                data = claim.json()
                assert data["ok"] is True
                assert data["email"] == email.lower()
                # Should set the session_token cookie
                assert "session_token" in claim.cookies or any(
                    c.startswith("session_token=")
                    for c in claim.headers.get_list("set-cookie")
                )

                # 3. /auth/me should now return the user using that cookie
                me = cli.get(f"{API_URL}/api/auth/me")
                assert me.status_code == 200
                assert me.json()["email"] == email.lower()
        finally:
            _cleanup_user(email)

    def test_token_is_single_use(self):
        email = _unique_email("reuse")
        try:
            r = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "Reuser", "send_email": False},
                timeout=15,
            )
            token = r.json()["magic_link"].split("token=")[1]

            # First claim works
            r1 = httpx.get(f"{API_URL}/api/auth/claim",
                           params={"token": token}, timeout=10)
            assert r1.status_code == 200

            # Second claim with same token must fail
            r2 = httpx.get(f"{API_URL}/api/auth/claim",
                           params={"token": token}, timeout=10)
            assert r2.status_code == 400
            assert "already" in r2.text.lower() or "used" in r2.text.lower()
        finally:
            _cleanup_user(email)


class TestResendInvite:
    def test_requires_admin(self):
        r = httpx.post(
            f"{API_URL}/api/admin/users/some_id/resend-invite",
            timeout=10,
        )
        assert r.status_code == 401

    def test_404_on_unknown_user(self):
        r = httpx.post(
            f"{API_URL}/api/admin/users/nonexistent_user_id/resend-invite",
            headers=H_ADMIN, timeout=10,
        )
        assert r.status_code == 404

    def test_resend_issues_fresh_link(self):
        email = _unique_email("resend")
        try:
            r1 = httpx.post(
                f"{API_URL}/api/admin/users/create",
                headers=H_ADMIN,
                json={"email": email, "name": "Resend", "send_email": False},
                timeout=15,
            )
            uid = r1.json()["user_id"]
            link1 = r1.json()["magic_link"]

            r2 = httpx.post(
                f"{API_URL}/api/admin/users/{uid}/resend-invite",
                headers=H_ADMIN, timeout=15,
            )
            assert r2.status_code == 200
            body = r2.json()
            assert body["ok"] is True
            assert body["magic_link"].startswith("http")
            assert body["magic_link"] != link1  # fresh token
        finally:
            _cleanup_user(email)
