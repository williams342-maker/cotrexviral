"""Iter20 — native LLM tool-calling wrapper (`cortex_tool_call`).

Validates:
- Native tool-call path: `_extract_tool_args` correctly pulls JSON
  arguments from a LiteLLM-shaped ModelResponse.
- JSON fallback path: when no tool_calls returned, wrapper falls back
  to cortex_chat(json_mode=True) and parses successfully.
- Hard-failure path: both native + fallback fail → returns (None, ..., "hard_fail").
- Stats counters increment correctly across paths.
- `required` parameter validation rejects incomplete args.
- _safe_parse_json handles fences / prose-wrapped JSON / invalid input.
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest

sys.path.insert(0, "/app/backend")

# Reset the stats counters before each test so assertions are clean.
from cortex import llm_provider  # noqa: E402


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset_stats():
    for k in llm_provider._TOOL_CALL_STATS:
        llm_provider._TOOL_CALL_STATS[k] = 0
    yield


# Helpers to build mock LiteLLM responses.
def _make_tool_call_response(name: str, args_json: str, usage_tokens: int = 100):
    fn = SimpleNamespace(name=name, arguments=args_json)
    tc = SimpleNamespace(function=fn)
    msg = SimpleNamespace(content=None, tool_calls=[tc])
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=50, completion_tokens=50,
                              total_tokens=usage_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_empty_response():
    msg = SimpleNamespace(content="some text", tool_calls=None)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice], usage=None)


# --- _extract_tool_args ---------------------------------------------
class TestExtractToolArgs:
    def test_parses_well_formed_args(self):
        r = _make_tool_call_response("classify", '{"intent":"launch","x":1}')
        out = llm_provider._extract_tool_args(r, "classify")
        assert out == {"intent": "launch", "x": 1}

    def test_rejects_other_tool_name(self):
        r = _make_tool_call_response("other_tool", '{"foo":1}')
        assert llm_provider._extract_tool_args(r, "classify") is None

    def test_handles_dict_arguments(self):
        # Some providers return args as dict directly, not stringified.
        fn = SimpleNamespace(name="x", arguments={"y": 2})
        tc = SimpleNamespace(function=fn)
        msg = SimpleNamespace(content=None, tool_calls=[tc])
        r = SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)
        assert llm_provider._extract_tool_args(r, "x") == {"y": 2}

    def test_extracts_json_from_messy_args(self):
        r = _make_tool_call_response("classify", 'prose before {"intent":"x"} prose after')
        out = llm_provider._extract_tool_args(r, "classify")
        assert out == {"intent": "x"}

    def test_returns_none_for_no_tool_calls(self):
        assert llm_provider._extract_tool_args(_make_empty_response(), "classify") is None


# --- _safe_parse_json -----------------------------------------------
class TestSafeParseJson:
    def test_strict_json(self):
        assert llm_provider._safe_parse_json('{"a":1}') == {"a": 1}

    def test_strips_fences(self):
        assert llm_provider._safe_parse_json('```json\n{"a":1}\n```') == {"a": 1}

    def test_extracts_from_prose(self):
        assert llm_provider._safe_parse_json('here is {"a":1} ok') == {"a": 1}

    def test_invalid(self):
        assert llm_provider._safe_parse_json("not json") is None
        assert llm_provider._safe_parse_json("") is None


# --- cortex_tool_call: native path ----------------------------------
class TestCortexToolCallNative:
    def test_native_path_success(self):
        """Native tool-call returns args, stats tick correctly."""
        os.environ["EMERGENT_LLM_KEY"] = "sk-test-fake"

        tool = {
            "name": "classify",
            "description": "Classify intent",
            "parameters": {"type": "object",
                            "properties": {"intent": {"type": "string"}},
                            "required": ["intent"]},
        }

        async def _mock_completion(self, messages):  # bound to LlmChat
            return _make_tool_call_response("classify", '{"intent":"launch_seller_mission","ack":"ok"}')

        with patch("emergentintegrations.llm.chat.LlmChat._execute_completion",
                    new=_mock_completion), \
             patch("emergentintegrations.llm.chat.LlmChat._add_user_message",
                    new=AsyncMock(return_value=None)), \
             patch("core.EMERGENT_LLM_KEY", "sk-test-fake"):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="recruit 50",
                tool=tool, user_id="u1",
                required=["intent"],
            ))
        assert mode == "tool_call"
        assert args == {"intent": "launch_seller_mission", "ack": "ok"}
        assert label in ("claude", "gpt")
        s = llm_provider._tool_call_stats()
        assert s["attempts"] == 1
        assert s["tool_call_ok"] == 1
        assert s["tool_call_rate"] == 1.0


# --- cortex_tool_call: fallback path --------------------------------
class TestCortexToolCallFallback:
    def test_falls_back_when_no_tool_calls_from_any_provider(self):
        """No tool_calls in response → falls back to cortex_chat(json_mode=True)."""
        async def _empty_completion(self, messages):
            return _make_empty_response()

        async def _mock_chat(system, user_text, *, session_id=None,
                              user_id="x", prefer="claude", json_mode=False):
            return '{"intent":"explain","ack":"explained"}', "claude"

        tool = {
            "name": "classify",
            "description": "Classify intent",
            "parameters": {"type": "object",
                            "properties": {"intent": {"type": "string"},
                                           "ack": {"type": "string"}},
                            "required": ["intent"]},
        }
        with patch("emergentintegrations.llm.chat.LlmChat._execute_completion",
                    new=_empty_completion), \
             patch("emergentintegrations.llm.chat.LlmChat._add_user_message",
                    new=AsyncMock(return_value=None)), \
             patch("core.EMERGENT_LLM_KEY", "sk-test-fake"), \
             patch.object(llm_provider, "cortex_chat", new=_mock_chat):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="explain mission",
                tool=tool, user_id="u2",
                required=["intent"],
            ))
        assert mode == "json_fallback"
        assert args == {"intent": "explain", "ack": "explained"}
        s = llm_provider._tool_call_stats()
        assert s["tool_call_empty"] >= 1
        assert s["json_fallback_ok"] == 1

    def test_hard_fail_when_fallback_also_fails(self):
        async def _empty_completion(self, messages):
            return _make_empty_response()

        async def _broken_chat(*a, **kw):
            raise RuntimeError("provider down")

        tool = {"name": "x", "parameters": {"type": "object"}}
        with patch("emergentintegrations.llm.chat.LlmChat._execute_completion",
                    new=_empty_completion), \
             patch("emergentintegrations.llm.chat.LlmChat._add_user_message",
                    new=AsyncMock(return_value=None)), \
             patch("core.EMERGENT_LLM_KEY", "sk-test-fake"), \
             patch.object(llm_provider, "cortex_chat", new=_broken_chat):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="anything",
                tool=tool, user_id="u3",
            ))
        assert args is None
        assert mode == "hard_fail"
        s = llm_provider._tool_call_stats()
        assert s["hard_fail"] == 1

    def test_required_keys_validated_in_fallback(self):
        """JSON fallback rejects args missing required keys."""
        async def _empty_completion(self, messages):
            return _make_empty_response()

        async def _mock_chat(*a, **kw):
            return '{"ack":"missing intent"}', "claude"

        tool = {"name": "x", "parameters": {"type": "object"}}
        with patch("emergentintegrations.llm.chat.LlmChat._execute_completion",
                    new=_empty_completion), \
             patch("emergentintegrations.llm.chat.LlmChat._add_user_message",
                    new=AsyncMock(return_value=None)), \
             patch("core.EMERGENT_LLM_KEY", "sk-test-fake"), \
             patch.object(llm_provider, "cortex_chat", new=_mock_chat):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="x",
                tool=tool, user_id="u4",
                required=["intent"],
            ))
        assert args is None
        assert mode == "hard_fail"

    def test_required_keys_validated_native(self):
        """Native path rejects args missing required keys, then falls back."""
        async def _incomplete_completion(self, messages):
            return _make_tool_call_response("x", '{"ack":"no intent"}')

        async def _mock_chat(*a, **kw):
            return '{"intent":"foo","ack":"ok"}', "claude"

        tool = {"name": "x", "parameters": {"type": "object"}}
        with patch("emergentintegrations.llm.chat.LlmChat._execute_completion",
                    new=_incomplete_completion), \
             patch("emergentintegrations.llm.chat.LlmChat._add_user_message",
                    new=AsyncMock(return_value=None)), \
             patch("core.EMERGENT_LLM_KEY", "sk-test-fake"), \
             patch.object(llm_provider, "cortex_chat", new=_mock_chat):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="x",
                tool=tool, user_id="u5",
                required=["intent"],
            ))
        # Native rejected (parse fail counter), fallback succeeded.
        assert mode == "json_fallback"
        assert args.get("intent") == "foo"
        s = llm_provider._tool_call_stats()
        assert s["tool_call_parse"] >= 1
        assert s["json_fallback_ok"] == 1


# --- No-key short-circuit --------------------------------------------
class TestNoKey:
    def test_no_key_skips_native_and_falls_back(self):
        async def _mock_chat(*a, **kw):
            return '{"intent":"x","ack":"a"}', "claude"

        tool = {"name": "x", "parameters": {"type": "object"}}
        with patch("core.EMERGENT_LLM_KEY", ""), \
             patch.object(llm_provider, "cortex_chat", new=_mock_chat):
            args, label, mode = _run(llm_provider.cortex_tool_call(
                system="sys", user_text="x",
                tool=tool, user_id="u6",
            ))
        assert mode == "json_fallback"
        assert args == {"intent": "x", "ack": "a"}
