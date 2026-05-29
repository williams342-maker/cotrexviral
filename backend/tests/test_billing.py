"""Stripe billing smoke tests.

Verifies the public surface area without invoking Stripe with real card data.
Full checkout flow can only be exercised by a human via the Stripe-hosted
checkout page.
"""
import os
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_billing_config_public():
    """The /billing/config endpoint is public — exposes publishable key + plans."""
    r = httpx.get(f"{API_URL}/api/billing/config", timeout=10)
    r.raise_for_status()
    body = r.json()
    assert body["publishable_key"].startswith("pk_test_")
    # New 3-tier model: starter / growth / agency
    assert "starter" in body["plans"]
    assert "growth" in body["plans"]
    assert "agency" in body["plans"]
    assert body["plans"]["starter"]["monthly"] == 15.0
    assert body["plans"]["starter"]["annual"] == 150.0
    assert body["plans"]["growth"]["monthly"] == 39.0
    assert body["plans"]["growth"]["annual"] == 390.0
    assert body["plans"]["agency"]["monthly"] == 99.0
    assert body["plans"]["agency"]["annual"] == 990.0
    assert body["plans"]["starter"]["trial_days"] == 14


def test_billing_me_requires_auth():
    r = httpx.get(f"{API_URL}/api/billing/me", timeout=10)
    assert r.status_code == 401


def test_billing_me_returns_plan_for_authed_user():
    """Auth'd user gets a plan back from /billing/me. The exact set of
    valid plans is whatever PLANS currently defines — we import it so
    this stays correct as the catalog evolves."""
    from routes.billing import PLANS
    valid_plans = {"free", *PLANS.keys()}
    r = httpx.get(f"{API_URL}/api/billing/me", headers=HEADERS, timeout=10)
    r.raise_for_status()
    body = r.json()
    assert body["plan"] in valid_plans, (
        f"billing/me returned plan={body['plan']!r}, expected one of {sorted(valid_plans)}"
    )
    assert "publishable_key" in body


def test_checkout_session_rejects_invalid_plan():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        headers=HEADERS,
        json={"plan": "enterprise", "interval": "month", "origin_url": "https://example.com"},
        timeout=10,
    )
    assert r.status_code == 400
    assert "Unknown plan" in r.text


def test_checkout_session_rejects_invalid_interval():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        headers=HEADERS,
        json={"plan": "growth", "interval": "weekly", "origin_url": "https://example.com"},
        timeout=10,
    )
    assert r.status_code == 400
    assert "interval" in r.text


def test_checkout_session_requires_auth():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        json={"plan": "growth", "interval": "month", "origin_url": "https://example.com"},
        timeout=10,
    )
    assert r.status_code == 401


def test_checkout_session_creates_real_stripe_url():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        headers=HEADERS,
        json={"plan": "growth", "interval": "month", "origin_url": "https://example.com"},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    assert body["url"].startswith("https://checkout.stripe.com/")
    assert body["session_id"].startswith("cs_test_")


def test_checkout_session_annual_works():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        headers=HEADERS,
        json={"plan": "agency", "interval": "year", "origin_url": "https://example.com"},
        timeout=15,
    )
    r.raise_for_status()
    assert "checkout.stripe.com" in r.json()["url"]


def test_checkout_session_starter_works():
    r = httpx.post(
        f"{API_URL}/api/billing/checkout-session",
        headers=HEADERS,
        json={"plan": "starter", "interval": "month", "origin_url": "https://example.com"},
        timeout=15,
    )
    r.raise_for_status()
    assert "checkout.stripe.com" in r.json()["url"]


def test_webhook_endpoint_exists_and_rejects_empty_body():
    """POST without any body — must respond 400, never 500/404."""
    r = httpx.post(f"{API_URL}/api/webhook/stripe", timeout=10)
    assert r.status_code == 400
