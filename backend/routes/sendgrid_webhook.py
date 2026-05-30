"""SendGrid Event Webhook → Seller Outreach Events bridge.

Receives SendGrid's `event` webhook (POST JSON array of events) and
projects each event onto the `seller_outreach_events` collection IFF
the event carries our `lead_id` custom_arg (set by the helpers in
`seller_emails.py`). This lets the Conversations UI surface real-time
engagement (delivered → opened → clicked → bounced) for every
SendGrid-routed lifecycle email.

Signature verification (optional but recommended in prod):
  Set `SENDGRID_WEBHOOK_VERIFY_KEY` (base64-encoded ECDSA public key from
  SendGrid → Settings → Mail Settings → Signed Event Webhook Requests).
  When set, every request is verified against the X-Twilio-Email-Event-Webhook-Signature
  header. When unset, the endpoint accepts any payload (preview-friendly).

SendGrid event → seller_outreach event mapping:
  processed/deferred  → ignored (intermediate states; we already log 'sent')
  delivered           → delivered
  open                → opened
  click               → clicked
  bounce/dropped      → bounced
  unsubscribe         → unsubscribed
  spamreport          → unsubscribed (treat as opt-out)
  group_unsubscribe   → unsubscribed
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from core import api, db

logger = logging.getLogger(__name__)


SG_EVENT_TO_OUTREACH = {
    "delivered":         "delivered",
    "open":              "opened",
    "click":             "clicked",
    "bounce":            "bounced",
    "dropped":           "bounced",
    "deferred":          None,   # intermediate; ignore
    "processed":         None,   # already logged on send
    "unsubscribe":       "unsubscribed",
    "group_unsubscribe": "unsubscribed",
    "spamreport":        "unsubscribed",
}


def _verify_signature(public_key_b64: str, timestamp: str,
                       signature: str, payload: bytes) -> bool:
    """Verify SendGrid's ECDSA-signed webhook payload."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.hazmat.primitives import hashes
        from cryptography.exceptions import InvalidSignature

        der_bytes = base64.b64decode(public_key_b64)
        pubkey = load_der_public_key(der_bytes)
        if not isinstance(pubkey, ec.EllipticCurvePublicKey):
            return False
        signed_message = timestamp.encode("utf-8") + payload
        sig_bytes = base64.b64decode(signature)
        try:
            pubkey.verify(sig_bytes, signed_message, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False
    except Exception:
        logger.exception("sendgrid webhook: signature verification crashed")
        return False


async def _record_engagement_event(lead_id: str, sg_event: str,
                                    raw: dict) -> Optional[dict]:
    """Project a SendGrid event onto a seller_outreach_events row.
    Idempotent on (lead_id, sg_event_id) so retries don't duplicate."""
    mapped = SG_EVENT_TO_OUTREACH.get(sg_event)
    if mapped is None:
        return None
    sg_event_id = raw.get("sg_event_id") or raw.get("sg_message_id")
    if sg_event_id:
        existing = await db.seller_outreach_events.find_one({
            "lead_id":     lead_id,
            "event":       mapped,
            "sg_event_id": sg_event_id,
        })
        if existing:
            return None

    # Resolve user_id from the lead so the row scopes correctly.
    lead = await db.seller_leads.find_one({"id": lead_id})
    if not lead:
        return None

    doc = {
        "id":          uuid.uuid4().hex,
        "user_id":     lead["user_id"],
        "lead_id":     lead_id,
        "event":       mapped,
        "channel":     "email",
        "offer_type":  raw.get("lifecycle"),
        "body":        None,
        "sg_event_id": sg_event_id,
        "sg_message_id": raw.get("sg_message_id"),
        "url":         raw.get("url"),  # click URL if event=click
        "reason":      raw.get("reason"),
        "created_at":  datetime.now(timezone.utc),
    }
    if raw.get("artifact_id"):
        doc["artifact_id"] = raw["artifact_id"]
    await db.seller_outreach_events.insert_one(doc)

    # When the seller bounces or unsubscribes, advance lead stage so the
    # operator stops sending more outreach.
    if mapped == "bounced":
        await db.seller_leads.update_one(
            {"id": lead_id},
            {"$set": {"stage": "unresponsive",
                      "updated_at": datetime.now(timezone.utc)}},
        )
    elif mapped == "unsubscribed":
        await db.seller_leads.update_one(
            {"id": lead_id},
            {"$set": {"stage": "not_interested",
                      "updated_at": datetime.now(timezone.utc),
                      "unsubscribed": True}},
        )
    return doc


# Dedicated raw-body endpoint (FastAPI APIRouter prefix=/api so the path
# becomes `/api/sendgrid/webhook`). We use a raw Request so we can pass
# the unparsed bytes to the signature verifier — re-serializing breaks
# the ECDSA digest.
@api.post("/sendgrid/webhook")
async def sendgrid_webhook(request: Request):
    """SendGrid Event Webhook endpoint. Configure at app.sendgrid.com
    → Settings → Mail Settings → Event Webhook with URL
    `https://<your-domain>/api/sendgrid/webhook`. Subscribe to:
    Processed, Delivered, Opened, Clicked, Bounced, Dropped, Spam
    Reports, Unsubscribes, Group Unsubscribes."""
    body = await request.body()

    # Signature verification (optional — only enforced if pub key set).
    pub_key = os.environ.get("SENDGRID_WEBHOOK_VERIFY_KEY", "").strip()
    if pub_key:
        ts = request.headers.get("x-twilio-email-event-webhook-timestamp", "")
        sig = request.headers.get("x-twilio-email-event-webhook-signature", "")
        if not ts or not sig or not _verify_signature(pub_key, ts, sig, body):
            raise HTTPException(401, "Invalid SendGrid webhook signature")

    import json
    try:
        events = json.loads(body or b"[]")
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")
    if not isinstance(events, list):
        raise HTTPException(400, "Expected a JSON array of events")

    inserted = 0
    skipped = 0
    for ev in events:
        if not isinstance(ev, dict):
            skipped += 1
            continue
        lead_id = ev.get("lead_id")     # custom_arg
        sg_event = ev.get("event")
        if not lead_id or not sg_event:
            skipped += 1
            continue
        try:
            row = await _record_engagement_event(lead_id, sg_event, ev)
            if row:
                inserted += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("sendgrid webhook: failed to project event %s", ev)
            skipped += 1

    return {"received": len(events), "projected": inserted, "skipped": skipped}
