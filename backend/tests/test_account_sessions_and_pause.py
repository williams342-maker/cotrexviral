"""Tests for 'sign out everywhere', pause/reactivate, and the password-changed
security email."""
import os
import asyncio
import secrets
import httpx
from datetime import datetime, timedelta, timezone

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
H_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _make_test_user(email: str | None = None):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    email = email or f"sesstest_{secrets.token_hex(4)}@account-test.dev"
    r = httpx.post(
        f"{API_URL}/api/admin/users/create",
        headers=H_ADMIN,
        json={"email": email, "name": "Sess Test", "send_email": False},
        timeout=15,
    )
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    token = f"sesstest_session_{secrets.token_hex(12)}"

    async def go():
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": token,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc),
        })
    asyncio.get_event_loop().run_until_complete(go())
    return user_id, token, email


def _add_extra_sessions(user_id: str, n: int) -> list[str]:
    """Mint n additional session_tokens for the user. Returns the list."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    tokens = [f"extra_{secrets.token_hex(10)}" for _ in range(n)]

    async def go():
        for tok in tokens:
            await db.user_sessions.insert_one({
                "user_id": user_id,
                "session_token": tok,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                "created_at": datetime.now(timezone.utc),
            })
    asyncio.get_event_loop().run_until_complete(go())
    return tokens


def _cleanup(email: str):
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
        await db.email_log.delete_many({"to": email.lower()})
    asyncio.get_event_loop().run_until_complete(go())


# ===========================================================================
# Sessions: list / revoke-others / revoke-all
# ===========================================================================
class TestSessionsManagement:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/account/sessions", timeout=10)
        assert r.status_code == 401

    def test_list_sessions_returns_counts(self):
        uid, token, email = _make_test_user()
        try:
            _add_extra_sessions(uid, 2)
            r = httpx.get(
                f"{API_URL}/api/account/sessions",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 3
            assert data["others"] == 2
            assert data["current"] is not None
            assert "expires_at" in data["current"]
        finally:
            _cleanup(email)

    def test_revoke_others_keeps_current(self):
        uid, token, email = _make_test_user()
        try:
            extras = _add_extra_sessions(uid, 3)
            r = httpx.post(
                f"{API_URL}/api/account/sessions/revoke-others",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["revoked"] == 3

            # Current token still works
            me = httpx.get(
                f"{API_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert me.status_code == 200

            # Extra tokens are gone
            for tok in extras:
                check = httpx.get(
                    f"{API_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {tok}"},
                    timeout=10,
                )
                assert check.status_code == 401
        finally:
            _cleanup(email)

    def test_revoke_all_kills_every_session(self):
        uid, token, email = _make_test_user()
        try:
            extras = _add_extra_sessions(uid, 2)
            r = httpx.post(
                f"{API_URL}/api/account/sessions/revoke-all",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["revoked"] == 3

            # Even the calling token is now invalid
            me = httpx.get(
                f"{API_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert me.status_code == 401
            for tok in extras:
                check = httpx.get(
                    f"{API_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {tok}"},
                    timeout=10,
                )
                assert check.status_code == 401
        finally:
            _cleanup(email)


# ===========================================================================
# Pause / Reactivate
# ===========================================================================
class TestPauseAccount:
    def test_requires_auth(self):
        r = httpx.post(f"{API_URL}/api/account/pause", json={}, timeout=10)
        assert r.status_code == 401

    def test_pause_sets_status_and_clears_sessions(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid, token, email = _make_test_user()
        try:
            _add_extra_sessions(uid, 1)
            r = httpx.post(
                f"{API_URL}/api/account/pause",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"reason": "Need a break"},
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["ok"] is True

            async def check():
                u = await db.users.find_one({"user_id": uid}, {"_id": 0})
                assert u is not None  # NOT deleted
                assert u["status"] == "paused"
                assert u.get("pause_reason") == "Need a break"
                sess = await db.user_sessions.count_documents({"user_id": uid})
                assert sess == 0
            asyncio.get_event_loop().run_until_complete(check())

            # The old token no longer authenticates
            me = httpx.get(
                f"{API_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert me.status_code == 401
        finally:
            _cleanup(email)

    def test_password_login_auto_reactivates_paused_account(self):
        """A paused user logging in with password reactivates the account."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid, token, email = _make_test_user()
        try:
            # Set a known password for the user via admin endpoint? We don't
            # have one. Set the hash directly using bcrypt.
            import bcrypt
            plain = "TestPassword!234"
            hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()

            async def setup():
                await db.users.update_one(
                    {"user_id": uid},
                    {"$set": {"password_hash": hashed,
                              "must_change_password": False}},
                )
            asyncio.get_event_loop().run_until_complete(setup())

            # Pause
            p = httpx.post(
                f"{API_URL}/api/account/pause",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"reason": "Bye for now"},
                timeout=10,
            )
            assert p.status_code == 200

            # Log in with password — should succeed AND flip status back
            login = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": plain},
                timeout=10,
            )
            assert login.status_code == 200, login.text
            body = login.json()
            assert body["ok"] is True
            assert body.get("reactivated") is True

            async def verify():
                u = await db.users.find_one({"user_id": uid}, {"_id": 0})
                assert u["status"] == "active"
                assert "paused_at" not in u
                assert "pause_reason" not in u
                assert u.get("reactivated_at") is not None
            asyncio.get_event_loop().run_until_complete(verify())
        finally:
            _cleanup(email)


# ===========================================================================
# Password-changed email notification
# ===========================================================================
class TestPasswordChangedEmail:
    def test_change_password_logs_security_email(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        uid, token, email = _make_test_user()
        try:
            import bcrypt
            plain_old = "OldPassword!1"
            plain_new = "NewPassword!2"
            hashed_old = bcrypt.hashpw(plain_old.encode(), bcrypt.gensalt(rounds=4)).decode()

            async def setup():
                await db.users.update_one(
                    {"user_id": uid},
                    {"$set": {"password_hash": hashed_old,
                              "must_change_password": False}},
                )
            asyncio.get_event_loop().run_until_complete(setup())

            # Authenticated change-password call
            r = httpx.post(
                f"{API_URL}/api/auth/password/change",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"current_password": plain_old, "new_password": plain_new},
                timeout=15,
            )
            assert r.status_code == 200, r.text

            # Give fire-and-forget a moment
            import time
            time.sleep(1.5)

            async def check_log():
                # We expect a "password_changed" tagged row for this user's email.
                rows = await db.email_log.find(
                    {"to": email.lower(), "tags": {"$in": ["password_changed"]}}
                ).to_list(length=10)
                assert len(rows) >= 1, (
                    f"Expected a password_changed email log row for {email}, "
                    f"found none."
                )
            asyncio.get_event_loop().run_until_complete(check_log())
        finally:
            _cleanup(email)
