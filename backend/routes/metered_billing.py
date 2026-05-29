"""Cortex Autopilot — metered Stripe billing on top of `agent_usage_ledger`.

Concept
-------
The user opts into the "Cortex Autopilot" plan via a normal Stripe Checkout
subscription. That plan has a `$0/month` base AND a metered price referencing
a Stripe `Meter` named `cortex_autopilot_usage_usd_cents`.

Each time `routes.autonomy.record_usage()` writes a USD delta to the ledger,
this module fires `stripe.billing.MeterEvent.create(...)` so the Stripe
side accumulates the same number the operator sees on the Autonomy page.
End of the billing cycle → Stripe invoices the customer for the accumulated
USD spend × the multiplier configured on the metered Price (default 1.5x →
healthy markup on top of raw LLM cost).

Key rules
~~~~~~~~~
- **Opt-in only**: the tick is a no-op unless `users.autopilot_enabled` is True.
  Setting this flag is owned by the Stripe webhook handler — never by the user.
- **Best-effort**: any Stripe error logs + swallows. A ledger write must never
  fail because the meter call hiccupped.
- **Idempotent**: each tick passes a deterministic `identifier`
  `f"{user_id}:{iso_week}:{ledger_seq}"` so Stripe rejects accidental re-deliveries.
- **No PII**: the meter event payload contains the Stripe customer id + an
  integer cents value. Nothing else.

The Stripe Meter + Price are provisioned by `billing.ensure_stripe_products()`
on startup so this module never needs to create resources on the fly.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import Request

from core import api, db, STRIPE_SECRET_KEY
from deps import get_current_user

logger = logging.getLogger(__name__)

# Public constants — referenced by billing.py + tests.
AUTOPILOT_PLAN_ID = "cortex_autopilot"
AUTOPILOT_METER_EVENT_NAME = "cortex_autopilot_usage_usd_cents"


# ---------------------------------------------------------------------
# Tick — fired from routes.autonomy.record_usage
# ---------------------------------------------------------------------
async def tick_autopilot_meter(
    user_id: str,
    usd: float,
    *,
    ledger_seq: Optional[str] = None,
) -> bool:
    """Forward a USD ledger delta to Stripe's MeterEvent API.

    Returns True if the event was POSTed, False if skipped (any reason).
    Never raises — Stripe outages must not break the calling ledger write.

    `ledger_seq` is any deterministic short token (we use uuid4 hex by
    default) that, combined with the user_id + iso-week, forms a stable
    `identifier`. Stripe deduplicates by identifier so retried writes
    won't double-bill.
    """
    if usd <= 0:
        return False
    if not STRIPE_SECRET_KEY:
        return False

    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "autopilot_enabled": 1, "stripe_customer_id": 1},
    )
    if not user_doc:
        return False
    if not user_doc.get("autopilot_enabled"):
        return False
    customer_id = user_doc.get("stripe_customer_id")
    if not customer_id:
        # Edge case: subscribed via a flow that didn't persist the id. Log
        # once so support can repair. Never block.
        logger.warning("autopilot tick skipped — user=%s has no stripe_customer_id", user_id)
        return False

    # Stripe meters bill in INTEGER units. Send cents so the metered Price
    # can be configured as "$0.015 per unit" → $1.50 per $1 of LLM spend.
    cents = max(1, int(round(usd * 100)))

    seq = ledger_seq or uuid.uuid4().hex[:12]
    iso_week = _iso_week_key()
    # Deterministic id → Stripe rejects duplicates with the same value.
    identifier = f"{user_id}:{iso_week}:{seq}"

    try:
        stripe.api_key = STRIPE_SECRET_KEY
        # The python SDK exposes the v2 Meter Events API under
        # `stripe.billing.MeterEvent`. `payload.value` MUST be a string per
        # the v2 API spec — Stripe rejects integers/floats with
        # `"You must pass a string for the value field"`.
        stripe.billing.MeterEvent.create(
            event_name=AUTOPILOT_METER_EVENT_NAME,
            identifier=identifier,
            payload={
                "stripe_customer_id": customer_id,
                "value":              str(cents),
            },
            timestamp=int(datetime.now(timezone.utc).timestamp()),
        )
    except Exception:
        logger.exception("autopilot meter tick failed (user=%s usd=%.6f)", user_id, usd)
        return False

    # Mirror the tick into a local audit log so support can reconcile if
    # Stripe ever drops a bill. ~1 row per LLM call for autopilot users.
    try:
        await db.autopilot_meter_events.insert_one({
            "id":          uuid.uuid4().hex,
            "user_id":     user_id,
            "customer_id": customer_id,
            "iso_week":    iso_week,
            "identifier":  identifier,
            "cents":       cents,
            "usd":         round(float(usd), 6),
            "created_at":  datetime.now(timezone.utc),
        })
    except Exception:
        logger.debug("autopilot meter mirror skipped", exc_info=True)

    return True


# ---------------------------------------------------------------------
# Read endpoints — the Autonomy page surfaces these
# ---------------------------------------------------------------------
@api.get("/billing/autopilot/status")
async def autopilot_status(request: Request):
    """Returns the user's autopilot opt-in + this week's accumulated spend.

    Powers the "Autopilot ON / billed $X.YZ this week" badge on the
    Team Performance + Autonomy pages."""
    user = await get_current_user(request)
    doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "autopilot_enabled": 1, "stripe_customer_id": 1,
         "subscription_status": 1, "plan": 1},
    ) or {}
    iso_week = _iso_week_key()

    cursor = db.autopilot_meter_events.find(
        {"user_id": user.user_id, "iso_week": iso_week},
        {"_id": 0, "cents": 1, "usd": 1, "created_at": 1, "identifier": 1},
    )
    rows = await cursor.to_list(length=5000)
    total_cents = sum(r.get("cents", 0) for r in rows)
    total_usd = round(sum(r.get("usd", 0.0) for r in rows), 4)

    return {
        "enabled":                 bool(doc.get("autopilot_enabled")),
        "stripe_customer_id":      doc.get("stripe_customer_id"),
        "plan":                    doc.get("plan"),
        "subscription_status":     doc.get("subscription_status"),
        "iso_week":                iso_week,
        "this_week_cents":         total_cents,
        "this_week_usd":           total_usd,
        "this_week_tick_count":    len(rows),
        "meter_event_name":        AUTOPILOT_METER_EVENT_NAME,
    }


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _iso_week_key(when: Optional[datetime] = None) -> str:
    dt = when or datetime.now(timezone.utc)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


async def set_autopilot_enabled(user_id: str, enabled: bool,
                                *, reason: str = "webhook") -> None:
    """Webhook entrypoint — flips the opt-in flag and audits the change."""
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "autopilot_enabled":    bool(enabled),
            "autopilot_updated_at": datetime.now(timezone.utc),
            "updated_at":           datetime.now(timezone.utc),
        }},
    )
    try:
        await db.autopilot_audit.insert_one({
            "id":         uuid.uuid4().hex,
            "user_id":    user_id,
            "enabled":    bool(enabled),
            "reason":     reason,
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.debug("autopilot audit skipped", exc_info=True)
