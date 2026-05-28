"""Tests for the SSE streaming variant of /api/ai/agent/chat.

We don't validate keepalive timing (LLM latency is non-deterministic);
we just confirm:
  • the endpoint emits the expected event vocabulary,
  • events arrive in the right order (started → memories → thinking → complete),
  • a `complete` event carries the same payload shape as the non-streaming
    endpoint,
  • auth + unknown-agent + plan-gating all behave identically.
"""
import json
import os
import re
import httpx

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
        headers=H, json={"plan": plan, "comped": True, "reason": "sse test"},
        timeout=10,
    )


def _parse_sse(blob: str) -> list[tuple[str, dict]]:
    """Parse a full SSE byte stream into a list of (event_name, data_dict)
    tuples. `data:` lines that aren't JSON are returned as raw strings."""
    out: list[tuple[str, dict]] = []
    # Records are blank-line separated.
    for record in re.split(r"\n\n", blob):
        record = record.strip()
        if not record or record.startswith(":"):
            continue
        ev, dat = None, None
        for line in record.split("\n"):
            if line.startswith("event: "):
                ev = line[len("event: "):].strip()
            elif line.startswith("data: "):
                payload = line[len("data: "):]
                try:
                    dat = json.loads(payload)
                except Exception:
                    dat = {"raw": payload}
        if ev:
            out.append((ev, dat or {}))
    return out


class TestStreamAuth:
    def test_stream_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat/stream",
            json={"agent_id": "nova", "message": "hi"},
            timeout=15,
        )
        # anonymous → 401 BEFORE the SSE handshake (orderly rejection).
        assert r.status_code == 401

    def test_stream_404_on_unknown_agent(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat/stream",
            headers=H, json={"agent_id": "ghost", "message": "hi"},
            timeout=15,
        )
        assert r.status_code == 404


class TestStreamHappyPath:
    def test_event_vocabulary_and_order(self):
        """One full streamed turn should emit: started → memories →
        thinking → complete (with 0+ keepalives interleaved)."""
        _comp("growth")
        with httpx.stream(
            "POST",
            f"{API_URL}/api/ai/agent/chat/stream",
            headers={**H, "Accept": "text/event-stream"},
            json={
                "agent_id": "kai",
                "message": "Reply with the word OK and nothing else.",
                "mode": "fast",  # Haiku is snappiest → keeps the test fast
            },
            timeout=120,
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            blob = "".join(r.iter_text())

        events = _parse_sse(blob)
        names = [ev for ev, _ in events]

        # The 3 mandatory events appear in this exact relative order.
        assert "started" in names
        assert "memories" in names
        assert "thinking" in names
        assert "complete" in names
        assert names.index("started") < names.index("memories")
        assert names.index("memories") < names.index("thinking")
        assert names.index("thinking") < names.index("complete")

        # `complete` payload mirrors the non-streaming endpoint shape.
        complete = dict(events)["complete"]
        assert complete["agent_id"] == "kai"
        assert isinstance(complete["answer"], str) and len(complete["answer"]) > 0
        assert isinstance(complete["follow_ups"], list)
        assert "memories_used" in complete
        assert "handoff" in complete  # null OK when no handoff fired
        assert complete["mode"] == "fast"
        assert "haiku" in complete["model"].lower()

    def test_started_event_carries_mode_metadata(self):
        """The frontend uses `started` to show a "Thinking with Opus…"
        label BEFORE the LLM call completes — so the payload must include
        the resolved mode + model."""
        _comp("growth")
        with httpx.stream(
            "POST",
            f"{API_URL}/api/ai/agent/chat/stream",
            headers={**H, "Accept": "text/event-stream"},
            json={"agent_id": "nova", "message": "Say OK.", "mode": "fast"},
            timeout=90,
        ) as r:
            assert r.status_code == 200
            blob = "".join(r.iter_text())

        events = _parse_sse(blob)
        started = next(d for ev, d in events if ev == "started")
        assert started["agent_id"] == "nova"
        assert started["agent_name"] == "Nova"
        assert started["mode"] == "fast"
        assert "haiku" in started["model"].lower()
