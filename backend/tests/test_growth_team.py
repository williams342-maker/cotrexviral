"""Phase 1 — Autonomous Growth Team tests (personas + standup + listening)."""
import asyncio
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes.agent_personas import PERSONAS  # noqa: E402

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestPersonas:

    def test_eight_personas_seeded(self):
        """The roster has all 8 agents."""
        r = requests.get(f"{API_URL}/api/agents/personas", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 8
        ids = {p["id"] for p in body["personas"]}
        assert ids == {"vera", "atlas", "nova", "rae", "lyra", "echo", "ori", "jules"}

    def test_personas_have_full_metadata(self):
        r = requests.get(f"{API_URL}/api/agents/personas", headers=HEADERS, timeout=15)
        for p in r.json()["personas"]:
            for k in ["id", "name", "role", "tagline", "voice", "color", "icon", "owns"]:
                assert k in p, f"persona {p.get('id')} missing key {k}"
            assert isinstance(p["owns"], list) and len(p["owns"]) >= 1

    def test_personas_redact_system_prompt(self):
        """The list endpoint must NOT leak system prompts or autonomy budgets."""
        r = requests.get(f"{API_URL}/api/agents/personas", headers=HEADERS, timeout=15)
        for p in r.json()["personas"]:
            assert "system_prompt" not in p
            assert "autonomy_budget" not in p

    def test_personas_constant_is_self_consistent(self):
        """Every persona's `collabs` references real persona ids."""
        ids = {p["id"] for p in PERSONAS}
        for p in PERSONAS:
            for c in p.get("collabs", []):
                assert c in ids, f"{p['id']}.collabs references unknown id {c}"


class TestStandup:

    def test_generate_then_fetch_latest(self):
        """Standup generation runs sync (~15s via combined LLM call) and
        returns a doc with 8 contributions; /standups/latest agrees."""
        r = requests.post(f"{API_URL}/api/standups/generate",
                           headers=HEADERS, timeout=60)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert len(doc["contributions"]) == 8
        for c in doc["contributions"]:
            assert c["text"] and len(c["text"]) >= 5
            assert c["agent_id"] in {"vera", "atlas", "nova", "rae", "lyra", "echo", "ori", "jules"}

        r2 = requests.get(f"{API_URL}/api/standups/latest", headers=HEADERS, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["id"] == doc["id"]

    def test_standups_list_returns_history(self):
        r = requests.get(f"{API_URL}/api/standups?limit=5", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["items"], list)
        for s in body["items"]:
            assert "contributions" in s
            assert "facts" in s


class TestListening:

    def test_manual_ingest_creates_signal(self):
        """POST /listening/signals records a normalized row."""
        payload = {
            "source":      "reddit",
            "text":        "Test signal from pytest " + uuid.uuid4().hex[:6],
            "sentiment":   "positive",
            "signal_type": "praise",
            "urgency":     2,
            "engagement":  42,
        }
        r = requests.post(f"{API_URL}/api/listening/signals", headers=HEADERS,
                           json=payload, timeout=15)
        assert r.status_code == 200, r.text
        sig = r.json()
        assert sig["id"]
        assert sig["sentiment"] == "positive"
        assert sig["engagement"] == 42

        # Cleanup
        async def go():
            db = _mongo()
            await db.social_listening_signals.delete_one({"id": sig["id"]})
        _run(go())

    def test_signals_filtered_by_sentiment(self):
        r = requests.get(f"{API_URL}/api/listening/signals?sentiment=negative",
                          headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        for s in items:
            assert s["sentiment"] == "negative"

    def test_listening_stats_shape(self):
        r = requests.get(f"{API_URL}/api/listening/stats", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ["total", "by_sentiment", "by_signal_type", "attention_score",
                   "alert_threshold", "alert_triggered"]:
            assert k in body
        assert isinstance(body["attention_score"], (int, float))
        assert body["alert_threshold"] == 10.0
        assert body["alert_triggered"] == (body["attention_score"] >= 10.0)

    def test_invalid_sentiment_coerced_to_neutral(self):
        """Defensive — a garbage sentiment shouldn't crash the row insert."""
        r = requests.post(
            f"{API_URL}/api/listening/signals",
            headers=HEADERS,
            json={"source": "manual", "text": "test", "sentiment": "garbage"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["sentiment"] == "neutral"
        # Cleanup
        async def go():
            db = _mongo()
            await db.social_listening_signals.delete_one({"id": r.json()["id"]})
        _run(go())
