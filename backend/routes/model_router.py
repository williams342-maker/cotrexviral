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
