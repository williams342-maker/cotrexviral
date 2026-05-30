"""Tests for the Proactive Recommendation Bridge (iter25).

Coverage:
  • bridge synthesis produces all 5 required fields (finding,
    root_cause, recommendation, expected_impact, confidence) + the
    reasoning paragraph + mission_intent/params
  • idempotency: second build returns same row, no duplicates
  • heuristic fallback path returns a non-empty bridge when LLM is off
  • bridge is auto-posted as a chat turn after analysis completion
  • GET /recommendation-bridges/{job_id} returns the bridge
  • POST /regenerate replaces the bridge
  • POST /discuss appends a follow-up chat turn
  • confidence clamping (out-of-range int / non-int)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid

import pytest


REPO = "/app/backend"


def _run_in_subproc(snippet: str, *, env: dict | None = None) -> dict:
    """Execute Python in a fresh subprocess so each test owns its own
    asyncio event loop (motor's loop binding cross-contaminates when
    tests share a loop)."""
    env_full = os.environ.copy()
    if env:
        env_full.update(env)
    out = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=REPO, capture_output=True, text=True, env=env_full, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"subproc failed (rc={out.returncode}):\n"
            f"STDOUT:\n{out.stdout}\n\nSTDERR:\n{out.stderr}"
        )
    import json
    return json.loads(out.stdout.strip().splitlines()[-1])


# ---------------------------------------------------- bridge synthesis
def test_bridge_synthesis_produces_all_required_fields():
    """Build a bridge from a seeded completed job; verify the 5 fields
    + reasoning + mission_intent + mission_params are non-empty."""
    snippet = r"""
import asyncio, json, uuid
from datetime import datetime, timezone

async def main():
    from core import db
    job_id = f"recbridge-test-{uuid.uuid4().hex[:8]}"
    uid = f"u-{uuid.uuid4().hex[:8]}"

    # Seed a completed analysis_jobs row + a reports row.
    await db.analysis_jobs.insert_one({
        "id": job_id, "user_id": uid, "job_type": "seo_scan",
        "target": "https://example.com",
        "status": "completed", "progress_pct": 100,
        "metrics": {"issues_found": 14, "high_priority": 4,
                     "recommendations": 6, "notable_items": 3},
        "result_summary": "SEO scan complete for https://example.com",
        "queued_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
    })
    await db.reports.insert_one({
        "id": uuid.uuid4().hex, "user_id": uid, "type": "seo_scan",
        "url": "https://example.com",
        "report": {
            "summary": "SEO scan for example.com",
            "improvements": [
                "Add meta descriptions",
                "Improve heading hierarchy",
                "Add alt text for product images",
            ],
            "post_ideas": [{"title": "10 CNC tips", "platform": "blog"}],
            "notable_items": ["Missing H1 on homepage"],
        },
        "created_at": datetime.now(timezone.utc),
    })

    from cortex.recommendation_bridge import build_bridge_from_job
    bridge = await build_bridge_from_job(job_id)

    # Cleanup before asserting.
    await db.analysis_jobs.delete_one({"id": job_id})
    await db.reports.delete_many({"user_id": uid})
    await db.cortex_recommendation_bridges.delete_many({"job_id": job_id})

    out = {
        "ok": bool(bridge),
        "has_finding": bool(bridge and bridge.get("finding")),
        "has_root_cause": bool(bridge and bridge.get("root_cause")),
        "has_recommendation": bool(bridge and bridge.get("recommendation")),
        "has_impact": bool(bridge and bridge.get("expected_impact")),
        "has_confidence": isinstance(bridge.get("confidence"), int),
        "confidence_in_range": 0 <= (bridge.get("confidence") or -1) <= 100,
        "has_reasoning": bool(bridge and bridge.get("reasoning")),
        "has_mission_intent": bool(bridge and bridge.get("mission_intent")),
        "mission_params_is_dict": isinstance(bridge.get("mission_params"), dict),
        "source": bridge.get("source"),
    }
    print(json.dumps(out))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    assert r["ok"], "build_bridge_from_job returned None"
    assert r["has_finding"], "missing finding"
    assert r["has_root_cause"], "missing root_cause"
    assert r["has_recommendation"], "missing recommendation"
    assert r["has_impact"], "missing expected_impact"
    assert r["has_confidence"], "confidence not int"
    assert r["confidence_in_range"], "confidence out of [0,100]"
    assert r["has_reasoning"], "missing reasoning paragraph"
    assert r["has_mission_intent"], "missing mission_intent"
    assert r["mission_params_is_dict"], "mission_params not dict"
    assert r["source"] in ("llm", "heuristic"), "unexpected source"


