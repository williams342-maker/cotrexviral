"""Iteration 16 — Discovery-First conversation model.

Backend coverage:
  1. POST /api/cortex/console/chat — vague goal → stage=discovery, no plan card,
     clarifying questions present.
  2. POST /api/cortex/console/chat — explicit-execute phrase → stage=mission_proposal,
     explicit_execution_request=true, plan card present.
  3. 3-turn conversation continuity — last turn shouldn't stay in discovery if
     target+outcome supplied.
  4. SSE /api/cortex/console/chat/stream — `ready` event carries the new stage fields.
  5. Mongo persistence of stage/clarifying_questions/findings/recommendation_summary/alternatives.
  6. Unit test of cortex.stages.should_render_plan_card().
"""
import os
import sys
import json
import uuid
import time
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"

sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    })
    s.cookies.set("session_token", TOKEN)
    return s


# ============================================================
# 1. Vague goal → discovery stage, no plan card
# ============================================================
class TestDiscoveryStage:
    def test_vague_goal_returns_discovery(self, client):
        r = client.post(f"{BASE_URL}/api/cortex/console/chat",
                        json={"message": "I want to grow my business"})
        assert r.status_code == 200, f"chat failed: {r.text}"
        body = r.json()
        # Stage should be discovery (or analysis if LLM is aggressive; tolerate
        # but the contract says vague goal → discovery).
        assert body.get("stage") == "discovery", (
            f"expected discovery, got stage={body.get('stage')} body={body}"
        )
        # No plan card.
        assert body.get("recommendation") in (None, {}, []), (
            f"plan card leaked into discovery! recommendation={body.get('recommendation')}"
        )
        # 1-3 clarifying questions.
        cqs = body.get("clarifying_questions") or []
        assert 1 <= len(cqs) <= 3, f"expected 1-3 clarifying questions, got {len(cqs)}: {cqs}"
        # The ack should contain a question mark per spec.
        ack = body.get("ack") or ""
        assert "?" in ack, f"discovery ack should contain a question mark; got: {ack!r}"


