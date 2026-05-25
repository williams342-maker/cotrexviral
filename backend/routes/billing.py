"""Stripe subscription billing for CortexViral.

Endpoints:
  POST /api/billing/checkout-session  → returns Stripe Checkout URL
  POST /api/billing/portal-session    → returns Customer Portal URL
  POST /api/webhook/stripe            → Stripe webhook receiver
  GET  /api/billing/me                → current user's plan + status
  GET  /api/billing/checkout/status/{session_id} → poll on return

Design choices:
- Prices are AUTO-PROVISIONED on startup. We define them in PLANS (server-side
  source of truth, never trust the frontend) and ensure_stripe_products()
  creates/looks-up matching Products + Prices in Stripe on first boot, then
  caches the resulting price IDs.
- Subscriptions use Stripe Checkout in `mode="subscription"` with a 14-day
  free trial (per pricing-page promise).
- Customer Portal handles cancel/upgrade/update-card.
- Webhook signature verification is enforced when STRIPE_WEBHOOK_SECRET is
  set. In dev (no secret), the receiver parses the event but logs a warning.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import (
    db,
    api,
    app,
    logger,
    STRIPE_SECRET_KEY,
    STRIPE_PUBLISHABLE_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_WEBHOOK_STRICT,
)
from deps import get_current_user


# -----------------------------------------------------------------------------
# Plan catalogue — server-side source of truth.
# Frontend can ONLY send a plan_id. Prices are looked up from here, never the
# request body (otherwise users could buy Agency for $0).
# Annual prices = 12 monthly − 2 months free.
# -----------------------------------------------------------------------------
PLANS = {
    "starter": {
        "name": "Starter",
        "description": "30+ content generations / month, TikTok + Reels support, improved hook engine.",
        "monthly_amount": 15_00,
        "annual_amount": 150_00,
        "trial_days": 14,
    },
    "growth": {
        "name": "Growth",
        "description": "Unlimited viral hooks, full TikTok/Reels/Shorts script engine, trend engine, A/B variations.",
        "monthly_amount": 39_00,
        "annual_amount": 390_00,
        "trial_days": 14,
    },
    "agency": {
        "name": "Agency",
        "description": "Multi-brand workspaces, bulk generation, team collaboration, API access.",
        "monthly_amount": 99_00,
        "annual_amount": 990_00,
        "trial_days": 14,
    },
}


def _ready() -> bool:
    return bool(STRIPE_SECRET_KEY)


def _stripe_init():
    if not _ready():
        raise HTTPException(
            status_code=503,
            detail="Stripe not configured. Set STRIPE_SECRET_KEY in /app/backend/.env.",
        )
    stripe.api_key = STRIPE_SECRET_KEY


# -----------------------------------------------------------------------------
# Product / price auto-provisioning
# -----------------------------------------------------------------------------
PRICE_CACHE: dict[str, str] = {}  # key: f"{plan}_{interval}" → price_id


async def ensure_stripe_products():
    """On startup, ensure each plan has a Product + monthly/annual Price in
    Stripe. Idempotent — looks for products tagged with metadata.cortexviral_plan."""
    if not _ready():
        logger.warning("Stripe not configured — skipping product provisioning.")
        return
    stripe.api_key = STRIPE_SECRET_KEY

    # Pull existing prices we created earlier (cached in mongo)
    saved = await db.stripe_products.find().to_list(length=20)
    for s in saved:
        PRICE_CACHE[s["key"]] = s["price_id"]

    for plan_id, plan in PLANS.items():
        # Find or create product
        existing = stripe.Product.list(limit=100, active=True)
        product = None
        for p in existing.auto_paging_iter():
            md = p.metadata.to_dict() if p.metadata else {}
            if md.get("cortexviral_plan") == plan_id:
                product = p
                break
        if not product:
            product = stripe.Product.create(
                name=f"CortexViral {plan['name']}",
                description=plan["description"],
                metadata={"cortexviral_plan": plan_id},
            )
            logger.info("Stripe: created product %s", product.id)

        # Ensure prices
        for interval, amount_key in [("month", "monthly_amount"), ("year", "annual_amount")]:
            cache_key = f"{plan_id}_{interval}"
            if cache_key in PRICE_CACHE:
                continue

            # Look up an existing price for this product+interval+amount
            existing_prices = stripe.Price.list(product=product.id, active=True, limit=100)
            match = None
            for pr in existing_prices.auto_paging_iter():
                recurring = pr.recurring.to_dict() if pr.recurring else {}
                if (
                    recurring.get("interval") == interval
                    and pr.unit_amount == plan[amount_key]
                    and pr.currency == "usd"
                ):
                    match = pr
                    break
            if not match:
                match = stripe.Price.create(
                    product=product.id,
                    unit_amount=plan[amount_key],
                    currency="usd",
                    recurring={"interval": interval},
                    metadata={"cortexviral_plan": plan_id, "interval": interval},
                )
                logger.info("Stripe: created price %s (%s %s)", match.id, plan_id, interval)

            PRICE_CACHE[cache_key] = match.id
            await db.stripe_products.update_one(
                {"key": cache_key},
                {"$set": {
                    "key": cache_key, "plan": plan_id, "interval": interval,
                    "price_id": match.id, "product_id": product.id,
                    "updated_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
async def _get_or_create_customer(user) -> str:
    """Return the Stripe customer ID for a user, creating one if needed."""
    user_doc = await db.users.find_one({"user_id": user.user_id}) or {}
    if user_doc.get("stripe_customer_id"):
        return user_doc["stripe_customer_id"]

    customer = stripe.Customer.create(
        email=user.email,
        name=getattr(user, "name", None) or user.email.split("@")[0],
        metadata={"cortexviral_user_id": user.user_id},
    )
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"stripe_customer_id": customer.id, "updated_at": datetime.now(timezone.utc)}},
    )
    return customer.id


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    plan: str = Field(..., description="'pro' or 'scale'")
    interval: str = Field("month", description="'month' or 'year'")
    origin_url: str = Field(..., description="window.location.origin from frontend")


@api.post("/billing/checkout-session")
async def create_checkout_session(payload: CheckoutRequest, request: Request):
    user = await get_current_user(request)
    _stripe_init()

    if payload.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.plan}'")
    if payload.interval not in ("month", "year"):
        raise HTTPException(status_code=400, detail="interval must be 'month' or 'year'")

    cache_key = f"{payload.plan}_{payload.interval}"
    price_id = PRICE_CACHE.get(cache_key)
    if not price_id:
        # Try to provision on-demand if we missed it at startup
        await ensure_stripe_products()
        price_id = PRICE_CACHE.get(cache_key)
        if not price_id:
            raise HTTPException(status_code=500, detail="Price not provisioned. Restart backend.")

    customer_id = await _get_or_create_customer(user)
    origin = payload.origin_url.rstrip("/")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=user.user_id,
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "trial_period_days": PLANS[payload.plan]["trial_days"],
            "metadata": {
                "cortexviral_user_id": user.user_id,
                "cortexviral_plan": payload.plan,
                "cortexviral_interval": payload.interval,
            },
        },
        success_url=f"{origin}/dashboard?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/pricing?billing=cancelled",
        metadata={
            "cortexviral_user_id": user.user_id,
            "cortexviral_plan": payload.plan,
            "cortexviral_interval": payload.interval,
        },
        allow_promotion_codes=True,
    )

    # Record the pending transaction
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.id,
        "user_id": user.user_id,
        "stripe_customer_id": customer_id,
        "plan": payload.plan,
        "interval": payload.interval,
        "amount": PLANS[payload.plan][f"{'monthly' if payload.interval == 'month' else 'annual'}_amount"],
        "currency": "usd",
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })

    return {"url": session.url, "session_id": session.id}


@api.post("/billing/portal-session")
async def create_portal_session(request: Request):
    user = await get_current_user(request)
    _stripe_init()

    user_doc = await db.users.find_one({"user_id": user.user_id}) or {}
    customer_id = user_doc.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet. Subscribe first.")

    body = await request.json() if request.headers.get("content-length") else {}
    origin = (body.get("origin_url") or "").rstrip("/") or "https://cortexviral.com"

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{origin}/dashboard",
    )
    return {"url": session.url}


@api.get("/billing/me")
async def billing_me(request: Request):
    user = await get_current_user(request)
    user_doc = await db.users.find_one({"user_id": user.user_id}) or {}
    # Lazy import to keep billing.py free of plan internals
    from routes.plans import get_usage
    usage = await get_usage(user.user_id)
    return {
        "plan": user_doc.get("plan", "free"),
        "subscription_status": user_doc.get("subscription_status"),
        "current_period_end": user_doc.get("current_period_end"),
        "billing_interval": user_doc.get("billing_interval"),
        "stripe_customer_id": user_doc.get("stripe_customer_id"),
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "usage": usage,
    }


@api.get("/billing/usage")
async def billing_usage(request: Request):
    """Lightweight endpoint just for the usage meter — polled more often than /me."""
    user = await get_current_user(request)
    from routes.plans import get_usage
    return await get_usage(user.user_id)


@api.get("/billing/checkout/status/{session_id}")
async def checkout_status(session_id: str, request: Request):
    """Frontend polls this after returning from Stripe to confirm payment."""
    await get_current_user(request)  # require auth, but anyone can poll their own
    _stripe_init()

    session = stripe.checkout.Session.retrieve(session_id)
    txn = await db.payment_transactions.find_one({"session_id": session_id})
    if txn and txn.get("status") != "completed" and session.payment_status == "paid":
        # Idempotently flip the user's plan even if the webhook hasn't fired yet.
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
        )
        await _apply_plan_to_user(
            user_id=txn["user_id"],
            plan=txn["plan"],
            interval=txn["interval"],
            subscription_id=session.subscription,
        )

    return {
        "session_id": session.id,
        "payment_status": session.payment_status,
        "status": session.status,
        "subscription_id": session.subscription,
    }


async def _apply_plan_to_user(user_id: str, plan: str, interval: str,
                              subscription_id: Optional[str] = None,
                              period_end: Optional[datetime] = None,
                              subscription_status: str = "active"):
    # Comped users are immune to webhook-driven plan changes — admin overrides
    # always win. We still record the subscription metadata for audit.
    existing = await db.users.find_one(
        {"user_id": user_id}, {"comped": 1, "plan": 1},
    ) or {}
    update = {
        "billing_interval": interval,
        "subscription_status": subscription_status,
        "updated_at": datetime.now(timezone.utc),
    }
    if not existing.get("comped"):
        update["plan"] = plan
    if subscription_id:
        update["subscription_id"] = subscription_id
    if period_end:
        update["current_period_end"] = period_end.isoformat()
    await db.users.update_one({"user_id": user_id}, {"$set": update})


# -----------------------------------------------------------------------------
# Webhook
# -----------------------------------------------------------------------------
# Idempotency: every Stripe event has a stable `id` (e.g. "evt_abc"). Stripe
# retries delivery until it gets a 2xx, so we MUST dedupe — re-applying a plan
# change twice can race with customer-portal events and produce flapping.
# We insert into `stripe_events` with a unique index on `event_id`; a duplicate
# is detected via a `DuplicateKeyError`.
_STRIPE_EVENTS_INDEX_BUILT = False


async def _ensure_stripe_events_index():
    global _STRIPE_EVENTS_INDEX_BUILT
    if _STRIPE_EVENTS_INDEX_BUILT:
        return
    try:
        await db.stripe_events.create_index("event_id", unique=True)
        _STRIPE_EVENTS_INDEX_BUILT = True
    except Exception:
        logger.exception("Failed to create stripe_events unique index (continuing)")


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # 1. Signature verification — strict in production.
    event = None
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET,
            )
        except stripe.error.SignatureVerificationError:
            logger.warning("Stripe webhook: BAD signature from %s", request.client.host if request.client else "?")
            raise HTTPException(status_code=400, detail="Bad signature")
        except Exception:
            logger.exception("Stripe webhook verification failed")
            raise HTTPException(status_code=400, detail="Invalid payload")
    else:
        # No secret configured. Refuse to accept unsigned events in strict mode
        # (default + production safety). Local dev / Stripe CLI without signing
        # can set STRIPE_WEBHOOK_STRICT=false to bypass.
        if STRIPE_WEBHOOK_STRICT:
            logger.error(
                "Stripe webhook REJECTED — STRIPE_WEBHOOK_SECRET is empty and "
                "STRIPE_WEBHOOK_STRICT=true. Set the signing secret in .env.",
            )
            raise HTTPException(
                status_code=503,
                detail="Webhook signature verification is required",
            )
        import json
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        logger.warning(
            "Stripe webhook accepted UNSIGNED (STRIPE_WEBHOOK_STRICT=false). "
            "Set STRIPE_WEBHOOK_SECRET + STRIPE_WEBHOOK_STRICT=true for prod.",
        )

    etype = event["type"] if isinstance(event, dict) else event.type
    data = event["data"]["object"] if isinstance(event, dict) else event.data.object
    event_id = event["id"] if isinstance(event, dict) else event.id

    # 2. Idempotency — refuse duplicate event IDs.
    await _ensure_stripe_events_index()
    try:
        await db.stripe_events.insert_one({
            "event_id": event_id,
            "type": etype,
            "received_at": datetime.now(timezone.utc),
            "redeliveries": 0,
        })
    except Exception as e:
        # DuplicateKeyError → already processed. Pymongo raises this with
        # `code=11000`; we check the str representation to keep the import light.
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            # Bump a redelivery counter on the existing row so the admin
            # "Webhook Events" page can show how often Stripe retried.
            await db.stripe_events.update_one(
                {"event_id": event_id},
                {"$inc": {"redeliveries": 1},
                 "$set": {"last_redelivery_at": datetime.now(timezone.utc)}},
            )
            logger.info("Stripe webhook: duplicate event_id=%s type=%s — skipping", event_id, etype)
            return {"received": True, "duplicate": True, "event_id": event_id}
        logger.exception("Failed to record stripe_event")
        # Don't fail the webhook — better to process than to make Stripe retry.

    logger.info("Stripe webhook: %s (event_id=%s)", etype, event_id)

    if etype == "checkout.session.completed":
        session = data
        user_id = (session.get("metadata") or {}).get("cortexviral_user_id") or session.get("client_reference_id")
        plan = (session.get("metadata") or {}).get("cortexviral_plan")
        interval = (session.get("metadata") or {}).get("cortexviral_interval", "month")
        if user_id and plan:
            await _apply_plan_to_user(
                user_id=user_id, plan=plan, interval=interval,
                subscription_id=session.get("subscription"),
                subscription_status="trialing" if PLANS.get(plan, {}).get("trial_days") else "active",
            )
            await db.payment_transactions.update_one(
                {"session_id": session.get("id")},
                {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
            )

    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        sub = data
        user_id = (sub.get("metadata") or {}).get("cortexviral_user_id")
        if not user_id:
            # Fall back: look up by customer id
            user_doc = await db.users.find_one({"stripe_customer_id": sub.get("customer")})
            user_id = user_doc.get("user_id") if user_doc else None
        if user_id:
            # Figure out the plan from the price metadata
            items = (sub.get("items") or {}).get("data") or []
            plan = None
            interval = "month"
            if items:
                price = items[0].get("price", {})
                plan = (price.get("metadata") or {}).get("cortexviral_plan")
                interval = (price.get("recurring") or {}).get("interval") or "month"
            period_end_ts = sub.get("current_period_end")
            period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
            await _apply_plan_to_user(
                user_id=user_id,
                plan=plan or "pro",
                interval=interval,
                subscription_id=sub.get("id"),
                subscription_status=sub.get("status"),
                period_end=period_end,
            )

    elif etype == "customer.subscription.deleted":
        sub = data
        user_doc = await db.users.find_one({"stripe_customer_id": sub.get("customer")})
        if user_doc:
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {
                    "plan": "free",
                    "subscription_status": "canceled",
                    "subscription_id": None,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )

    elif etype == "customer.subscription.trial_will_end":
        # Fires ~3 days before trial ends. We email the user a heads-up.
        sub = data
        user_doc = await db.users.find_one({"stripe_customer_id": sub.get("customer")})
        if user_doc and user_doc.get("email"):
            trial_end_ts = sub.get("trial_end")
            days_left = 3
            if trial_end_ts:
                delta = datetime.fromtimestamp(trial_end_ts, tz=timezone.utc) - datetime.now(timezone.utc)
                days_left = max(1, delta.days)
            from routes.email import send_trial_ending_email, fire
            fire(send_trial_ending_email(
                to=user_doc["email"],
                name=user_doc.get("name") or "",
                plan=user_doc.get("plan", "growth"),
                days_left=days_left,
            ))

    elif etype == "invoice.payment_failed":
        invoice = data
        user_doc = await db.users.find_one({"stripe_customer_id": invoice.get("customer")})
        if user_doc:
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"subscription_status": "past_due",
                          "updated_at": datetime.now(timezone.utc)}},
            )
            if user_doc.get("email") and not user_doc.get("comped"):
                from routes.email import send_past_due_email, fire
                fire(send_past_due_email(
                    to=user_doc["email"],
                    name=user_doc.get("name") or "",
                    plan=user_doc.get("plan", "growth"),
                ))

    return {"received": True}


@api.get("/billing/config")
async def billing_config():
    """Public — returns the publishable key + plan price metadata for the
    pricing UI. Safe to expose since the publishable key is meant to be public."""
    return {
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "plans": {
            plan_id: {
                "name": p["name"],
                "monthly": p["monthly_amount"] / 100,
                "annual": p["annual_amount"] / 100,
                "trial_days": p["trial_days"],
            }
            for plan_id, p in PLANS.items()
        },
    }


# -----------------------------------------------------------------------------
# Admin — list recent Stripe webhook events for debugging deliveries.
# -----------------------------------------------------------------------------
@api.get("/admin/webhook-events")
async def admin_list_webhook_events(request: Request, limit: int = 50):
    """Return the most recent Stripe events received by /api/webhook/stripe.

    Powers the /admin/webhook-events page. Useful for sanity-checking Stripe
    deliveries after a deploy, debugging why a subscription didn't apply, and
    confirming idempotency (the `duplicate` flag tells you which events were
    re-deliveries Stripe sent because of network issues)."""
    from deps import require_admin
    await require_admin(request)
    limit = max(1, min(limit, 200))

    cursor = db.stripe_events.find({}, {"_id": 0}).sort("received_at", -1).limit(limit)
    items = []
    async for row in cursor:
        if isinstance(row.get("received_at"), datetime):
            row["received_at"] = row["received_at"].isoformat()
        items.append(row)

    total = await db.stripe_events.count_documents({})
    by_type_pipe = [
        {"$group": {"_id": "$type", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 8},
    ]
    by_type = [{"type": r["_id"], "n": r["n"]} async for r in db.stripe_events.aggregate(by_type_pipe)]

    return {
        "total": total,
        "limit": limit,
        "items": items,
        "top_event_types": by_type,
    }
