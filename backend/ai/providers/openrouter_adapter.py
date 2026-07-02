"""OpenRouter OpenAI-compatible chat adapter."""
import os

import httpx

from ai.providers.base import ProviderAdapter, ProviderResult


class OpenRouterAdapter(ProviderAdapter):
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    async def generate(
        self, *, system_prompt: str, user_prompt: str, model: str
    ) -> ProviderResult:
        if not self.configured:
            raise ValueError("OpenRouter API key is not configured")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "CortexViral",
        }
        site_url = os.environ.get("PUBLIC_SITE_URL")
        if site_url:
            headers["HTTP-Referer"] = site_url
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout
            ) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self.safe_error(exc) from exc

        choices = data.get("choices") or []
        text = (
            str(((choices[0].get("message") or {}).get("content") or "")).strip()
            if choices else ""
        )
        if not text:
            raise ValueError("OpenRouter returned no text output")
        usage = data.get("usage") or {}
        reported_cost = usage.get("cost")
        return ProviderResult(
            provider=self.name,
            model=data.get("model") or model,
            text=text,
            usage={
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            cost_estimate=(
                float(reported_cost) if reported_cost is not None else None
            ),
            metadata={"response_id": data.get("id")},
        )

