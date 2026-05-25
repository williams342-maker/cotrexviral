"""Self-serve account deletion tests."""
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


def _make_test_user(email: str | None = None) -> tuple[str, str]:
    """Create a fresh test user via the admin-create endpoint and return
    (user_id, session_token) for that user."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    email = email or f"deltest_{secrets.token_hex(4)}@account-test.dev"
    # Use the admin endpoint so it cascades correctly
    r = httpx.post(
        f"{API_URL}/api/admin/users/create",
        headers=H_ADMIN,
        json={"email": email, "name": "Delete Test", "send_email": False},
        timeout=15,
    )
    assert r.status_code == 200
    user_id = r.json()["user_id"]

    # Mint a session_token directly in DB so the test can authenticate as
    # this user without going through Google Auth.
    token = f"deltest_session_{secrets.token_hex(12)}"

    async def go():
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": token,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            "created_at": datetime.now(timezone.utc),
        })
    asyncio.get_event_loop().run_until_complete(go())
    return user_id, token, email


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
            await db.posts.delete_many({"user_id": uid})
        await db.account_deletions.delete_many({"email": email})
    asyncio.get_event_loop().run_until_complete(go())


class TestSelfServeDelete:
    def test_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/account/delete",
            json={"confirmation": "DELETE MY ACCOUNT"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_rejects_wrong_confirmation(self):
        uid, token, email = _make_test_user()
        try:
            r = httpx.post(
                f"{API_URL}/api/account/delete",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"confirmation": "delete my account"},  # lowercase
                timeout=10,
            )
            assert r.status_code == 400
            assert "confirmation" in r.text.lower()
            # User still exists
            import sys
            sys.path.insert(0, "/app/backend")
            from core import db

            async def check():
                u = await db.users.find_one({"user_id": uid})
                assert u is not None
            asyncio.get_event_loop().run_until_complete(check())
        finally:
            _cleanup(email)

    def test_happy_path_deletes_user_and_cascades(self):
        uid, token, email = _make_test_user()
        # Seed a couple of related rows so we can verify the cascade
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def seed():
            await db.posts.insert_one({
                "id": f"post_{secrets.token_hex(4)}",
                "user_id": uid,
                "content": "cascade-test",
                "platforms": ["instagram"],
                "status": "published",
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(seed())

        try:
            r = httpx.post(
                f"{API_URL}/api/account/delete",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"confirmation": "DELETE MY ACCOUNT", "reason": "Test cleanup"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is True
            assert r.json()["deleted_user_id"] == uid

            # User + sessions + posts all gone
            async def verify():
                u = await db.users.find_one({"user_id": uid})
                assert u is None, "User should be deleted"
                s = await db.user_sessions.find_one({"user_id": uid})
                assert s is None
                p = await db.posts.find_one({"user_id": uid})
                assert p is None
                # Audit row was created
                audit = await db.account_deletions.find_one({"user_id": uid})
                assert audit is not None
                assert audit.get("reason") == "Test cleanup"
                assert audit.get("via") == "self_serve"
            asyncio.get_event_loop().run_until_complete(verify())
        finally:
            _cleanup(email)

    def test_session_invalidated_after_delete(self):
        uid, token, email = _make_test_user()
        try:
            d = httpx.post(
                f"{API_URL}/api/account/delete",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"confirmation": "DELETE MY ACCOUNT"},
                timeout=15,
            )
            assert d.status_code == 200

            # Attempting to use the same session now returns 401
            me = httpx.get(
                f"{API_URL}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert me.status_code == 401
        finally:
            _cleanup(email)
