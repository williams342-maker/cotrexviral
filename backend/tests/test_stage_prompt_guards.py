"""Guard tests for the stage controller prompt (cortex/stages.py).

The "stranded analysis" bug — where Cortex narratively promises future
work but the backend stops streaming — was rooted in the LLM
classifier returning analysis turns with empty `findings` and empty
`clarifying_questions`. We fixed it by tightening the controller
prompt; these tests pin the prompt text so a future refactor can't
silently delete the rule and reintroduce the bug.

These are STATIC tests (no LLM calls) — they assert presence of the
critical clauses in the prompt string.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app/backend")

from cortex import stages   # noqa: E402


def test_analysis_delivery_rule_present():
    """The hard rule that prevents stranded-analysis turns. If this test
    fails, the LLM is free to once again return analysis turns with no
    findings and no clarifying questions, stranding the user."""
    text = stages.PROMPT_TEMPLATE if hasattr(stages, "PROMPT_TEMPLATE") else (
        # Fallback: scrape the module source so we still catch a deletion
        # even if the constant gets renamed.
        open(stages.__file__).read()
    )
    assert "ANALYSIS DELIVERY RULE" in text, \
        "Lost the ANALYSIS DELIVERY RULE in stages.py — stranded-analysis bug will return."
    # The rule explicitly forbids the empty-empty combination.
    assert "empty findings AND empty clarifying_questions" in text


def test_analysis_stage_description_forbids_future_work_hedges():
    """The stage description must explicitly forbid 'I'll come back with'
    style hedges. Without this, the LLM happily promises future work."""
    src = open(stages.__file__).read()
    # Tokens may be split across lines by the source formatter, so check
    # each clause independently.
    assert "NEVER end an" in src
    assert "promise to do future work" in src


def test_analysis_tone_demands_delivery():
    """The tone block must instruct the LLM to DELIVER in-turn, not hedge."""
    src = open(stages.__file__).read()
    assert "No \"I'll work on it\" hedges" in src
    assert "do the work" in src
