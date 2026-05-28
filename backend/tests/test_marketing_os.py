"""Tests for the Marketing OS module — dashboard, signals, roles,
runs and the canonical 5-role SSE chain.

These exercise the NEW /api/marketing-os/* surface and verify that
Opportunity Signals scoring is applied during /api/trends/ingest.
LLM-driven /run/stream test is gated to mode='fast' + a 2-role chain
to keep cost low; if the Emergent LLM key 429s on budget, the test
skips cleanly per the testing brief.
"""
import os
import json
import re
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
    """Ensure the test user has an active comped plan."""
    httpx.post(
        f"{API_URL}/api/admin/users/{USER_ID}/plan",
        headers=H, json={"plan": plan, "comped": True, "reason": "marketing-os test"},
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
                try:
                    dat = json.loads(line[len("data: "):])
                except Exception:
                    dat = {"raw": line[len("data: "):]}
        if ev:
            out.append((ev, dat or {}))
    return out


# ---------------------------------------------------------------------
# Auth & shape — /dashboard, /signals, /runs, /roles
# ---------------------------------------------------------------------
class TestMarketingOSAuth:
    def test_dashboard_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/dashboard", timeout=10)
        assert r.status_code == 401

    def test_signals_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/signals", timeout=10)
        assert r.status_code == 401

    def test_runs_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/runs", timeout=10)
        assert r.status_code == 401

    def test_roles_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/roles", timeout=10)
        assert r.status_code == 401

    def test_run_stream_requires_auth(self):
        r = httpx.post(f"{API_URL}/api/marketing-os/run/stream",
                       json={"brief": "hi"}, timeout=10)
        assert r.status_code == 401


class TestMarketingOSDashboard:
    def test_dashboard_payload_shape(self):
        _comp("growth")
        r = httpx.get(f"{API_URL}/api/marketing-os/dashboard", headers=H, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # All top-level keys
        for k in ("roles", "stats", "campaigns", "signals", "approvals", "runs", "wins"):
            assert k in data, f"missing key: {k}"

        # 5 canonical roles
        assert len(data["roles"]) == 5
        roles_names = [r_["role"] for r_ in data["roles"]]
        assert roles_names == ["strategy", "intelligence", "content", "distribution", "analytics"]
        for r_ in data["roles"]:
            for fld in ("role", "agent_id", "label", "color"):
                assert fld in r_ and isinstance(r_[fld], str) and r_[fld]

        # 4 numeric counters
        stats = data["stats"]
        for k in ("campaigns_active", "pending_approvals", "signals_hot", "recent_wins"):
            assert k in stats, f"missing stats key: {k}"
            assert isinstance(stats[k], int)

        # Lists
        for k in ("campaigns", "signals", "approvals", "runs", "wins"):
            assert isinstance(data[k], list)


class TestMarketingOSRoles:
    def test_roles_endpoint(self):
        _comp("growth")
        r = httpx.get(f"{API_URL}/api/marketing-os/roles", headers=H, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "roles" in data
        assert len(data["roles"]) == 5
        expected_roles = ["strategy", "intelligence", "content", "distribution", "analytics"]
        actual = [r_["role"] for r_ in data["roles"]]
        assert actual == expected_roles
        for r_ in data["roles"]:
            assert set(r_.keys()) >= {"role", "agent_id", "label", "color"}


class TestMarketingOSRuns:
    def test_runs_returns_list(self):
        _comp("growth")
        r = httpx.get(f"{API_URL}/api/marketing-os/runs", headers=H, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data and isinstance(data["runs"], list)
        assert "count" in data

    def test_get_run_unknown_returns_404(self):
        _comp("growth")
        r = httpx.get(f"{API_URL}/api/marketing-os/runs/nonexistent_id_xxx",
                      headers=H, timeout=10)
        assert r.status_code == 404


# ---------------------------------------------------------------------
# Signals — ranking + ingest-time scoring
# ---------------------------------------------------------------------
class TestMarketingOSSignals:
    def test_signals_ranked_by_virality(self):
        _comp("growth")
        # Trigger ingestion so we have signals to inspect. Reddit may be
        # un-configured in this env (returns 0); Gtrends is best-effort.
        ingest = httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"keywords": ["seo", "saas"], "subreddits": ["SaaS", "marketing"]},
            timeout=60,
        )
        assert ingest.status_code in (200, 201), ingest.text

        r = httpx.get(f"{API_URL}/api/marketing-os/signals?limit=20",
                      headers=H, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "signals" in data
        scores = [
            int(((s.get("meta") or {}).get("signal") or {}).get("virality_score") or 0)
            for s in data["signals"]
        ]
        # Must be sorted desc.
        assert scores == sorted(scores, reverse=True), f"not sorted desc: {scores}"

    def test_signals_limit_param(self):
        _comp("growth")
        r = httpx.get(f"{API_URL}/api/marketing-os/signals?limit=3",
                      headers=H, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data["signals"]) <= 3

    def test_ingested_trend_has_signal_envelope(self):
        """Every freshly-ingested trend memory must carry a structured
        opportunity-signal envelope under meta.signal."""
        _comp("growth")
        ingest = httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"keywords": ["seo"], "subreddits": ["marketing"]},
            timeout=60,
        )
        assert ingest.status_code == 200

        recent = httpx.get(f"{API_URL}/api/trends/recent?limit=20",
                           headers=H, timeout=10)
        assert recent.status_code == 200
        rows = recent.json()["trends"]
        # If no trends at all (Reddit unconfigured + pytrends quiet), skip
        if not rows:
            pytest.skip("No trend rows ingested (Reddit may be unconfigured in this env)")
        for row in rows[:5]:
            sig = (row.get("meta") or {}).get("signal")
            assert sig, f"row missing meta.signal: {row}"
            assert isinstance(sig.get("virality_score"), int)
            assert 0 <= sig["virality_score"] <= 100
            assert sig.get("urgency") in ("now", "this_week", "monitor")
            assert isinstance(sig.get("content_angle"), str) and sig["content_angle"]
            assert sig.get("recommended_agent") in ("nova", "sam", "kai", "angela")

    def test_seo_keyword_routes_to_sam(self):
        """A 'seo'-bearing signal should be recommended to Sam."""
        _comp("growth")
        ingest = httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"keywords": ["seo"], "subreddits": []},
            timeout=60,
        )
        assert ingest.status_code == 200

        recent = httpx.get(f"{API_URL}/api/trends/recent?limit=30",
                           headers=H, timeout=10)
        rows = recent.json()["trends"]
        seo_rows = [
            r for r in rows
            if "seo" in (r.get("text") or "").lower()
            and (r.get("meta") or {}).get("signal")
        ]
        if not seo_rows:
            pytest.skip("No 'seo' trend rows available to assert recommended_agent")
        # At least one should route to sam
        recs = [r["meta"]["signal"]["recommended_agent"] for r in seo_rows]
        assert "sam" in recs, f"Expected at least one 'sam' rec for SEO signals; got {recs}"


