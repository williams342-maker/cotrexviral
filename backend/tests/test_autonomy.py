"""Autonomy Budgets — Phase 5 of the Autonomous Growth Team.

Covers:
  - Auth gating on every endpoint
  - record_usage atomic upsert per ISO week
  - check_budget returns the right shape + percentages
  - can_auto_approve gates on the irreversible cap
  - List endpoint shows all 8 personas with budget snapshot
  - GET single agent budget
  - Admin reset wipes the current week's row
  - Briefs auto-approve path: autopilot + opt-in + budget-OK → campaign spawned
    skipping HITL; cap exhaustion → falls back to pending
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin_user_id():
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    return r.json().get("user_id") if r.status_code == 200 else None


@pytest.fixture
def admin_user_id():
    uid = _admin_user_id()
    if not uid:
        pytest.skip("Admin test user missing")
    return uid


@pytest.fixture(autouse=True)
def cleanup(admin_user_id):
    async def go():
        db = _mongo()
        await db.agent_usage_ledger.delete_many({"user_id": admin_user_id})
        await db.autopilot_settings.delete_many({"user_id": admin_user_id})
        await db.proposed_briefs.delete_many({"user_id": admin_user_id, "title": {"$regex": "pytest_"}})
        await db.campaigns.delete_many({"user_id": admin_user_id, "name": {"$regex": "pytest_"}})
    _run(go())
    yield
    _run(go())


class TestAuth:
    def test_endpoints_require_auth(self):
        for path, method, body in [
            ("/api/agents/budgets",           "get",  None),
            ("/api/agents/budgets/atlas",     "get",  None),
            ("/api/agents/budgets/reset",     "post", {"agent_id": "atlas"}),
        ]:
            kw = {"timeout": 10}
            if body is not None: kw["json"] = body
            r = getattr(requests, method)(f"{API_URL}{path}", **kw)
            assert r.status_code == 401, f"{method.upper()} {path} → {r.status_code}"


class TestListAndGet:
    def test_list_returns_all_personas(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/agents/budgets", headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        agent_ids = {it["agent_id"] for it in body["items"]}
        assert {"vera", "atlas", "nova", "rae", "lyra", "echo", "ori", "jules"}.issubset(agent_ids)
        # Each row has the expected shape
        for it in body["items"]:
            for k in ("tokens_used", "tokens_cap", "tokens_pct",
                      "usd_used", "usd_cap", "usd_pct",
                      "irreversible_used", "irreversible_cap", "irreversible_pct",
                      "can_act", "headroom_pct"):
                assert k in it, f"missing {k} in {it}"

    def test_single_agent(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/agents/budgets/atlas",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["agent_id"] == "atlas"
        assert r.json()["tokens_used"] == 0
        assert r.json()["can_act"] is True

    def test_unknown_agent_404(self, admin_user_id):
        r = requests.get(f"{API_URL}/api/agents/budgets/nobody",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 404


class TestRecordUsageAndCheck:
    def test_record_usage_increments(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, check_budget

        # Burn 2 irreversible from Atlas's budget
        _run(record_usage("atlas", admin_user_id, irreversible=1, tokens=500, usd=0.05))
        _run(record_usage("atlas", admin_user_id, irreversible=1, tokens=500, usd=0.05))
        snap = _run(check_budget("atlas", admin_user_id))
        assert snap["irreversible_used"] == 2
        assert snap["tokens_used"] == 1000
        assert abs(snap["usd_used"] - 0.1) < 0.001
        assert snap["can_act"] is True

    def test_check_budget_pct_math(self, admin_user_id):
        """tokens_pct = used/cap*100 with cap from PERSONAS registry."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, check_budget
        from routes.agent_personas import PERSONAS

        atlas_cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]
        irr_cap = atlas_cap["max_irreversible_per_week"]
        # Burn exactly to the cap
        for _ in range(irr_cap):
            _run(record_usage("atlas", admin_user_id, irreversible=1))
        snap = _run(check_budget("atlas", admin_user_id))
        assert snap["irreversible_used"] == irr_cap
        assert snap["irreversible_pct"] == 100.0
        assert snap["can_act"] is False
        assert snap["headroom_pct"] >= 100.0


