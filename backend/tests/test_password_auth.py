"""Email + password auth tests + lead-form temp-password flow."""
import os
import asyncio
import secrets
import httpx
from datetime import datetime, timezone

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)


def _setup_test_user_with_password(password: str = "TempPw1234"):
    """Create a fresh user with a known password hash (so we can test login)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db
    from routes.password_auth import hash_password

    email = f"pwtest_{secrets.token_hex(4)}@auth-test.dev"
    user_id = f"user_pwtest_{secrets.token_hex(4)}"

    async def go():
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": "Pw Test",
            "is_admin": False,
            "status": "active",
            "password_hash": hash_password(password),
            "must_change_password": False,
            "created_at": datetime.now(timezone.utc),
        })
    asyncio.get_event_loop().run_until_complete(go())
    return user_id, email


def _cleanup_user(email: str):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        u = await db.users.find_one({"email": email.lower()}, {"_id": 0})
        if u:
            uid = u["user_id"]
            await db.users.delete_one({"user_id": uid})
            await db.user_sessions.delete_many({"user_id": uid})
        await db.login_attempts.delete_many({"identifier": {"$regex": email}})
    asyncio.get_event_loop().run_until_complete(go())


class TestPasswordLogin:
    def test_rejects_unknown_email_with_generic_error(self):
        # No enumeration: 401 regardless of whether email exists.
        r = httpx.post(
            f"{API_URL}/api/auth/password/login",
            json={"email": f"nope_{secrets.token_hex(4)}@x.com", "password": "anything"},
            timeout=10,
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"

    def test_happy_path_sets_session_cookie(self):
        uid, email = _setup_test_user_with_password("CorrectPw123")
        try:
            with httpx.Client(timeout=10) as cli:
                r = cli.post(
                    f"{API_URL}/api/auth/password/login",
                    json={"email": email, "password": "CorrectPw123"},
                )
                assert r.status_code == 200
                body = r.json()
                assert body["ok"] is True
                assert body["user_id"] == uid
                assert body["must_change_password"] is False
                # session_token cookie was set
                assert any(c.startswith("session_token=")
                           for c in r.headers.get_list("set-cookie"))
                # And /auth/me works using that cookie
                me = cli.get(f"{API_URL}/api/auth/me")
                assert me.status_code == 200
                assert me.json()["email"] == email
        finally:
            _cleanup_user(email)

    def test_wrong_password_401(self):
        uid, email = _setup_test_user_with_password("CorrectPw123")
        try:
            r = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "WrongPassword"},
                timeout=10,
            )
            assert r.status_code == 401
        finally:
            _cleanup_user(email)

    def test_must_change_password_flag_returned(self):
        """Users created via the lead form / admin path have must_change=True.
        Verify the login response surfaces this so the SPA can force the
        password-change UI before redirecting to the dashboard."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.password_auth import hash_password

        email = f"forced_{secrets.token_hex(4)}@auth-test.dev"
        uid = f"user_forced_{secrets.token_hex(4)}"
        async def setup():
            await db.users.insert_one({
                "user_id": uid, "email": email, "name": "F",
                "status": "active",
                "password_hash": hash_password("TempPw123"),
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            r = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "TempPw123"},
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["must_change_password"] is True
        finally:
            _cleanup_user(email)

    def test_suspended_account_403(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.password_auth import hash_password

        email = f"susp_{secrets.token_hex(4)}@auth-test.dev"
        async def setup():
            await db.users.insert_one({
                "user_id": f"user_susp_{secrets.token_hex(4)}",
                "email": email, "name": "S", "status": "suspended",
                "password_hash": hash_password("AnyPw1234"),
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            r = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "AnyPw1234"},
                timeout=10,
            )
            assert r.status_code == 403
        finally:
            _cleanup_user(email)


class TestBruteForce:
    def test_lockout_after_5_failed_attempts(self):
        uid, email = _setup_test_user_with_password("CorrectPw123")
        try:
            for i in range(5):
                r = httpx.post(
                    f"{API_URL}/api/auth/password/login",
                    json={"email": email, "password": "Wrong"},
                    timeout=10,
                )
                assert r.status_code == 401
            # 6th attempt → 429 lockout
            r = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "Wrong"},
                timeout=10,
            )
            assert r.status_code == 429
            # Even the CORRECT password is locked out during the window
            r = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "CorrectPw123"},
                timeout=10,
            )
            assert r.status_code == 429
        finally:
            _cleanup_user(email)


