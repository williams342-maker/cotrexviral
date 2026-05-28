"""Model routing layer — picks the right (provider, model) for the task.

Why
----
Different tasks have different optimal cost/latency/quality tradeoffs.
Routing makes this explicit instead of using one model for everything.

Available routes (all through the Emergent LLM key — no extra credentials):
  • "fast"        → claude-haiku-4-5     ~1-2s   short replies, classification, parsing
  • "default"     → gpt-5                ~5-6s   the safe choice when no router taste
  • "creative"    → claude-sonnet-4-5    ~6-8s   long-form writing, hooks, marketing copy
  • "deep"        → claude-opus-4-7      ~10-15s strategy, deep research, multi-step planning
  • "research"    → gemini-2.5-pro       ~5-7s   web-anchored answers, large-context summarisation

Usage:
    from routes.model_router import for_task
    provider, model = for_task("creative")
    chat = await _llm_for_user(user_id, session_id, system,
                               provider=provider, model=model)

We also expose `for_agent(agent_id)` so the per-agent chat picks a sensible
default per persona — Atlas (Strategy) gets "deep", Iris (Research) gets
"research", Sam/Angela/Nova/Kai get "creative" since they ship copy.

User-facing modes
-----------------
For UI surfaces (composer toggle, settings) we expose a smaller, friendlier
set of "modes" that are aliases or pass-throughs of the internal task names.
`USER_MODES` is the single source of truth for what the frontend may send;
`resolve_user_mode("deep")` maps it to a (provider, model) pair.
"""

# Each entry: (provider, model_id) — provider is what `LlmChat.with_model`
# expects. Emergent's proxy accepts these provider strings.
ROUTES: dict[str, tuple[str, str]] = {
    "fast":     ("anthropic", "claude-haiku-4-5-20251001"),
    "default":  ("openai",    "gpt-5"),
    "creative": ("anthropic", "claude-sonnet-4-5"),
    "deep":     ("anthropic", "claude-opus-4-7"),
    "research": ("gemini",    "gemini-2.5-pro"),
}


def for_task(task: str) -> tuple[str, str]:
    """Return (provider, model) for the given task. Unknown tasks fall back
    to `default` so callers never crash on a typo."""
    return ROUTES.get(task, ROUTES["default"])


# Agent → task mapping. The agent module imports this directly.
AGENT_TASKS: dict[str, str] = {
    "strategy": "deep",
    "research": "research",
    "nova":     "creative",
    "sam":      "creative",
    "kai":      "creative",
    "angela":   "creative",
}


def for_agent(agent_id: str) -> tuple[str, str]:
    """Convenience — return (provider, model) for the given agent."""
    return for_task(AGENT_TASKS.get(agent_id, "default"))


# ---------------------------------------------------------------------------
# User-facing modes (composer toggle in the agent workspace)
# ---------------------------------------------------------------------------
# Public, UI-safe metadata. We deliberately omit `default` (it's covered by
# "auto" → agent's natural task) and `research` (already the implicit mode
# for Iris). The frontend renders one chip per entry.
USER_MODES: list[dict] = [
    {
        "id": "auto",
        "label": "Auto",
        "blurb": "Use this agent's recommended model.",
    },
    {
        "id": "fast",
        "label": "Fast",
        "blurb": "Snappier replies, cheaper. Great for quick iterations.",
    },
    {
        "id": "deep",
        "label": "Deep",
        "blurb": "Slower, more thorough reasoning. Best for strategy + audits.",
    },
    {
        "id": "creative",
        "label": "Creative",
        "blurb": "Long-form writing, hooks, marketing copy.",
    },
]

USER_MODE_IDS: set[str] = {m["id"] for m in USER_MODES}


def resolve_user_mode(mode: str | None, agent_id: str) -> tuple[str, str, str]:
    """Resolve a user-supplied mode override into `(provider, model, task)`.

    `mode` may be `None`, empty, "auto", or any key in `USER_MODE_IDS`.
    Anything else (or "auto") falls back to the agent's natural task. The
    returned `task` is the internal `ROUTES` key actually used — handy for
    surfacing "Using deep mode (claude-opus-4-7)" in the UI."""
    if mode and mode != "auto" and mode in USER_MODE_IDS:
        task = mode
    else:
        task = AGENT_TASKS.get(agent_id, "default")
    provider, model = for_task(task)
    return provider, model, task
