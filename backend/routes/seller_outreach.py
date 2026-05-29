"""Phase 2 — Personalized Outreach Engine + Conversation events.

For each Qualified lead, the engine generates a custom-fit OFFER based on
the seller's niche / platform / activity, then dispatches the message
through the configured channel. All events are persisted in
`seller_outreach_events` so the Conversations UI + funnel KPIs reflect
real activity.

Offer types
~~~~~~~~~~~
  free_seo_audit          — best for sellers with a website
  marketplace_growth      — best for established Etsy/Shopify sellers
  product_optimization    — best for sellers with weak/no product cats
  free_onboarding         — best for new/low-activity sellers
  featured_invite         — best for high-activity / multi-channel sellers

The Outreach Engine picks an offer type heuristically from the lead's
profile (no LLM call required) and generates a personalized message body
using the Emergent LLM key. Falls back to a deterministic template if
the LLM is unavailable so the pipeline is testable offline.

Channel adapters (Phase 2 stubs — real channel wiring lives in their
own modules: routes/oauth_meta.py, routes/oauth_linkedin.py, etc.):
  email | instagram_dm | facebook_message | linkedin_inmail | contact_form

Each channel `send()` records a `seller_outreach_event` row of type
'sent' so the funnel + per-lead thread can be reconstructed.
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db, EMERGENT_LLM_KEY
from deps import get_current_user

logger = logging.getLogger(__name__)


# Allowed offer types + their default subject lines.
OFFER_TYPES = {
    "free_seo_audit": {
        "headline": "A free SEO audit of {business_name}",
        "value":    "Show how to drive more organic traffic to their products.",
    },
    "marketplace_growth": {
        "headline": "Marketplace growth audit for {business_name}",
        "value":    "Benchmark them against top performers + reveal 3 conversion fixes.",
    },
    "product_optimization": {
        "headline": "Product listing optimization for {business_name}",
        "value":    "Title, photo & description fixes that lift listing visibility.",
    },
    "free_onboarding": {
        "headline": "Free onboarding to CraftersMarket for {business_name}",
        "value":    "Storefront + product import + SEO metadata done in <10 min.",
    },
    "featured_invite": {
        "headline": "Featured-seller invitation to CraftersMarket",
        "value":    "Premium placement + co-marketing for {business_name}.",
    },
}

CHANNELS = ("email", "instagram_dm", "facebook_message", "linkedin_inmail", "contact_form")

EVENT_TYPES = ("sent", "delivered", "opened", "replied", "interested",
               "not_interested", "bounced", "unsubscribed")


# ---------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------
class OutreachGenerate(BaseModel):
    lead_id: str
    offer_type: Optional[str] = None         # auto-pick if blank
    channel:    Optional[str] = None         # auto-pick if blank
    custom_brief: Optional[str] = None       # extra context for the LLM
    dry_run:    bool = False                 # generate only — don't record sent


class OutreachBulk(BaseModel):
    mission_id: str
    limit: int = 25
    channel: Optional[str] = None            # default = per-lead best channel


class OutreachEvent(BaseModel):
    lead_id: str
    event:   str                              # one of EVENT_TYPES
    channel: Optional[str] = None
    body:    Optional[str] = None             # raw payload from the channel (reply text, etc.)


# ---------------------------------------------------------------------
# Offer + channel selection — deterministic heuristic
# ---------------------------------------------------------------------
def _pick_offer(lead: dict) -> str:
    """Choose the offer-type that best fits this seller's profile."""
    socials = lead.get("socials") or {}
    cats = lead.get("product_categories") or []
    activity = (lead.get("estimated_activity") or "").lower()
    has_website = bool(lead.get("website"))

    if activity == "high" and len(socials) >= 2:
        return "featured_invite"
    if activity == "low":
        return "free_onboarding"
    if has_website and len(cats) >= 2:
        return "free_seo_audit"
    if lead.get("source") in ("etsy", "shopify"):
        return "marketplace_growth"
    return "product_optimization"


def _pick_channel(lead: dict) -> str:
    """Pick the best channel to reach this lead based on observed signals."""
    socials = lead.get("socials") or {}
    if "instagram" in socials:
        return "instagram_dm"
    if "facebook" in socials:
        return "facebook_message"
    if "linkedin" in socials:
        return "linkedin_inmail"
    if lead.get("website"):
        return "contact_form"
    return "email"


# ---------------------------------------------------------------------
# LLM body generation (with deterministic fallback)
# ---------------------------------------------------------------------
def _fallback_body(lead: dict, offer: str, mission_title: Optional[str]) -> str:
    """Deterministic template — used when EMERGENT_LLM_KEY is absent or
    the LLM call errors. Keeps the pipeline testable offline."""
    name = lead.get("business_name") or "there"
    niche = lead.get("niche") or "your category"
    headline = OFFER_TYPES[offer]["headline"].format(business_name=name)
    value = OFFER_TYPES[offer]["value"].format(business_name=name)
    mission_line = f"\n\nWe're building a marketplace called CraftersMarket for {niche} makers." if mission_title else ""
    return (
        f"Hi {name.split()[0]},{mission_line}\n\n"
        f"{headline}.\n\n"
        f"{value}\n\n"
        "Would you have 10 minutes for a no-strings look?\n\n— The CraftersMarket team"
    )


