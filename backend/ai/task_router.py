"""Task metadata used by the AI orchestration layer."""

TASK_TYPES = (
    "campaign_plan",
    "social_post",
    "reddit_post",
    "pinterest_pin",
    "seo_recommendation",
    "listing_optimization",
    "email_reply",
    "ad_script",
    "daily_brief",
    "autonomous_action_plan",
)

DRAFTING_TASKS = {
    "social_post", "email_reply", "reddit_post", "pinterest_pin", "ad_script",
}
STRATEGY_TASKS = {
    "campaign_plan", "seo_recommendation", "daily_brief",
    "autonomous_action_plan",
}
LISTING_TASKS = {"listing_optimization"}

# These tasks can produce material that is eventually sent, posted, or used
# in an ad. The current phase can draft them, but never executes them.
EXTERNAL_ACTION_TASKS = {
    "social_post", "reddit_post", "pinterest_pin", "email_reply", "ad_script",
}


def require_task_type(task_type: str) -> str:
    normalized = (task_type or "").strip().lower()
    if normalized not in TASK_TYPES:
        supported = ", ".join(TASK_TYPES)
        raise ValueError(f"Unsupported task_type '{task_type}'. Supported: {supported}")
    return normalized


def task_group(task_type: str) -> str:
    task_type = require_task_type(task_type)
    if task_type in DRAFTING_TASKS:
        return "drafting"
    if task_type in LISTING_TASKS:
        return "listing"
    return "strategy"

