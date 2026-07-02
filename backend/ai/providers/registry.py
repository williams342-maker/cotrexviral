"""Provider construction and ordered fallback execution."""
import os

from ai.providers.base import ProviderError, ProviderResult
from ai.providers.gemini_adapter import GeminiAdapter
from ai.providers.openai_adapter import OpenAIAdapter
from ai.providers.openrouter_adapter import OpenRouterAdapter

ADAPTER_TYPES = {
    "openai": OpenAIAdapter,
    "gemini": GeminiAdapter,
    "openrouter": OpenRouterAdapter,
}

KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def build_adapter(provider: str):
    adapter_type = ADAPTER_TYPES.get(provider)
    if not adapter_type:
        raise ValueError(f"Unknown AI provider '{provider}'")
    return adapter_type(os.environ.get(KEY_ENV[provider], ""))


async def generate_with_fallback(
    *,
    candidates: list[dict],
    system_prompt: str,
    user_prompt: str,
) -> tuple[ProviderResult, list[dict]]:
    attempts = []
    for candidate in candidates:
        provider = candidate["provider"]
        model = candidate["model"]
        adapter = build_adapter(provider)
        if not adapter.configured:
            attempts.append({
                "provider": provider,
                "model": model,
                "status": "not_configured",
            })
            continue
        try:
            result = await adapter.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
            )
            attempts.append({
                "provider": provider,
                "model": result.model,
                "status": "success",
            })
            return result, attempts
        except Exception as exc:
            attempts.append({
                "provider": provider,
                "model": model,
                "status": "error",
                "error": str(exc)[:300],
            })

    summary = "; ".join(
        f"{item['provider']}={item['status']}" for item in attempts
    ) or "no providers configured"
    raise ProviderError(f"All AI providers failed: {summary}")

