"""Cortex LLM provider abstraction.

Goal: Cortex's orchestration code must NEVER be coupled to a single
model. The same call site can target Claude Sonnet 4.5 (primary) or
GPT-5.2 (fallback) — swappable via a single config flag, with auto
failover when the primary errors out.

Public API:
    await cortex_chat(system, user, *, session_id, user_id,
                       prefer="claude", json_mode=False) -> str

    await cortex_tool_call(system, user, *, tool, session_id, user_id,
                            prefer="claude", required=None) -> (args, label, mode)
        Native LLM tool-calling via LiteLLM under emergentintegrations.
        Falls back to cortex_chat(json_mode=True) when tool-calling fails.

Both providers go through emergentintegrations.LlmChat using the
EMERGENT_LLM_KEY universal key. Usage attributes to the `cortex`
agent_id via routes.ai.send_with_usage so token spend rolls up the
admin LLM-spend dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# Provider preference resolves to (provider_str, model_str) tuples.
# `claude-sonnet-4-5-20250929` honors the user's explicit "Sonnet 4.5"
# request; `gpt-5.2` is the second-stage fallback they specified.
_PROVIDERS: dict[str, Tuple[str, str]] = {
    "claude":   ("anthropic", "claude-sonnet-4-5-20250929"),
    "gpt":      ("openai",    "gpt-5.2"),
    "fast":     ("openai",    "gpt-5.4-mini"),    # cheap classification
}

# Order matters: tried left-to-right on failure.
_FAILOVER_CHAIN = ["claude", "gpt"]


# Observability counters — exposed via cortex/_tool_call_stats() for
# admin dashboards. Reset on process restart (good enough for trend
# visibility; for persistent stats use the usage table downstream).
_TOOL_CALL_STATS = {
    "attempts":         0,
    "tool_call_ok":     0,    # native tool-call succeeded + parsed
    "tool_call_empty":  0,    # provider returned no tool_calls
    "tool_call_parse":  0,    # tool_calls returned but JSON args parse failed
    "json_fallback_ok": 0,    # fallback to cortex_chat(json_mode=True) succeeded
    "hard_fail":        0,    # both paths failed
}


def _tool_call_stats() -> dict:
    """Snapshot of tool-call success rate vs JSON fallback rate. Used
    by admin dashboards / debug endpoints to monitor wrapper stability."""
    s = dict(_TOOL_CALL_STATS)
    s["tool_call_rate"] = (
        s["tool_call_ok"] / s["attempts"] if s["attempts"] else 0.0
    )
    s["fallback_rate"] = (
        s["json_fallback_ok"] / s["attempts"] if s["attempts"] else 0.0
    )
    return s


def _resolve(prefer: str) -> list[Tuple[str, str, str]]:
    """Return ordered [(label, provider, model), ...] chain to try."""
    chain: list[Tuple[str, str, str]] = []
    seen: set[str] = set()
    # User-preferred first, then failover chain (deduped).
    for label in [prefer, *_FAILOVER_CHAIN]:
        if label in _PROVIDERS and label not in seen:
            p, m = _PROVIDERS[label]
            chain.append((label, p, m))
            seen.add(label)
    return chain


async def cortex_chat(
    system: str,
    user_text: str,
    *,
    session_id: Optional[str] = None,
    user_id: str = "anonymous",
    prefer: str = "claude",
    json_mode: bool = False,
) -> Tuple[str, str]:
    """Send a single prompt through the provider chain.

    Returns: (response_text, label_used) — label is "claude", "gpt", etc.
    Raises: RuntimeError if every provider in the chain fails.
    """
    from core import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY missing — Cortex cannot reach any LLM provider")

    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.ai import send_with_usage

    sid = session_id or f"cortex-{user_id}-{uuid.uuid4().hex[:8]}"

    # JSON-mode hardening — prepend instruction to the system prompt
    # so all providers produce valid JSON without prose. emergent's
    # LlmChat doesn't expose response_format on every provider, so we
    # use prompt-level enforcement + post-parse cleanup downstream.
    sys_prompt = system
    if json_mode:
        sys_prompt = (
            system.rstrip()
            + "\n\n---\nReturn STRICT JSON only. No prose. No markdown fences."
        )

    last_err: Optional[Exception] = None
    for label, provider, model in _resolve(prefer):
        try:
            chat = (
                LlmChat(api_key=EMERGENT_LLM_KEY,
                        session_id=sid,
                        system_message=sys_prompt)
                .with_model(provider, model)
            )
            raw, _ = await send_with_usage(
                chat, UserMessage(text=user_text),
                agent_id="cortex", user_id=user_id, model=model,
            )
            text = (raw or "").strip()
            if json_mode:
                text = _strip_code_fence(text)
            return text, label
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("cortex_chat: provider %s failed (%s); trying next", label, e)
            continue

    raise RuntimeError(f"All Cortex LLM providers failed: {last_err}")


def _strip_code_fence(text: str) -> str:
    """Strip ```json ... ``` fences if a model adds them despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?|```\s*$", "", t, flags=re.MULTILINE).strip()
    return t


# ============================================================ tool_call
# Native LLM tool-calling via LiteLLM under emergentintegrations.
#
# WHY THIS EXISTS — emergentintegrations.LlmChat.send_message() returns
# only `message.content` (text) and discards `message.tool_calls` from
# the underlying LiteLLM ModelResponse. To unlock native function-
# calling without losing the Emergent LLM key proxy / spend tracking,
# we forward `tools=[...]` + `tool_choice` through `.with_params(...)`
# (LiteLLM accepts them as extra kwargs) and then call the private
# `_execute_completion()` to capture the raw ModelResponse so we can
# extract `tool_calls` ourselves.
#
# RISK — this depends on `emergentintegrations` internals. If the lib
# refactors `_execute_completion` or `_add_user_message`, the wrapper
# fails closed (graceful fallback to `cortex_chat(json_mode=True)`).
# Risk is isolated to this file by design. Track _TOOL_CALL_STATS to
# decide when to refactor to LiteLLM-direct.
async def cortex_tool_call(
    system: str,
    user_text: str,
    *,
    tool: dict,
    session_id: Optional[str] = None,
    user_id: str = "anonymous",
    prefer: str = "claude",
    required: Optional[list[str]] = None,
) -> Tuple[Optional[dict], str, str]:
    """Send a prompt and force the model to call ONE named tool. Returns
    the parsed args dict from the tool call.

    Args:
        tool: OpenAI-format function schema:
              {"name": str, "description": str, "parameters": <JSON Schema>}
        required: Required keys to verify in the parsed args (validation).

    Returns:
        (args_dict, label, mode)
        mode ∈ {"tool_call", "json_fallback"}.
        args_dict is None only on total hard failure (caller decides
        how to recover — typically a deterministic regex/heuristic).
    """
    _TOOL_CALL_STATS["attempts"] += 1
    from core import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        return await _json_fallback(system, user_text, tool=tool,
                                      session_id=session_id, user_id=user_id,
                                      prefer=prefer, required=required,
                                      reason="no_key")

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    sid = session_id or f"cortex-tool-{user_id}-{uuid.uuid4().hex[:8]}"
    tool_name = tool.get("name") or "extract"
    tools_payload = [{
        "type": "function",
        "function": {
            "name":        tool_name,
            "description": tool.get("description") or "",
            "parameters":  tool.get("parameters") or {"type": "object", "properties": {}},
        },
    }]
    # Force the model to call this exact tool (not optional).
    tool_choice = {"type": "function", "function": {"name": tool_name}}

    last_err: Optional[Exception] = None
    for label, provider, model in _resolve(prefer):
        try:
            chat = (
                LlmChat(api_key=EMERGENT_LLM_KEY,
                        session_id=sid,
                        system_message=system)
                .with_model(provider, model)
                .with_params(tools=tools_payload, tool_choice=tool_choice)
            )
            # Bypass send_message (which extracts only .content). Drive
            # the private completion path to keep tool_calls on the
            # raw response.
            messages = await chat.get_messages()
            await chat._add_user_message(messages, UserMessage(text=user_text))
            response = await chat._execute_completion(messages)

            # Attribute spend best-effort (mirrors send_with_usage tail).
            _attribute_spend(response, user_id=user_id, model=model)

            args = _extract_tool_args(response, tool_name)
            if args is None:
                _TOOL_CALL_STATS["tool_call_empty"] += 1
                # Try the next provider in the chain before falling back.
                continue
            if required and not all(k in args for k in required):
                _TOOL_CALL_STATS["tool_call_parse"] += 1
                logger.warning("cortex_tool_call: missing required keys %s in args=%s",
                                required, list(args.keys()))
                continue
            _TOOL_CALL_STATS["tool_call_ok"] += 1
            logger.info("cortex_tool_call: %s OK via %s (rate=%.2f)",
                         tool_name, label, _tool_call_stats()["tool_call_rate"])
            return args, label, "tool_call"
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("cortex_tool_call: %s via %s failed: %s",
                            tool_name, label, e)
            continue

    # Native path exhausted — fall back to JSON mode.
    return await _json_fallback(system, user_text, tool=tool,
                                  session_id=sid, user_id=user_id,
                                  prefer=prefer, required=required,
                                  reason=f"native_exhausted({last_err})")


def _extract_tool_args(response, tool_name: str) -> Optional[dict]:
    """Pull arguments dict from a LiteLLM ModelResponse's tool_calls.
    Returns None if no matching tool_call or JSON parse fails."""
    try:
        if not response.choices:
            return None
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return None
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if not fn:
                continue
            name = getattr(fn, "name", None)
            args_raw = getattr(fn, "arguments", None)
            if name != tool_name or not args_raw:
                continue
            if isinstance(args_raw, dict):
                return args_raw
            try:
                return json.loads(args_raw)
            except Exception:
                # Some models leak whitespace or trailing prose — try to
                # extract the first balanced {...}.
                m = re.search(r"\{.*\}", str(args_raw), re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        return None
                return None
        return None
    except Exception:
        logger.exception("cortex_tool_call: _extract_tool_args crashed")
        return None


async def _json_fallback(system: str, user_text: str, *, tool: dict,
                          session_id: Optional[str], user_id: str,
                          prefer: str, required: Optional[list[str]],
                          reason: str) -> Tuple[Optional[dict], str, str]:
    """Fallback path — call cortex_chat(json_mode=True) with a schema
    hint inlined into the system prompt, then parse JSON. This is the
    same pattern the codebase used before native tool-calling existed,
    so the wrapper degrades to status quo on library breakage."""
    logger.info("cortex_tool_call: json_fallback engaged (%s)", reason)
    schema = json.dumps(tool.get("parameters") or {}, indent=2)
    system_with_hint = (
        system.rstrip()
        + f"\n\n---\nReturn STRICT JSON matching this schema:\n{schema}\n"
        "No prose, no markdown fences, no extra fields."
    )
    try:
        raw, label = await cortex_chat(
            system_with_hint, user_text,
            session_id=session_id, user_id=user_id,
            prefer=prefer, json_mode=True,
        )
    except Exception as e:  # noqa: BLE001
        _TOOL_CALL_STATS["hard_fail"] += 1
        logger.warning("cortex_tool_call: json_fallback also failed: %s", e)
        return None, "none", "hard_fail"

    args = _safe_parse_json(raw)
    if args is None or not isinstance(args, dict):
        _TOOL_CALL_STATS["hard_fail"] += 1
        return None, label, "hard_fail"
    if required and not all(k in args for k in required):
        _TOOL_CALL_STATS["hard_fail"] += 1
        return None, label, "hard_fail"
    _TOOL_CALL_STATS["json_fallback_ok"] += 1
    return args, label, "json_fallback"


def _safe_parse_json(text: str):
    """Robust JSON parser — strips fences, extracts the first balanced
    {...} when the model wraps with prose."""
    if not text:
        return None
    t = _strip_code_fence(text)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


def _attribute_spend(response, *, user_id: str, model: str) -> None:
    """Mirror routes.ai.send_with_usage's spend-tick tail. Best-effort —
    never blocks or raises. Token counts on the raw ModelResponse roll
    up into the autonomy ledger so `cortex_tool_call` spend is visible
    in admin LLM-spend dashboards alongside `cortex_chat`."""
    try:
        u = getattr(response, "usage", None)
        if not u:
            return
        total = int(getattr(u, "total_tokens", 0) or 0)
        if total <= 0:
            return
        from routes.ai import _estimate_usd
        from routes.autonomy import record_usage
        usd = _estimate_usd(
            model,
            int(getattr(u, "prompt_tokens", 0) or 0),
            int(getattr(u, "completion_tokens", 0) or 0),
        )
        import asyncio
        # record_usage is async — schedule it; we're already in async ctx.
        asyncio.create_task(record_usage("cortex", user_id, tokens=total, usd=usd))
    except Exception:
        logger.debug("cortex_tool_call: spend attribution skipped", exc_info=True)


# ----------------------------------------------------------------- diag
def active_chain(prefer: str = "claude") -> list[dict]:
    """Diagnostic — used by admin /api/cortex/memory/health to show
    which providers will be tried, in order."""
    return [
        {"label": label, "provider": p, "model": m}
        for (label, p, m) in _resolve(prefer)
    ]
