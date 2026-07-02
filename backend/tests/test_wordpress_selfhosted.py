"""Tests for the WordPress self-hosted connector.

Covers:
  - Fernet encrypt/decrypt round trip works and produces different
    ciphertext each call (nonce)
  - `_normalize_site_url` refuses http:// and strips trailing slash
  - `_wp_verify` maps WP status codes to the right FastAPI errors
  - `_wp_verify` refuses users whose roles are all below `author`
  - `publish_to_wordpress` returns {ok:False,...} when channel row is
    missing (no exceptions escape to the mission dispatcher)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response
from fastapi import HTTPException

# Ensure the Fernet key exists before we import the module under test.
os.environ.setdefault(
    "CORTEXVIRAL_WORDPRESS_FERNET_KEY",
    "9SdVQFxznii-Mydl2Q9pjbkhEp-7Z6-BOoO_IgLMn6Q=",
)

# Make sure the backend package is on the path when pytest is run from /app/backend
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes.wordpress_selfhosted import (   # noqa: E402
    _encrypt, _decrypt,
    _normalize_site_url,
    _wp_verify,
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
    """Fernet uses a random IV so two encryptions of the same value must
    differ. Guards against accidentally swapping to a deterministic scheme."""
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
# _wp_verify — status code mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_401_returns_400_with_credentials_hint():
    route = respx.get("https://example.com/wp-json/wp/v2/users/me?context=edit").mock(
        return_value=Response(401, json={"code": "rest_not_logged_in"}),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 400
    assert "401" in ei.value.detail
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_404_returns_rest_api_error():
    respx.get("https://example.com/wp-json/wp/v2/users/me?context=edit").mock(
        return_value=Response(404),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 400
    assert "REST API" in ei.value.detail


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_500_returns_502():
    respx.get("https://example.com/wp-json/wp/v2/users/me?context=edit").mock(
        return_value=Response(503),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="u", application_password="p"))
    assert ei.value.status_code == 502


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_success_returns_user():
    respx.get("https://example.com/wp-json/wp/v2/users/me?context=edit").mock(
        return_value=Response(200, json={
            "id": 42, "name": "Jane Editor", "roles": ["editor"],
        }),
    )
    info = await _wp_verify(WPCreds(
        site_url="https://example.com/",   # trailing slash — should be stripped
        username="jane",
        application_password="app-pw",
    ))
    assert info["id"] == 42
    assert info["name"] == "Jane Editor"
    assert info["roles"] == ["editor"]
    assert info["site_url"] == "https://example.com"


@pytest.mark.asyncio
@respx.mock
async def test_wp_verify_rejects_subscriber_role():
    respx.get("https://example.com/wp-json/wp/v2/users/me?context=edit").mock(
        return_value=Response(200, json={
            "id": 7, "name": "Sub", "roles": ["subscriber"],
        }),
    )
    with pytest.raises(HTTPException) as ei:
        await _wp_verify(WPCreds(site_url="https://example.com", username="s", application_password="p"))
    assert ei.value.status_code == 400
    assert "author" in ei.value.detail.lower()


# ---------------------------------------------------------------------------
# publish_to_wordpress — dispatcher never raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_to_wordpress_returns_ok_false_when_no_channel():
    """If the user has no WordPress row in db.channels the helper must
    return a structured error, not raise — otherwise it would crash the
    entire channels.publish() dispatch."""
    with patch("routes.wordpress_selfhosted.db") as mock_db:
        mock_db.channels.find_one = AsyncMock(return_value=None)
        result = await publish_to_wordpress("user-with-no-wp", "Title", "<p>body</p>")
    assert result == {"ok": False, "error": "WordPress channel not connected"}


@pytest.mark.asyncio
@respx.mock
async def test_publish_to_wordpress_success_path():
    """Given a connected channel, publish_to_wordpress should hit the
    /wp/v2/posts endpoint and return the WordPress post id + link."""
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
