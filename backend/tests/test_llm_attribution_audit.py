"""LLM call-site ledger audit — P2 full-coverage of token/USD ticks.

The Team Performance + Autonomy pages only reflect reality when EVERY
user-attributable LLM call ticks the per-agent ledger. This audit locks
that down two ways:

  1. **Static source check** — greps the user-facing route files for any
     bare `chat.send_message(...)` calls. Every hit is a regression.

  2. **Persona enumeration** — verifies the agent IDs hard-coded into the
     route files all match real personas in `agent_personas.PERSONAS`.
     Prevents typos like `agent_id="kai"` (legacy name, not a persona).
"""
import re

import pytest


# Files whose user-facing endpoints MUST go through send_with_usage.
FILES_THAT_MUST_USE_SEND_WITH_USAGE = [
    "/app/backend/routes/ai.py",
    "/app/backend/routes/ab_lab.py",
    "/app/backend/routes/channels.py",
]


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestNoBareSendMessage:
    """Bare `chat.send_message()` is forbidden in user-facing route files —
    every LLM call must go through `send_with_usage()` so the ledger ticks.

    Exceptions (must be explicitly allow-listed):
      • `routes/ai.py` defines `send_with_usage` itself; references in
        its docstring + the underlying `chat._execute_completion(...)` call
        are NOT bare send_message calls.
      • `routes/trends.py` and `routes/support.py` make global / chatbot
        LLM calls that aren't attributable to a growth-team persona —
        outside this audit's scope.
    """

    def test_no_bare_send_message_calls(self):
        offenders = []
        for path in FILES_THAT_MUST_USE_SEND_WITH_USAGE:
            src = _read(path)
            for i, line in enumerate(src.splitlines(), 1):
                if ".send_message(" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Skip docstring references (the send_with_usage docstring
                # mentions `chat.send_message(user_message)` as the legacy
                # API it replaces).
                if 'send_message(user_message)' in line:
                    continue
                # Skip lines inside send_with_usage that touch private
                # chat internals like `chat._add_user_message(...)` —
                # those aren't send_message calls.
                if "chat._" in line:
                    continue
                offenders.append(f"{path}:{i}  {stripped}")
        assert not offenders, (
            "Bare chat.send_message() found in user-facing route — must "
            "go through send_with_usage so the agent ledger ticks:\n  "
            + "\n  ".join(offenders)
        )


class TestAttributedAgentsExist:
    """Every `agent_id=...` string passed to send_with_usage must reference
    a real persona id in agent_personas.PERSONAS. Catches typos before
    they ship (a misspelled agent_id silently logs 'unknown agent — skipping'
    inside record_usage, so the ledger row is never written)."""

    def test_all_agent_ids_resolve_to_personas(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.agent_personas import PERSONAS
        valid_ids = {p["id"] for p in PERSONAS}

        pattern = re.compile(r'agent_id\s*=\s*"([^"]+)"')
        bad = []
        for path in FILES_THAT_MUST_USE_SEND_WITH_USAGE:
            src = _read(path)
            for m in pattern.finditer(src):
                aid = m.group(1)
                if aid not in valid_ids:
                    # Compute the line number for a friendly message.
                    line_no = src[:m.start()].count("\n") + 1
                    bad.append(f"{path}:{line_no}  agent_id=\"{aid}\"")
        assert not bad, (
            "Found `agent_id=\"...\"` references to non-existent personas. "
            f"Valid persona ids: {sorted(valid_ids)}\nOffenders:\n  "
            + "\n  ".join(bad)
        )


class TestCoverageMatrix:
    """Sanity-check: each known persona that owns content-generation duties
    appears as an attribution target at least once. If a persona drops out
    of the codebase silently, this test fires — useful as a watchdog
    when refactoring agent ownership.

    Skips when a persona simply has no LLM-generation duties (e.g. Echo
    is mostly scheduling, Jules is mostly ops alerts). Tracked via the
    EXPECTED_TARGETS dict below.
    """

    # Personas that MUST show up at least once in the audited files.
    EXPECTED_TARGETS = {"nova", "rae", "echo"}

    def test_expected_personas_have_at_least_one_attribution(self):
        pattern = re.compile(r'agent_id\s*=\s*"([^"]+)"')
        found = set()
        for path in FILES_THAT_MUST_USE_SEND_WITH_USAGE:
            src = _read(path)
            for m in pattern.finditer(src):
                found.add(m.group(1))
        missing = self.EXPECTED_TARGETS - found
        assert not missing, (
            f"Expected personas {sorted(missing)} have no LLM attribution. "
            f"Found attributions for: {sorted(found)}"
        )
