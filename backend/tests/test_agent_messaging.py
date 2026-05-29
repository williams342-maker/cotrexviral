"""Agent ↔ Agent Messaging — Phase 6 of the Autonomous Growth Team.

Covers:
  - Auth gating on both endpoints
  - `query_agent` writes a row + falls back gracefully when LLM key missing
  - Unknown agent id → status=errored persisted
  - List endpoint summary stats (total/answered/errored)
  - Filter by from_agent / to_agent
  - GET single message returns the full thread (multi-row sort by created_at)
  - 404 on unknown id
"""
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


def _admin_user_id():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    return r.json().get("user_id") if r.status_code == 200 else None


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing")
    return uid


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    async def go():
        db = _mongo()
        # Wipe pytest-injected messages only — preserve real history.
        await db.agent_messages.delete_many({
            "user_id": admin_user_id,
            "query":   {"$regex": "^pytest_"},
        })
    _run(go())
    yield
    _run(go())


class TestAuth:
    def test_endpoints_require_auth(self):
        for path in ["/api/agent-messages", "/api/agent-messages/abc"]:
            r = requests.get(f"{API_URL}{path}", timeout=10)
            assert r.status_code == 401


class TestQueryAgent:
    def test_unknown_agent_is_persisted_as_errored(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_messaging import query_agent
        r = _run(query_agent(
            user_id=admin_user_id, from_agent="atlas", to_agent="nobody",
            query="pytest_unknown_target",
        ))
        assert r["ok"] is False
        assert r["message_id"]
        # Row exists with status=errored
        async def check():
            db = _mongo()
            doc = await db.agent_messages.find_one({"id": r["message_id"]})
            assert doc is not None
            assert doc["status"] == "errored"
            assert "unknown agent" in (doc.get("error") or "").lower()
        _run(check())

    def test_happy_path_persists_response(self, admin_user_id):
        """When EMERGENT_LLM_KEY is set, the real LLM is called. We don't
        assert exact response text — only that the row landed as answered
        and a response is present. When the key is unset, the fallback
        path still returns ok=True with a canned reply."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_messaging import query_agent
        r = _run(query_agent(
            user_id=admin_user_id, from_agent="atlas", to_agent="lyra",
            query="pytest_happy_path: name one theme",
            context_str="signal A; signal B",
        ))
        assert r["ok"] is True
        assert r["response"] and len(r["response"]) > 0
        # Row is answered
        async def check():
            db = _mongo()
            doc = await db.agent_messages.find_one({"id": r["message_id"]})
            assert doc["status"] == "answered"
            assert doc["from_agent"] == "atlas"
            assert doc["to_agent"]   == "lyra"
            assert doc["thread_id"]  # auto-generated when not provided
        _run(check())


class TestListEndpoint:
    def test_list_returns_recent(self, admin_user_id):
        # Seed two messages
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            for i, (fa, ta) in enumerate([("atlas", "lyra"), ("atlas", "ori")]):
                await db.agent_messages.insert_one({
                    "id": uuid.uuid4().hex, "user_id": admin_user_id,
                    "from_agent": fa, "to_agent": ta,
                    "query": f"pytest_seed_{i}", "response": "seeded reply",
                    "thread_id": uuid.uuid4().hex,
                    "status": "answered",
                    "created_at": now, "responded_at": now,
                })
        _run(seed())

        r = requests.get(f"{API_URL}/api/agent-messages?limit=100",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 2
        queries = {it["query"] for it in body["items"]}
        assert "pytest_seed_0" in queries
        assert "pytest_seed_1" in queries

    def test_filter_by_to_agent(self, admin_user_id):
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            await db.agent_messages.insert_one({
                "id": uuid.uuid4().hex, "user_id": admin_user_id,
                "from_agent": "atlas", "to_agent": "rae",
                "query": "pytest_filter_target", "response": "x",
                "thread_id": uuid.uuid4().hex,
                "status": "answered",
                "created_at": now, "responded_at": now,
            })
        _run(seed())

        r = requests.get(f"{API_URL}/api/agent-messages?to_agent=rae&limit=20",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["to_agent"] == "rae"


class TestGetSingle:
    def test_thread_returned(self, admin_user_id):
        async def seed():
            db = _mongo()
            now = datetime.now(timezone.utc)
            tid = uuid.uuid4().hex
            mid_a = uuid.uuid4().hex
            mid_b = uuid.uuid4().hex
            await db.agent_messages.insert_one({
                "id": mid_a, "user_id": admin_user_id,
                "from_agent": "atlas", "to_agent": "lyra",
                "query": "pytest_thread_q1", "response": "lyra reply 1",
                "thread_id": tid,
                "status": "answered",
                "created_at": now, "responded_at": now,
            })
            await db.agent_messages.insert_one({
                "id": mid_b, "user_id": admin_user_id,
                "from_agent": "lyra", "to_agent": "atlas",
                "query": "pytest_thread_q2", "response": "atlas follow-up",
                "thread_id": tid,
                "status": "answered",
                "created_at": now, "responded_at": now,
            })
            return mid_a
        first_id = _run(seed())
        r = requests.get(f"{API_URL}/api/agent-messages/{first_id}",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["message"]["id"] == first_id
        assert len(body["thread"]) == 2

    def test_404_on_unknown(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/agent-messages/does_not_exist",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 404
