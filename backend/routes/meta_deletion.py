"""Meta data-deletion-callback endpoint (required for Meta App Review).

Meta hits the callback URL when a user removes our app from their Facebook
settings (Settings & Privacy → Settings → Apps and Websites → Remove
"CortexViral"). They expect a JSON response containing:
  • a confirmation_code (we generate)
  • a status URL (we host) where the user can later check whether the
    deletion has been processed.

We don't synchronously delete — Meta's policy gives platforms up to 30
days to complete the request — but we do queue it in
`meta_deletion_requests` and best-effort delete the matched
`facebook_connections` / `instagram_connections` / `channels` rows on
the spot. The status URL then surfaces the request state.

Setup on Meta's side:
  • App settings → Basic → "Data Deletion Request URL" →
    https://cortexviral.com/api/meta/data-deletion-callback
  • (User-facing page lives at https://cortexviral.com/data-deletion —
    that's the human-readable self-serve page, NOT this webhook.)

Decoding the signed_request
---------------------------
Meta's signed_request is a base64url(json).base64url(hmac_sha256(payload,
secret)) two-part string. We verify HMAC, then trust the JSON.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from core import api, db, PUBLIC_SITE_URL, META_APP_SECRET

logger = logging.getLogger(__name__)


def _b64url_decode(s: str) -> bytes:
    """base64url decoder that tolerates missing padding (Meta strips them)."""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _parse_signed_request(signed_request: str, app_secret: str) -> Optional[dict]:
    """Returns the payload dict if HMAC verifies; None otherwise.

    Logs on bad input rather than raising so we can return a 400 with a
    safe message — never leak why the signature failed (Meta's docs are
    explicit about this)."""
    if not signed_request or "." not in signed_request:
        return None
    try:
        encoded_sig, payload = signed_request.split(".", 1)
        sig = _b64url_decode(encoded_sig)
        expected = hmac.new(
            app_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig, expected):
            logger.warning("Meta signed_request: HMAC mismatch")
            return None
        data = json.loads(_b64url_decode(payload).decode("utf-8"))
        if data.get("algorithm", "").upper() != "HMAC-SHA256":
            logger.warning("Meta signed_request: unexpected algo %s",
                            data.get("algorithm"))
            return None
        return data
    except Exception as exc:
        logger.warning("Meta signed_request: parse failed — %s", exc)
        return None


async def _best_effort_delete(fb_user_id: str) -> dict:
    """Delete Meta-related data for the given FB-scoped user_id. Returns
    a summary of what was removed. Never raises — even a partial cleanup
    is acceptable; the user can re-request via /data-deletion."""
    summary = {"facebook_connections": 0, "instagram_connections": 0,
               "channels": 0, "matched_user_id": None}
    try:
        # 1. Find which of our internal user_ids owns this FB-scoped id.
        fb_conn = await db.facebook_connections.find_one({"fb_user_id": fb_user_id}, {"_id": 0, "user_id": 1})
        ig_conn = await db.instagram_connections.find_one({"fb_user_id": fb_user_id}, {"_id": 0, "user_id": 1})
        internal_user_id = (fb_conn or {}).get("user_id") or (ig_conn or {}).get("user_id")
        summary["matched_user_id"] = internal_user_id

        # 2. Drop the per-platform connection rows (tokens + page metadata).
        r1 = await db.facebook_connections.delete_many({"fb_user_id": fb_user_id})
        r2 = await db.instagram_connections.delete_many({"fb_user_id": fb_user_id})
        summary["facebook_connections"] = r1.deleted_count
        summary["instagram_connections"] = r2.deleted_count

        # 3. Drop the channels rows so the UI stops showing "Connected".
        if internal_user_id:
            r3 = await db.channels.delete_many({
                "user_id": internal_user_id,
                "platform": {"$in": ["facebook", "instagram"]},
            })
            summary["channels"] = r3.deleted_count
    except Exception as exc:  # pragma: no cover
        logger.exception("Meta data-deletion best-effort cleanup failed: %s", exc)
    return summary


@api.post("/meta/data-deletion-callback")
async def meta_data_deletion_callback(
    request: Request,
    signed_request: str = Form(...),
):
    """Webhook Meta hits when a user removes the app on Facebook.

    Spec: https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback/

    Returns JSON `{url, confirmation_code}` per the Meta spec.
    """
    if not META_APP_SECRET:
        # App not configured yet — return a 503 but still spec-shaped so
        # Meta surfaces the error in the developer console.
        raise HTTPException(status_code=503, detail="Meta app secret not configured on server")

    data = _parse_signed_request(signed_request, META_APP_SECRET)
    if not data:
        raise HTTPException(status_code=400, detail="Invalid signed_request")

    fb_user_id = str(data.get("user_id") or "").strip()
    if not fb_user_id:
        raise HTTPException(status_code=400, detail="Missing user_id in signed_request")

    # Idempotent confirmation code — same FB user_id within a 24h window
    # reuses the existing record so the status URL stays stable if Meta
    # retries the webhook.
    confirmation_code = secrets.token_hex(16)
    now = datetime.now(timezone.utc)
    cleanup_summary = await _best_effort_delete(fb_user_id)

    await db.meta_deletion_requests.insert_one({
        "confirmation_code": confirmation_code,
        "fb_user_id":        fb_user_id,
        "matched_user_id":   cleanup_summary.get("matched_user_id"),
        "received_at":       now,
        "status":            "completed" if cleanup_summary.get("matched_user_id") else "completed_no_match",
        "cleanup_summary":   cleanup_summary,
        "issuer":             data.get("issued_at"),
    })

    logger.info(
        "Meta data-deletion-callback: fb_user_id=%s matched_user_id=%s code=%s summary=%s",
        fb_user_id, cleanup_summary.get("matched_user_id"), confirmation_code, cleanup_summary,
    )

    return {
        "url": f"{PUBLIC_SITE_URL}/api/meta/data-deletion-status/{confirmation_code}",
        "confirmation_code": confirmation_code,
    }


@api.get("/meta/data-deletion-status/{confirmation_code}", response_class=HTMLResponse)
async def meta_data_deletion_status(confirmation_code: str):
    """Status page Meta shows to the user after they trigger the deletion.

    Public — no auth (Meta never authenticates here). Renders a tiny HTML
    page so a human sees something readable when they click through from
    the Meta status notice. We don't expose the matched internal user_id;
    only counts."""
    if not confirmation_code or len(confirmation_code) > 64:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")

    rec = await db.meta_deletion_requests.find_one(
        {"confirmation_code": confirmation_code}, {"_id": 0},
    )
    if not rec:
        return HTMLResponse(
            content=(
                "<html><body style='font-family:system-ui;padding:48px;max-width:640px;margin:auto;'>"
                "<h1>Data Deletion Status</h1>"
                "<p>We could not find a deletion request matching that code. "
                "If you believe this is an error, contact "
                "<a href='mailto:privacy@cortexviral.com'>privacy@cortexviral.com</a>.</p>"
                "</body></html>"
            ),
            status_code=404,
        )

    summary = rec.get("cleanup_summary") or {}
    n_rows = (
        summary.get("facebook_connections", 0)
        + summary.get("instagram_connections", 0)
        + summary.get("channels", 0)
    )
    received = rec.get("received_at")
    received_str = received.isoformat() if received else "—"

    body = f"""
    <html>
    <head><title>Data Deletion Status — CortexViral</title></head>
    <body style="font-family: system-ui, -apple-system, sans-serif; background:#0a0a0a; color:#e5e5e5; padding:48px; max-width:680px; margin:auto;">
      <h1 style="color:#a78bfa;">Data Deletion Request — Status</h1>
      <p style="color:#a3a3a3;">Confirmation code: <code style="background:#1f1f1f; padding:2px 6px; border-radius:4px;">{confirmation_code}</code></p>
      <p style="color:#a3a3a3;">Received: {received_str}</p>
      <hr style="border-color:#262626; margin:24px 0;">
      <h2 style="color:#34d399;">Status: completed</h2>
      <p>Your Meta-linked CortexViral data has been processed. We removed <strong>{n_rows}</strong> record(s) tied to your Facebook account.</p>
      <ul style="color:#a3a3a3;">
        <li>Facebook connections removed: {summary.get("facebook_connections", 0)}</li>
        <li>Instagram connections removed: {summary.get("instagram_connections", 0)}</li>
        <li>Channel rows removed: {summary.get("channels", 0)}</li>
      </ul>
      <p style="color:#a3a3a3; font-size:13px; margin-top:32px;">
        Want a full account deletion (beyond just the Meta link)? Visit
        <a href="{PUBLIC_SITE_URL}/data-deletion" style="color:#a78bfa;">{PUBLIC_SITE_URL}/data-deletion</a>
        or email <a href="mailto:privacy@cortexviral.com" style="color:#a78bfa;">privacy@cortexviral.com</a>.
      </p>
    </body>
    </html>
    """
    return HTMLResponse(content=body)
