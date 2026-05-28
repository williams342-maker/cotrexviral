"""User onboarding — collects business context after first signup.

Flow:
  - On every authenticated page-load, the frontend calls /auth/me which now
    returns `onboarding_required: bool`. True when any required field is empty.
  - The frontend redirects to /onboarding when this is True (unless the user
    has clicked "Skip for now", in which case a dismissible banner shows on
    /dashboard).
  - Submitting /api/onboarding writes the fields to the user doc and fires an
    admin notification email (so the support team can proactively reach out).
"""
from datetime import datetime, timezone
from fastapi import HTTPException, Request

from core import db, api, logger, LEADS_NOTIFY_EMAILS
from deps import get_current_user
from models import (
    OnboardingPayload, ONBOARDING_NICHES, ONBOARDING_GOALS, ONBOARDING_PLATFORMS,
)


def _onboarding_required(user_doc: dict) -> bool:
    """Returns True when the user is missing any of the 3 required fields."""
    if user_doc is None:
        return False
    return not (
        user_doc.get("website")
        and user_doc.get("brand_name")
        and user_doc.get("niche")
    )


@api.get("/onboarding/options")
async def onboarding_options(request: Request):
    """Public-to-logged-in: lists the valid niche / goal / platform options."""
    await get_current_user(request)
    return {
        "niches": ONBOARDING_NICHES,
        "goals": ONBOARDING_GOALS,
        "platforms": ONBOARDING_PLATFORMS,
    }


@api.get("/onboarding/me")
async def onboarding_me(request: Request):
    """Returns the current user's profile + whether onboarding is needed."""
    user = await get_current_user(request)
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0}) or {}
    return {
        "required": _onboarding_required(doc),
        "profile": {
            "website": doc.get("website") or "",
            "brand_name": doc.get("brand_name") or "",
            "niche": doc.get("niche") or "",
            "goals": doc.get("goals") or [],
            "platforms": doc.get("platforms") or [],
            "challenge": doc.get("challenge") or "",
        },
        "completed_at": (
            doc.get("onboarding_completed_at").isoformat()
            if isinstance(doc.get("onboarding_completed_at"), datetime)
            else doc.get("onboarding_completed_at")
        ),
    }


@api.post("/onboarding")
async def submit_onboarding(payload: OnboardingPayload, request: Request):
    user = await get_current_user(request)

    # Validate goals/platforms against the canonical lists.
    bad = [g for g in payload.goals if g not in ONBOARDING_GOALS]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown goals: {bad}")
    bad_p = [p for p in payload.platforms if p not in ONBOARDING_PLATFORMS]
    if bad_p:
        raise HTTPException(status_code=400, detail=f"Unknown platforms: {bad_p}")

    # Lightly normalise website — add https:// if user typed bare domain
    website = payload.website.strip()
    if website and "://" not in website:
        website = "https://" + website.lstrip("/")

    now = datetime.now(timezone.utc)
    existing = await db.users.find_one(
        {"user_id": user.user_id},
        {"onboarding_completed_at": 1},
    ) or {}
    is_first_completion = not existing.get("onboarding_completed_at")

    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "website": website,
            "brand_name": payload.brand_name.strip(),
            "niche": payload.niche,
            "goals": payload.goals,
            "platforms": payload.platforms,
            "challenge": (payload.challenge or "").strip() or None,
            "onboarding_completed_at": now,
            "updated_at": now,
        }},
    )

    # Notify admin on FIRST completion only (so editing later doesn't spam them).
    if is_first_completion and LEADS_NOTIFY_EMAILS:
        try:
            from routes.email import send_onboarding_admin_notification, fire
            fire(send_onboarding_admin_notification(
                user_email=user.email,
                user_name=user.name or "",
                profile={
                    "website": website,
                    "brand_name": payload.brand_name,
                    "niche": payload.niche,
                    "goals": payload.goals,
                    "platforms": payload.platforms,
                    "challenge": payload.challenge,
                },
                recipients=LEADS_NOTIFY_EMAILS,
            ))
        except Exception:
            logger.exception("Failed to schedule onboarding admin notification")

    # Index the brand profile into the memory system so every agent reply
    # immediately has access to who this user is. Fire-and-forget — never
    # block onboarding submission on a memory-layer hiccup.
    try:
        from routes.memory import remember
        profile_bits = [
            f"Brand: {payload.brand_name.strip()}",
            f"Website: {website}",
            f"Niche: {payload.niche}",
        ]
        if payload.goals:
            profile_bits.append("Goals: " + ", ".join(payload.goals))
        if payload.platforms:
            profile_bits.append("Platforms: " + ", ".join(payload.platforms))
        if (payload.challenge or "").strip():
            profile_bits.append(f"Biggest challenge: {payload.challenge.strip()}")
        await remember(
            user.user_id, "brand_profile",
            ". ".join(profile_bits),
            meta={"source": "onboarding"},
            dedupe_key="brand_profile",
        )
    except Exception:
        logger.exception("Memory ingest of brand profile failed")

    return {"ok": True, "first_completion": is_first_completion}
