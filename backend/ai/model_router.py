"""Environment-driven model selection and provider fallback order."""
import os

from ai.task_router import task_group

DEFAULT_MODELS = {
    "openai": {
        "drafting": "gpt-5.4-mini",
        "strategy": "gpt-5.5",
        "listing": "gpt-5.5",
    },
    "gemini": {
        "drafting": "gemini-3.5-flash",
        "strategy": "gemini-3.5-flash",
        "listing": "gemini-3.5-flash",
    },
    "openrouter": {
        "drafting": "openai/gpt-5.4-mini",
        "strategy": "openai/gpt-5.5",
        "listing": "openai/gpt-5.5",
    },
}


def _provider_order() -> list[str]:
    configured = os.environ.get(
        "AI_PROVIDER_ORDER", "openai,gemini,openrouter"
    )
    order = [
        item.strip().lower() for item in configured.split(",")
        if item.strip().lower() in DEFAULT_MODELS
    ]
    preferred = os.environ.get("AI_MODEL_PROVIDER", "auto").lower()
    if preferred in DEFAULT_MODELS:
        order = [preferred] + [item for item in order if item != preferred]
    if os.environ.get("AI_ENABLE_PROVIDER_FALLBACKS", "true").lower() == "false":
        order = order[:1]
    return order or ["openai"]


def _model_for(provider: str, group: str) -> str:
    env_group = "FAST" if group == "drafting" else "STRONG"
    provider_override = os.environ.get(
        f"AI_{provider.upper()}_{env_group}_MODEL"
    )
    if provider_override:
        return provider_override
    # Preserve the original generic overrides for OpenAI.
    generic_override = os.environ.get(f"AI_{env_group}_MODEL")
    if provider == "openai" and generic_override:
        return generic_override
    return DEFAULT_MODELS[provider][group]


def select_model(task_type: str) -> dict:
    group = task_group(task_type)
    candidates = [
        {"provider": provider, "model": _model_for(provider, group)}
        for provider in _provider_order()
    ]
    return {
        **candidates[0],
        "group": group,
        "candidates": candidates,
    }
