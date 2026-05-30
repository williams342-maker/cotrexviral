"""Iter18 backend tests:
- Cortex conversation history endpoints (list/get/new)
- Chat persistence with conversation_id (POST + SSE stream)
- Apply Cortex's recommendation endpoint + idempotency + error cases
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HDRS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
COOKIES = {"session_token": TOKEN}


def _get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES, timeout=30, **kw)


def _post(path, json=None, **kw):
    return requests.post(f"{BASE_URL}{path}", headers=HDRS, cookies=COOKIES,
                          json=json or {}, timeout=60, **kw)


# ---------------------- Conversation history ----------------------
class TestConversationHistory:
    def test_list_conversations_shape(self):
        r = _get("/api/cortex/console/conversations?limit=50")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "count" in data
        assert isinstance(data["items"], list)
        for it in data["items"]:
            assert {"id", "title", "last_message",
                    "message_count", "updated_at", "created_at"} <= set(it.keys())
        # Items must be sorted newest-first by updated_at
        ts = [it["updated_at"] for it in data["items"] if it.get("updated_at")]
        assert ts == sorted(ts, reverse=True), "items not newest-first"

    def test_legacy_bucket_returns_thread(self):
        r = _get("/api/cortex/console/conversations?limit=50")
        items = r.json().get("items", [])
        legacy = [it for it in items if it["id"] == "legacy"]
        if legacy:
            # legacy bucket should have at least 1 message
            assert legacy[0]["message_count"] >= 1
            g = _get("/api/cortex/console/conversations/legacy?limit=200")
            assert g.status_code == 200, g.text
            body = g.json()
            assert body["id"] == "legacy"
            assert isinstance(body["turns"], list)
            assert body["count"] >= 1
        else:
            pytest.skip("No legacy bucket present for this user")

    def test_new_conversation_mints_uuid(self):
        r = _post("/api/cortex/console/conversations/new")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "conversation_id" in body and len(body["conversation_id"]) >= 16
        assert body["created_for"] == USER_ID
        assert "created_at" in body
        # Distinct calls produce distinct ids
        r2 = _post("/api/cortex/console/conversations/new")
        assert r2.json()["conversation_id"] != body["conversation_id"]

    def test_get_nonexistent_conversation_404(self):
        r = _get(f"/api/cortex/console/conversations/{uuid.uuid4().hex}")
        assert r.status_code == 404


# ---------------------- Chat persists w/ conversation_id ----------------------
class TestChatPersistence:
    def test_chat_post_persists_with_conversation_id(self):
        # Mint fresh conv
        cid = _post("/api/cortex/console/conversations/new").json()["conversation_id"]
        # Send a message
        msg = f"TEST_iter18 hi cortex {uuid.uuid4().hex[:6]}"
        r = _post("/api/cortex/console/chat",
                   json={"message": msg, "conversation_id": cid})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("conversation_id") == cid

        # New thread should now appear in the list
        time.sleep(0.5)
        items = _get("/api/cortex/console/conversations?limit=50").json()["items"]
        ids = {it["id"] for it in items}
        assert cid in ids, f"new conv {cid} not in history listing"

        # GET the thread -> contains our message
        g = _get(f"/api/cortex/console/conversations/{cid}?limit=200").json()
        msgs = [t.get("message", "") for t in g.get("turns", [])]
        assert any(msg == m for m in msgs), "user message not persisted in thread"
        # both user + cortex turns
        roles = {t.get("role") for t in g["turns"]}
        assert "user" in roles and "cortex" in roles

    def test_sse_stream_echoes_conversation_id_in_ready(self):
        cid = _post("/api/cortex/console/conversations/new").json()["conversation_id"]
        url = f"{BASE_URL}/api/cortex/console/chat/stream"
        params = {"message": f"TEST_iter18 stream ping {uuid.uuid4().hex[:6]}",
                   "conversation_id": cid}
        with requests.get(url, params=params, headers=HDRS,
                            cookies=COOKIES, stream=True, timeout=90) as resp:
            assert resp.status_code == 200
            saw_ready = False
            cid_echoed = None
            current_event = None
            for raw in resp.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                if raw.startswith("event:"):
                    current_event = raw.split(":", 1)[1].strip()
                elif raw.startswith("data:") and current_event == "ready":
                    import json
                    payload = json.loads(raw.split(":", 1)[1].strip())
                    cid_echoed = payload.get("conversation_id")
                    saw_ready = True
                    break
            assert saw_ready, "no ready event received"
            assert cid_echoed == cid, f"ready event did not echo conversation_id ({cid_echoed!r} != {cid!r})"

        # Persisted rows carry the conversation_id
        time.sleep(0.5)
        g = _get(f"/api/cortex/console/conversations/{cid}?limit=200")
        assert g.status_code == 200
        assert g.json()["count"] >= 2  # at least user + cortex


# ---------------------- Apply optimization ----------------------
class TestApplyOptimization:
    @classmethod
    def setup_class(cls):
        """Trigger a run-now to ensure at least one un-applied finding exists.
        If a finding is already applied, we'll pick a fresh one."""
        # Try to trigger; ignore failures (dedupe within 12h is fine).
        _post("/api/cortex/optimization/run-now")
        time.sleep(0.3)

    def _pick_finding(self, applied=False):
        r = _get("/api/cortex/optimization/log?limit=30")
        assert r.status_code == 200
        items = r.json()["items"]
        for it in items:
            has_applied = bool(it.get("applied_at"))
            if applied == has_applied and it.get("kind"):
                return it
        return None

    def test_apply_invalid_finding_id_404(self):
        r = _post(f"/api/cortex/optimization/{uuid.uuid4().hex}/apply")
        assert r.status_code == 404, r.text

    def test_apply_happy_path_and_idempotent(self):
        # Find an unapplied finding (or apply will be idempotent already)
        f = self._pick_finding(applied=False)
        if not f:
            f = self._pick_finding(applied=True)
            if not f:
                pytest.skip("No optimization findings to test apply against")
            # Already applied → second call should still return already_applied
            r = _post(f"/api/cortex/optimization/{f['id']}/apply")
            assert r.status_code == 200, r.text
            assert r.json().get("already_applied") is True
            assert "applied_at" in r.json()
            return

        finding_id = f["id"]
        r1 = _post(f"/api/cortex/optimization/{finding_id}/apply")
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body.get("applied") is True
        assert body.get("action_taken") in ("queued", "launched")
        assert isinstance(body.get("label"), str) and body["label"]
        assert isinstance(body.get("result"), dict)

        # Second call → idempotent
        r2 = _post(f"/api/cortex/optimization/{finding_id}/apply")
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2.get("already_applied") is True
        assert "applied_at" in body2

        # Verify applied_at is stamped on the finding via log endpoint
        log = _get("/api/cortex/optimization/log?limit=30").json()["items"]
        match = next((x for x in log if x["id"] == finding_id), None)
        assert match is not None
        assert match.get("applied_at") is not None
        assert match.get("applied_action_taken") in ("queued", "launched")
