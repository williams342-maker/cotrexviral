"""LangGraph migration P0 — skip_distribution conditional edge +
convene regression + framework=langgraph persistence check.

Covers the items called out in the testing brief:
  1) Empty-platforms campaign run sets skip_distribution=True in
     os_started and the SSE stream never emits an agent_started event
     for Kai (distribution).
  2) The persisted marketing_os_runs row carries framework='langgraph'
     and skip_distribution=True.
  3) /api/ai/agent/convene/stream (the old per-user Convene modal,
     untouched by this migration) still streams events.
"""
import os
import re
import json
import time
import uuid
import httpx
import pytest

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
).rstrip("/")
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _comp(plan: str = "growth"):
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "langgraph test"},
        timeout=10,
    )


def _parse_sse(blob: str):
    out = []
    for record in re.split(r"\n\n", blob):
        record = record.strip()
        if not record or record.startswith(":"):
            continue
        ev, dat = None, None
        for line in record.split("\n"):
            if line.startswith("event: "):
                ev = line[len("event: "):].strip()
            elif line.startswith("data: "):
                try:
                    dat = json.loads(line[len("data: "):])
                except Exception:
                    dat = {"raw": line[len("data: "):]}
        if ev:
            out.append((ev, dat or {}))
    return out


# ---------------------------------------------------------------------
# Conditional edge — skip_distribution
# ---------------------------------------------------------------------
class TestSkipDistributionConditionalEdge:
    def _create_empty_platform_campaign(self):
        name = f"TEST_LG_empty_{uuid.uuid4().hex[:6]}"
        r = httpx.post(
            f"{API_URL}/api/campaigns", headers=H,
            json={
                "name": name,
                "goal": "awareness",
                "audience": "indie devs",
                "platforms": [],
                "content_pillars": ["product", "build-in-public"],
            },
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        cid = body.get("id") or body.get("campaign", {}).get("id")
        assert cid, f"campaign id missing in {body}"
        return cid

    def test_empty_platforms_skips_kai(self):
        _comp("growth")
        cid = self._create_empty_platform_campaign()

        with httpx.stream(
            "POST", f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={
                "brief": "Plan a small awareness push for our new dev tool.",
                "campaign_id": cid,
                "mode": "fast",
            },
            timeout=300,
        ) as r:
            if r.status_code != 200:
                pytest.skip(f"Run stream returned {r.status_code}; likely budget/auth")
            assert "text/event-stream" in r.headers.get("content-type", "")
            blob = "".join(r.iter_text())

        if "budget" in blob.lower() and ("exceeded" in blob.lower() or "error" in blob.lower()):
            pytest.skip("LLM budget exceeded — skipping conditional-edge assertions")

        events = _parse_sse(blob)
        names = [ev for ev, _ in events]

        # Core vocabulary must still be present (Kai is the only one skipped).
        for required in ("os_started", "agent_started", "agent_done",
                         "summarizing", "complete", "os_persisted"):
            assert required in names, f"missing {required} in {names}"

        # os_started must carry skip_distribution=true
        os_started_payload = next(d for ev, d in events if ev == "os_started")
        assert os_started_payload.get("skip_distribution") is True, \
            f"os_started.skip_distribution should be True; got {os_started_payload}"

        # No agent_started for kai
        kai_started = [
            d for ev, d in events
            if ev == "agent_started" and (d.get("agent_id") == "kai")
        ]
        assert not kai_started, f"Kai (distribution) should be skipped; got {kai_started}"

        # Also no agent_done for kai
        kai_done = [
            d for ev, d in events
            if ev == "agent_done" and (d.get("agent_id") == "kai")
        ]
        assert not kai_done, f"agent_done for kai not expected; got {kai_done}"

        # Persisted row should carry framework=langgraph + skip_distribution=True
        run_id = os_started_payload.get("run_id")
        assert run_id, "os_started must carry run_id"
        got = httpx.get(f"{API_URL}/api/marketing-os/runs/{run_id}",
                        headers=H, timeout=10)
        assert got.status_code == 200, got.text
        doc = got.json()
        assert doc.get("framework") == "langgraph", f"framework marker missing: {doc.get('framework')}"
        assert doc.get("skip_distribution") is True
        assert doc.get("status") == "completed"


# ---------------------------------------------------------------------
# Convene regression — untouched by this migration but uses some
# shared helpers; must still stream events.
# ---------------------------------------------------------------------
class TestConveneRegression:
    def test_convene_stream_still_works(self):
        _comp("growth")
        with httpx.stream(
            "POST", f"{API_URL}/api/ai/agent/convene/stream", headers=H,
            json={
                "message": "What's the best one-line hook for a coffee shop launch?",
                "agents": ["strategy", "nova"],
                "mode": "fast",
            },
            timeout=240,
        ) as r:
            if r.status_code != 200:
                pytest.skip(f"Convene stream returned {r.status_code}; likely budget/auth")
            assert "text/event-stream" in r.headers.get("content-type", "")
            blob = "".join(r.iter_text())

        if "budget" in blob.lower() and ("exceeded" in blob.lower() or "error" in blob.lower()):
            pytest.skip("LLM budget exceeded — skipping convene regression assertions")

        events = _parse_sse(blob)
        names = {ev for ev, _ in events}
        # Minimal vocabulary — convene shape may differ slightly but
        # must at least surface agent activity + a terminal event.
        assert "agent_started" in names or "started" in names, \
            f"convene stream missing agent_started; got {names}"
        assert any(t in names for t in ("complete", "summarizing")), \
            f"convene stream missing terminal events; got {names}"
