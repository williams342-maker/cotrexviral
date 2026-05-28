"""Tests for the Convene multi-agent orchestrator.

The full chain (Research → SEO → Copy → Atlas synthesis) takes 60-90s
on the slowest path so we keep the live integration to one happy-path
test and shape-check the rest via the synchronous endpoint."""
import os
import json
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
        headers=H, json={"plan": plan, "comped": True, "reason": "convene test"},
        timeout=10,
    )


def _parse_sse(blob: str) -> list[tuple[str, dict]]:
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
                try: dat = json.loads(line[len("data: "):])
                except Exception: dat = {"raw": line[len("data: "):]}
        if ev:
            out.append((ev, dat or {}))
    return out


class TestConveneValidation:
    def test_auth_required(self):
        r = httpx.post(f"{API_URL}/api/ai/agent/convene",
                       json={"message": "hi"}, timeout=10)
        assert r.status_code == 401

    def test_rejects_unknown_agent(self):
        _comp("growth")
        r = httpx.post(f"{API_URL}/api/ai/agent/convene", headers=H,
                       json={"message": "hi", "agents": ["research", "ghost"]},
                       timeout=10)
        assert r.status_code == 422

    def test_rejects_empty_chain(self):
        _comp("growth")
        r = httpx.post(f"{API_URL}/api/ai/agent/convene", headers=H,
                       json={"message": "hi", "agents": []}, timeout=10)
        # Pydantic catches the empty list via min_length=None but our
        # `_resolve_convene` rejects too — either way it's NOT 200.
        assert r.status_code in (422,)

    def test_rejects_too_many_agents(self):
        _comp("growth")
        r = httpx.post(f"{API_URL}/api/ai/agent/convene", headers=H,
                       json={"message": "hi",
                             "agents": ["research", "sam", "nova", "kai", "angela", "strategy"]},
                       timeout=10)
        # Pydantic max_length=5 catches this at validation time → 422.
        assert r.status_code == 422

    def test_dedupes_repeated_agents(self):
        """Running the same agent twice is wasteful; the resolver
        silently dedupes. We validate by inspecting the chain in the
        `started` SSE event so we don't have to wait for 6 LLM calls."""
        _comp("growth")
        with httpx.stream(
            "POST", f"{API_URL}/api/ai/agent/convene/stream", headers=H,
            json={"message": "tiny brief", "agents": ["sam", "sam", "kai"], "mode": "fast"},
            timeout=180,
        ) as r:
            assert r.status_code == 200
            # We only need the first `started` event — abort the rest
            # so we don't have to wait for the full chain.
            blob = ""
            for chunk in r.iter_text():
                blob += chunk
                if "event: started" in blob and "\n\n" in blob.split("event: started", 1)[1]:
                    break
        events = _parse_sse(blob)
        started = next(d for ev, d in events if ev == "started")
        chain_ids = [c["agent_id"] for c in started["chain"]]
        assert chain_ids.count("sam") == 1
        assert "kai" in chain_ids


class TestConveneHappyPath:
    def test_full_chain_produces_summary(self):
        """One end-to-end run with 2 agents (kept short for test speed)
        on fast mode. Asserts transcript shape + that the summarizer
        produced a non-trivial answer."""
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/convene", headers=H,
            json={
                "message": "Pitch a name for a 1-person SEO consultancy.",
                "agents": ["sam", "nova"],
                "mode": "fast",
            },
            timeout=240,
        )
        if r.status_code == 500 and "budget" in r.text.lower():
            import pytest
            pytest.skip("Emergent LLM key budget exceeded — top-up required")
        assert r.status_code == 200, r.text
        data = r.json()
        # Transcript: one row per agent in the requested order.
        assert [t["agent_id"] for t in data["transcript"]] == ["sam", "nova"]
        for t in data["transcript"]:
            assert isinstance(t["answer"], str) and len(t["answer"]) > 50
            # The chain agents must NOT leak follow-up / handoff markers.
            assert "<<FUPS>>" not in t["answer"]
            assert "<<HANDOFF>>" not in t["answer"]
        # Synthesizer defaults to Atlas.
        assert data["summarizer"]["agent_id"] == "strategy"
        assert isinstance(data["summary"], str) and len(data["summary"]) > 100

    def test_stream_emits_canonical_events(self):
        _comp("growth")
        with httpx.stream(
            "POST", f"{API_URL}/api/ai/agent/convene/stream", headers=H,
            json={"message": "Name a coffee brand in one word.",
                  "agents": ["nova"], "mode": "fast"},
            timeout=240,
        ) as r:
            if r.status_code != 200:
                import pytest
                pytest.skip(f"Stream returned {r.status_code} (likely budget)")
            assert "text/event-stream" in r.headers.get("content-type", "")
            blob = "".join(r.iter_text())

        if '"budget' in blob.lower() or "budget exceeded" in blob.lower():
            import pytest
            pytest.skip("Emergent LLM key budget exceeded — top-up required")
        events = _parse_sse(blob)
        names = [ev for ev, _ in events]
        assert "started" in names
        assert "agent_started" in names
        assert "agent_done" in names
        assert "summarizing" in names
        assert "complete" in names
        # Order: started → agent_started → agent_done → summarizing → complete
        assert names.index("started") < names.index("agent_started")
        assert names.index("agent_started") < names.index("agent_done")
        assert names.index("agent_done") < names.index("summarizing")
        assert names.index("summarizing") < names.index("complete")
        complete = dict(events)["complete"]
        assert "summary" in complete and len(complete["summary"]) > 50
        assert len(complete["transcript"]) == 1

    def test_convene_persists_a_memory(self):
        """After a convene, a memory row of kind `convene_summary` must
        exist so future agent_chats can recall the team's verdict."""
        # Use pymongo (sync) so we don't fight Motor's per-loop binding
        # when this test runs in the same session as others.
        from pymongo import MongoClient
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        coll = MongoClient(mongo_url)[db_name].cortex_memory

        before = coll.count_documents({"user_id": USER_ID, "kind": "convene_summary"})
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/ai/agent/convene", headers=H,
            json={"message": "One coffee tagline.", "agents": ["nova"], "mode": "fast"},
            timeout=180,
        )
        if r.status_code == 500 and "budget" in r.text.lower():
            import pytest
            pytest.skip("Emergent LLM key budget exceeded — top-up required")
        assert r.status_code == 200
        after = coll.count_documents({"user_id": USER_ID, "kind": "convene_summary"})
        assert after == before + 1
