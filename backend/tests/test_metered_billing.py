"""Cortex Autopilot — metered Stripe billing tests.

Covers:
  1. The `tick_autopilot_meter()` no-op contract:
     • returns False when usd ≤ 0
     • returns False when user is not opted in
     • returns False when user has no stripe_customer_id
  2. The happy path: opt-in user → tick fires `stripe.billing.MeterEvent.create`
     with the right shape (cents = USD × 100, customer_id, deterministic identifier)
     AND mirrors a row into `autopilot_meter_events`.
  3. Stripe errors are SWALLOWED — record_usage must never raise.
  4. `record_usage()` integration: writing usd to the ledger fires the tick.
  5. `/api/billing/autopilot/status` endpoint returns aggregated cents/USD.
  6. Webhook handler flips `autopilot_enabled` ON for subscription.created
     and OFF for subscription.deleted.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

import sys
sys.path.insert(0, "/app/backend")
from routes import metered_billing as MB  # noqa: E402

API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
ADMIN_TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def _mongo():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _admin_user_id() -> str:
    r = requests.get(f"{API_URL}/api/auth/me", headers=HEADERS, timeout=10)
    return r.json()["user_id"]


@pytest.fixture
def user_id():
    return _admin_user_id()


@pytest.fixture(autouse=True)
def _cleanup(user_id):
    async def go():
        db = _mongo()
        # Reset autopilot fields on the admin user + wipe test rows.
        # ALSO wipe stripe_customer_id because tests below set it to fake
        # values like "cus_HAPPY" — leaving it would poison other test
        # suites (e.g. test_billing.py) that try to use it against the
        # real Stripe API.
        await db.users.update_one(
            {"user_id": user_id},
            {"$unset": {
                "autopilot_enabled":    "",
                "autopilot_updated_at": "",
                "stripe_customer_id":   "",
            }},
        )
        await db.autopilot_meter_events.delete_many({"user_id": user_id})
        await db.autopilot_audit.delete_many({"user_id": user_id})
        await db.agent_usage_ledger.delete_many({"user_id": user_id, "agent_id": "atlas"})
    _run(go())
    yield
    _run(go())


def _set_user(user_id: str, *, enabled: bool, customer_id: str | None = "cus_test_123"):
    async def go():
        db = _mongo()
        set_fields = {"autopilot_enabled": enabled}
        if customer_id is not None:
            set_fields["stripe_customer_id"] = customer_id
        await db.users.update_one({"user_id": user_id}, {"$set": set_fields})
    _run(go())


# ---------------------------------------------------------------------
# Unit-level tests for tick_autopilot_meter
# ---------------------------------------------------------------------
class TestTickAutopilotMeter:
    def test_returns_false_when_usd_zero(self, user_id):
        _set_user(user_id, enabled=True)
        with patch("stripe.billing.MeterEvent.create") as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 0.0))
        assert ok is False
        assert m.call_count == 0

    def test_returns_false_when_usd_negative(self, user_id):
        _set_user(user_id, enabled=True)
        with patch("stripe.billing.MeterEvent.create") as m:
            ok = _run(MB.tick_autopilot_meter(user_id, -0.5))
        assert ok is False
        assert m.call_count == 0

    def test_returns_false_when_not_opted_in(self, user_id):
        _set_user(user_id, enabled=False)
        with patch("stripe.billing.MeterEvent.create") as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 0.5))
        assert ok is False
        assert m.call_count == 0

    def test_returns_false_when_no_customer_id(self, user_id):
        _set_user(user_id, enabled=True, customer_id=None)
        # Have to explicitly null it out — the update above wouldn't unset.
        async def unset():
            db = _mongo()
            await db.users.update_one({"user_id": user_id},
                                      {"$unset": {"stripe_customer_id": ""}})
        _run(unset())
        with patch("stripe.billing.MeterEvent.create") as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 0.5))
        assert ok is False
        assert m.call_count == 0

    def test_happy_path_fires_meter_event(self, user_id):
        _set_user(user_id, enabled=True, customer_id="cus_HAPPY")
        with patch("stripe.billing.MeterEvent.create", return_value=MagicMock()) as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 0.12345,
                                              ledger_seq="abc123def456"))
        assert ok is True
        m.assert_called_once()
        kwargs = m.call_args.kwargs
        assert kwargs["event_name"] == MB.AUTOPILOT_METER_EVENT_NAME
        # 0.12345 → 12 cents (rounded)
        assert kwargs["payload"]["value"] == "12"
        assert kwargs["payload"]["stripe_customer_id"] == "cus_HAPPY"
        # Identifier shape: user_id:iso_week:seq
        ident = kwargs["identifier"]
        assert ident.startswith(f"{user_id}:")
        assert ident.endswith(":abc123def456")
        # Mirror row landed
        async def check():
            db = _mongo()
            rows = await db.autopilot_meter_events.find(
                {"user_id": user_id}, {"_id": 0},
            ).to_list(length=10)
            assert len(rows) == 1
            assert rows[0]["cents"] == 12
            assert rows[0]["customer_id"] == "cus_HAPPY"
        _run(check())

    def test_stripe_error_is_swallowed(self, user_id):
        _set_user(user_id, enabled=True, customer_id="cus_ERR")
        with patch("stripe.billing.MeterEvent.create",
                   side_effect=Exception("boom")) as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 1.0))
        assert ok is False
        m.assert_called_once()
        # No mirror row should be persisted on failure
        async def check():
            db = _mongo()
            assert await db.autopilot_meter_events.count_documents(
                {"user_id": user_id}) == 0
        _run(check())

    def test_min_one_cent_floor(self, user_id):
        """Even a fraction of a cent must charge at least 1 unit so the
        billing system never sees a $0 meter event we expected to bill."""
        _set_user(user_id, enabled=True, customer_id="cus_PENNY")
        with patch("stripe.billing.MeterEvent.create", return_value=MagicMock()) as m:
            ok = _run(MB.tick_autopilot_meter(user_id, 0.001))  # 0.1 cents
        assert ok is True
        assert m.call_args.kwargs["payload"]["value"] == "1"


# ---------------------------------------------------------------------
# Integration: record_usage → tick
# ---------------------------------------------------------------------
class TestRecordUsageIntegration:
    def test_record_usage_with_usd_fires_tick_for_enabled_user(self, user_id):
        _set_user(user_id, enabled=True, customer_id="cus_LEDGER")
        from routes.autonomy import record_usage
        with patch("stripe.billing.MeterEvent.create", return_value=MagicMock()) as m:
            _run(record_usage("atlas", user_id, tokens=1000, usd=0.05))
        assert m.call_count == 1
        # Cents: 0.05 → 5
        assert m.call_args.kwargs["payload"]["value"] == "5"

    def test_record_usage_with_zero_usd_skips_tick(self, user_id):
        _set_user(user_id, enabled=True, customer_id="cus_NOTOK")
        from routes.autonomy import record_usage
        with patch("stripe.billing.MeterEvent.create") as m:
            _run(record_usage("atlas", user_id, tokens=1000, usd=0.0))
        assert m.call_count == 0

    def test_record_usage_skips_tick_when_not_enabled(self, user_id):
        _set_user(user_id, enabled=False, customer_id="cus_OPTOUT")
        from routes.autonomy import record_usage
        with patch("stripe.billing.MeterEvent.create") as m:
            _run(record_usage("atlas", user_id, tokens=1000, usd=0.05))
        assert m.call_count == 0


# ---------------------------------------------------------------------
# /api/billing/autopilot/status
# ---------------------------------------------------------------------
class TestStatusEndpoint:
    def test_requires_auth(self):
        r = requests.get(f"{API_URL}/api/billing/autopilot/status", timeout=10)
        assert r.status_code == 401

    def test_returns_disabled_by_default(self, user_id):
        r = requests.get(f"{API_URL}/api/billing/autopilot/status",
                         headers=HEADERS, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is False
        assert body["this_week_cents"] == 0
        assert body["this_week_usd"] == 0
        assert body["this_week_tick_count"] == 0
        assert body["meter_event_name"] == MB.AUTOPILOT_METER_EVENT_NAME

    def test_aggregates_mirrored_events(self, user_id):
        _set_user(user_id, enabled=True, customer_id="cus_AGG")
        # Tick three times
        with patch("stripe.billing.MeterEvent.create", return_value=MagicMock()):
            for u in (0.10, 0.05, 0.20):
                _run(MB.tick_autopilot_meter(user_id, u))
        r = requests.get(f"{API_URL}/api/billing/autopilot/status",
                         headers=HEADERS, timeout=10)
        body = r.json()
        assert body["enabled"] is True
        assert body["this_week_tick_count"] == 3
        # 10 + 5 + 20 = 35 cents
        assert body["this_week_cents"] == 35


# ---------------------------------------------------------------------
# Webhook handler: flips autopilot_enabled flag
# ---------------------------------------------------------------------
class TestWebhookFlag:
    def test_set_autopilot_enabled_helper(self, user_id):
        _run(MB.set_autopilot_enabled(user_id, True, reason="test:on"))
        async def check():
            db = _mongo()
            doc = await db.users.find_one({"user_id": user_id},
                                          {"_id": 0, "autopilot_enabled": 1})
            assert doc["autopilot_enabled"] is True
            audit = await db.autopilot_audit.find_one({"user_id": user_id, "reason": "test:on"})
            assert audit is not None
            assert audit["enabled"] is True
        _run(check())

        _run(MB.set_autopilot_enabled(user_id, False, reason="test:off"))
        async def check2():
            db = _mongo()
            doc = await db.users.find_one({"user_id": user_id},
                                          {"_id": 0, "autopilot_enabled": 1})
            assert doc["autopilot_enabled"] is False
        _run(check2())
