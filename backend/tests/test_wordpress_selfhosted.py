"""Tests for the WordPress self-hosted connector.

Covers:
  - Fernet encrypt/decrypt round trip
  - URL normalization
  - _wp_verify two-step probe (base -> ?context=edit fallback)
  - _wp_verify failure modes
  - Roles unknown behaviour on hardened WP installs
  - publish_to_wordpress dispatcher contract
  - Rate limiter (per-user hourly + per-host 15-min sliding windows)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response
from fastapi import HTTPException

os.environ.setdefault(
    "CORTEXVIRAL_WORDPRESS_FERNET_KEY",
    "9SdVQFxznii-Mydl2Q9pjbkhEp-7Z6-BOoO_IgLMn6Q=",
)

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes.wordpress_selfhosted import (   # noqa: E402
    _encrypt, _decrypt,
    _normalize_site_url,
    _wp_verify,
    _rate_limit_check, _rate_limit_reset,
    MAX_PER_USER_HOURLY, MAX_PER_HOST_15MIN,
    publish_to_wordpress,
    WPCreds,
)


# ---------------------------------------------------------------------------
# Fernet round trip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    plain = "abcd 1234 EFGH 5678 zzzz 9999"
    tok = _encrypt(plain)
    assert tok != plain
    assert _decrypt(tok) == plain


def test_encrypt_produces_unique_ciphertext_per_call():
    a = _encrypt("same-value")
    b = _encrypt("same-value")
    assert a != b
    assert _decrypt(a) == _decrypt(b) == "same-value"


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------

def test_normalize_site_url_strips_trailing_slash():
    assert _normalize_site_url("https://example.com/") == "https://example.com"
    assert _normalize_site_url("https://example.com/wp/") == "https://example.com/wp"


def test_normalize_site_url_refuses_http():
    with pytest.raises(HTTPException) as ei:
        _normalize_site_url("http://example.com")
    assert ei.value.status_code == 400
    assert "https://" in ei.value.detail


def test_normalize_site_url_refuses_empty():
    with pytest.raises(HTTPException):
        _normalize_site_url("")


# ---------------------------------------------------------------------------
# _wp_verify — status code mapping (base probe)
# ---------------------------------------------------------------------------

# All test URLs live at https://example.com/wp-json/wp/v2/users/me (with or
# without ?context=edit). respx matches by path only, so we use a side_effect
# router that inspects the full URL to return different responses per variant.
_USERS_ME_RX = re.compile(r"^https://example\.com/wp-json/wp/v2/users/me")


def _route_users_me(base_resp: Response, edit_resp: Response | None = None):
    """Return a side_effect that hands out different responses depending on
    whether the outbound request had ?context=edit or not."""
    def _handler(request):
        if "context=edit" in str(request.url):
            return edit_resp if edit_resp is not None else base_resp
        return base_resp
    return _handler


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_401_on_base_probe_returns_400_with_credentials_hint():
    """When the base probe (no context) returns 401 the App Password itself
    is invalid — this is the case where we surface 'Invalid credentials'."""
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(Response(401, json={"code": "rest_not_logged_in"})),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 400
    assert "401" in ei.value.detail


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_404_returns_rest_api_error():
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(Response(404)),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 400
    assert "REST API" in ei.value.detail


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_500_returns_502():
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(Response(503)),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 502


# ---------------------------------------------------------------------------
# _wp_verify — happy path + two-step probe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_success_reads_roles_from_edit_context():
    """Base probe returns minimal user (no roles), ?context=edit returns
    roles. This is the standard flow on a normal WP install."""
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(
            base_resp=Response(200, json={"id": 42, "name": "Jane Editor"}),
            edit_resp=Response(200, json={"id": 42, "name": "Jane Editor", "roles": ["editor"]}),
        ),
    )
    info = await _wp_verify(WPCreds(
        site_url="https://example.com/",
        username="jane",
        application_password="app-pw",
    ))
    assert info["id"] == 42
    assert info["name"] == "Jane Editor"
    assert info["roles"] == ["editor"]
    assert info["roles_unknown"] is False
    assert info["site_url"] == "https://example.com"


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_rejects_subscriber_when_roles_visible():
    """If roles ARE visible via ?context=edit and none are author+, reject."""
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(
            base_resp=Response(200, json={"id": 7, "name": "Sub"}),
            edit_resp=Response(200, json={"id": 7, "name": "Sub", "roles": ["subscriber"]}),
        ),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="s", application_password="p"))
    assert ei.value.status_code == 400
    assert "author" in ei.value.detail.lower()


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_hardened_wp_accepts_with_roles_unknown_flag():
    """Regression for the P2 fix: base probe succeeds (creds are valid) but
    ?context=edit is blocked by a security plugin. We MUST accept the
    connection and mark roles_unknown=True instead of raising a false
    'Invalid credentials' error."""
    respx.get(url__regex=_USERS_ME_RX).mock(
        side_effect=_route_users_me(
            base_resp=Response(200, json={"id": 1, "name": "Root"}),
            edit_resp=Response(401, json={"code": "rest_forbidden_context"}),
        ),
    )
    info = await _wp_verify(WPCreds(site_url="https://example.com", username="root", application_password="pw"))
    assert info["id"] == 1
    assert info["roles"] == []
    assert info["roles_unknown"] is True


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_uses_base_roles_when_present_and_skips_edit_probe():
    """If the base probe already exposes `roles` we shouldn't need the
    second call at all."""
    call_urls: list[str] = []
    def _handler(request):
        call_urls.append(str(request.url))
        return Response(200, json={"id": 5, "name": "Admin", "roles": ["administrator"]})
    respx.get(url__regex=_USERS_ME_RX).mock(side_effect=_handler)

    info = await _wp_verify(WPCreds(site_url="https://example.com", username="a", application_password="pw"))
    assert info["roles"] == ["administrator"]
    assert info["roles_unknown"] is False
    assert len(call_urls) == 1
    assert "context=edit" not in call_urls[0]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Every test starts with a clean rate-limit history so ordering doesn't
    matter."""
    _rate_limit_reset()
    yield
    _rate_limit_reset()


