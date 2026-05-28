"""Tests for token-accurate cost tracking and Compose URL-param plumbing."""
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
        headers=H, json={"plan": plan, "comped": True, "reason": "token cost test"},
        timeout=10,
    )


# ----------------------------------------------------------------------
# Token-accurate cost computation (pure unit tests, no network)
# ----------------------------------------------------------------------
class TestExactCost:
    def test_known_model_uses_per_mtok_rates(self):
        from routes.llm_spend import _exact_cost
        # Sonnet: $3/M input, $15/M output. 1500 in + 500 out =
        # 0.0015 * 3 + 0.0005 * 15 = 0.0045 + 0.0075 = 0.0120
        c = _exact_cost("claude-sonnet-4-5", 1500, 500)
        assert abs(c - 0.012) < 1e-6, c

    def test_opus_is_pricier_than_sonnet_is_pricier_than_haiku(self):
        """Strict ordering at identical token counts."""
        from routes.llm_spend import _exact_cost
        in_t, out_t = 1000, 500
        opus = _exact_cost("claude-opus-4-7", in_t, out_t)
        sonnet = _exact_cost("claude-sonnet-4-5", in_t, out_t)
        haiku = _exact_cost("claude-haiku-4-5-20251001", in_t, out_t)
        assert opus > sonnet > haiku > 0

    def test_zero_tokens_returns_zero(self):
        from routes.llm_spend import _exact_cost
        assert _exact_cost("claude-opus-4-7", 0, 0) == 0.0

    def test_unknown_model_returns_zero(self):
        """Unknown models intentionally return 0 from the EXACT path —
        the caller (record_llm_call) falls back to the per-call average
        for those instead."""
        from routes.llm_spend import _exact_cost
        assert _exact_cost("nonexistent-llm", 1000, 500) == 0.0

    def test_prefix_match_picks_up_minor_versions(self):
        """Future minor versions (`claude-sonnet-4-6-future`) should
        inherit the family rate via prefix match."""
        from routes.llm_spend import _exact_cost, _per_mtok_for
        # Same rates as claude-sonnet
        assert _per_mtok_for("claude-sonnet-4-6-future") == _per_mtok_for("claude-sonnet")
        a = _exact_cost("claude-sonnet-4-5", 1000, 500)
        b = _exact_cost("claude-sonnet-4-6-future", 1000, 500)
        assert abs(a - b) < 1e-9


# ----------------------------------------------------------------------
# record_llm_call with usage data
# ----------------------------------------------------------------------
class TestRecordWithUsage:
    def _coll(self):
        from pymongo import MongoClient
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        return MongoClient(mongo_url)[db_name].llm_usage

    def test_writes_tokens_and_exact_cost(self):
        """When usage dict is passed, the row stores prompt/completion/total
        token counts AND `cost_source: tokens`."""
        import asyncio
        from routes.llm_spend import record_llm_call

        coll = self._coll()
        coll.delete_many({"user_id": USER_ID, "model": "claude-sonnet-4-5-test"})
        try:
            asyncio.new_event_loop().run_until_complete(
                record_llm_call(
                    USER_ID, "nova", "creative", "claude-sonnet-4-5-test",
                    {"prompt_tokens": 1500, "completion_tokens": 500, "total_tokens": 2000},
                )
            )
            row = coll.find_one({"user_id": USER_ID, "model": "claude-sonnet-4-5-test"})
            assert row is not None
            assert row["prompt_tokens"] == 1500
            assert row["completion_tokens"] == 500
            assert row["total_tokens"] == 2000
            assert row["cost_source"] == "tokens"
            # Sonnet pricing: 1500/M * $3 + 500/M * $15 = $0.012
            assert abs(row["cost"] - 0.012) < 1e-6
        finally:
            coll.delete_many({"user_id": USER_ID, "model": "claude-sonnet-4-5-test"})

    def test_falls_back_to_per_call_when_no_usage(self):
        """No usage dict (or zero tokens) → falls back to the per-call
        average, with `cost_source: per_call_estimate`."""
        import asyncio
        from routes.llm_spend import record_llm_call, _cost_for

        coll = self._coll()
        coll.delete_many({"user_id": USER_ID, "model": "claude-opus-4-7-test"})
        try:
            asyncio.new_event_loop().run_until_complete(
                record_llm_call(USER_ID, "strategy", "deep", "claude-opus-4-7-test")
            )
            row = coll.find_one({"user_id": USER_ID, "model": "claude-opus-4-7-test"})
            assert row["cost_source"] == "per_call_estimate"
            assert row["cost"] == _cost_for("claude-opus-4-7-test")
            assert row["prompt_tokens"] == 0
            assert row["completion_tokens"] == 0
        finally:
            coll.delete_many({"user_id": USER_ID, "model": "claude-opus-4-7-test"})


