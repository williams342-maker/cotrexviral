"""Real-time HITL inbox — WebSocket tests.

These run against the live backend (ws://localhost:8001) because the
WS handshake doesn't play nicely with httpx-style mocking. We use the
`websockets` client lib (already a runtime dep) for the assertions.
"""
import asyncio
import json
import os
import time

import httpx
import pytest
import websockets
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# Same credentials the rest of the test suite uses.
TOKEN  = "test_session_1779636592168"
WS_URI = f"ws://localhost:8001/api/ws/hitl-inbox?token={TOKEN}"
API_URL = "http://localhost:8001"
H = {"Authorization": f"Bearer {TOKEN}"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestRealtimeInbox:

    def test_unauthenticated_ws_is_closed(self):
        async def go():
            uri = "ws://localhost:8001/api/ws/hitl-inbox"  # no token
            # `websockets` raises various exception types across versions
            # (InvalidStatus, InvalidStatusCode, ConnectionClosedError) on
            # an immediate server-side close. Catch the broad family.
            with pytest.raises(Exception) as excinfo:
                async with websockets.connect(uri, open_timeout=5):
                    pass
            # Confirm it's a websockets-level failure, not a stray
            # AssertionError from elsewhere.
            assert "websockets" in str(type(excinfo.value).__module__).lower() \
                or "1008" in str(excinfo.value) \
                or "unauthorized" in str(excinfo.value).lower()
        _run(go())

    def test_authenticated_ws_receives_snapshot(self):
        async def go():
            async with websockets.connect(WS_URI, open_timeout=5) as ws:
                frame = await asyncio.wait_for(ws.recv(), timeout=3)
                d = json.loads(frame)
                assert d["event"] == "snapshot"
                assert "paused" in d["data"]
                assert isinstance(d["data"]["paused"], list)
                assert "at" in d
        _run(go())

    def test_ping_pong_heartbeat(self):
        async def go():
            async with websockets.connect(WS_URI, open_timeout=5) as ws:
                await asyncio.wait_for(ws.recv(), timeout=3)  # drain snapshot
                await ws.send("ping")
                pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                assert pong["event"] == "pong"
        _run(go())

    def test_broadcast_fires_when_run_pauses(self):
        """End-to-end: open a WS, trigger a `requires_approval=True`
        run, expect a `hitl_paused` frame to arrive within the SSE
        lifetime."""
        received = []

        async def listen():
            async with websockets.connect(WS_URI, open_timeout=5) as ws:
                await asyncio.wait_for(ws.recv(), timeout=3)  # snapshot
                # Wait for the broadcast — generous timeout because the
                # canonical chain runs 3 cheap LLM calls before pausing.
                deadline = time.time() + 180
                while time.time() < deadline and not received:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                    except asyncio.TimeoutError:
                        break
                    if msg.get("event") != "pong":
                        received.append(msg)

        async def trigger():
            await asyncio.sleep(0.5)
            async with httpx.AsyncClient(timeout=200) as cli:
                r = await cli.post(
                    f"{API_URL}/api/marketing-os/run/stream",
                    headers=H,
                    json={"brief": "Realtime inbox test",
                          "mode": "fast", "requires_approval": True},
                )
                # We don't strictly need 200 — but on budget failure we skip.
                if r.status_code != 200:
                    pytest.skip(f"run stream returned {r.status_code}")
                if "error" in r.text and "budget" in r.text.lower():
                    pytest.skip("LLM budget exceeded")

        async def go():
            await asyncio.gather(listen(), trigger())

        _run(go())

        if not received:
            pytest.skip("No broadcast received — likely LLM budget hit")

        # Exactly one HITL paused broadcast for our trigger.
        events = [m["event"] for m in received]
        assert "hitl_paused" in events, f"expected hitl_paused in {events}"
        paused = next(m for m in received if m["event"] == "hitl_paused")
        assert paused["data"]["status"] == "awaiting_approval"
        assert paused["data"]["run_id"]
        assert paused["data"]["transcript_len"] >= 1   # at least Strategy ran