def test_rate_limit_allows_under_hourly_cap():
    """First N calls (N = MAX_PER_USER_HOURLY) must succeed."""
    # Vary the host so the 15-min per-host cap doesn't interfere.
    for i in range(MAX_PER_USER_HOURLY):
        _rate_limit_check("user-1", f"https://site-{i}.com")


def test_rate_limit_blocks_over_hourly_cap():
    for i in range(MAX_PER_USER_HOURLY):
        _rate_limit_check("user-1", f"https://site-{i}.com")
    with pytest.raises(HTTPException) as ei:
        _rate_limit_check("user-1", "https://site-999.com")
    assert ei.value.status_code == 429
    assert "hour" in ei.value.detail.lower()
    assert "Retry-After" in ei.value.headers


def test_rate_limit_per_host_15min_cap():
    """Even inside the hourly cap, hitting the SAME host too many times
    should trip the 15-min per-host limit first."""
    for i in range(MAX_PER_HOST_15MIN):
        _rate_limit_check("user-1", "https://target.example.com")
    with pytest.raises(HTTPException) as ei:
        _rate_limit_check("user-1", "https://target.example.com")
    assert ei.value.status_code == 429
    assert "target.example.com" in ei.value.detail
    assert "Retry-After" in ei.value.headers


def test_rate_limit_isolates_users():
    """One user's abuse must not block a different user."""
    for i in range(MAX_PER_USER_HOURLY):
        _rate_limit_check("user-a", f"https://site-{i}.com")
    # user-b starts fresh.
    _rate_limit_check("user-b", "https://site-0.com")


# ---------------------------------------------------------------------------
# publish_to_wordpress — dispatcher never raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_to_wordpress_returns_ok_false_when_no_channel():
    with patch("routes.wordpress_selfhosted.db") as mock_db:
        mock_db.channels.find_one = AsyncMock(return_value=None)
        result = await publish_to_wordpress("user-with-no-wp", "Title", "<p>body</p>")
    assert result == {"ok": False, "error": "WordPress channel not connected"}


@pytest.mark.asyncio
@respx.mock
async def test_publish_to_wordpress_success_path():
    respx.post("https://blog.example.com/wp-json/wp/v2/posts").mock(
        return_value=Response(201, json={
            "id": 987, "link": "https://blog.example.com/?p=987", "status": "publish",
        }),
    )
    encrypted = _encrypt("real-app-password")
    fake_doc = {
        "site_url":     "https://blog.example.com",
        "wp_username":  "jane",
        "credentials":  {"encrypted_app_password": encrypted},
    }
    with patch("routes.wordpress_selfhosted.db") as mock_db:
        mock_db.channels.find_one   = AsyncMock(return_value=fake_doc)
        mock_db.channels.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        result = await publish_to_wordpress("some-user", "Hello world", "<p>Body.</p>")

    assert result["ok"] is True
    assert result["post_id"] == 987
    assert result["link"] == "https://blog.example.com/?p=987"
    assert result["status"] == "publish"


@pytest.mark.asyncio
@respx.mock
async def test_publish_to_wordpress_wordpress_rejects():
    respx.post("https://blog.example.com/wp-json/wp/v2/posts").mock(
        return_value=Response(403, text="Forbidden"),
    )
    fake_doc = {
        "site_url":     "https://blog.example.com",
        "wp_username":  "jane",
        "credentials":  {"encrypted_app_password": _encrypt("pw")},
    }
    with patch("routes.wordpress_selfhosted.db") as mock_db:
        mock_db.channels.find_one   = AsyncMock(return_value=fake_doc)
        mock_db.channels.update_one = AsyncMock()
        result = await publish_to_wordpress("some-user", "Hello", "<p>Body</p>")
    assert result["ok"] is False
    assert "403" in result["error"]