async def _llm_generate_body(lead: dict, offer: str, channel: str,
                               mission_title: Optional[str],
                               custom_brief: Optional[str], user_id: str) -> str:
    if not EMERGENT_LLM_KEY:
        return _fallback_body(lead, offer, mission_title)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage

        system = (
            "You are Nova writing 100% personalized seller-recruitment outreach "
            "for the CortexViral Seller Acquisition OS. Tone: warm, specific, "
            "no marketing fluff. Length: 70-130 words. Always reference one "
            "concrete detail from the seller's profile. End with a single low-friction CTA. "
            "Output ONLY the message body — no subject line, no signature padding, "
            "no greeting boilerplate beyond a first-name salutation."
        )
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY,
                    session_id=f"outreach-{lead['id']}",
                    system_message=system)
            .with_model("openai", "gpt-5")
        )
        prompt = (
            f"Seller: {lead.get('business_name')}\n"
            f"Niche: {lead.get('niche')}\n"
            f"Platform: {lead.get('platform')}\n"
            f"Activity: {lead.get('estimated_activity')}\n"
            f"Channel: {channel}\n"
            f"Offer to lead with: {offer} — {OFFER_TYPES[offer]['value']}\n"
            f"Mission: {mission_title or 'CraftersMarket recruitment'}"
        )
        if custom_brief:
            prompt += f"\n\nExtra context from operator:\n{custom_brief}"
        body, _ = await send_with_usage(
            chat, UserMessage(text=prompt),
            agent_id="nova", user_id=user_id, model="gpt-5",
        )
        return (body or "").strip() or _fallback_body(lead, offer, mission_title)
    except Exception:
        logger.exception("outreach: LLM body gen failed — using fallback")
        return _fallback_body(lead, offer, mission_title)


# ---------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------
async def _record_event(user_id: str, lead_id: str, event: str,
                         channel: Optional[str] = None,
                         body: Optional[str] = None,
                         offer_type: Optional[str] = None) -> dict:
    if event not in EVENT_TYPES:
        raise HTTPException(400, f"Unknown event type: {event}")
    now = datetime.now(timezone.utc)
    doc = {
        "id":         uuid.uuid4().hex,
        "user_id":    user_id,
        "lead_id":    lead_id,
        "event":      event,
        "channel":    channel,
        "offer_type": offer_type,
        "body":       body,
        "created_at": now,
    }
    await db.seller_outreach_events.insert_one(doc)
    return doc


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at",):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _advance_stage_for_event(event: str) -> Optional[str]:
    """Map inbound event → desired lead stage transition."""
    return {
        "sent":           "outreached",
        "replied":        "interested",
        "interested":     "interested",
        "unsubscribed":   "unresponsive",
        "not_interested": "unresponsive",
    }.get(event)


