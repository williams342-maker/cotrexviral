"""Iter19 backend tests — LLM-augmented detector + a11y polish.

Validates:
- `_llm_rules` returns empty when snapshot signal is too thin.
- `_llm_rules` respects rate-limit (no second call within window).
- `_parse_llm_findings` is robust against fences, prose, malformed JSON.
- `run_for_user` folds LLM findings in only when heuristics are silent
  and stamps `source='llm_augmented'` on the persisted doc.
- `run_for_user` keeps `source='heuristic'` when heuristics fire (LLM
  call is skipped — saves cost).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest

os.environ.setdefault("CORTEX_LLM_DETECTOR_ENABLED", "true")

from cortex import optimization_loop as ol  # noqa: E402


def _run(coro):
    """Run an async coroutine reusing a single event loop so motor's
    cached loop binding stays valid across tests. Creates a new loop
    if the current one is missing/closed."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# --- _parse_llm_findings: robust parsing ----------------------------
class TestParseLlmFindings:
    def test_strict_json(self):
        text = '{"findings":[{"kind":"capacity_overload","bottleneck":"too many missions","hypothesis":"split focus","recommendation":"pause 2 missions","confidence":0.8}]}'
        out = ol._parse_llm_findings(text, set())
        assert len(out) == 1
        assert out[0]["kind"] == "llm_capacity_overload"   # auto-prefixed
        assert 0 <= out[0]["confidence"] <= 1

    def test_strips_code_fence(self):
        text = '```json\n{"findings":[{"kind":"llm_x","bottleneck":"b","hypothesis":"h","recommendation":"r","confidence":0.5}]}\n```'
        out = ol._parse_llm_findings(text, set())
        assert len(out) == 1 and out[0]["kind"] == "llm_x"

    def test_extracts_json_from_prose(self):
        text = 'Sure! Here is my analysis: {"findings":[{"kind":"llm_y","bottleneck":"b","hypothesis":"","recommendation":"r","confidence":0.3}]} let me know'
        out = ol._parse_llm_findings(text, set())
        assert len(out) == 1 and out[0]["kind"] == "llm_y"

    def test_empty_findings(self):
        assert ol._parse_llm_findings('{"findings":[]}', set()) == []

    def test_invalid_json(self):
        assert ol._parse_llm_findings("not json at all", set()) == []
        assert ol._parse_llm_findings("", set()) == []

    def test_skips_duplicate_kinds(self):
        text = '{"findings":[{"kind":"discovery_stall","bottleneck":"b","hypothesis":"h","recommendation":"r","confidence":0.9}]}'
        out = ol._parse_llm_findings(text, already_detected_kinds={"discovery_stall"})
        assert out == []  # already covered by deterministic rules

    def test_skips_missing_required_fields(self):
        text = '{"findings":[{"kind":"x","bottleneck":"","recommendation":""}]}'
        assert ol._parse_llm_findings(text, set()) == []

    def test_clamps_confidence(self):
        text = '{"findings":[{"kind":"z","bottleneck":"b","hypothesis":"h","recommendation":"r","confidence":5.0}]}'
        out = ol._parse_llm_findings(text, set())
        assert out and out[0]["confidence"] == 1.0


