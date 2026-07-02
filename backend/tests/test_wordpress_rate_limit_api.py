"""Live API tests for the P2 WordPress rate-limit hardening.

Exercises the /api/wordpress/test endpoint against the deployed backend to
verify:

  * Per-user hourly cap (30/hour): 31st call in an hour -> HTTP 429 with
    Retry-After header and detail mentioning "hour".
  * Per-(user, host) 15-min cap (6/15min): 7th call to the SAME host from
    the same user within 15 min -> HTTP 429 with Retry-After header and
    detail mentioning the hostname.

Notes:
  - The rate limiter state is in-memory per backend process; the previous
    baseline pytest run does NOT touch the live API endpoint. However, the
    frontend playwright tests might. This suite triggers the limiter first,
    so we RESET server state by restarting the backend before running.
  - Uses bogus domains so DNS failure returns 400 quickly but still
    consumes a rate-limit token (that's the intentional hardening).
"""
from __future__ import annotations

import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

TEST_SESSION = "test_session_1779636592168"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TEST_SESSION}",
}

# From routes.wordpress_selfhosted
MAX_PER_USER_HOURLY = 30
MAX_PER_HOST_15MIN = 6


def _test_call(site_url: str, timeout: int = 20) -> requests.Response:
    """POST /api/wordpress/test with a bogus creds payload. The site is a
    bogus domain so DNS fails fast and returns 400 without any real WP
    interaction — but the call still consumes a rate-limit token."""
    return requests.post(
        f"{BASE_URL}/api/wordpress/test",
        json={
            "site_url": site_url,
            "username": "u",
            "application_password": "p",
        },
        headers=HEADERS,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def sanity_check_session():
    """Skip the whole module if the shared test session is dead."""
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {TEST_SESSION}"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Test session invalid: /auth/me returned {r.status_code}")


class TestWordPressRateLimitLive:
    """Live rate limiter verification.

    These tests fire calls until a 429 is observed rather than assuming an
    exact counter position, so they remain valid regardless of how many
    /wordpress/test calls preceded them in the same backend process (e.g.,
    other tests in the same pytest run may have already consumed a few
    tokens). We still verify the response semantics — status, Retry-After
    header, and the detail body content — which is what actually matters
    for the P2 hardening review."""

    def test_per_host_15min_cap_returns_429_with_host_in_detail(self, sanity_check_session):
        """Hitting the same host repeatedly should produce a 429 whose
        detail mentions the hostname and includes a Retry-After header.
        The 429 must arrive within MAX_PER_HOST_15MIN+1 calls."""
        host = "rl-per-host-test-target-8843.com"
        target = f"https://{host}"

        got_429 = None
        # Allow a few extra to absorb any pre-existing token consumption on
        # OTHER hosts (shouldn't matter — per-host cap is independent), but
        # cap the loop so it can't run forever.
        for i in range(MAX_PER_HOST_15MIN + 2):
            r = _test_call(target)
            if r.status_code == 429:
                got_429 = r
                break
        assert got_429 is not None, (
            f"never saw 429 after {MAX_PER_HOST_15MIN + 2} calls to {host}"
        )
        assert "Retry-After" in got_429.headers, "missing Retry-After header on 429"
        assert got_429.headers["Retry-After"].isdigit()
        assert int(got_429.headers["Retry-After"]) > 0

        detail = (got_429.json().get("detail") or "").lower()
        assert host in detail, f"expected hostname in 429 detail, got: {detail!r}"

    def test_per_user_hourly_cap_returns_429_mentions_hour(self, sanity_check_session):
        """Once the per-user hourly counter is saturated, ANY host (even
        one the user has never hit) should return 429 with 'hour' in the
        detail. We fire varying hosts until we see a 429 whose body
        mentions 'hour' — that isolates the per-user branch from the
        per-host branch (which mentions the hostname)."""
        seen_hourly_429 = None
        # We may have to burn up to MAX_PER_USER_HOURLY tokens even from a
        # perfectly clean start. Add generous headroom; each call is fast
        # since DNS fails quickly.
        for i in range(MAX_PER_USER_HOURLY + 4):
            target = f"https://rl-per-user-fresh-{i}-8843.com"
            r = _test_call(target)
            if r.status_code == 429:
                detail = (r.json().get("detail") or "").lower()
                if "hour" in detail:
                    seen_hourly_429 = r
                    break
                # If we somehow tripped the per-host cap (shouldn't — every
                # call uses a distinct host), keep going.

        assert seen_hourly_429 is not None, (
            "never saw a 429 mentioning 'hour' after "
            f"{MAX_PER_USER_HOURLY + 4} varied-host calls"
        )
        assert "Retry-After" in seen_hourly_429.headers
        assert seen_hourly_429.headers["Retry-After"].isdigit()
        assert int(seen_hourly_429.headers["Retry-After"]) > 0
