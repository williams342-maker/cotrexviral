"""Iter24 — Cortex Discovery & Executive Consultant Behavior Redesign.

Validates the 5 priority pieces:
  1. Action-First routing — show/list/scan intents bypass discovery.
  2. Discovery Budget — after 2 discovery rounds, force progression.
  3. Discovery Triggers (prompt-level — verified indirectly).
  4. Answer Shortcuts — discovery turns must include clickable answers.
  5. Auto-trigger scans from chat — "scan craftersmarket.org" creates
     a real analysis_jobs row.
"""
import os
import time
import uuid
import subprocess

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
COOKIES = {"session_token": TOKEN}


def _post(path, body=None):
    return requests.post(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES,
                          json=body or {}, timeout=30)


def _get(path):
    return requests.get(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES, timeout=20)


@pytest.fixture(autouse=True)
def _isolate_conv():
    """Each test runs in its own conversation_id so prior discovery
    turns don't leak across tests."""
    pytest.conv_id = f"iter24-{uuid.uuid4().hex[:10]}"
    yield


# -------------------------------- 1. Action-First routing
class TestActionFirstRouting:
    def test_show_leads_routes_to_action(self):
        r = _post("/api/cortex/console/chat",
                   {"message": "show me the leads",
                    "conversation_id": pytest.conv_id})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["stage"] == "action", \
            f"Expected stage=action, got {d.get('stage')}"
        assert d.get("action_kind") in ("show_leads", "empty")
        # No clarifying questions on Action-First.
        assert not d.get("clarifying_questions"), \
            "Action-First MUST NOT ask clarifying questions"

    def test_show_opportunities_routes_to_action(self):
        r = _post("/api/cortex/console/chat",
                   {"message": "show opportunities",
                    "conversation_id": pytest.conv_id})
        assert r.json()["stage"] == "action"

    def test_show_missions_routes_to_action(self):
        r = _post("/api/cortex/console/chat",
                   {"message": "list active missions",
                    "conversation_id": pytest.conv_id})
        assert r.json()["stage"] == "action"


# -------------------------------- 2. Discovery Budget
class TestDiscoveryBudget:
    def test_after_2_discovery_rounds_forces_advance(self):
        """Seed 2 discovery turns in history, then send an ambiguous
        message. The classifier MUST advance past discovery."""
        from datetime import datetime, timezone
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    now = datetime.now(timezone.utc)
    for _ in range(2):
        await db.cortex_conversations.insert_one({{
            'id': uuid.uuid4().hex,
            'user_id': '{USER_ID}',
            'conversation_id': '{pytest.conv_id}',
            'role': 'cortex',
            'message': 'Tell me more',
            'stage': 'discovery',
            'created_at': now,
        }})
asyncio.run(go())
"""
        ], check=True, timeout=15)

        r = _post("/api/cortex/console/chat",
                   {"message": "still vague",
                    "conversation_id": pytest.conv_id})
        d = r.json()
        # MUST NOT return another discovery turn.
        assert d["stage"] != "discovery", \
            f"Discovery Budget violated — got stage={d['stage']}"


# -------------------------------- 3. Answer Shortcuts
class TestAnswerShortcuts:
    def test_ambiguous_request_returns_shortcuts(self):
        """'Grow my business' is the canonical ambiguous request.
        Cortex must return answer_shortcuts that aren't repeated questions."""
        r = _post("/api/cortex/console/chat",
                   {"message": "grow my business",
                    "conversation_id": pytest.conv_id})
        d = r.json()
        assert d["stage"] == "discovery", \
            f"Truly ambiguous request should land in discovery, got {d.get('stage')}"
        shortcuts = d.get("answer_shortcuts") or []
        assert len(shortcuts) >= 3, \
            f"Expected ≥3 answer shortcuts, got {shortcuts}"
        # Shortcuts must not contain '?' (they're answers, not questions).
        for s in shortcuts:
            assert "?" not in s, \
                f"Shortcut contains question mark: {s!r}"


# -------------------------------- 4. Discovery NOT fired for show-me
class TestNoDiscoveryOnShowRequests:
    def test_show_request_never_triggers_discovery(self):
        """Per the redesign mandate: 'show me X' must NEVER trigger
        another discovery round, even on first interaction."""
        for q in ("show me the leads",
                  "view the SEO report",
                  "list opportunities",
                  "show me my candidates"):
            r = _post("/api/cortex/console/chat",
                       {"message": q,
                        "conversation_id": f"iter24-{uuid.uuid4().hex[:8]}"})
            d = r.json()
            assert d["stage"] != "discovery", \
                f"'{q}' triggered discovery — that's the BAD pattern"


