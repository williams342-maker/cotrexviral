"""Tests for per-agent mode persistence + LLM spend tracking +
unified AI Team dashboard data endpoints."""
import os
import sys
import asyncio
import httpx

sys.path.insert(0, "/app/backend")

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _comp(plan: str = "growth"):
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "ai-team test"},
        timeout=10,
    )


def _wipe_usage():
    """Clear `llm_usage` so spend assertions are deterministic."""
    from core import db

    async def go():
        await db.llm_usage.delete_many({"user_id": USER_ID})

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        loop.run_until_complete(go())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(go())


# ----------------------------------------------------------------------
# 1) Per-agent mode preferences
# ----------------------------------------------------------------------
class TestAgentPrefs:
    def test_get_prefs_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/prefs", timeout=10)
        assert r.status_code == 401

    def test_default_prefs_empty(self):
        """Brand-new user (no prefs set) → empty object, not 404."""
        # Reset prefs first.
        httpx.put(f"{API_URL}/api/ai/agent/prefs", headers=H,
                  json={"agent_id": "strategy", "mode": "auto"}, timeout=10)
        r = httpx.get(f"{API_URL}/api/ai/agent/prefs", headers=H, timeout=10)
        assert r.status_code == 200
        assert "prefs" in r.json()
        assert isinstance(r.json()["prefs"], dict)

    def test_set_pref_persists_and_round_trips(self):
        # Save deep for Atlas
        r = httpx.put(f"{API_URL}/api/ai/agent/prefs", headers=H,
                      json={"agent_id": "strategy", "mode": "deep"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["mode"] == "deep"
        # Save fast for Sam
        httpx.put(f"{API_URL}/api/ai/agent/prefs", headers=H,
                  json={"agent_id": "sam", "mode": "fast"}, timeout=10)
        # Re-fetch
        r = httpx.get(f"{API_URL}/api/ai/agent/prefs", headers=H, timeout=10)
        prefs = r.json()["prefs"]
        assert prefs.get("strategy") == "deep"
        assert prefs.get("sam") == "fast"

    def test_rejects_unknown_agent(self):
        r = httpx.put(f"{API_URL}/api/ai/agent/prefs", headers=H,
                      json={"agent_id": "ghost", "mode": "fast"}, timeout=10)
        assert r.status_code == 422

    def test_rejects_unknown_mode(self):
        r = httpx.put(f"{API_URL}/api/ai/agent/prefs", headers=H,
                      json={"agent_id": "strategy", "mode": "bogus"}, timeout=10)
        assert r.status_code == 422


# ----------------------------------------------------------------------
# 2) Cost tracking + admin spend endpoint
# ----------------------------------------------------------------------
class TestCostLookup:
    def test_cost_for_known_models(self):
        from routes.llm_spend import _cost_for
        assert _cost_for("claude-opus-4-7") > _cost_for("claude-sonnet-4-5")
        assert _cost_for("claude-sonnet-4-5") > _cost_for("claude-haiku-4-5-20251001")
        # Prefix match should work for unknown minor versions.
        assert _cost_for("claude-opus-99-future") == _cost_for("claude-opus")

    def test_cost_for_unknown_falls_back(self):
        from routes.llm_spend import _cost_for, DEFAULT_COST_PER_CALL
        assert _cost_for("totally-made-up-model") == DEFAULT_COST_PER_CALL
        assert _cost_for("") == DEFAULT_COST_PER_CALL


class TestLLMSpendEndpoint:
    def test_requires_admin(self):
        r = httpx.get(f"{API_URL}/api/admin/llm-spend", timeout=10)
        assert r.status_code == 401

    def test_empty_window_returns_zeros(self):
        _wipe_usage()
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=1", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["total_calls"] == 0
        assert body["total_estimated_cost"] == 0
        assert body["by_mode"] == []
        assert body["by_agent"] == []
        assert body["biggest_driver"] is None

    def test_chat_records_a_spend_row(self):
        """A successful agent_chat call must add ONE row to llm_usage
        and surface it in the admin spend aggregate."""
        _comp("growth")
        _wipe_usage()
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "kai", "message": "Say OK.", "mode": "fast"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=1", headers=H, timeout=10)
        body = r.json()
        assert body["total_calls"] >= 1
        assert body["total_estimated_cost"] > 0
        # by_agent must include Kai
        agents = {row["agent_id"] for row in body["by_agent"]}
        assert "kai" in agents
        # by_mode must include "fast"
        modes = {row["mode"] for row in body["by_mode"]}
        assert "fast" in modes
        # by_model must include a haiku entry
        models = " ".join(row["model"] for row in body["by_model"])
        assert "haiku" in models.lower()

    def test_days_param_is_clamped(self):
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=99999", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["days"] == 365
        # days=0 → falls back to default (30) via the `int(days or 30)` guard.
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=0", headers=H, timeout=10)
        assert r.status_code == 200
        assert r.json()["days"] == 30


# ----------------------------------------------------------------------
# 3) AI Team dashboard data endpoints
# ----------------------------------------------------------------------
class TestRecentConversations:
    def test_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/conversations/recent", timeout=10)
        assert r.status_code == 401

    def test_shape_and_dedupe_per_agent(self):
        """One row per agent_id with the most-recent prompt preview."""
        _comp("growth")
        # Fire two chats with the same agent — should still show ONE row.
        httpx.post(f"{API_URL}/api/ai/agent/chat", headers=H,
                   json={"agent_id": "nova", "message": "First nova message.", "mode": "fast"},
                   timeout=90)
        httpx.post(f"{API_URL}/api/ai/agent/chat", headers=H,
                   json={"agent_id": "nova", "message": "Second nova message.", "mode": "fast"},
                   timeout=90)
        httpx.post(f"{API_URL}/api/ai/agent/chat", headers=H,
                   json={"agent_id": "kai", "message": "First kai message.", "mode": "fast"},
                   timeout=90)

        r = httpx.get(f"{API_URL}/api/ai/agent/conversations/recent?limit=10",
                      headers=H, timeout=10)
        assert r.status_code == 200
        convos = r.json()["conversations"]
        agent_ids = [c["agent_id"] for c in convos]
        # Exactly one row per agent (dedupe via $group)
        assert agent_ids.count("nova") == 1
        assert agent_ids.count("kai") == 1
        nova_row = next(c for c in convos if c["agent_id"] == "nova")
        assert {"agent_id", "agent_name", "last_at", "preview"} <= set(nova_row.keys())
        # Preview is the LATEST message body, not the first.
        assert "Second" in nova_row["preview"] or len(nova_row["preview"]) > 0
        # "User asked Nova: " prefix is stripped.
        assert not nova_row["preview"].startswith("User asked")