# ----------------------------------------------------------------------
# send_with_usage helper
# ----------------------------------------------------------------------
class TestSendWithUsage:
    def test_returns_text_and_real_usage(self):
        """End-to-end LLM round-trip — confirms LiteLLM surfaces non-zero
        token counts via `response.usage` and our helper passes them
        through correctly."""
        import asyncio
        from routes.ai import send_with_usage, _llm
        from emergentintegrations.llm.chat import UserMessage

        async def go():
            chat = _llm("token-probe", "Reply OK only.", model="claude-haiku-4-5-20251001", provider="anthropic")
            return await send_with_usage(chat, UserMessage(text="Say OK."))

        try:
            text, usage = asyncio.new_event_loop().run_until_complete(go())
        except Exception as e:
            if "budget" in str(e).lower():
                import pytest
                pytest.skip("Emergent LLM key budget exceeded")
            raise
        assert isinstance(text, str) and len(text) > 0
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


# ----------------------------------------------------------------------
# End-to-end: agent_chat populates token data on the spend row
# ----------------------------------------------------------------------
class TestAgentChatTokenAccountingE2E:
    def _coll(self):
        from pymongo import MongoClient
        mongo_url = open("/app/backend/.env").read().split("MONGO_URL=")[1].split("\n")[0].strip().strip("'\"")
        db_name = open("/app/backend/.env").read().split("DB_NAME=")[1].split("\n")[0].strip().strip("'\"")
        return MongoClient(mongo_url)[db_name].llm_usage

    def test_chat_persists_actual_tokens(self):
        """Live agent_chat with `mode=fast` (Haiku) — the resulting
        llm_usage row must have real (non-zero) token counts and a
        token-accurate cost, not the per-call fallback."""
        _comp("growth")
        coll = self._coll()
        # Snapshot the latest row count before the call.
        before_marker = coll.find_one({"user_id": USER_ID}, sort=[("ts", -1)])
        before_ts = before_marker.get("ts") if before_marker else None

        r = httpx.post(
            f"{API_URL}/api/ai/agent/chat", headers=H,
            json={"agent_id": "kai", "message": "Reply OK only.", "mode": "fast"},
            timeout=90,
        )
        if r.status_code in (500, 502, 503) and "budget" in r.text.lower():
            import pytest
            pytest.skip("Emergent LLM key budget exceeded")
        assert r.status_code == 200, r.text

        # The most recent row should be ours.
        q = {"user_id": USER_ID, "agent_id": "kai"}
        if before_ts:
            q["ts"] = {"$gt": before_ts}
        row = coll.find_one(q, sort=[("ts", -1)])
        assert row is not None, "No llm_usage row produced by agent_chat"
        # Tokens captured from the real LLM response.
        assert row.get("prompt_tokens", 0) > 0
        assert row.get("completion_tokens", 0) > 0
        assert row.get("cost_source") == "tokens"
        # Cost should match the exact per-token calculation, not a flat
        # per-call estimate. For Haiku ($1/M in, $5/M out), a "say OK" turn
        # is on the order of $0.0001-$0.0005 — i.e. cheaper than the
        # $0.0012 per-call fallback. Assert it's strictly under that cap.
        assert row["cost"] < 0.0012, f"cost {row['cost']} suggests we fell back to per-call"


# ----------------------------------------------------------------------
# Admin spend dashboard surfaces token totals
# ----------------------------------------------------------------------
class TestSpendEndpointSurfacesTokens:
    def test_total_tokens_present(self):
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=30", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "total_tokens" in body
        tt = body["total_tokens"]
        assert {"prompt", "completion", "total"} <= set(tt.keys())
        for k in ("prompt", "completion", "total"):
            assert isinstance(tt[k], int)
            assert tt[k] >= 0

    def test_by_mode_rows_include_tokens(self):
        r = httpx.get(f"{API_URL}/api/admin/llm-spend?days=30", headers=H, timeout=10)
        body = r.json()
        for row in body.get("by_mode", []):
            assert "tokens" in row and isinstance(row["tokens"], int) and row["tokens"] >= 0
        for row in body.get("by_model", []):
            assert "tokens" in row