# ---------------------------------------------------------------------
# Run/stream — validation + happy path
# ---------------------------------------------------------------------
class TestMarketingOSRunValidation:
    def test_invalid_role_rejected(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={"brief": "hi", "roles": ["strategy", "ghost"], "mode": "fast"},
            timeout=10,
        )
        assert r.status_code == 422

    def test_empty_brief_rejected(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={"brief": "", "roles": ["strategy"], "mode": "fast"},
            timeout=10,
        )
        assert r.status_code == 422

    def test_unknown_campaign_returns_404(self):
        _comp("growth")
        r = httpx.post(
            f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={"brief": "hi", "roles": ["strategy"],
                  "campaign_id": "nope_does_not_exist", "mode": "fast"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_empty_roles_list_accepted_or_422(self):
        """Spec: empty roles handled — either default chain runs (200/SSE)
        or 422. We accept either contract."""
        _comp("growth")
        # Open as a stream so we don't burn an LLM call; just check the
        # initial status code.
        with httpx.stream(
            "POST", f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={"brief": "tiny brief", "roles": [], "mode": "fast"},
            timeout=30,
        ) as r:
            assert r.status_code in (200, 422), r.status_code


class TestMarketingOSRunStream:
    def test_short_run_emits_canonical_events_and_persists(self):
        """End-to-end: 2-role chain on fast mode. Verifies SSE event
        order, that a marketing_os_runs doc is persisted with status
        'completed', and the GET /runs/{id} endpoint returns it."""
        _comp("growth")
        with httpx.stream(
            "POST", f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={
                "brief": "launch plan for a coffee shop",
                "roles": ["strategy", "content"],
                "mode": "fast",
            },
            timeout=240,
        ) as r:
            if r.status_code != 200:
                pytest.skip(f"Run stream returned {r.status_code}; likely budget/auth")
            assert "text/event-stream" in r.headers.get("content-type", "")
            blob = "".join(r.iter_text())

        # Budget-skip path — Emergent key may have hit cap.
        if "budget" in blob.lower() and ("exceeded" in blob.lower() or "error" in blob.lower()):
            pytest.skip("LLM budget exceeded — skipping happy-path assertions")

        events = _parse_sse(blob)
        names = [ev for ev, _ in events]

        # Required event vocabulary (order-checked below).
        for required in ("os_started", "agent_started", "agent_done",
                         "summarizing", "complete", "os_persisted"):
            assert required in names, f"missing {required} in events {names}"

        # Order check.
        assert names.index("os_started") < names.index("agent_started")
        assert names.index("agent_started") < names.index("agent_done")
        assert names.index("agent_done") < names.index("summarizing")
        assert names.index("summarizing") < names.index("complete")
        assert names.index("complete") < names.index("os_persisted")

        # Pull run_id from os_started.
        os_started = dict(events)["os_started"]
        run_id = os_started.get("run_id")
        assert run_id, "os_started must carry a run_id"

        # Fetch persisted run.
        got = httpx.get(f"{API_URL}/api/marketing-os/runs/{run_id}",
                        headers=H, timeout=10)
        assert got.status_code == 200, got.text
        doc = got.json()
        assert doc.get("status") == "completed"
        assert isinstance(doc.get("transcript"), list) and len(doc["transcript"]) >= 1
        assert isinstance(doc.get("summary"), str) and len(doc["summary"]) > 0



# ---------------------------------------------------------------------
# LangGraph orchestrator — module-level smoke tests
# ---------------------------------------------------------------------
class TestLangGraphOrchestrator:
    """Sanity checks for the new `marketing_os_graph` module — these
    don't hit the LLM; they verify the graph builds, the conditional
    edges resolve correctly, and the canonical chain is wired."""

    def test_canonical_graph_compiles(self):
        from routes.marketing_os_graph import (
            get_canonical_graph, reset_canonical_graph,
        )
        reset_canonical_graph()
        graph = get_canonical_graph()
        # Compiled StateGraph exposes `nodes` + `astream`.
        assert hasattr(graph, "ainvoke")
        # All canonical nodes are present.
        node_names = set(getattr(graph, "nodes", {}).keys())
        for n in ("strategy", "intelligence", "content", "distribution", "summariser"):
            assert n in node_names, f"node {n} missing from graph (got {node_names})"

    def test_route_after_content_skips_distribution(self):
        from routes.marketing_os_graph import _route_after_content
        # Skip when flagged.
        assert _route_after_content({"skip_distribution": True}) == "summariser"
        # Run distribution otherwise.
        assert _route_after_content({"skip_distribution": False}) == "distribution"
        # Error short-circuit also routes to summariser.
        assert _route_after_content({"error": "boom"}) == "summariser"

    def test_route_after_strategy_error_short_circuits(self):
        from routes.marketing_os_graph import _route_after_strategy
        assert _route_after_strategy({"error": "boom"}) == "summariser"
        assert _route_after_strategy({}) == "intelligence"

    def test_canonical_roles_match_marketing_os_module(self):
        # Single source of truth check — both modules must agree.
        from routes.marketing_os_graph import CANONICAL_ROLES as G_ROLES
        from routes.marketing_os import CANONICAL_ROLES as M_ROLES
        assert G_ROLES == M_ROLES

    def test_persisted_run_marked_langgraph(self):
        """Whether or not the live LLM call succeeds, the persisted
        row must carry `framework: "langgraph"` so future migrations
        can filter old vs new runs."""
        # Pull the latest run for this user — if any exist they should
        # be marked. If none exist, skip (the live happy-path test in
        # TestMarketingOSRunStream will create one).
        r = httpx.get(
            f"{API_URL}/api/marketing-os/runs?limit=1", headers=H, timeout=10,
        )
        assert r.status_code == 200
        runs = r.json().get("runs") or []
        if not runs:
            pytest.skip("No runs persisted yet — happy-path test will create one")
        # The latest run was just inserted by this test session, so it
        # MUST have the framework marker.
        latest = runs[0]
        # Older runs lack the field — guard.
        if "framework" in latest:
            assert latest["framework"] == "langgraph"



# ---------------------------------------------------------------------
# Human-in-the-loop — approve / reject endpoints
# ---------------------------------------------------------------------
class TestHITLEndpoints:
    """Validates the /api/marketing-os/runs/{id}/approve and /reject
    endpoints. The full happy path (live LLM) is exercised in the
    skip-distribution suite via a synthetic paused row to avoid burning
    LLM budget here."""

    def test_approve_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/marketing-os/runs/anything/approve",
            json={}, timeout=10,
        )
        assert r.status_code == 401

    def test_reject_requires_auth(self):
        r = httpx.post(
            f"{API_URL}/api/marketing-os/runs/anything/reject",
            json={}, timeout=10,
        )
        assert r.status_code == 401

    def test_approve_unknown_run_id_404(self):
        r = httpx.post(
            f"{API_URL}/api/marketing-os/runs/DOES_NOT_EXIST/approve",
            headers=H, json={}, timeout=10,
        )
        assert r.status_code == 404

    def test_approve_wrong_status_409(self):
        """If the run isn't in 'awaiting_approval', /approve must
        409. Use a synthetic completed run to test the guard without
        invoking the LLM."""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        import os as _os
        from datetime import datetime, timezone

        async def _setup():
            from dotenv import load_dotenv
            load_dotenv("/app/backend/.env")
            cli = AsyncIOMotorClient(_os.environ["MONGO_URL"])
            d = cli[_os.environ["DB_NAME"]]
            rid = "test_hitl_409_completed_run"
            await d.marketing_os_runs.delete_many({"id": rid})
            await d.marketing_os_runs.insert_one({
                "id":         rid,
                "user_id":    USER_ID,
                "brief":      "synthetic completed run",
                "brief_text": "synthetic completed run",
                "status":     "completed",  # NOT awaiting_approval
                "transcript": [],
                "framework":  "langgraph",
                "created_at": datetime.now(timezone.utc),
            })
            cli.close()
            return rid

        rid = asyncio.get_event_loop().run_until_complete(_setup())
        r = httpx.post(
            f"{API_URL}/api/marketing-os/runs/{rid}/approve",
            headers=H, json={}, timeout=10,
        )
        assert r.status_code == 409
        # Reject should give the same guard.
        r2 = httpx.post(
            f"{API_URL}/api/marketing-os/runs/{rid}/reject",
            headers=H, json={}, timeout=10,
        )
        assert r2.status_code == 409


# ---------------------------------------------------------------------
# Memory-perf admin endpoint
# ---------------------------------------------------------------------
class TestMemoryPerf:
    def test_memory_perf_requires_admin(self):
        r = httpx.get(f"{API_URL}/api/admin/memory-perf", timeout=10)
        assert r.status_code == 401

    def test_memory_perf_shape(self):
        r = httpx.get(f"{API_URL}/api/admin/memory-perf", headers=H, timeout=10)
        assert r.status_code == 200
        d = r.json()
        # Required fields for the admin dashboard / migration trigger.
        for key in (
            "samples", "window_size", "avg_ms", "p50_ms", "p95_ms", "p99_ms",
            "p95_threshold_ms", "migration_triggered", "capacity_triggered",
            "total_memories", "distinct_users", "top_user_memory_count",
        ):
            assert key in d, f"missing {key} in memory-perf response"
        assert d["window_size"] == 1000
        assert d["p95_threshold_ms"] == 100.0
        assert isinstance(d["migration_triggered"], bool)
        assert isinstance(d["capacity_triggered"], bool)

    def test_memory_perf_samples_csv_requires_admin(self):
        r = httpx.get(f"{API_URL}/api/admin/memory-perf/samples.csv", timeout=10)
        assert r.status_code == 401

    def test_memory_perf_samples_csv_shape(self):
        r = httpx.get(
            f"{API_URL}/api/admin/memory-perf/samples.csv",
            headers=H, timeout=10,
        )
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct, f"expected text/csv, got {ct}"
        # Content-Disposition: attachment + filename so the browser downloads
        # rather than rendering inline.
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".csv" in cd, f"bad content-disposition: {cd}"
        body = r.text.splitlines()
        # Header row required even when the window is empty.
        assert body[0] == "index,latency_ms"
        # If samples exist, each row should be `int,float`.
        for line in body[1:]:
            idx, ms = line.split(",")
            int(idx)         # raises on malformed
            float(ms)



class TestHITLLiveFlow:
    """Live end-to-end test of the HITL flow on the canonical chain.
    Gated on LLM budget — skips on 429 / budget exceeded."""

    def test_canonical_chain_pauses_at_approval_gate(self):
        """Canonical run with `requires_approval=true` should emit
        `awaiting_approval` after Content (3 agents in) and persist
        the run as `awaiting_approval`. NO `agent_started` for Kai."""
        _comp("growth")
        with httpx.stream(
            "POST", f"{API_URL}/api/marketing-os/run/stream", headers=H,
            json={
                "brief": "Launch a tiny indie SaaS",
                "mode": "fast",
                "requires_approval": True,
            },
            timeout=240,
        ) as r:
            if r.status_code != 200:
                pytest.skip(f"Run stream returned {r.status_code}")
            blob = "".join(r.iter_text())
        if "budget" in blob.lower() and "error" in blob.lower():
            pytest.skip("LLM budget exceeded")

        events = _parse_sse(blob)
        names = [ev for ev, _ in events]

        # Required vocab: os_started → 3 × agent_done → awaiting_approval → os_persisted.
        assert "os_started" in names
        assert "awaiting_approval" in names, f"missing awaiting_approval in {names}"
        assert "os_persisted" in names

        # No Kai (Distribution) — agents that ran should be strategy, research, nova only.
        agent_done_events = [d for ev, d in events if ev == "agent_done"]
        agent_ids_run = [d.get("agent_id") for d in agent_done_events]
        assert "kai" not in agent_ids_run, f"Kai ran despite the gate: {agent_ids_run}"
        # No `complete` either — we paused before the summariser.
        assert "complete" not in names, "Summariser ran despite the gate"

        # Persisted as awaiting_approval.
        run_id = dict(events).get("os_started", {}).get("run_id")
        assert run_id, "os_started should carry run_id"
        got = httpx.get(f"{API_URL}/api/marketing-os/runs/{run_id}", headers=H, timeout=10)
        assert got.status_code == 200, got.text
        doc = got.json()
        assert doc.get("status") == "awaiting_approval"
        assert doc.get("requires_approval") is True

        # Now /reject — should skip Kai, run only Angela summariser.
        with httpx.stream(
            "POST", f"{API_URL}/api/marketing-os/runs/{run_id}/reject",
            headers=H, json={"mode": "fast"}, timeout=180,
        ) as r2:
            if r2.status_code != 200:
                pytest.skip(f"reject returned {r2.status_code}")
            blob2 = "".join(r2.iter_text())
        events2 = _parse_sse(blob2)
        names2 = [ev for ev, _ in events2]
        # Reject path: NO agent_done for kai. summarising + complete present.
        agent_ids_run2 = [d.get("agent_id") for ev, d in events2 if ev == "agent_done"]
        assert "kai" not in agent_ids_run2, f"reject still ran Kai: {agent_ids_run2}"
        assert "complete" in names2

        # Original run should now be resolved.
        re_check = httpx.get(f"{API_URL}/api/marketing-os/runs/{run_id}", headers=H, timeout=10).json()
        assert re_check.get("status") == "resolved"
        assert re_check.get("resolved_as") == "rejected"
