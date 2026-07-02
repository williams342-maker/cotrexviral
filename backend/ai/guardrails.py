"""Autonomy and external-execution safety policy."""
import os

from ai.task_router import EXTERNAL_ACTION_TASKS, require_task_type

AUTONOMY_LABELS = {
    0: "suggest_only",
    1: "draft_only",
    2: "prepare_for_approval",
    3: "approval_required_execution",
    4: "rules_bounded_execution",
    5: "fully_autonomous",
}


def evaluate(task_type: str, autonomy_level: int, context: dict | None = None) -> dict:
    task_type = require_task_type(task_type)
    if autonomy_level not in AUTONOMY_LABELS:
        raise ValueError("autonomy_level must be an integer from 0 through 5")

    external_capable = task_type in EXTERNAL_ACTION_TASKS
    execution_requested = bool((context or {}).get("execute"))
    l5_enabled = os.environ.get("AI_ENABLE_L5", "false").lower() == "true"

    needs_approval = external_capable and autonomy_level >= 2
    if execution_requested:
        needs_approval = True
    if autonomy_level == 5 and not l5_enabled:
        needs_approval = True

    return {
        "label": AUTONOMY_LABELS[autonomy_level],
        "needs_approval": needs_approval,
        "approval_status": "pending" if needs_approval else "not_required",
        "executed": False,
        "external_execution_enabled": False,
        "instruction": (
            "Suggest only; do not provide a finished draft."
            if autonomy_level == 0
            else "Return a reviewable draft only. Never execute external actions."
        ),
    }

