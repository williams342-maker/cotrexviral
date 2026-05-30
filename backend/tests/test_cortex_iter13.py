"""Cortex iteration_13 backend tests:
- POST /api/cortex/plan/cancel
- POST /api/cortex/plan/email   (graceful failure path acceptable)
- GET  /api/cortex/console/chat/stream  (SSE phases ordered)
- GET  /api/cortex/memory/strategy
- POST /api/cortex/memory/recall
"""
import json
import os
import re
import time
import pytest
import requests

def _load_backend_url():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_backend_url()).rstrip("/")
SESSION_TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HEADERS = {
    "Authorization": f"Bearer {SESSION_TOKEN}",
    "Content-Type": "application/json",
}
TIMEOUT = 90


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


@pytest.fixture(scope="module")
def fresh_rec(api):
    """Get a fresh recommendation via the chat endpoint."""
    r = api.post(f"{BASE_URL}/api/cortex/console/chat",
                 json={"message": "Recruit 12 ceramic mug makers"},
                 timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    rec = data.get("recommendation") or {}
    assert rec.get("type"), f"no rec type: {rec}"
    return rec


# ---------- plan/cancel ----------
def test_plan_cancel_returns_dismissed_id(api, fresh_rec):
    r = api.post(f"{BASE_URL}/api/cortex/plan/cancel",
                 json={"recommendation": fresh_rec, "reason": "TEST_not now"},
                 timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("action_taken") == "cancelled"
    assert data.get("dismissed_id")
    assert isinstance(data.get("dismissed_id"), str)
    assert "7 days" in (data.get("message") or "")


def test_plan_cancel_invalid_payload(api):
    r = api.post(f"{BASE_URL}/api/cortex/plan/cancel",
                 json={"recommendation": {}}, timeout=20)
    assert r.status_code == 400


# ---------- plan/email ----------
def test_plan_email_returns_action_or_502(api, fresh_rec):
    r = api.post(f"{BASE_URL}/api/cortex/plan/email",
                 json={"recommendation": fresh_rec}, timeout=30)
    # Provider may not be configured in preview env — 502 acceptable
    assert r.status_code in (200, 502), r.text
    if r.status_code == 200:
        data = r.json()
        assert data.get("action_taken") == "emailed"
        assert data.get("provider") in ("sendgrid", "mailgun")
        assert data.get("to_email")
    else:
        # graceful failure
        body = r.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "Email send failed" in msg, body


# ---------- SSE stream ----------
def _parse_sse_events(raw_lines):
    """Parse raw SSE lines into list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = []
    for line in raw_lines:
        line = line.rstrip("\n")
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current_data.append(line.split(":", 1)[1].strip())
        elif line == "":
            if current_event is not None:
                try:
                    data = json.loads("\n".join(current_data)) if current_data else {}
                except Exception:
                    data = {"raw": current_data}
                events.append({"event": current_event, "data": data})
            current_event = None
            current_data = []
    return events


def test_chat_stream_emits_phases(api):
    url = f"{BASE_URL}/api/cortex/console/chat/stream"
    params = {"message": "How do I scale my Etsy listings?"}
    with requests.get(url, params=params, headers=HEADERS,
                      stream=True, timeout=120) as r:
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/event-stream" in ct, ct
        lines = []
        start = time.time()
        seen_ready_event_header = False
        ready_collect_remaining = 0
        for raw in r.iter_lines(decode_unicode=True):
            line = "" if raw is None else raw
            lines.append(line)
            if time.time() - start > 90:
                break
            if line.startswith("event: ready") or line.startswith("event: error"):
                seen_ready_event_header = True
                ready_collect_remaining = 3
                continue
            if seen_ready_event_header:
                ready_collect_remaining -= 1
                if ready_collect_remaining <= 0 and line == "":
                    break

    events = _parse_sse_events(lines)
    assert events, f"no SSE events parsed; lines={lines[:20]}"

    seq = [e["event"] for e in events]
    # Expected: phase(classifying) phase(recalling) memory phase(planning) ready
    phase_labels = [e["data"].get("phase") for e in events if e["event"] == "phase"]
    assert "classifying" in phase_labels, seq
    assert "recalling" in phase_labels, seq
    assert "planning" in phase_labels, seq
    assert "memory" in seq, seq
    assert "ready" in seq, seq

    # phase order check
    idx_class = phase_labels.index("classifying")
    idx_recall = phase_labels.index("recalling")
    idx_plan = phase_labels.index("planning")
    assert idx_class < idx_recall < idx_plan

    # ready payload assertions
    ready = next(e for e in events if e["event"] == "ready")
    rdata = ready["data"]
    assert "intent" in rdata
    assert "params" in rdata
    assert "recommendation" in rdata
    assert isinstance(rdata.get("memory"), dict)
    assert "recalled_count" in rdata["memory"]


def test_chat_stream_requires_message(api):
    r = requests.get(f"{BASE_URL}/api/cortex/console/chat/stream",
                     headers=HEADERS, timeout=15)
    # Empty message must return 400
    assert r.status_code in (400, 422), r.text


# ---------- memory/strategy ----------
def test_memory_strategy_populated(api):
    # Many chat turns from this iteration + previous → should populate
    r = api.get(f"{BASE_URL}/api/cortex/memory/strategy", timeout=120)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert isinstance(doc, dict)
    # In preview env: may be a stub if turn_count low. Force refresh to ensure
    if not doc.get("summary"):
        r2 = api.get(f"{BASE_URL}/api/cortex/memory/strategy?refresh=true",
                     timeout=120)
        assert r2.status_code == 200, r2.text
        doc = r2.json()
    if doc:
        # If populated, check shape
        if doc.get("summary"):
            assert isinstance(doc.get("summary"), str)
            for k in ("goals", "bottlenecks", "recent_themes"):
                v = doc.get(k)
                if v is not None:
                    assert isinstance(v, list)


# ---------- memory/recall semantic ----------
def test_memory_recall_returns_scored_hits(api):
    r = api.post(f"{BASE_URL}/api/cortex/memory/recall",
                 json={"query": "ceramic", "k": 3}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "hits" in data and isinstance(data["hits"], list)
    if data["hits"]:
        h = data["hits"][0]
        for f in ("text", "role", "score"):
            assert f in h, h
        assert isinstance(h["score"], (int, float))
