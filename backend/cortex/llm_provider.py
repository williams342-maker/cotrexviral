"""Cortex LLM provider abstraction.

Goal: Cortex's orchestration code must NEVER be coupled to a single
model. The same call site can target Claude Sonnet 4.5 (primary) or
GPT-5.2 (fallback) — swappable via a single config flag, with auto
failover when the primary errors out.

Public API:
    await cortex_chat(system, user, *, session_id, user_id,
                       prefer="claude", json_mode=False) -> str

Both providers go through emergentintegrations.LlmChat using the
EMERGENT_LLM_KEY universal key. Usage attributes to the `cortex`
agent_id via routes.ai.send_with_usage so token spend rolls up the
admin LLM-spend dashboard.
"""
from __future__ import annotations

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


# ----------------------------------------------------------------- diag
def active_chain(prefer: str = "claude") -> list[dict]:
    """Diagnostic — used by admin /api/cortex/memory/health to show
    which providers will be tried, in order."""
    return [
        {"label": label, "provider": p, "model": m}
        for (label, p, m) in _resolve(prefer)
    ]