class TestPasswordReset:
    def test_request_reset_always_200_no_enumeration(self):
        """Even for nonexistent emails, we return 200 — prevents email
        enumeration via the reset endpoint."""
        r = httpx.post(
            f"{API_URL}/api/auth/password/request-reset",
            json={"email": f"nope_{secrets.token_hex(4)}@x.com"},
            timeout=10,
        )
        assert r.status_code == 200
        assert "If the email is registered" in r.json()["message"]

    def test_request_reset_for_real_user_rotates_password(self):
        uid, email = _setup_test_user_with_password("OriginalPw1")
        try:
            # Snapshot old hash
            import sys
            sys.path.insert(0, "/app/backend")
            from core import db
            async def get_hash():
                u = await db.users.find_one({"email": email})
                return u.get("password_hash")
            old_hash = asyncio.get_event_loop().run_until_complete(get_hash())

            r = httpx.post(
                f"{API_URL}/api/auth/password/request-reset",
                json={"email": email},
                timeout=10,
            )
            assert r.status_code == 200

            new_hash = asyncio.get_event_loop().run_until_complete(get_hash())
            assert new_hash != old_hash
            # Old password no longer works
            login = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "OriginalPw1"},
                timeout=10,
            )
            assert login.status_code == 401
        finally:
            _cleanup_user(email)


