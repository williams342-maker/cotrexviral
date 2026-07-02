import asyncio
import json

import httpx

from ai.model_router import select_model
from ai.providers.gemini_adapter import GeminiAdapter
from ai.providers.openai_adapter import OpenAIAdapter
from ai.providers.openrouter_adapter import OpenRouterAdapter


def test_openai_adapter_normalizes_responses_api():
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-openai"
        body = json.loads(request.content)
        assert body["text"]["format"]["type"] == "json_object"
        return httpx.Response(200, json={
            "id": "resp_1",
            "model": "gpt-5.5",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": '{"ok":true}'}],
            }],
            "usage": {
                "input_tokens": 11,
                "output_tokens": 4,
                "total_tokens": 15,
            },
        })

    async def scenario():
        adapter = OpenAIAdapter(
            "test-openai", transport=httpx.MockTransport(handler)
        )
        result = await adapter.generate(
            system_prompt="system", user_prompt="user", model="gpt-5.5"
        )
        assert result.provider == "openai"
        assert result.text == '{"ok":true}'
        assert result.usage["total_tokens"] == 15

    asyncio.run(scenario())


def test_gemini_adapter_normalizes_generate_content():
    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-gemini"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(200, json={
            "modelVersion": "gemini-3.5-flash",
            "candidates": [{
                "content": {"parts": [{"text": '{"ok":true}'}]},
            }],
            "usageMetadata": {
                "promptTokenCount": 9,
                "candidatesTokenCount": 3,
                "totalTokenCount": 12,
            },
        })

    async def scenario():
        adapter = GeminiAdapter(
            "test-gemini", transport=httpx.MockTransport(handler)
        )
        result = await adapter.generate(
            system_prompt="system",
            user_prompt="user",
            model="gemini-3.5-flash",
        )
        assert result.provider == "gemini"
        assert result.text == '{"ok":true}'
        assert result.usage["input_tokens"] == 9

    asyncio.run(scenario())


def test_openrouter_adapter_normalizes_chat_completion():
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-openrouter"
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_object"
        return httpx.Response(200, json={
            "id": "gen_1",
            "model": "openai/gpt-5.4-mini",
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
                "cost": 0.0002,
            },
        })

    async def scenario():
        adapter = OpenRouterAdapter(
            "test-openrouter", transport=httpx.MockTransport(handler)
        )
        result = await adapter.generate(
            system_prompt="system",
            user_prompt="user",
            model="openai/gpt-5.4-mini",
        )
        assert result.provider == "openrouter"
        assert result.cost_estimate == 0.0002
        assert result.usage["output_tokens"] == 2

    asyncio.run(scenario())


def test_model_router_builds_ordered_provider_candidates(monkeypatch):
    monkeypatch.setenv("AI_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "openai,gemini,openrouter")
    selection = select_model("campaign_plan")
    assert selection["provider"] == "gemini"
    assert selection["model"] == "gemini-3.5-flash"
    assert [item["provider"] for item in selection["candidates"]] == [
        "gemini", "openai", "openrouter",
    ]
