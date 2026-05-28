"""Tests for the model-routing layer (router unit tests + per-task user
override surfaced via `/api/ai/agent/chat` and `/api/ai/agent/modes`)."""
import os
import sys
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
        headers=H, json={"plan": plan, "comped": True, "reason": "router test"},
        timeout=10,
    )


class TestRouterUnit:
    def test_for_task_known(self):
        from routes.model_router import for_task
        assert for_task("deep") == ("anthropic", "claude-opus-4-7")
        assert for_task("fast")[0] == "anthropic"
        assert for_task("research") == ("gemini", "gemini-2.5-pro")

    def test_for_task_unknown_falls_back_to_default(self):
        from routes.model_router import for_task, ROUTES
        assert for_task("nonsense") == ROUTES["default"]
        assert for_task("") == ROUTES["default"]

    def test_for_agent_uses_per_persona_default(self):
        from routes.model_router import for_agent
        # Atlas = deep (Opus), Iris = research (Gemini), the rest = creative (Sonnet)
        assert for_agent("strategy") == ("anthropic", "claude-opus-4-7")
        assert for_agent("research") == ("gemini", "gemini-2.5-pro")
        assert for_agent("nova")[0] == "anthropic"

    def test_resolve_user_mode_override_wins(self):
        """Explicit user mode beats the agent's natural task."""
        from routes.model_router import resolve_user_mode
        provider, model, task = resolve_user_mode("fast", "strategy")
        assert task == "fast"
        assert "haiku" in model

    def test_resolve_user_mode_auto_falls_back_to_agent_default(self):
        from routes.model_router import resolve_user_mode
        provider, model, task = resolve_user_mode("auto", "strategy")
        # Atlas's natural task is "deep" -> Claude Opus
        assert task == "deep"
        assert "opus" in model

    def test_resolve_user_mode_none_falls_back_to_agent_default(self):
        from routes.model_router import resolve_user_mode
        _, _, task = resolve_user_mode(None, "research")
        assert task == "research"

    def test_resolve_user_mode_unknown_silently_falls_back(self):
        """Unknown mode strings must not crash — silently treated as auto."""
        from routes.model_router import resolve_user_mode
        _, _, task = resolve_user_mode("hacker", "nova")
        # Nova's natural task is creative, not the bogus 'hacker'
        assert task == "creative"


class TestModesEndpoint:
    def test_modes_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/modes", timeout=10)
        assert r.status_code == 401

    def test_modes_returns_canonical_set(self):
        r = httpx.get(f"{API_URL}/api/ai/agent/modes", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        ids = {m["id"] for m in body["modes"]}
        # Auto must always be first-class (the UI default), plus the three
        # explicit overrides surfaced as chips.
        assert {"auto", "fast", "deep", "creative"} <= ids
        for m in body["modes"]:
            assert {"id", "label", "blurb"} <= set(m.keys())
            assert isinstance(m["label"], str) and len(m["label"]) > 0


class TestAgentChatRespectsMode:
    """End-to-end: passing `mode="fast"` to /api/ai/agent/chat must surface
    `mode: "fast"` (and the haiku model id) in the response."""

    def test_chat_default_mode_uses_agent_natural_task(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "nova", "message": "Reply with the word HELLO and nothing else."},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Nova's natural task is creative -> claude-sonnet
        assert data["mode"] == "creative"
        assert "sonnet" in data["model"].lower()

    def test_chat_fast_mode_overrides_agent_task(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={
                "agent_id": "strategy",  # would normally use deep/opus
                "message": "Say OK.",
                "mode": "fast",
            },
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["mode"] == "fast"
        # Fast = Claude Haiku (~1-2s) — must NOT have routed to Opus.
        assert "haiku" in data["model"].lower()
        assert "opus" not in data["model"].lower()

    def test_chat_auto_mode_is_a_noop(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "sam", "message": "Say OK.", "mode": "auto"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Sam's natural task is creative; "auto" must not change that.
        assert data["mode"] == "creative"

    def test_chat_unknown_mode_silently_falls_back(self):
        """The frontend should never crash the backend by sending a typo."""
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={"agent_id": "kai", "message": "Say OK.", "mode": "ultra-mega"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Kai's natural task is creative — must NOT be the bogus mode.
        assert data["mode"] == "creative"
