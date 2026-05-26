"""Tests for the in-dashboard agent chat endpoint."""
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
H = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


class TestAgentList:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/list", timeout=10)
        assert r.status_code == 401

    def test_lists_all_four_agents(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/list", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        ids = sorted(a["id"] for a in body["agents"])
        assert ids == ["angela", "kai", "nova", "sam"]
        for a in body["agents"]:
            # Public payload should NOT leak the system prompt
            assert "system" not in a
            assert {"id", "name", "role", "color", "blurb"} <= set(a.keys())


class TestAgentProfile:
    def test_404_on_unknown_agent(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/profile?agent_id=ghost", headers=H, timeout=10)
        assert r.status_code == 404

    def test_returns_profile_without_system_prompt(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/profile?agent_id=nova", headers=H, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "nova"
        assert data["name"] == "Nova"
        assert "system" not in data


class TestAgentChat:
    def test_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            json={"agent_id": "nova", "message": "hi"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_404_on_unknown_agent(self):
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "ghost", "message": "hi"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_422_on_blank_message(self):
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "nova", "message": ""},
            timeout=10,
        )
        assert r.status_code == 422

    def test_happy_path_returns_answer(self):
        """Live LLM round-trip. Single call → fast (~6s). We assert the
        response shape + non-empty answer text only (content is non-determ)."""
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={
                "agent_id": "kai",
                "message": "Reply with the word HELLO and nothing else.",
            },
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["agent_id"] == "kai"
        assert isinstance(data["answer"], str) and len(data["answer"]) >= 1
        assert isinstance(data["follow_ups"], list)

    def test_ai_generation_recorded(self):
        """Each successful chat must $inc the user's monthly counter."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def read_count():
            doc = await db.users.find_one(
                {"session_token": ADMIN_TOKEN},
                {"_id": 0},
            )
            # admin token doesn't map to a user via session_token; we read from sessions
            sess = await db.user_sessions.find_one({"session_token": ADMIN_TOKEN}, {"_id": 0})
            if not sess:
                return None
            user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            return ((user.get("usage") or {}).get(month) or {}).get("ai_generations", 0)

        before = asyncio.get_event_loop().run_until_complete(read_count())
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "angela", "message": "Say OK."},
            timeout=90,
        )
        assert r.status_code == 200
        after = asyncio.get_event_loop().run_until_complete(read_count())
        # Counter should have advanced by at least 1 if both reads succeeded.
        if before is not None and after is not None:
            assert after >= before + 1