# --- _llm_rules: rate-limit + thin-signal guard ---------------------
class TestLlmRulesGuards:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro) \
            if not asyncio.get_event_loop().is_running() else _run(coro)

    def test_skips_on_thin_signal(self):
        snap = {"funnel_total": 0, "outreach_24h": {"sent": 0}, "missions": {"running": 0}}
        out = _run(ol._llm_rules(snap, user_id="u-empty", already_detected_kinds=set()))
        assert out == []  # no signal → no LLM call

    def test_disabled_flag(self):
        snap = {"funnel_total": 50, "outreach_24h": {"sent": 30}, "missions": {"running": 2}}
        with patch.object(ol, "_LLM_DETECTOR_ENABLED", False):
            out = _run(ol._llm_rules(snap, user_id="u-disabled",
                                              already_detected_kinds=set()))
        assert out == []

    def test_rate_limit_blocks_within_window(self):
        """Recent llm_augmented finding in DB → next call must short-circuit and
        skip the LLM call entirely (cost guard)."""
        uid = "u-ratelimit"
        snap = {"funnel_total": 50, "outreach_24h": {"sent": 30},
                "missions": {"running": 2}}
        mock_chat = AsyncMock(return_value=('{"findings":[]}', "claude"))

        # Simulate a recent prior llm_augmented finding in DB.
        mock_log = AsyncMock()
        mock_log.find_one = AsyncMock(return_value={"id": "prior"})
        mock_db = type("MockDb", (), {"cortex_optimization_log": mock_log})

        async def _go():
            with patch("core.db", mock_db), \
                 patch("cortex.llm_provider.cortex_chat", new=mock_chat):
                return await ol._llm_rules(snap, user_id=uid,
                                             already_detected_kinds=set())
        out = _run(_go())
        assert out == []
        mock_chat.assert_not_called()
        mock_log.find_one.assert_awaited_once()

    def test_calls_llm_with_real_signal(self):
        """When signal is present and no rate-limit hit, LLM is invoked
        and its findings are returned + tagged."""
        uid = "u-real"
        snap = {"funnel_total": 30, "outreach_24h": {"sent": 30},
                "missions": {"running": 2}, "open_rate": 0.18, "reply_rate": 0.02}
        # cortex_tool_call returns (args_dict, label, mode)
        tool_args = {"findings": [{
            "kind": "capacity_overload",
            "bottleneck": "running missions split focus",
            "hypothesis": "too many parallel campaigns dilute attention",
            "recommendation": "pause 1 mission to focus",
            "confidence": 0.7,
        }]}
        mock_tc = AsyncMock(return_value=(tool_args, "claude", "tool_call"))
        mock_log = AsyncMock()
        mock_log.find_one = AsyncMock(return_value=None)   # no prior LLM call
        mock_db = type("MockDb", (), {"cortex_optimization_log": mock_log})

        async def _go():
            with patch("core.db", mock_db), \
                 patch("cortex.llm_provider.cortex_tool_call", new=mock_tc):
                return await ol._llm_rules(snap, user_id=uid,
                                             already_detected_kinds=set())
        out = _run(_go())
        assert len(out) == 1
        assert out[0]["source"] == "llm_augmented"
        assert out[0]["kind"].startswith("llm_")
        assert out[0]["bottleneck"]
        mock_tc.assert_awaited_once()


# --- run_for_user: end-to-end source tagging -------------------------
class TestRunForUserSourceTagging:
    def test_heuristic_wins_when_rule_fires(self):
        """If a deterministic rule fires, LLM is NOT called and source='heuristic'."""
        uid = "u-heur"
        async def _patched_observe(_user_id):
            return {
                "user_id": uid, "funnel": {}, "funnel_total": 0,
                "missions": {"running": 1, "paused": 0},
                "outreach_24h": {"sent": 0, "opened": 0, "replied": 0},
                "open_rate": None, "reply_rate": None, "autonomy_level": 2,
            }
        mock_chat = AsyncMock(return_value=('{"findings":[]}', "claude"))
        mock_log = AsyncMock()
        mock_log.find_one = AsyncMock(return_value=None)
        mock_log.insert_one = AsyncMock(return_value=None)
        mock_db = type("MockDb", (), {"cortex_optimization_log": mock_log})

        async def _go():
            with patch.object(ol, "_observe", new=_patched_observe), \
                 patch.object(ol, "_measure_prior", new=AsyncMock()), \
                 patch("core.db", mock_db), \
                 patch("cortex.llm_provider.cortex_chat", new=mock_chat):
                return await ol.run_for_user(uid)
        doc = _run(_go())
        assert doc is not None
        assert doc["source"] == "heuristic"
        assert doc["kind"] == "discovery_stall"
        mock_chat.assert_not_called()

    def test_llm_augments_when_rules_silent(self):
        """If no deterministic rule fires, LLM is called and source='llm_augmented'."""
        uid = "u-llm"
        async def _patched_observe(_user_id):
            return {
                "user_id": uid,
                "funnel": {"discovered": 5, "qualified": 4},
                "funnel_total": 9,
                "missions": {"running": 1, "paused": 0},
                "outreach_24h": {"sent": 5, "opened": 2, "replied": 1},
                "open_rate": 0.4, "reply_rate": 0.2,
                "autonomy_level": 2,
            }
        tool_args = {"findings": [{
            "kind": "slow_velocity",
            "bottleneck": "funnel velocity decaying",
            "hypothesis": "top-of-funnel volume too low",
            "recommendation": "increase Scout activity",
            "confidence": 0.65,
        }]}
        mock_tc = AsyncMock(return_value=(tool_args, "claude", "tool_call"))
        mock_log = AsyncMock()
        mock_log.find_one = AsyncMock(return_value=None)
        mock_log.insert_one = AsyncMock(return_value=None)
        mock_db = type("MockDb", (), {"cortex_optimization_log": mock_log})

        async def _go():
            with patch.object(ol, "_observe", new=_patched_observe), \
                 patch.object(ol, "_measure_prior", new=AsyncMock()), \
                 patch("core.db", mock_db), \
                 patch("cortex.llm_provider.cortex_tool_call", new=mock_tc):
                return await ol.run_for_user(uid)
        doc = _run(_go())
        assert doc is not None
        assert doc["source"] == "llm_augmented"
        assert doc["kind"].startswith("llm_")
        mock_tc.assert_awaited_once()