# ---------------------------------------------------------------------
# Routes — generate + send (Phase 2 stub: send IS record-as-sent)
# ---------------------------------------------------------------------
@api.post("/seller-outreach/generate")
async def generate_outreach(payload: OutreachGenerate, request: Request):
    """Generate (and optionally send) a personalized outreach message
    for a single lead. `dry_run=True` returns the body without recording
    a 'sent' event — useful for the preview UI."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one({"id": payload.lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead["stage"] not in ("qualified", "discovered"):
        raise HTTPException(400,
            f"Cannot outreach to lead in stage '{lead['stage']}'. "
            f"Qualify it first."
        )

    offer = payload.offer_type or _pick_offer(lead)
    if offer not in OFFER_TYPES:
        raise HTTPException(400, f"Unknown offer_type: {offer}")
    channel = payload.channel or _pick_channel(lead)
    if channel not in CHANNELS:
        raise HTTPException(400, f"Unknown channel: {channel}")

    mission_title = None
    if lead.get("mission_id"):
        m = await db.missions.find_one({"id": lead["mission_id"]})
        if m:
            mission_title = m.get("title")

    body = await _llm_generate_body(
        lead, offer, channel, mission_title, payload.custom_brief, user.user_id,
    )

    out: dict = {
        "lead_id":     payload.lead_id,
        "offer_type":  offer,
        "channel":     channel,
        "headline":    OFFER_TYPES[offer]["headline"].format(business_name=lead.get("business_name") or "your shop"),
        "body":        body,
    }

    if not payload.dry_run:
        # Phase 2: "send" = record + flip lead stage. Real channel sends
        # ship in Phase 3 via the existing OAuth modules.
        evt = await _record_event(user.user_id, payload.lead_id, "sent",
                                    channel=channel, body=body, offer_type=offer)
        out["event_id"] = evt["id"]
        new_stage = _advance_stage_for_event("sent")
        if new_stage:
            now = datetime.now(timezone.utc)
            await db.seller_leads.update_one(
                {"id": payload.lead_id},
                {"$set": {"stage": new_stage,
                          "outreached_at": now,
                          "updated_at": now,
                          "last_outreach_offer": offer,
                          "last_outreach_channel": channel}},
            )
    return out


@api.post("/seller-outreach/bulk")
async def bulk_outreach(payload: OutreachBulk, request: Request):
    """Fire personalized outreach at every Qualified lead for a mission.

    Auto-picks offer-type + channel per lead. Stops at `limit` so a
    runaway loop can't blast a thousand sellers in one click.
    """
    user = await get_current_user(request)
    mission = await db.missions.find_one(
        {"id": payload.mission_id, "user_id": user.user_id})
    if not mission:
        raise HTTPException(404, "Mission not found")

    cursor = db.seller_leads.find({
        "user_id":    user.user_id,
        "mission_id": payload.mission_id,
        "stage":      "qualified",
    }).sort("seller_score", -1).limit(min(200, max(1, payload.limit)))
    leads = await cursor.to_list(length=payload.limit)

    sent = []
    for lead in leads:
        offer = _pick_offer(lead)
        channel = payload.channel or _pick_channel(lead)
        # Bulk path uses the deterministic fallback template — going
        # through the LLM for N leads sequentially exceeds proxy timeouts
        # AND burns the budget fast. Single-lead /generate stays LLM-backed.
        body = _fallback_body(lead, offer, mission.get("title"))
        evt = await _record_event(user.user_id, lead["id"], "sent",
                                    channel=channel, body=body, offer_type=offer)
        now = datetime.now(timezone.utc)
        await db.seller_leads.update_one(
            {"id": lead["id"]},
            {"$set": {"stage": "outreached",
                      "outreached_at": now,
                      "updated_at": now,
                      "last_outreach_offer": offer,
                      "last_outreach_channel": channel}},
        )
        sent.append({"lead_id": lead["id"], "event_id": evt["id"],
                     "offer": offer, "channel": channel})

    return {"mission_id": payload.mission_id, "sent": len(sent), "results": sent}


@api.post("/seller-outreach/events")
async def post_event(payload: OutreachEvent, request: Request):
    """Record a downstream event (delivered/opened/replied/etc.).
    Called by webhook adapters (email open pixel, IG reply webhook).
    Also advances the lead's stage when the event implies a transition."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one(
        {"id": payload.lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")

    evt = await _record_event(user.user_id, payload.lead_id, payload.event,
                                channel=payload.channel, body=payload.body)
    new_stage = _advance_stage_for_event(payload.event)
    if new_stage:
        now = datetime.now(timezone.utc)
        updates = {"stage": new_stage, "updated_at": now}
        if new_stage == "interested" and not lead.get("responded_at"):
            updates["responded_at"] = now
        await db.seller_leads.update_one({"id": payload.lead_id}, {"$set": updates})
    return _serialize(evt)


# ---------------------------------------------------------------------
# Read endpoints — Conversations UI
# ---------------------------------------------------------------------
@api.get("/seller-outreach/events/{lead_id}")
async def get_thread(lead_id: str, request: Request, limit: int = 100):
    """Full event thread for a single lead — powers the Conversations panel."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one({"id": lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    cursor = db.seller_outreach_events.find(
        {"user_id": user.user_id, "lead_id": lead_id},
        {"_id": 0},
    ).sort("created_at", 1).limit(min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    return {"lead": {k: v for k, v in lead.items() if k != "_id"},
            "events": rows, "count": len(rows)}


@api.get("/seller-outreach/threads/{mission_id}")
async def list_threads(mission_id: str, request: Request, limit: int = 50):
    """List of leads in active conversation (stage ∈ outreached/interested)
    for the Conversations index."""
    user = await get_current_user(request)
    cursor = db.seller_leads.find({
        "user_id":    user.user_id,
        "mission_id": mission_id,
        "stage":      {"$in": ["outreached", "interested"]},
    }).sort("outreached_at", -1).limit(min(200, max(1, limit)))
    leads = await cursor.to_list(length=limit)

    # Attach last event per lead for the index row.
    out = []
    for lead in leads:
        last = await db.seller_outreach_events.find_one(
            {"user_id": user.user_id, "lead_id": lead["id"]},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if last and isinstance(last.get("created_at"), datetime):
            last["created_at"] = last["created_at"].isoformat()
        out.append({
            **{k: v for k, v in lead.items() if k != "_id"},
            "last_event": last,
        })
    return {"threads": out, "count": len(out)}
