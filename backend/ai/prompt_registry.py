"""Versioned prompts and structured output contracts."""

_BASE_RULES = (
    "Return valid JSON only. Do not claim that anything was published, sent, "
    "launched, purchased, or changed in an external system. Treat all output "
    "as a draft for human review."
)

PROMPTS = {
    "campaign_plan": {
        "version": "campaign_plan_v1",
        "system_prompt": (
            "You are a senior campaign strategist. Build a practical campaign "
            "plan with goals, audience, messaging, channels, timeline, and KPIs. "
            + _BASE_RULES
        ),
        "output_contract": {
            "summary": "string", "objectives": ["string"], "audience": "string",
            "channels": ["string"], "timeline": ["object"], "kpis": ["string"],
        },
    },
    "social_post": {
        "version": "social_post_v1",
        "system_prompt": (
            "You are a social media copywriter. Create one platform-specific "
            "draft with a strong hook, useful caption, relevant hashtags, and CTA. "
            + _BASE_RULES
        ),
        "output_contract": {
            "hook": "string", "caption": "string", "hashtags": ["string"],
            "cta": "string",
        },
    },
    "reddit_post": {
        "version": "reddit_post_v1",
        "system_prompt": (
            "Write a useful, community-first Reddit draft. Avoid marketing hype "
            "and disclose relevant affiliation. " + _BASE_RULES
        ),
        "output_contract": {
            "title": "string", "body": "string", "suggested_subreddits": ["string"],
            "disclosure": "string",
        },
    },
    "pinterest_pin": {
        "version": "pinterest_pin_v1",
        "system_prompt": (
            "Create an SEO-aware Pinterest Pin draft with a concise title, "
            "description, keywords, alt text, and CTA. " + _BASE_RULES
        ),
        "output_contract": {
            "title": "string", "description": "string", "keywords": ["string"],
            "alt_text": "string", "cta": "string",
        },
    },
    "seo_recommendation": {
        "version": "seo_recommendation_v1",
        "system_prompt": (
            "You are an SEO strategist. Produce a scored, prioritized audit from "
            "the supplied page context. Be honest when page data is incomplete. "
            + _BASE_RULES
        ),
        "output_contract": {
            "score": "integer", "strengths": ["string"],
            "issues": [{"title": "string", "severity": "high|medium|low", "fix": "string"}],
            "recommendations": ["string"], "keywords": ["string"],
        },
    },
    "listing_optimization": {
        "version": "listing_optimization_v1",
        "system_prompt": (
            "Optimize a marketplace listing for clarity, search discovery, and "
            "conversion without inventing product claims. " + _BASE_RULES
        ),
        "output_contract": {
            "title": "string", "description": "string", "keywords": ["string"],
            "improvements": ["string"],
        },
    },
    "email_reply": {
        "version": "email_reply_v1",
        "system_prompt": (
            "Draft a concise, helpful email reply that matches the requested tone. "
            "Never send it. " + _BASE_RULES
        ),
        "output_contract": {
            "subject": "string", "body": "string", "follow_up": "string",
        },
    },
    "ad_script": {
        "version": "ad_script_v1",
        "system_prompt": (
            "Create a conversion-focused short-form video ad draft. Include a "
            "headline, timed scenes, storyboard guidance, and CTA. Never launch "
            "or purchase ads. " + _BASE_RULES
        ),
        "output_contract": {
            "headline": "string", "title": "string", "hook": "string",
            "script": ["object"], "scenes": ["object"], "storyboard": ["object"],
            "cta": "string",
        },
    },
    "daily_brief": {
        "version": "daily_brief_v1",
        "system_prompt": (
            "Create an executive daily marketing brief with priorities, signals, "
            "risks, and recommended next actions. " + _BASE_RULES
        ),
        "output_contract": {
            "summary": "string", "priorities": ["string"], "signals": ["string"],
            "risks": ["string"], "next_actions": ["string"],
        },
    },
    "autonomous_action_plan": {
        "version": "autonomous_action_plan_v1",
        "system_prompt": (
            "Prepare a bounded action plan with steps, dependencies, risk checks, "
            "and explicit approval gates. Do not execute any step. " + _BASE_RULES
        ),
        "output_contract": {
            "objective": "string", "steps": ["object"], "approval_gates": ["string"],
            "risks": ["string"],
        },
    },
}


def get_prompt(task_type: str) -> dict:
    try:
        return PROMPTS[task_type]
    except KeyError as exc:
        raise ValueError(f"No prompt registered for '{task_type}'") from exc