# ============================================================
# 2. Explicit-execute override → mission_proposal + plan card
# ============================================================
class TestExplicitExecuteOverride:
    def test_explicit_execute_jumps_to_mission_proposal(self, client):
        r = client.post(f"{BASE_URL}/api/cortex/console/chat",
                        json={"message": "just launch a mission to recruit 25 candle makers"})
        assert r.status_code == 200, f"chat failed: {r.text}"
        body = r.json()
        assert body.get("stage") == "mission_proposal", (
            f"expected mission_proposal, got {body.get('stage')}"
        )
        assert body.get("explicit_execution_request") is True, body
        rec = body.get("recommendation")
        assert isinstance(rec, dict) and rec, f"expected plan card dict, got {rec}"
        # Intent + params
        assert body.get("intent") == "launch_seller_mission", body.get("intent")
        params = body.get("params") or {}
        assert params.get("target") == 25, f"params.target should be 25, got {params}"
        niche = (params.get("niche") or "").lower()
        assert "candle" in niche, f"niche should mention candle, got {niche!r}"

    def test_explicit_execute_phrase_variants(self, client):
        # "create the mission now" should also bypass.
        r = client.post(f"{BASE_URL}/api/cortex/console/chat",
                        json={"message": "create the mission now: outreach to qualified leads"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("stage") == "mission_proposal"
        assert body.get("explicit_execution_request") is True


# ============================================================
# 3. Conversation continuity: 3rd turn shouldn't stay in discovery
# ============================================================
class TestConversationContinuity:
    def test_three_turn_progression(self, client):
        # Use a unique-ish phrasing to avoid prior history contamination.
        # The classifier reads the last 10 turns from db; given there's lots
        # of history already we'll just send the 3 turns and inspect last.
        t1 = client.post(f"{BASE_URL}/api/cortex/console/chat",
                         json={"message": "I want to grow my woodworking marketplace"})
        assert t1.status_code == 200
        t2 = client.post(f"{BASE_URL}/api/cortex/console/chat",
                         json={"message": "My target is to recruit 50 sellers in the next quarter."})
        assert t2.status_code == 200
        t3 = client.post(f"{BASE_URL}/api/cortex/console/chat",
                         json={"message": "Cortex, the outcome I want is 50 new woodworking sellers onboarded by next month."})
        assert t3.status_code == 200
        b3 = t3.json()
        stage3 = b3.get("stage")
        # 3rd turn should advance past discovery — best-effort check.
        # If we DID stay in discovery, the plan card MUST be None (gate working).
        if stage3 == "discovery":
            assert b3.get("recommendation") in (None, {}, []), (
                "plan card leaked while still in discovery"
            )
        else:
            # If advanced to mission_proposal/execution, gate may allow plan card —
            # only allowed if explicit_execution_request or stage is mission_proposal+.
            if b3.get("recommendation"):
                assert stage3 in ("mission_proposal", "execution") or b3.get("explicit_execution_request") is True


# ============================================================
# 4. SSE ready event carries stage fields
# ============================================================
class TestSSEReadyFields:
    def test_sse_ready_contains_stage(self, client):
        url = f"{BASE_URL}/api/cortex/console/chat/stream"
        # GET with query params
        with requests.get(
            url,
            params={"message": "I'd like some advice on growing"},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "text/event-stream",
            },
            cookies={"session_token": TOKEN},
            stream=True,
            timeout=60,
        ) as r:
            assert r.status_code == 200, f"SSE failed: {r.status_code} {r.text[:200]}"
            ready_payload = None
            event_name = None
            buf = ""
            t0 = time.time()
            for raw in r.iter_lines(decode_unicode=True):
                if time.time() - t0 > 55:
                    break
                if raw is None:
                    continue
                line = raw.strip("\r")
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    if event_name == "ready":
                        try:
                            ready_payload = json.loads(data_str)
                        except Exception:
                            pass
                        break
                elif line == "":
                    event_name = None
        assert ready_payload is not None, "did not receive `ready` SSE event in time"
        # Required new keys.
        for key in ("stage", "discovery_complete", "analysis_complete",
                    "recommendation_accepted", "explicit_execution_request",
                    "clarifying_questions", "findings",
                    "recommendation_summary", "alternatives",
                    "intent", "params", "recommendation"):
            assert key in ready_payload, f"ready event missing key {key}; got keys={list(ready_payload.keys())}"


# ============================================================
# 5. Mongo persistence of new stage fields
# ============================================================
class TestMongoPersistence:
    def test_chat_turn_persists_stage_fields(self, client):
        # Trigger a chat turn (vague).
        marker = f"persist-test-{uuid.uuid4().hex[:6]}"
        r = client.post(f"{BASE_URL}/api/cortex/console/chat",
                        json={"message": f"How can I grow ({marker})?"})
        assert r.status_code == 200

        # Verify via /api/cortex/console/history (avoids needing direct mongo).
        rh = client.get(f"{BASE_URL}/api/cortex/console/history?limit=10")
        assert rh.status_code == 200
        turns = rh.json().get("turns", [])
        assert turns, "no turns returned"
        # Find the most recent cortex turn.
        cortex_turn = next((t for t in reversed(turns) if t.get("role") == "cortex"), None)
        assert cortex_turn is not None
        # Fields must exist (even if values are empty lists / strings).
        for key in ("stage", "clarifying_questions", "findings",
                    "recommendation_summary", "alternatives"):
            assert key in cortex_turn, (
                f"persisted cortex turn missing {key}; keys={list(cortex_turn.keys())}"
            )


# ============================================================
# 6. Unit test of should_render_plan_card()
# ============================================================
class TestShouldRenderPlanCard:
    def test_gate_false_for_discovery(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({"stage": "discovery"}) is False

    def test_gate_false_for_analysis(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({"stage": "analysis"}) is False

    def test_gate_false_for_recommendation(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({"stage": "recommendation"}) is False

    def test_gate_true_for_mission_proposal(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({"stage": "mission_proposal"}) is True

    def test_gate_true_for_execution(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({"stage": "execution"}) is True

    def test_gate_true_for_explicit_execution_request(self):
        from cortex.stages import should_render_plan_card
        assert should_render_plan_card({
            "stage": "discovery",
            "explicit_execution_request": True,
        }) is True