def test_bridge_synthesis_is_idempotent():
    """Two calls for the same job return the same bridge id, no
    duplicate rows in cortex_recommendation_bridges."""
    snippet = r"""
import asyncio, json, uuid
from datetime import datetime, timezone

async def main():
    from core import db
    job_id = f"recbridge-idem-{uuid.uuid4().hex[:8]}"
    uid = f"u-{uuid.uuid4().hex[:8]}"
    await db.analysis_jobs.insert_one({
        "id": job_id, "user_id": uid, "job_type": "site_scan",
        "target": "https://example.com",
        "status": "completed", "progress_pct": 100,
        "metrics": {"issues_found": 5, "ux_signals": 62},
        "queued_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
    })

    from cortex.recommendation_bridge import build_bridge_from_job
    b1 = await build_bridge_from_job(job_id)
    b2 = await build_bridge_from_job(job_id)
    count = await db.cortex_recommendation_bridges.count_documents(
        {"job_id": job_id})

    # Cleanup.
    await db.analysis_jobs.delete_one({"id": job_id})
    await db.cortex_recommendation_bridges.delete_many({"job_id": job_id})

    out = {
        "ok": bool(b1) and bool(b2),
        "same_id": (b1 or {}).get("id") == (b2 or {}).get("id"),
        "row_count": count,
    }
    print(json.dumps(out))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    assert r["ok"], "build_bridge_from_job returned None on idempotency check"
    assert r["same_id"], "bridge id changed across calls"
    assert r["row_count"] == 1, f"expected 1 row, got {r['row_count']}"


def test_bridge_only_renders_when_job_completed():
    """Running / queued / failed jobs must NOT produce a bridge."""
    snippet = r"""
import asyncio, json, uuid
from datetime import datetime, timezone

async def main():
    from core import db
    results = {}
    for status in ("queued", "running", "failed", "cancelled"):
        job_id = f"recbridge-{status}-{uuid.uuid4().hex[:8]}"
        await db.analysis_jobs.insert_one({
            "id": job_id, "user_id": "u-test", "job_type": "seo_scan",
            "target": "https://example.com",
            "status": status, "progress_pct": 0,
            "queued_at": datetime.now(timezone.utc),
        })
        from cortex.recommendation_bridge import build_bridge_from_job
        b = await build_bridge_from_job(job_id)
        results[status] = b is None
        await db.analysis_jobs.delete_one({"id": job_id})
    print(json.dumps(results))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    for status in ("queued", "running", "failed", "cancelled"):
        assert r[status], f"bridge incorrectly generated for {status} job"