class TestCanAutoApprove:
    def test_blocks_when_irreversible_exhausted(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, can_auto_approve
        from routes.agent_personas import PERSONAS

        atlas_cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]
        for _ in range(atlas_cap["max_irreversible_per_week"]):
            _run(record_usage("atlas", admin_user_id, irreversible=1))
        allowed, reason = _run(can_auto_approve("atlas", admin_user_id))
        assert allowed is False
        assert "irreversible" in reason.lower()

    def test_allows_when_budget_healthy(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import can_auto_approve
        allowed, reason = _run(can_auto_approve("atlas", admin_user_id))
        assert allowed is True


class TestAdminReset:
    def test_reset_requires_admin(self):
        # No auth → 401 (already covered above). Empty-key body without auth.
        r = requests.post(f"{API_URL}/api/agents/budgets/reset",
                          json={"agent_id": "atlas"}, timeout=10)
        assert r.status_code == 401

    def test_reset_wipes_week_row(self, admin_user_id):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage, check_budget
        _run(record_usage("atlas", admin_user_id, irreversible=2))
        before = _run(check_budget("atlas", admin_user_id))
        assert before["irreversible_used"] == 2

        r = requests.post(f"{API_URL}/api/agents/budgets/reset",
                          json={"agent_id": "atlas"}, headers=HEADERS, timeout=10)
        assert r.status_code == 200
        after = _run(check_budget("atlas", admin_user_id))
        assert after["irreversible_used"] == 0


class TestBriefsAutoApprove:
    """Phase 3 + Phase 5 integration: autopilot scan with auto_approve_briefs=true
    AND budget healthy → brief is inserted as approved + campaign spawned."""

    def test_autopilot_auto_approves_when_opted_in_and_budget_ok(self, admin_user_id):
        # Opt the user into autopilot + auto-approve
        async def setup():
            db = _mongo()
            await db.autopilot_settings.update_one(
                {"user_id": admin_user_id},
                {"$set": {
                    "user_id":             admin_user_id,
                    "briefs_mode":         "autopilot",
                    "auto_approve_briefs": True,
                    "updated_at":          datetime.now(timezone.utc),
                }}, upsert=True,
            )
        _run(setup())

        # Persist a brief directly via the helper so we don't burn an LLM call
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.briefs import _persist_proposals
        briefs = [{
            "title":               "pytest_phase5_auto",
            "hypothesis":          "Auto-approval test",
            "body":                "Auto-approval path body text " * 5,
            "rationale":           "Test signal",
            "suggested_platforms": ["instagram"],
            "target_metric":       "engagements",
        }]
        saved = _run(_persist_proposals(admin_user_id, briefs, source="autopilot"))
        assert len(saved) == 1
        b = saved[0]
        assert b["status"] == "approved"
        assert b["auto_approved"] is True
        assert b["resolved_into_campaign_id"]
        # Campaign exists
        async def check():
            db = _mongo()
            camp = await db.campaigns.find_one({"id": b["resolved_into_campaign_id"]})
            assert camp is not None
            assert "Auto-approved" in (camp.get("notes") or "")
        _run(check())

    def test_autopilot_falls_back_to_pending_when_opt_out(self, admin_user_id):
        # Autopilot ON, but auto_approve_briefs OFF → status=pending
        async def setup():
            db = _mongo()
            await db.autopilot_settings.update_one(
                {"user_id": admin_user_id},
                {"$set": {
                    "user_id":             admin_user_id,
                    "briefs_mode":         "autopilot",
                    "auto_approve_briefs": False,
                    "updated_at":          datetime.now(timezone.utc),
                }}, upsert=True,
            )
        _run(setup())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.briefs import _persist_proposals
        briefs = [{
            "title": "pytest_phase5_optout", "hypothesis": "x",
            "body":  "Opt-out path body " * 5, "rationale": "x",
            "suggested_platforms": ["x"], "target_metric": "engagements",
        }]
        saved = _run(_persist_proposals(admin_user_id, briefs, source="autopilot"))
        assert saved[0]["status"] == "pending"
        assert saved[0]["auto_approved"] is False

    def test_autopilot_falls_back_when_budget_exhausted(self, admin_user_id):
        """Budget exhausted → fall back to HITL even when opted in."""
        # Opt in + auto-approve
        async def setup():
            db = _mongo()
            await db.autopilot_settings.update_one(
                {"user_id": admin_user_id},
                {"$set": {
                    "user_id": admin_user_id,
                    "briefs_mode": "autopilot",
                    "auto_approve_briefs": True,
                    "updated_at": datetime.now(timezone.utc),
                }}, upsert=True,
            )
        _run(setup())

        # Burn Atlas's irreversible cap
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.autonomy import record_usage
        from routes.agent_personas import PERSONAS
        cap = next(p for p in PERSONAS if p["id"] == "atlas")["autonomy_budget"]["max_irreversible_per_week"]
        for _ in range(cap):
            _run(record_usage("atlas", admin_user_id, irreversible=1))

        from routes.briefs import _persist_proposals
        briefs = [{
            "title": "pytest_phase5_capped", "hypothesis": "x",
            "body":  "Cap-exhausted body " * 5, "rationale": "x",
            "suggested_platforms": [], "target_metric": "engagements",
        }]
        saved = _run(_persist_proposals(admin_user_id, briefs, source="autopilot"))
        # Even though opted in, the brief stays pending because budget is exhausted.
        assert saved[0]["status"] == "pending"
        assert saved[0]["auto_approved"] is False

    def test_manual_source_never_auto_approves(self, admin_user_id):
        """Manual 'Propose now' always goes to inbox even with opt-in toggled."""
        async def setup():
            db = _mongo()
            await db.autopilot_settings.update_one(
                {"user_id": admin_user_id},
                {"$set": {
                    "user_id": admin_user_id,
                    "briefs_mode": "manual",
                    "auto_approve_briefs": True,
                    "updated_at": datetime.now(timezone.utc),
                }}, upsert=True,
            )
        _run(setup())

        import sys
        sys.path.insert(0, "/app/backend")
        from routes.briefs import _persist_proposals
        briefs = [{
            "title": "pytest_manual_no_auto", "hypothesis": "x",
            "body":  "Manual path " * 5, "rationale": "x",
            "suggested_platforms": [], "target_metric": "engagements",
        }]
        saved = _run(_persist_proposals(admin_user_id, briefs, source="manual"))
        assert saved[0]["status"] == "pending"
        assert saved[0]["auto_approved"] is False


class TestBriefSettingsAutoApproveToggle:
    def test_toggle_auto_approve(self, admin_user_id):
        r = requests.put(f"{API_URL}/api/briefs/settings",
                         json={"auto_approve_briefs": True},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["auto_approve_briefs"] is True

        r = requests.put(f"{API_URL}/api/briefs/settings",
                         json={"auto_approve_briefs": False},
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200
        assert r.json()["auto_approve_briefs"] is False
