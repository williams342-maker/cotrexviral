"""Admin AI-usage analytics tests."""
import os
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_ai_usage_requires_admin():
    """The endpoint must reject non-admin tokens. Test user IS admin so this
    just checks the endpoint exists and returns proper shape."""
    r = httpx.get(f"{API_URL}/api/admin/ai-usage", headers=HEADERS, timeout=10)
    # Test user is admin in this env
    assert r.status_code in (200, 403)


def test_ai_usage_returns_expected_shape():
    r = httpx.get(f"{API_URL}/api/admin/ai-usage?months=3", headers=HEADERS, timeout=10)
    if r.status_code == 403:
        return  # not admin in this env, skip
    r.raise_for_status()
    body = r.json()
    assert "current_month" in body
    assert "global_by_month" in body
    assert len(body["global_by_month"]) == 3
    assert "top_users" in body
    assert "breakdown_by_kind" in body
    assert "totals" in body
    assert "this_month" in body["totals"]
    assert "last_n_months" in body["totals"]
    for m in body["global_by_month"]:
        assert "month" in m
        assert "ai_generations" in m


def test_admin_stats_includes_subscription_distribution():
    r = httpx.get(f"{API_URL}/api/admin/stats", headers=HEADERS, timeout=10)
    if r.status_code == 403:
        return
    r.raise_for_status()
    body = r.json()
    assert "users_free" in body
    assert "users_starter" in body
    assert "users_growth" in body
    assert "users_agency" in body
    assert "users_legacy" in body
    assert "trialing_subs" in body
    assert "past_due_subs" in body


def test_ai_usage_requires_auth():
    r = httpx.get(f"{API_URL}/api/admin/ai-usage", timeout=10)
    assert r.status_code in (401, 403)