# -------------------------------- 5. Auto-trigger scans from chat
class TestAutoTriggerScans:
    def test_scan_url_creates_real_analysis_job(self):
        """User types 'scan craftersmarket.org' → real analysis_jobs
        row created → ack references the job_id."""
        # Wipe prior analysis jobs to make assertion clean.
        subprocess.run([
            "python3", "-c",
            f"""
import asyncio, sys
sys.path.insert(0, '/app/backend')
from core import db
async def go():
    await db.analysis_jobs.delete_many({{'user_id': '{USER_ID}'}})
asyncio.run(go())
"""
        ], check=True, timeout=15)

        r = _post("/api/cortex/console/chat",
                   {"message": "scan craftersmarket.org",
                    "conversation_id": pytest.conv_id})
        d = r.json()
        assert d["stage"] == "action"
        assert d.get("action_kind") == "run_scan_started"
        job_id = (d.get("action_data") or {}).get("job_id")
        assert job_id, f"Expected job_id in action_data, got {d.get('action_data')}"
        # Ack must reference the job ID — verifying the "no fake scanning" rule.
        assert "#" in d["ack"] and job_id[:8] in d["ack"], \
            f"Ack must reference job ID, got: {d['ack']}"
        # Real analysis_jobs row exists.
        r = _get(f"/api/cortex/analysis-jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_type"] == "seo_scan"
        assert r.json()["target"].startswith("https://craftersmarket.org")

    def test_audit_my_site_prompts_for_url(self):
        """'audit my site' without a URL → no job created; Cortex asks
        for the URL in the ack."""
        r = _post("/api/cortex/console/chat",
                   {"message": "audit my site",
                    "conversation_id": pytest.conv_id})
        d = r.json()
        assert d["stage"] == "action"
        assert d.get("action_kind") == "run_scan_needs_url"
        # Should NOT have created a job row.
        assert "job_id" not in (d.get("action_data") or {})

    def test_review_url_with_subdomain_works(self):
        r = _post("/api/cortex/console/chat",
                   {"message": "review https://www.cortexviral.com",
                    "conversation_id": pytest.conv_id})
        d = r.json()
        assert d["stage"] == "action"
        assert d.get("action_kind") == "run_scan_started"


# -------------------------------- 6. Action-First matcher unit tests
class TestActionMatcher:
    def test_matchers_directly(self):
        """Unit tests on the regex matchers — no LLM dependency."""
        import sys
        sys.path.insert(0, "/app/backend")
        from cortex.action_first import match_action_intent

        cases = [
            ("show me the leads",          {"kind": "show_leads"}),
            ("list leads",                  {"kind": "show_leads"}),
            ("export the qualified leads", {"kind": "show_leads"}),
            ("show me the SEO report",     {"kind": "show_reports"}),
            ("view scan results",          {"kind": "show_reports"}),
            ("show opportunities",         {"kind": "show_opportunities"}),
            ("list active missions",       {"kind": "show_missions"}),
            ("scan cortexviral.com",       {"kind": "run_scan",
                                             "url": "https://cortexviral.com"}),
            ("audit craftersmarket.org",   {"kind": "run_scan",
                                             "url": "https://craftersmarket.org"}),
            ("analyze https://example.com/foo",
                                             {"kind": "run_scan",
                                              "url": "https://example.com/foo"}),
            ("audit my site",              {"kind": "run_scan", "needs_url": True}),
            ("scan my SEO",                {"kind": "run_scan", "needs_url": True}),
        ]
        for msg, expected in cases:
            got = match_action_intent(msg)
            assert got is not None, f"No match for {msg!r}"
            for k, v in expected.items():
                assert got.get(k) == v, \
                    f"For {msg!r}: expected {k}={v!r}, got {got.get(k)!r}"

    def test_non_action_messages_return_none(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from cortex.action_first import match_action_intent
        for msg in ("Hello how are you?",
                     "I want to grow my business",
                     "what should I focus on this week",
                     "tell me about my seller funnel"):
            assert match_action_intent(msg) is None, \
                f"False positive on {msg!r}"
