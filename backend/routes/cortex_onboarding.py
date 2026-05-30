"""Cortex onboarding — AI-guided first-run mission.

NOT a traditional product tour. Cortex teaches the platform through
conversation: ask the user's goal, build a demo mission, animate the
mission lifecycle, explain autonomy, then hand them the keys.

State machine (single-row per user in `cortex_onboarding`):

    welcome              → introduction + ask name/business
    set_goal             → ask user's #1 growth goal
    cc_intro             → "this is the Command Center" + spotlight composer
    sample_mission_proposal → Cortex builds a DEMO mission from their goal
    mission_lifecycle    → spotlight rail + narrate phases
    autonomous_execution → demo mission auto-advances; Cortex narrates
    autonomy_explain     → L0-L5 levels demystified
    complete             → "you're ready" — stamps users.onboarded_at

Gate (in `should_show()`):
  Show onboarding when ALL true:
    1) user.onboarded_at is null
    2) user has zero `missions`
    3) user has zero `cortex_conversations`
  Replays (manual "Show me around") bypass the gate.

Demo missions:
  - Inserted with demo=True and `demo_phase_idx` so the polling rail
    fast-forwards through phases on the user's screen (~8s total).
  - Hard-deleted on `complete` or `skip` so no faux data leaks.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# Ordered state machine. Each step declares:
#   spotlight: which UI region Cortex points at (or None)
#   expects_user_reply: should we wait for user input before advancing
#   replay_only_skip: bool — included in replay walkthroughs
ONBOARDING_STEPS: list[str] = [
    "welcome",
    "set_goal",
    "cc_intro",
    "sample_mission_proposal",
    "mission_lifecycle",
    "autonomous_execution",
    "autonomy_explain",
    "complete",
]

SPOTLIGHT = {
    "welcome":                 None,
    "set_goal":                "composer",
    "cc_intro":                "composer",
    "sample_mission_proposal": None,
    "mission_lifecycle":       "mission_rail",
    "autonomous_execution":    "mission_rail",
    "autonomy_explain":        "autonomy_chip",
    "complete":                None,
}

# Steps that wait for the user to actually type something before
# advancing. The rest just need a "Next" click from the orchestrator.
EXPECTS_USER_REPLY = {"set_goal"}


def _next_step(current: str) -> str:
    try:
        i = ONBOARDING_STEPS.index(current)
        return ONBOARDING_STEPS[min(i + 1, len(ONBOARDING_STEPS) - 1)]
    except ValueError:
        return ONBOARDING_STEPS[0]


# ----------------------------------------------------------- script
def _scripted(step: str, *, name: str = "there", goal: str = "") -> str:
    """Cortex's scripted message for each step. Personalized by the
    user's first name and stated goal where available. Kept short —
    the typewriter animation does the dramatic work."""
    g = (goal or "your goal").strip()
    return {
        "welcome": (
            f"Hello {name} — I'm Cortex. I'm your AI executive, not a software product. "
            "I run growth missions in the background while you focus on direction. "
            "Let me show you how this works in about 90 seconds. Ready?"
        ),
        "set_goal": (
            "First — what's the #1 business outcome you want me to drive this quarter? "
            "One sentence. Examples: \"Recruit 50 woodworking sellers on Etsy.\" "
            "\"Lift trial-to-paid by 15%.\" \"Land 10 enterprise demos.\""
        ),
        "cc_intro": (
            f"Got it — \"{g}\". This box is your Command Center. Talk to me here. "
            "No menus, no forms — just goals. I'll handle the breakdown into missions."
        ),
        "sample_mission_proposal": (
            "Watch — I'm building a demo mission off your goal right now. It's labeled "
            "DEMO so you can see the shape without me firing real outreach. "
            "Look at the right rail."
        ),
        "mission_lifecycle": (
            "Every mission has phases: Discovery → Qualification → Outreach → Conversations. "
            "I drive each one through my agent team — Scout, Creator, Operator, Intelligence. "
            "You'll see this demo run through every phase in a few seconds."
        ),
        "autonomous_execution": (
            "See the progress bar moving on its own? That's me working in the background. "
            "Missions don't need you to click. They run, learn, and surface findings to you "
            "when something needs your judgment."
        ),
        "autonomy_explain": (
            "One more thing — autonomy levels. L0 means I draft only, you approve every step. "
            "L3 means I run missions end-to-end, escalating only on risk. L5 means I act fully on my own. "
            "Yours starts at L2 — semi-autonomous. Change it any time in Settings."
        ),
        "complete": (
            f"That's the tour. Your real mission for \"{g}\" is one message away — "
            "just tell me when you're ready and I'll build it for real. "
            "You can replay this walkthrough any time by typing \"show me around\"."
        ),
    }.get(step, "")


# ---------------------------------------------------------- helpers
async def _eligible_first_time_user(user_id: str) -> bool:
    """First-time gate (1a/2a): unset onboarded_at AND zero missions AND
    zero conversations. Repeat users with data never see onboarding."""
    u = await db.users.find_one({"user_id": user_id},
                                  {"_id": 0, "onboarded_at": 1})
    if u and u.get("onboarded_at"):
        return False
    miss = await db.missions.count_documents({"user_id": user_id})
    if miss > 0:
        return False
    convs = await db.cortex_conversations.count_documents({"user_id": user_id})
    if convs > 0:
        return False
    return True


async def _delete_demo_mission(user_id: str, mission_id: Optional[str]) -> None:
    """Hard-delete the demo mission + any related events so no faux
    data lingers after completion/skip."""
    if not mission_id:
        return
    try:
        await db.missions.delete_one(
            {"id": mission_id, "user_id": user_id, "demo": True})
        # Best-effort cleanup of any spawned demo events.
        await db.mission_events.delete_many(
            {"mission_id": mission_id, "user_id": user_id})
    except Exception:
        logger.exception("onboarding: demo mission cleanup failed (non-fatal)")


def _project_state(doc: dict, *, eligible: bool) -> dict:
    """Shape the row for the frontend. Excludes Mongo internals."""
    return {
        "step":              doc.get("step") if doc else None,
        "goal":              (doc or {}).get("goal") or "",
        "name":              (doc or {}).get("name") or "",
        "demo_mission_id":   (doc or {}).get("demo_mission_id"),
        "started_at":        _iso((doc or {}).get("started_at")),
        "completed_at":      _iso((doc or {}).get("completed_at")),
        "skipped_at":        _iso((doc or {}).get("skipped_at")),
        "replay":            bool((doc or {}).get("replay")),
        "eligible":          bool(eligible),
        "spotlight":         SPOTLIGHT.get((doc or {}).get("step") or ""),
        "message":           _scripted(
            (doc or {}).get("step") or "welcome",
            name=(doc or {}).get("name") or "there",
            goal=(doc or {}).get("goal") or "",
        ),
        "expects_user_reply": ((doc or {}).get("step") in EXPECTS_USER_REPLY),
        "is_terminal":       ((doc or {}).get("step") == "complete"),
    }


def _iso(v) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


# ---------------------------------------------------------- payloads
class AdvancePayload(BaseModel):
    from_step:  Optional[str] = None
    user_input: Optional[str] = Field(None, max_length=600)


class StartPayload(BaseModel):
    replay: bool = False


# ---------------------------------------------------------- endpoints
@api.get("/cortex/onboarding/state")
async def onboarding_state(request: Request):
    """Return the user's current onboarding row, or a stub indicating
    eligibility if none exists yet. Frontend decides whether to render
    the orchestrator overlay."""
    user = await get_current_user(request)
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0})
    eligible = await _eligible_first_time_user(user.user_id)
    return _project_state(doc, eligible=eligible)


@api.post("/cortex/onboarding/start")
async def onboarding_start(payload: StartPayload, request: Request):
    """Begin (or replay) the onboarding mission for this user.
    Replay bypasses the first-time gate."""
    user = await get_current_user(request)
    if not payload.replay and not await _eligible_first_time_user(user.user_id):
        # User isn't a first-timer — don't auto-start. Frontend honors
        # this by not rendering the orchestrator.
        raise HTTPException(409, "User is not first-time eligible. "
                                  "Use replay=true to manually trigger.")

    # Pull a friendly name from the user record so Cortex's opener
    # personalizes from the first byte.
    u = await db.users.find_one({"user_id": user.user_id},
                                  {"_id": 0, "name": 1, "display_name": 1,
                                   "email": 1})
    name = ((u or {}).get("name")
             or (u or {}).get("display_name")
             or ((u or {}).get("email") or "").split("@")[0]
             or "there").split(" ")[0]

    # Wipe any prior in-progress run (only one active row at a time).
    now = datetime.now(timezone.utc)
    await db.cortex_onboarding.update_one(
        {"user_id": user.user_id},
        {"$set": {"user_id":     user.user_id,
                   "step":        "welcome",
                   "name":        name,
                   "goal":        "",
                   "demo_mission_id": None,
                   "started_at":  now,
                   "completed_at": None,
                   "skipped_at":  None,
                   "replay":      bool(payload.replay)}},
        upsert=True,
    )
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0})
    return _project_state(doc, eligible=True)


@api.post("/cortex/onboarding/advance")
async def onboarding_advance(payload: AdvancePayload, request: Request):
    """Move the state machine forward by one step. If the previous
    step expected user input (`set_goal`), the input is stored on the
    row so subsequent messages can personalize off it."""
    user = await get_current_user(request)
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Onboarding not started")
    if doc.get("step") == "complete":
        return _project_state(doc, eligible=False)

    update: dict = {}
    current = doc.get("step") or "welcome"

    # Capture user input where the step calls for it.
    if current == "set_goal" and (payload.user_input or "").strip():
        update["goal"] = payload.user_input.strip()[:280]

    next_step = _next_step(current)
    update["step"] = next_step

    # When transitioning INTO sample_mission_proposal, mint a demo
    # mission row so the right rail picks it up immediately.
    if next_step == "sample_mission_proposal" and not doc.get("demo_mission_id"):
        mid = uuid.uuid4().hex
        goal = update.get("goal") or doc.get("goal") or "your goal"
        demo_title = _demo_title_from_goal(goal)
        await db.missions.insert_one({
            "id":             mid,
            "user_id":        user.user_id,
            "title":          demo_title,
            "mission_type":   "seller_acquisition",
            "status":         "running",
            "autonomy_level": 2,
            "target":         10,
            "niche":          goal[:60],
            "demo":           True,
            "demo_phase_idx": 0,
            "demo_started_at": datetime.now(timezone.utc),
            "created_at":     datetime.now(timezone.utc),
        })
        update["demo_mission_id"] = mid

    if next_step == "complete":
        update["completed_at"] = datetime.now(timezone.utc)
        # Hard-delete demo mission (rule from user choice 5a).
        await _delete_demo_mission(user.user_id, doc.get("demo_mission_id"))
        update["demo_mission_id"] = None
        # Stamp users.onboarded_at so the gate never re-opens unless
        # explicitly replayed.
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {"onboarded_at": datetime.now(timezone.utc)}},
        )

    await db.cortex_onboarding.update_one(
        {"user_id": user.user_id}, {"$set": update})
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0})
    return _project_state(doc, eligible=False)


@api.post("/cortex/onboarding/skip")
async def onboarding_skip(request: Request):
    """Skip-out at any point. Stamps `users.onboarded_at` so the gate
    closes permanently (replay button remains available)."""
    user = await get_current_user(request)
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0}) or {}
    await _delete_demo_mission(user.user_id, doc.get("demo_mission_id"))
    now = datetime.now(timezone.utc)
    await db.cortex_onboarding.update_one(
        {"user_id": user.user_id},
        {"$set": {"step":        "complete",
                   "skipped_at":  now,
                   "completed_at": now,
                   "demo_mission_id": None}},
        upsert=True,
    )
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"onboarded_at": now}},
    )
    return {"skipped": True}


# ---------------------------------------------------------- demo tick
@api.post("/cortex/onboarding/demo-tick")
async def onboarding_demo_tick(request: Request):
    """Advance the demo mission's phase + progress one notch so the
    rail animates while the user reads the lifecycle narration. Called
    by the frontend orchestrator on a short interval during the
    `mission_lifecycle` + `autonomous_execution` steps."""
    user = await get_current_user(request)
    doc = await db.cortex_onboarding.find_one(
        {"user_id": user.user_id}, {"_id": 0})
    mid = (doc or {}).get("demo_mission_id")
    if not mid:
        return {"ticked": False, "reason": "no_demo_mission"}
    m = await db.missions.find_one(
        {"id": mid, "user_id": user.user_id, "demo": True}, {"_id": 0})
    if not m:
        return {"ticked": False, "reason": "missing"}
    idx = int(m.get("demo_phase_idx") or 0)
    next_idx = min(idx + 1, len(_DEMO_PHASES) - 1)
    await db.missions.update_one(
        {"id": mid, "user_id": user.user_id},
        {"$set": {"demo_phase_idx": next_idx,
                   "demo_progress_pct": _DEMO_PHASES[next_idx]["pct"]}},
    )
    return {"ticked": True, "phase_idx": next_idx,
            "phase": _DEMO_PHASES[next_idx]}


_DEMO_PHASES = [
    {"key": "discovery",      "label": "Discovery",      "pct": 15},
    {"key": "qualification",  "label": "Qualification",  "pct": 38},
    {"key": "outreach",       "label": "Outreach",       "pct": 67},
    {"key": "conversations",  "label": "Conversations",  "pct": 92},
]


def _demo_title_from_goal(goal: str) -> str:
    """Build a believable demo mission title from the user's stated
    goal (one short title — no quotes / no punctuation tail)."""
    g = (goal or "").strip().rstrip(".!?")
    if not g:
        return "Demo: sample growth mission"
    return f"Demo: {g[:64]}"