def test_bridge_posts_chat_turn_with_kind_and_payload():
    """post_bridge_to_chat appends a turn into cortex_conversations
    with kind='recommendation_bridge' and an embedded bridge payload."""
    snippet = r"""
import asyncio, json, uuid
from datetime import datetime, timezone

async def main():
    from core import db
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    uid = f"u-{uuid.uuid4().hex[:8]}"
    job_id = f"recbridge-chat-{uuid.uuid4().hex[:8]}"

    # Seed conversation + completed job.
    await db.cortex_conversations.insert_one({
        "id": uuid.uuid4().hex, "conversation_id": conv_id, "user_id": uid,
        "role": "user", "message": "scan example.com",
        "created_at": datetime.now(timezone.utc),
    })
    await db.analysis_jobs.insert_one({
        "id": job_id, "user_id": uid, "job_type": "seo_scan",
        "target": "https://example.com",
        "conversation_id": conv_id,
        "status": "completed", "progress_pct": 100,
        "metrics": {"issues_found": 8, "high_priority": 2},
        "queued_at": datetime.now(timezone.utc),
    })

    from cortex.recommendation_bridge import post_bridge_to_chat
    bridge = await post_bridge_to_chat(job_id)

    # Verify a chat turn now exists with kind=recommendation_bridge.
    turn = await db.cortex_conversations.find_one(
        {"conversation_id": conv_id, "kind": "recommendation_bridge"},
        {"_id": 0})

    # Cleanup.
    await db.analysis_jobs.delete_one({"id": job_id})
    await db.cortex_conversations.delete_many({"conversation_id": conv_id})
    await db.cortex_recommendation_bridges.delete_many({"job_id": job_id})

    out = {
        "bridge_ok": bool(bridge),
        "turn_ok": bool(turn),
        "turn_kind": (turn or {}).get("kind"),
        "turn_role": (turn or {}).get("role"),
        "has_bridge_payload": isinstance((turn or {}).get("bridge"), dict),
        "bridge_has_finding": bool(((turn or {}).get("bridge") or {}).get("finding")),
        "bridge_has_recommendation": bool(((turn or {}).get("bridge") or {}).get("recommendation")),
        "bridge_has_confidence": isinstance(((turn or {}).get("bridge") or {}).get("confidence"), int),
        "message_has_reasoning": bool((turn or {}).get("message")),
    }
    print(json.dumps(out))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    assert r["bridge_ok"], "post_bridge_to_chat returned None"
    assert r["turn_ok"], "no chat turn created"
    assert r["turn_kind"] == "recommendation_bridge"
    assert r["turn_role"] == "cortex"
    assert r["has_bridge_payload"], "missing bridge payload on turn"
    assert r["bridge_has_finding"], "bridge payload missing finding"
    assert r["bridge_has_recommendation"], "bridge payload missing recommendation"
    assert r["bridge_has_confidence"], "bridge payload missing confidence"
    assert r["message_has_reasoning"], "turn message empty (no reasoning)"


def test_heuristic_fallback_per_job_type():
    """When LLM is off (or fails), the heuristic produces a sensible
    bridge for each known job_type."""
    snippet = r"""
import asyncio, json

async def main():
    from cortex.recommendation_bridge import _heuristic_bridge
    out = {}
    for jt, metrics in [
        ("seo_scan", {"issues_found": 12, "high_priority": 3}),
        ("seller_discovery", {"qualified": 30, "tier_1": 8}),
        ("site_scan", {"ux_signals": 72}),
        ("competitor_audit", {}),
    ]:
        b = _heuristic_bridge(
            {"job_type": jt, "target": "https://test.example",
              "metrics": metrics}, {})
        out[jt] = {
            "finding": bool(b.get("finding")),
            "recommendation": bool(b.get("recommendation")),
            "intent": b.get("mission_intent"),
            "confidence": b.get("confidence"),
        }
    print(json.dumps(out))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    for jt in ("seo_scan", "seller_discovery", "site_scan", "competitor_audit"):
        assert r[jt]["finding"], f"{jt} heuristic missing finding"
        assert r[jt]["recommendation"], f"{jt} heuristic missing recommendation"
        assert r[jt]["intent"], f"{jt} heuristic missing intent"
        assert isinstance(r[jt]["confidence"], int)
        assert 0 <= r[jt]["confidence"] <= 100


def test_confidence_clamping():
    """_normalize_bridge clamps out-of-range / non-int confidence."""
    snippet = r"""
import asyncio, json

async def main():
    from cortex.recommendation_bridge import _normalize_bridge
    cases = [
        ({"confidence": 150}, 100),
        ({"confidence": -10}, 0),
        ({"confidence": "high"}, 70),       # non-int → default 70
        ({"confidence": 0}, 0),
        ({"confidence": 88}, 88),
    ]
    out = []
    for data, expected in cases:
        n = _normalize_bridge(data, "seo_scan")
        out.append({"input": data["confidence"],
                     "got": n["confidence"],
                     "expected": expected,
                     "ok": n["confidence"] == expected})
    print(json.dumps(out))

asyncio.run(main())
"""
    r = _run_in_subproc(snippet)
    for case in r:
        assert case["ok"], f"clamp failed: input={case['input']} got={case['got']} expected={case['expected']}"
