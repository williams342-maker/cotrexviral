"""Mission event loop — drains `team_dispatches` and advances missions.

The loop closes the four-team relay:

    scout       → produces a Signal       → kicks Creator
    creator     → produces a Draft        → kicks Operator
    operator    → produces a PublishIntent → kicks Intelligence
    intelligence → produces a Score       → IF score < threshold, kicks Creator
                                            (with variant=True) for a re-take

Design choices
~~~~~~~~~~~~~~
- The loop is **deterministic & cheap** — no LLM calls. Real LLM work is
  attached to the personas at the user-facing layer (existing ai.py). The
  loop's only job is to keep moving work through the graph.
- Each dispatch is a row in `team_dispatches` + a mirror row in
  `agent_messages` (so the existing chatter UI shows the conversation).
- **Autonomy gating**: a dispatch is only processed if the mission's
  autonomy level for the dispatch's team is high enough. Otherwise the
  dispatch stays in `queued` and the user must approve it manually.
- We never process the same dispatch twice — successful processing flips
  `status` to `done` (or `awaiting_approval` if blocked).
- Iteration cap: 1 mission accumulates max 25 dispatches/day so a runaway
  loop can't burn the meter.

Autonomy thresholds (minimum mission.autonomy_level for the dispatch's
team to be auto-processed):

  team          required mission.autonomy_level
  ---------     --------------------------------
  scout         1      (Scout is research; safe to auto-run from L1)
  creator       1      (auto-create content from L1)
  operator      2      (auto-publish from L2)
  intelligence  3      (auto-optimize from L3)
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from core import api, db
from deps import get_current_user
from fastapi import Request

from routes.missions import compute_progress, _serialize, TEAMS
from routes.teams import TEAM_DEFS

logger = logging.getLogger(__name__)


TEAM_MIN_AUTONOMY = {
    "scout":        1,
    "creator":      1,
    "operator":     2,
    "intelligence": 3,
}

# The next team in the relay.
NEXT_TEAM_AFTER = {
    "scout":        "creator",
    "creator":      "operator",
    "operator":     "intelligence",
    "intelligence": "creator",  # variant loop — only fired when score < threshold
}

# Daily cap per mission (prevents runaway loops).
MAX_DISPATCHES_PER_MISSION_PER_DAY = 25

# Minimum confidence threshold below which Intelligence kicks Creator for a variant.
INTELLIGENCE_RETRY_THRESHOLD = 60

# Dispatch status values
ST_QUEUED            = "queued"
ST_DONE              = "done"
ST_AWAITING_APPROVAL = "awaiting_approval"
ST_BLOCKED_CAP       = "blocked_cap"


async def _team_autonomy_for(mission: dict, team: str) -> int:
    """Effective autonomy level for a (mission, team).
    Per-team override beats mission default."""
    overrides = mission.get("team_autonomy") or {}
    if team in overrides:
        return int(overrides[team])
    return int(mission.get("autonomy_level", 1))


async def _dispatches_today_for_mission(mission_id: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    return await db.team_dispatches.count_documents({
        "mission_id": mission_id, "created_at": {"$gte": since},
    })


def _next_task_label(team_from: str, team_to: str, mission_title: str) -> str:
    """Human-readable task title for the next-team dispatch."""
    return {
        ("scout", "creator"):
            f"Turn Scout's opportunity into a creative draft for: {mission_title}",
        ("creator", "operator"):
            f"Schedule + publish the Creator drafts for: {mission_title}",
        ("operator", "intelligence"):
            f"Measure the Operator-published content for: {mission_title}",
        ("intelligence", "creator"):
            f"Generate sharper variant — Intelligence flagged underperformance "
            f"on: {mission_title}",
    }.get((team_from, team_to), f"{team_to.title()} follow-up for: {mission_title}")


async def _process_dispatch(dispatch: dict) -> dict:
    """Process a single queued dispatch:
        - Verify autonomy gate
        - Mark this dispatch done
        - If the team relay calls for one, write the next-step dispatch
    Returns a small status dict for logging.
    """
    mid = dispatch.get("mission_id")
    team = dispatch.get("team")
    if not mid or team not in TEAMS:
        # Orphaned dispatch — mark done so we don't reprocess.
        await _mark(dispatch, ST_DONE, note="orphan: missing mission_id or invalid team")
        return {"status": "orphan", "dispatch_id": dispatch.get("id")}

    mission = await db.missions.find_one({"id": mid})
    if not mission:
        await _mark(dispatch, ST_DONE, note="orphan: mission deleted")
        return {"status": "mission_gone", "dispatch_id": dispatch.get("id")}

    # Stop processing if the mission is paused / completed / abandoned.
    if mission.get("status") != "running":
        # Leave the dispatch queued so it resumes when the mission resumes.
        return {"status": "mission_not_running", "dispatch_id": dispatch.get("id")}

    # Daily cap
    count_today = await _dispatches_today_for_mission(mid)
    if count_today > MAX_DISPATCHES_PER_MISSION_PER_DAY:
        await _mark(dispatch, ST_BLOCKED_CAP,
                    note=f"daily cap {MAX_DISPATCHES_PER_MISSION_PER_DAY} exceeded")
        return {"status": "blocked_cap", "dispatch_id": dispatch.get("id")}

    # Autonomy gate
    autonomy = await _team_autonomy_for(mission, team)
    if autonomy < TEAM_MIN_AUTONOMY[team]:
        await _mark(dispatch, ST_AWAITING_APPROVAL,
                    note=f"autonomy={autonomy} < required {TEAM_MIN_AUTONOMY[team]}")
        return {"status": "awaiting_approval", "dispatch_id": dispatch.get("id")}

    # ------------------------------------------------------------
    # Team-specific "advance the relay" logic.
    # We don't generate real content here — that's the existing user-facing
    # ai.py + briefs.py + channels.py flow. The loop's only job is to write
    # the NEXT-step dispatch in the chain.
    # ------------------------------------------------------------
    next_team: Optional[str] = NEXT_TEAM_AFTER.get(team)
    write_next = bool(next_team)

    # Intelligence: only spawn a variant when confidence is below threshold.
    if team == "intelligence":
        progress = await compute_progress(mission)
        confidence = progress.get("confidence") or 0
        if confidence >= INTELLIGENCE_RETRY_THRESHOLD:
            write_next = False
            # Mission may have hit target — auto-flip status if so.
            if progress.get("current", 0) >= progress.get("target", 1):
                await db.missions.update_one(
                    {"id": mid},
                    {"$set": {
                        "status":       "succeeded",
                        "completed_at": datetime.now(timezone.utc),
                        "updated_at":   datetime.now(timezone.utc),
                    }},
                )
        else:
            # Goal-seeking (Level 4+): if the mission is well behind pace
            # AND has a deadline AND we're past 50% of the timeline, auto-extend
            # the deadline by 7 days. Capped at 2 extensions per mission so
            # Cortex doesn't drift forever.
            autonomy_level = int(mission.get("autonomy_level", 1))
            extensions = int(mission.get("deadline_extensions", 0))
            deadline = mission.get("deadline")
            started_at = mission.get("started_at") or mission.get("created_at")
            # Coerce naive datetimes (Mongo strips tzinfo) → UTC-aware.
            if isinstance(deadline, datetime) and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if isinstance(started_at, datetime) and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if (autonomy_level >= 4 and deadline and started_at
                    and confidence < INTELLIGENCE_RETRY_THRESHOLD
                    and extensions < 2):
                total = (deadline - started_at).total_seconds()
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                if total > 0 and (elapsed / total) >= 0.5:
                    new_deadline = deadline + timedelta(days=7)
                    await db.missions.update_one(
                        {"id": mid},
                        {"$set": {
                            "deadline":             new_deadline,
                            "deadline_extensions":  extensions + 1,
                            "updated_at":           datetime.now(timezone.utc),
                            f"goal_seeking.extension_{extensions + 1}_at":
                                datetime.now(timezone.utc),
                            f"goal_seeking.extension_{extensions + 1}_reason":
                                f"Confidence {confidence}% at {round(100 * elapsed / total)}% time elapsed",
                        }},
                    )
                    logger.info(
                        "goal-seeking: extended deadline of mission %s by 7d (ext #%d)",
                        mid, extensions + 1,
                    )

    await _mark(dispatch, ST_DONE, note="processed by mission event loop")

    if write_next:
        # Cap check again — we may have just hit the cap by writing this one.
        if count_today + 1 > MAX_DISPATCHES_PER_MISSION_PER_DAY:
            return {"status": "done_capped_before_next", "dispatch_id": dispatch.get("id")}

        defn = TEAM_DEFS[next_team]
        lead = defn["personas"][0]
        now = datetime.now(timezone.utc)
        msg = {
            "id":         uuid.uuid4().hex,
            "user_id":    mission["user_id"],
            "from_agent": "cortex",
            "to_agent":   lead,
            "team":       next_team,
            "mission_id": mid,
            "task":       _next_task_label(team, next_team, mission["title"]),
            "context":    {"prev_dispatch_id": dispatch["id"], "prev_team": team},
            "status":     ST_QUEUED,
            "created_at": now,
            "updated_at": now,
        }
        await db.agent_messages.insert_one(msg)
        await db.team_dispatches.insert_one({**msg})
        return {"status": "done_relayed",
                "dispatch_id": dispatch.get("id"),
                "next_dispatch_id": msg["id"], "next_team": next_team}

    return {"status": "done", "dispatch_id": dispatch.get("id")}


async def _mark(dispatch: dict, status: str, note: str = "") -> None:
    now = datetime.now(timezone.utc)
    updates = {"status": status, "updated_at": now, "processed_at": now}
    if note:
        updates["processor_note"] = note
    await db.team_dispatches.update_one({"id": dispatch["id"]}, {"$set": updates})
    # Keep the agent_messages mirror in sync.
    await db.agent_messages.update_one({"id": dispatch["id"]}, {"$set": updates})


async def drain_mission_loop(limit: int = 100) -> dict:
    """Drain up to `limit` queued dispatches. Called by the apscheduler
    every minute AND by the `POST /missions/loop/run-once` admin endpoint
    for testing.
    """
    cursor = db.team_dispatches.find({"status": ST_QUEUED}).sort("created_at", 1).limit(limit)
    rows = await cursor.to_list(length=limit)
    results = []
    for r in rows:
        try:
            res = await _process_dispatch(r)
            results.append(res)
        except Exception:
            logger.exception("loop: failed to process dispatch %s", r.get("id"))
            results.append({"status": "error", "dispatch_id": r.get("id")})
    return {"processed": len(results), "results": results}


# ---------------------------------------------------------------------
# Admin-ish endpoint — manual loop drain (testing + dashboard CTA).
# ---------------------------------------------------------------------
@api.post("/missions/loop/run-once")
async def run_loop_once(request: Request, limit: int = 100):
    user = await get_current_user(request)
    # Scope: only drain THIS user's dispatches even when called by admin.
    # We re-query inside drain to ensure user-scoping.
    cursor = db.team_dispatches.find({
        "status":  ST_QUEUED,
        "user_id": user.user_id,
    }).sort("created_at", 1).limit(min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    results = []
    for r in rows:
        try:
            res = await _process_dispatch(r)
            results.append(res)
        except Exception:
            logger.exception("loop: failed to process dispatch %s", r.get("id"))
            results.append({"status": "error", "dispatch_id": r.get("id")})
    return {"processed": len(results), "results": results}


@api.get("/missions/{mission_id}/dispatches")
async def list_mission_dispatches(mission_id: str, request: Request, limit: int = 100):
    """Mission detail page renders the full event-relay timeline from this."""
    user = await get_current_user(request)
    mission = await db.missions.find_one({"id": mission_id, "user_id": user.user_id})
    if not mission:
        from fastapi import HTTPException
        raise HTTPException(404, "Mission not found")
    cursor = db.team_dispatches.find(
        {"mission_id": mission_id, "user_id": user.user_id},
        {"_id": 0},
    ).sort("created_at", 1).limit(min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    # ISO format datetimes for the response
    for r in rows:
        for k in ("created_at", "updated_at", "processed_at"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = v.isoformat()
    return {"dispatches": rows, "count": len(rows)}
