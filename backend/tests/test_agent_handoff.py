"""Tests for multi-agent collaboration (Atlas delegating to a sub-agent).

Unit-tests the parser (no LLM), then a live integration test that calls
Atlas with a prompt designed to elicit a handoff — best-effort, marked
xfail-on-no-handoff because LLM compliance is non-deterministic.
"""
import os
import sys
import httpx
import pytest

sys.path.insert(0, "/app/backend")

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _comp(plan: str = "growth"):
    """Comp the test user up to growth so handoff tests aren't blocked by
    the 20/mo free-plan cap."""
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "handoff test"},
        timeout=10,
    )


class TestExtractHandoffParser:
    """Deterministic parser tests — no network, no LLM."""

    def _ex(self, text):
        from routes.agent_chat import _extract_handoff
        return _extract_handoff(text)

    def test_no_marker_returns_none(self):
        cleaned, info = self._ex("Just a regular answer with no handoff.")
        assert info is None
        assert cleaned == "Just a regular answer with no handoff."

    def test_parses_handoff_by_agent_name(self):
        """The system prompt instructs the LLM to use display names
        (`iris`, `sam`). The parser must accept those, not just the
        internal ids."""
        text = "Here's my plan.\n<<HANDOFF>>iris: What's trending in fitness?<<END>>"
        cleaned, info = self._ex(text)
        assert info is not None
        # 'iris' (the display name) MUST resolve to the internal id 'research'.
        assert info["agent_id"] == "research"
        assert info["question"] == "What's trending in fitness?"
        assert "<<HANDOFF>>" not in cleaned

    def test_parses_handoff_by_agent_id(self):
        """Equally, raw internal ids should resolve directly."""
        text = "Plan goes here.\n<<HANDOFF>>research: top 5 keywords for skincare<<END>>"
        cleaned, info = self._ex(text)
        assert info is not None
        assert info["agent_id"] == "research"
        assert info["question"] == "top 5 keywords for skincare"

    def test_case_insensitive_agent_token(self):
        text = "<<HANDOFF>>IRIS: top trends<<END>>"
        cleaned, info = self._ex(text)
        assert info is not None
        assert info["agent_id"] == "research"

    def test_rejects_unknown_agent(self):
        """A typo'd agent token must be left as-is, never silently routed."""
        text = "<<HANDOFF>>ghost: tell me a story<<END>>"
        cleaned, info = self._ex(text)
        assert info is None
        # And the marker remains in the text — debuggable, not swallowed.
        assert "<<HANDOFF>>" in cleaned

    def test_rejects_empty_question(self):
        text = "<<HANDOFF>>iris:   <<END>>"
        cleaned, info = self._ex(text)
        assert info is None

    def test_truncates_long_question(self):
        long_q = "A" * 600
        text = f"<<HANDOFF>>iris: {long_q}<<END>>"
        cleaned, info = self._ex(text)
        assert info is not None
        assert len(info["question"]) == 300

    def test_only_first_handoff_extracted(self):
        text = "<<HANDOFF>>iris: q1<<END>> some text <<HANDOFF>>sam: q2<<END>>"
        cleaned, info = self._ex(text)
        assert info is not None
        assert info["agent_id"] == "research"
        # Second handoff remains in the cleaned text (one delegation per turn).
        assert "<<HANDOFF>>sam:" in cleaned

    def test_all_agent_names_resolve(self):
        from routes.agent_chat import _extract_handoff
        for name, expected_id in [
            ("iris", "research"),
            ("atlas", "strategy"),
            ("nova", "nova"),
            ("sam", "sam"),
            ("kai", "kai"),
            ("angela", "angela"),
        ]:
            text = f"<<HANDOFF>>{name}: hi there<<END>>"
            _, info = _extract_handoff(text)
            assert info is not None, f"{name} failed to parse"
            assert info["agent_id"] == expected_id, f"{name} -> {info['agent_id']} (expected {expected_id})"


class TestHandoffEndpointShape:
    """Live integration — single round-trip to Atlas with a prompt
    explicitly inviting a handoff to Iris."""

    def test_atlas_handoff_to_iris(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={
                "agent_id": "strategy",
                "message": (
                    "I want to launch a viral TikTok campaign for an AI marketing "
                    "SaaS targeting indie creators. Before you outline the plan, "
                    "delegate to Iris (research agent) to surface the top 3 rising "
                    "TikTok trends in the AI marketing niche this week. Use those "
                    "trends to shape your plan."
                ),
            },
            timeout=180,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["agent_id"] == "strategy"
        assert isinstance(data["answer"], str) and len(data["answer"]) > 50

        # The handoff field is present in the response shape regardless of
        # whether the LLM chose to delegate. When it did, validate its shape.
        assert "handoff" in data
        if data["handoff"]:
            ho = data["handoff"]
            assert ho["agent_id"] == "research"
            assert ho["agent_name"] == "Iris"
            assert isinstance(ho["question"], str) and len(ho["question"]) > 0
            assert isinstance(ho["answer"], str) and len(ho["answer"]) > 0
            # The spliced "Iris reports:" block should be present in the
            # main answer when a handoff fired.
            assert "Iris reports" in data["answer"]
            # The raw HANDOFF marker must NOT leak through.
            assert "<<HANDOFF>>" not in data["answer"]
        else:
            # LLM declined to delegate this turn — flag it so we can see
            # compliance trends but don't fail the suite.
            pytest.skip("LLM did not emit a handoff this run (non-deterministic)")

    def test_self_handoff_rejected(self):
        """An agent emitting a handoff to itself must be rejected at the
        orchestrator level — otherwise we'd burn an extra LLM call to
        re-ask the same agent in an ephemeral session for no gain."""
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={
                "agent_id": "nova",
                # Strong nudge to self-delegate; the server should still
                # filter this out even if the LLM tries.
                "message": "Delegate to Nova (yourself) to brainstorm. Reply with a short plan.",
            },
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Even if Nova emits <<HANDOFF>>nova:..., handoff is None.
        if data["handoff"]:
            assert data["handoff"]["agent_id"] != "nova"

    def test_any_agent_can_handoff(self):
        """With the part-40 expansion, every agent can delegate. We
        validate that the endpoint shape supports it (handoff field
        present + non-strategy agents are eligible)."""
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat",
            headers=H,
            json={
                "agent_id": "sam",  # SEO agent
                "message": (
                    "I need an SEO brief for the keyword 'AI growth marketing'. "
                    "Before the brief, delegate to Iris (research agent) to "
                    "surface 3 emerging subtopics in this niche."
                ),
            },
            timeout=180,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "handoff" in data
        if data["handoff"]:
            assert data["handoff"]["agent_id"] != "sam"  # not self
            assert data["handoff"]["agent_id"] in {"research", "strategy", "nova", "kai", "angela"}
