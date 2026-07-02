"""OpenAI Responses API adapter."""
import httpx

from ai.providers.base import ProviderAdapter, ProviderResult


def _output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    for item in payload.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                return str(part["text"])
    raise ValueError("OpenAI returned no text output")


class OpenAIAdapter(ProviderAdapter):
    name = "openai"
    endpoint = "https://api.openai.com/v1/responses"

    async def generate(
        self, *, system_prompt: str, user_prompt: str, model: str
    ) -> ProviderResult:
        if not self.configured:
            raise ValueError("OpenAI API key is not configured")
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout
            ) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "input": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "text": {"format": {"type": "json_object"}},
                        "store": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self.safe_error(exc) from exc

        usage = data.get("usage") or {}
        return ProviderResult(
            provider=self.name,
            model=data.get("model") or model,
            text=_output_text(data),
            usage={
                "input_tokens": int(usage.get("input_tokens") or 0),
                "output_tokens": int(usage.get("output_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
            metadata={"response_id": data.get("id")},
        )

