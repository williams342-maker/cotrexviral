import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from ai.ai_logs import list_runs
from ai.orchestrator import AIExecutionRequest, execute
from ai.prompt_registry import get_prompt
from ai.providers.base import ProviderResult
from ai.task_router import TASK_TYPES


@pytest.fixture
def db():
    return AsyncMongoMockClient()["ai_orchestration_tests"]


def test_ad_script_l1_is_logged_as_draft(db, monkeypatch):
    async def scenario():
        monkeypatch.setenv("AI_OFFLINE_MODE", "true")
        await db.users.insert_one({
            "user_id": "user_1",
            "brand_name": "Crafters Market",
            "niche": "Handmade marketplace",
        })
        payload = AIExecutionRequest(
            task_type="ad_script",
            user_goal="Create a 45-second recruitment video ad for makers.",
            autonomy_level=1,
            context={"cta": "Become a Founding Seller", "duration_seconds": 45},
        )

        response = await execute(db, "user_1", payload)

        assert response["status"] == "success"
        assert response["executed"] is False
        assert response["prompt_version"] == "ad_script_v1"
        assert response["result"]["cta"] == "Become a Founding Seller"
        stored = await db.ai_runs.find_one({"run_id": response["run_id"]})
        assert stored["task_type"] == "ad_script"
        assert stored["status"] == "success"

    asyncio.run(scenario())


def test_social_post_l2_requires_approval_and_never_executes(db, monkeypatch):
    async def scenario():
        monkeypatch.setenv("AI_OFFLINE_MODE", "true")
        response = await execute(db, "user_2", AIExecutionRequest(
            task_type="social_post",
            user_goal="Draft a launch post.",
            autonomy_level=2,
            context={"platform": "instagram", "execute": True},
        ))

        assert response["status"] == "needs_approval"
        assert response["approval_status"] == "pending"
        assert response["executed"] is False
        runs = await list_runs(db, "user_2")
        assert len(runs) == 1

    asyncio.run(scenario())



def test_saved_autonomy_is_used_when_request_omits_level(db, monkeypatch):
    async def scenario():
        monkeypatch.setenv("AI_OFFLINE_MODE", "true")
        await db.users.insert_one({
            "user_id": "user_default_level",
            "preferences": {"ai_autonomy_level": 2},
        })
        response = await execute(db, "user_default_level", AIExecutionRequest(
            task_type="social_post",
            user_goal="Draft a launch announcement.",
        ))
        assert response["autonomy_level"] == 2
        assert response["status"] == "needs_approval"
        assert response["executed"] is False

    asyncio.run(scenario())
def test_every_initial_task_has_a_versioned_prompt():
    for task_type in TASK_TYPES:
        prompt = get_prompt(task_type)
        assert prompt["version"] == f"{task_type}_v1"
        assert prompt["output_contract"]


def test_live_orchestration_uses_normalized_provider_result(db, monkeypatch):
    async def fake_generate(**kwargs):
        return ProviderResult(
            provider="openai",
            model="gpt-5.5",
            text='{"headline":"A governed draft"}',
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        ), [{"provider": "openai", "model": "gpt-5.5", "status": "success"}]

    async def scenario():
        monkeypatch.setenv("AI_OFFLINE_MODE", "false")
        monkeypatch.setattr(
            "ai.orchestrator.generate_with_fallback", fake_generate
        )
        response = await execute(db, "user_live", AIExecutionRequest(
            task_type="campaign_plan",
            user_goal="Build a governed launch campaign.",
            autonomy_level=1,
        ))
        assert response["status"] == "success"
        assert response["provider_used"] == "openai"
        assert response["model_used"] == "gpt-5.5"
        assert response["result"]["headline"] == "A governed draft"
        assert response["tokens"]["total"] == 120
        stored = await db.ai_runs.find_one({"run_id": response["run_id"]})
        assert stored["provider_attempts"][0]["status"] == "success"

    asyncio.run(scenario())
