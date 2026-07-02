"""Google Gemini generateContent adapter."""
from urllib.parse import quote

import httpx

from ai.providers.base import ProviderAdapter, ProviderResult


class GeminiAdapter(ProviderAdapter):
    name = "gemini"
    endpoint_template = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{model}:generateContent"
    )

    async def generate(
        self, *, system_prompt: str, user_prompt: str, model: str
    ) -> ProviderResult:
        if not self.configured:
            raise ValueError("Gemini API key is not configured")
        endpoint = self.endpoint_template.format(model=quote(model, safe=".-_"))
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "x-goog-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "systemInstruction": {
                            "parts": [{"text": system_prompt}],
                        },
                        "contents": [{
                            "role": "user",
                            "parts": [{"text": user_prompt}],
                        }],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self.safe_error(exc) from exc

        candidates = data.get("candidates") or []
        parts = (
            ((candidates[0].get("content") or {}).get("parts") or [])
            if candidates else []
        )
        text = "".join(str(part.get("text") or "") for part in parts).strip()
        if not text:
            raise ValueError("Gemini returned no text output")
        usage = data.get("usageMetadata") or {}
        return ProviderResult(
            provider=self.name,
            model=data.get("modelVersion") or model,
            text=text,
            usage={
                "input_tokens": int(usage.get("promptTokenCount") or 0),
                "output_tokens": int(usage.get("candidatesTokenCount") or 0),
                "total_tokens": int(usage.get("totalTokenCount") or 0),
            },
        )