class TestSetInitialPassword:
    def test_must_change_path_works_end_to_end(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.password_auth import hash_password

        email = f"setinitial_{secrets.token_hex(4)}@auth-test.dev"
        uid = f"user_si_{secrets.token_hex(4)}"
        async def setup():
            await db.users.insert_one({
                "user_id": uid, "email": email, "name": "SI",
                "status": "active",
                "password_hash": hash_password("TempPw123"),
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            with httpx.Client(timeout=10) as cli:
                # 1. Sign in with temp password
                r = cli.post(
                    f"{API_URL}/api/auth/password/login",
                    json={"email": email, "password": "TempPw123"},
                )
                assert r.status_code == 200
                assert r.json()["must_change_password"] is True

                # 2. Set new permanent password
                r2 = cli.post(
                    f"{API_URL}/api/auth/password/set-initial",
                    json={"new_password": "MyPermanentPw1"},
                )
                assert r2.status_code == 200

                # 3. Old temp pw no longer works
                r3 = cli.post(
                    f"{API_URL}/api/auth/password/login",
                    json={"email": email, "password": "TempPw123"},
                )
                assert r3.status_code == 401

                # 4. New pw works AND must_change is False
                r4 = cli.post(
                    f"{API_URL}/api/auth/password/login",
                    json={"email": email, "password": "MyPermanentPw1"},
                )
                assert r4.status_code == 200
                assert r4.json()["must_change_password"] is False
        finally:
            _cleanup_user(email)

    def test_set_initial_requires_must_change_flag(self):
        """Can't call set-initial unless must_change_password is True."""
        uid, email = _setup_test_user_with_password("RegularPw1")
        try:
            with httpx.Client(timeout=10) as cli:
                cli.post(f"{API_URL}/api/auth/password/login",
                         json={"email": email, "password": "RegularPw1"})
                r = cli.post(f"{API_URL}/api/auth/password/set-initial",
                             json={"new_password": "NewPw12345"})
                assert r.status_code == 400
        finally:
            _cleanup_user(email)

    def test_short_password_rejected(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.password_auth import hash_password
        email = f"short_{secrets.token_hex(4)}@auth-test.dev"
        async def setup():
            await db.users.insert_one({
                "user_id": f"user_short_{secrets.token_hex(4)}",
                "email": email, "name": "S", "status": "active",
                "password_hash": hash_password("TempPw123"),
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            with httpx.Client(timeout=10) as cli:
                cli.post(f"{API_URL}/api/auth/password/login",
                         json={"email": email, "password": "TempPw123"})
                r = cli.post(f"{API_URL}/api/auth/password/set-initial",
                             json={"new_password": "short"})
                assert r.status_code == 422  # Pydantic min_length
        finally:
            _cleanup_user(email)


class TestLeadFormCreatesPasswordUser:
    def test_lead_email_sets_password_hash_with_must_change(self):
        """When the lead form auto-creates a user, they must end up with a
        bcrypt hash + must_change_password=True so they can log in via
        email+temp_pw on next visit."""
        email = f"leadpw_{secrets.token_hex(4)}@auth-test.dev"
        try:
            r = httpx.post(
                f"{API_URL}/api/leads",
                json={"agent_id": "nova", "name": "Lead PW Test", "email": email},
                timeout=15,
            )
            assert r.status_code == 200

            import time
            time.sleep(0.5)

            import sys
            sys.path.insert(0, "/app/backend")
            from core import db

            async def check():
                u = await db.users.find_one({"email": email.lower()})
                assert u is not None
                assert u.get("password_hash"), "Password hash should be set"
                assert u["password_hash"].startswith("$2"), "Should be bcrypt"
                assert u.get("must_change_password") is True
                assert u.get("created_via") == "lead_form"
            asyncio.get_event_loop().run_until_complete(check())
        finally:
            _cleanup_user(email)


class TestHelpersAndUtilities:
    def test_temp_password_strength(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.password_auth import generate_temp_password
        pw = generate_temp_password()
        assert len(pw) == 12
        # No ambiguous chars (0, O, 1, l, I)
        for c in "0O1lI":
            assert c not in pw

    def test_hash_verify_roundtrip(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.password_auth import hash_password, verify_password
        h = hash_password("SecurePw1234")
        assert h.startswith("$2"), "Must be bcrypt"
        assert verify_password("SecurePw1234", h) is True
        assert verify_password("Wrong", h) is False

    def test_verify_password_safe_on_invalid_hash(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.password_auth import verify_password
        # Don't crash on malformed hashes — just return False.
        assert verify_password("anything", "not-a-real-hash") is False
        assert verify_password("anything", "") is False


class TestAuthMeExposesPasswordState:
    """The /auth/me endpoint must surface has_password + must_change_password
    so the SPA can render the correct Account Settings UI (Add vs Change
    password) and the must-change redirect."""

    def test_password_user_has_password_true_and_must_change_false(self):
        uid, email = _setup_test_user_with_password("RegularPw1")
        try:
            with httpx.Client(timeout=10) as cli:
                cli.post(f"{API_URL}/api/auth/password/login",
                         json={"email": email, "password": "RegularPw1"})
                me = cli.get(f"{API_URL}/api/auth/me")
                assert me.status_code == 200
                body = me.json()
                assert body["has_password"] is True
                assert body["must_change_password"] is False
        finally:
            _cleanup_user(email)

    def test_temp_pw_user_has_must_change_true(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.password_auth import hash_password
        email = f"tempme_{secrets.token_hex(4)}@auth-test.dev"
        async def setup():
            await db.users.insert_one({
                "user_id": f"user_tempme_{secrets.token_hex(4)}",
                "email": email, "name": "T", "status": "active",
                "password_hash": hash_password("TempPw123"),
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            with httpx.Client(timeout=10) as cli:
                cli.post(f"{API_URL}/api/auth/password/login",
                         json={"email": email, "password": "TempPw123"})
                me = cli.get(f"{API_URL}/api/auth/me")
                assert me.status_code == 200
                body = me.json()
                assert body["has_password"] is True
                assert body["must_change_password"] is True
        finally:
            _cleanup_user(email)


class TestPasswordChangeFlow:
    """Google-only users (no password_hash) can call /change with no
    current_password to set their first password. Existing password users
    must provide the correct current_password."""

    def test_google_only_user_can_add_password(self):
        """Add `password_hash` to a user that started with no password."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        email = f"addpw_{secrets.token_hex(4)}@auth-test.dev"
        uid = f"user_addpw_{secrets.token_hex(4)}"
        token = f"addpw_session_{secrets.token_hex(8)}"
        async def setup():
            await db.users.insert_one({
                "user_id": uid, "email": email, "name": "G", "status": "active",
                "created_at": datetime.now(timezone.utc),
            })
            from datetime import timedelta
            await db.user_sessions.insert_one({
                "user_id": uid, "session_token": token,
                "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                "created_at": datetime.now(timezone.utc),
            })
        asyncio.get_event_loop().run_until_complete(setup())
        try:
            h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            r = httpx.post(
                f"{API_URL}/api/auth/password/change",
                headers=h,
                # No current_password — backend should allow because they had none
                json={"current_password": "", "new_password": "MyFirstPw1"},
                timeout=10,
            )
            assert r.status_code == 200

            # Now they can log in with the new password
            login = httpx.post(
                f"{API_URL}/api/auth/password/login",
                json={"email": email, "password": "MyFirstPw1"},
                timeout=10,
            )
            assert login.status_code == 200
            assert login.json()["must_change_password"] is False
        finally:
            _cleanup_user(email)

    def test_change_requires_correct_current_password(self):
        uid, email = _setup_test_user_with_password("Original1")
        try:
            with httpx.Client(timeout=10) as cli:
                cli.post(f"{API_URL}/api/auth/password/login",
                         json={"email": email, "password": "Original1"})
                # Wrong current password → 401
                r = cli.post(f"{API_URL}/api/auth/password/change",
                             json={"current_password": "WrongOldPw",
                                   "new_password": "NewPw123!"})
                assert r.status_code == 401
                # Original password still works
                r2 = cli.post(f"{API_URL}/api/auth/password/login",
                              json={"email": email, "password": "Original1"})
                assert r2.status_code == 200
        finally:
            _cleanup_user(email)
