"""Single entry point for every centrally orchestrated AI task."""
from datetime import datetime, timezone
import json
import os
import re
import uuid

from pydantic import BaseModel, Field

from ai.ai_logs import create_run, finish_run
from ai.cost_tracker import estimate_cost, normalize_usage
from ai.guardrails import evaluate
from ai.memory_context import build_memory_context
from ai.model_router import select_model
from ai.prompt_registry import get_prompt
from ai.providers import generate_with_fallback
from ai.task_router import require_task_type
from ai.tool_registry import available_tools


class AIExecutionRequest(BaseModel):
    task_type: str
    user_goal: str = Field(..., min_length=3, max_length=8000)
    autonomy_level: int | None = Field(default=None, ge=0, le=5)
    context: dict = Field(default_factory=dict)
    output_schema: dict | None = None


def _parse_result(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except Exception:
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
        candidate = fenced.group(1) if fenced else raw
        match = re.search(r"\{[\s\S]*\}", candidate)
        if not match:
            raise ValueError("AI provider did not return a JSON object")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        return {"value": parsed}
    return parsed


def _offline_result(task_type: str, goal: str, context: dict) -> dict:
    """Useful local drafts when AI_OFFLINE_MODE is explicitly enabled."""
    request_context = context.get("request_context", {})
    if task_type == "ad_script":
        duration = int(request_context.get("duration_seconds") or 45)
        platform = request_context.get("platform") or "short-form video"
        return {
            "headline": "One Clear Promise. One Strong Next Step.",
            "title": f"{duration}-second {platform} ad",
            "hook": goal[:140],
            "script": [
                {"timestamp": "0-5s", "voiceover": goal[:180], "visual": "Open on the audience's current problem."},
                {"timestamp": f"5-{max(10, duration - 8)}s", "voiceover": "Show the product solving that problem in a concrete, believable way.", "visual": "Demonstrate the core workflow and outcome."},
                {"timestamp": f"{max(10, duration - 8)}-{duration}s", "voiceover": request_context.get("cta") or "Take the next step today.", "visual": "Brand card and CTA."},
            ],
            "scenes": [
                {"timestamp": "0-5s", "visual": "Problem", "voiceover": goal[:180]},
                {"timestamp": f"5-{duration}s", "visual": "Solution and CTA", "voiceover": request_context.get("cta") or "Take the next step today."},
            ],
            "storyboard": [
                {"scene": 1, "direction": "Lead with a specific pain point."},
                {"scene": 2, "direction": "Demonstrate the promised result."},
            ],
            "cta": request_context.get("cta") or "Learn more",
        }
    if task_type == "social_post":
        platform = request_context.get("platform") or "social"
        return {
            "hook": goal[:120],
            "caption": f"{goal}\n\nDrafted for {platform}. Add one concrete proof point before publishing.",
            "hashtags": [platform.replace(" ", ""), "marketing", "growth"],
            "cta": request_context.get("cta") or "What would you try first?",
        }
    if task_type == "pinterest_pin":
        return {
            "title": goal[:95],
            "description": f"{goal} Save this idea for later and adapt it to your brand.",
            "keywords": ["marketing ideas", "small business growth", "content strategy"],
            "alt_text": f"Pinterest graphic about {goal[:120]}",
            "cta": request_context.get("cta") or "Learn more",
        }
    if task_type == "seo_recommendation":
        url = request_context.get("url") or request_context.get("website") or "the supplied page"
        return {
            "score": 65,
            "strengths": ["A clear page target was supplied", "The page can be evaluated against a specific search intent"],
            "issues": [
                {"title": "Live page analysis unavailable offline", "severity": "medium", "fix": f"Connect an AI provider and crawl {url} for evidence-based recommendations."},
            ],
            "recommendations": ["Define one primary keyword", "Align the title, H1, and opening paragraph", "Add descriptive internal links"],
            "keywords": ["primary topic", "audience need", "product category"],
        }
    return {
        "summary": goal,
        "recommendations": [
            "Review this draft with the accountable owner.",
            "Add brand-specific evidence before use.",
            "Keep all external execution behind approval.",
        ],
    }


async def execute(db, user_id: str, payload: AIExecutionRequest) -> dict:
    task_type = require_task_type(payload.task_type)
    prompt = get_prompt(task_type)
    model = select_model(task_type)
    autonomy_level = payload.autonomy_level
    if autonomy_level is None:
        user_doc = await db.users.find_one(
            {"user_id": user_id},
            {"_id": 0, "preferences.ai_autonomy_level": 1},
        ) or {}
        autonomy_level = int(
            ((user_doc.get("preferences") or {}).get("ai_autonomy_level", 1))
        )
    safety = evaluate(task_type, autonomy_level, payload.context)
    memory = await build_memory_context(db, user_id, payload.context)
    run_id = f"ai_run_{uuid.uuid4().hex}"

    await create_run(db, {
        "run_id": run_id,
        "user_id": user_id,
        "task_type": task_type,
        "user_goal": payload.user_goal,
        "context": payload.context,
        "autonomy_level": autonomy_level,
        "model_used": model["model"],
        "provider_used": model["provider"],
        "provider_candidates": model["candidates"],
        "prompt_version": prompt["version"],
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_estimate": 0.0,
        "approval_status": safety["approval_status"],
    })

    provider_used = "offline"
    model_used = model["model"]
    provider_attempts = []
    provider_cost = None
    try:
        if os.environ.get("AI_OFFLINE_MODE", "false").lower() == "true":
            result = _offline_result(task_type, payload.user_goal, memory)
            usage = {}
        else:
            system = (
                f"{prompt['system_prompt']}\n\n"
                f"AUTONOMY POLICY: {safety['instruction']}\n"
                f"OUTPUT CONTRACT: {json.dumps(payload.output_schema or prompt['output_contract'])}\n"
                f"AVAILABLE TOOLS: {json.dumps(available_tools())}"
            )
            message = (
                f"USER GOAL:\n{payload.user_goal}\n\n"
                f"CONTEXT:\n{json.dumps(memory, default=str)}"
            )
            provider_response, provider_attempts = await generate_with_fallback(
                candidates=model["candidates"],
                system_prompt=system,
                user_prompt=message,
            )
            provider_used = provider_response.provider
            model_used = provider_response.model
            provider_cost = provider_response.cost_estimate
            usage = provider_response.usage
            result = _parse_result(provider_response.text)

        tokens = normalize_usage(usage)
        pricing_model = model_used.split("/")[-1]
        cost = (
            round(float(provider_cost), 6)
            if provider_cost is not None
            else estimate_cost(pricing_model, tokens)
        )
        status = "needs_approval" if safety["needs_approval"] else "success"
        row = await finish_run(
            db, run_id,
            status=status,
            result=result,
            error_message=None,
            approval_status=safety["approval_status"],
            executed=False,
            provider_used=provider_used,
            provider_attempts=provider_attempts,
            model_used=model_used,
            input_tokens=tokens["input"],
            output_tokens=tokens["output"],
            total_tokens=tokens["total"],
            cost_estimate=cost,
        )
    except Exception as exc:
        tokens = normalize_usage({})
        row = await finish_run(
            db, run_id,
            status="error",
            result={},
            error_message=str(exc),
            approval_status=safety["approval_status"],
            executed=False,
            provider_used=provider_used,
            provider_attempts=provider_attempts,
            model_used=model_used,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_estimate=0.0,
        )

    return {
        "run_id": row["run_id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "model_used": row["model_used"],
        "provider_used": row.get("provider_used"),
        "autonomy_level": row["autonomy_level"],
        "result": row.get("result") or {},
        "error_message": row.get("error_message"),
        "approval_status": row.get("approval_status", "not_required"),
        "executed": False,
        "cost_estimate": row.get("cost_estimate", 0.0),
        "tokens": {
            "input": row.get("input_tokens", 0),
            "output": row.get("output_tokens", 0),
            "total": row.get("total_tokens", 0),
        },
        "prompt_version": row["prompt_version"],
        "created_at": row.get("created_at") or datetime.now(timezone.utc),
    }
