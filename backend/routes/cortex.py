"""Cortex — the master orchestrator.

User interacts primarily with Cortex via natural-language goals:
    "Generate 50 new maker signups for CraftersMarket"

Cortex:
  1. Parses the goal into a structured Mission (title, metric, target).
  2. Creates the Mission record.
  3. Dispatches scout → creator → operator → intelligence in order
     (Phase 1 sends an INITIAL dispatch to each. Phase 2 will close the
     event loop: scout finds opp → creator brief → operator publish →
     intel score → creator variant → ...).
  4. Returns the Mission + dispatch IDs.

For Phase 1 the goal parser uses a tiny LLM call (best-effort, falls
back to a deterministic regex parse). All ticks attribute to a new
'cortex' persona via `send_with_usage`.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db, EMERGENT_LLM_KEY, logger as core_logger
from deps import get_current_user
from routes.missions import compute_progress, _serialize, TEAMS, AUTONOMY_LEVELS
from routes.teams import TEAM_DEFS

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Pydantic schemas
# -----------------------------------------------------------------
class CortexBrief(BaseModel):
    goal: str                       # natural-language goal
    autonomy_level: int = 1
    deadline_days: Optional[int] = None
    budget_usd_cap: Optional[float] = None
    teams_assigned: Optional[List[str]] = None  # default all 4


# -----------------------------------------------------------------
# Goal parsing — LLM with regex fallback
# -----------------------------------------------------------------
_NUMBER_RX = re.compile(r"\b(\d{1,7})\b")


def _regex_parse_goal(goal: str) -> dict:
    """Very small deterministic fallback parser.

    Pulls the first integer as the target. The whole sentence becomes
    the mission title. metric stays None — the user can edit it later.
    """
    m = _NUMBER_RX.search(goal)
    target = int(m.group(1)) if m else None
    title = goal.strip()
    if len(title) > 200:
        title = title[:200].rstrip() + "…"
    return {"title": title, "target": target, "metric": None, "description": None}


async def _llm_parse_goal(goal: str, user_id: str) -> dict:
    """Best-effort LLM parse — falls back to regex on any error/empty key.

    The LLM is asked to return STRICT JSON with title / target / metric / description.
    """
    if not EMERGENT_LLM_KEY:
        return _regex_parse_goal(goal)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage  # uses agent ledger tick

        system = (
            "You are Cortex, the master marketing orchestrator. Parse the user's "
            "high-level marketing goal into a STRICT JSON object with these keys:\n"
            "  title       (short, <=80 chars, action-oriented — e.g. 'Get 50 maker signups')\n"
            "  target      (integer or null — the numeric target if stated)\n"
            "  metric      (one of: leads, signups, instagram.posts, facebook.posts, "
            "linkedin.posts, tiktok.posts, total_impressions, total_engagements, "
            "listening_signals, or null if unclear)\n"
            "  description (1-2 sentence explanation of the mission, <=200 chars)\n"
            "Return ONLY the JSON object, no prose, no code-fences."
        )
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY,
                    session_id=f"cortex-parse-{user_id}",
                    system_message=system)
            .with_model("openai", "gpt-5")
        )
        raw, _ = await send_with_usage(
            chat, UserMessage(text=goal),
            agent_id="cortex", user_id=user_id, model="gpt-5",
        )
        # Defensive JSON extraction — strip code fences if the LLM ignored instructions.
        s = raw.strip().lstrip("`").lstrip("json").strip().rstrip("`").strip()
        try:
            data = json.loads(s)
        except Exception:
            mm = re.search(r"\{.*\}", s, re.DOTALL)
            if not mm:
                raise
            data = json.loads(mm.group(0))
        # Validate
        out = {
            "title":       (data.get("title") or "").strip()[:200] or _regex_parse_goal(goal)["title"],
            "target":      int(data["target"]) if isinstance(data.get("target"), (int, float)) and data["target"] > 0 else None,
            "metric":      data.get("metric") or None,
            "description": (data.get("description") or "").strip()[:300] or None,
        }
        return out
    except Exception:
        logger.exception("Cortex goal parse failed — falling back to regex")
        return _regex_parse_goal(goal)


# -----------------------------------------------------------------
# Routes
# -----------------------------------------------------------------
@api.post("/cortex/missions")
async def cortex_create_mission(payload: CortexBrief, request: Request):
    """The single entry-point users (or other agents) use to ask Cortex
    to start a mission. Parses the natural-language goal, persists the
    mission, and fires initial team dispatches.
    """
    user = await get_current_user(request)
    if payload.autonomy_level not in AUTONOMY_LEVELS:
        raise HTTPException(400, "autonomy_level must be 0-5")
    teams_assigned = payload.teams_assigned or list(TEAMS)
    for t in teams_assigned:
        if t not in TEAMS:
            raise HTTPException(400, f"Unknown team: {t}")

    parsed = await _llm_parse_goal(payload.goal, user.user_id)
    deadline = None
    if payload.deadline_days:
        deadline = datetime.now(timezone.utc) + timedelta(days=int(payload.deadline_days))

    now = datetime.now(timezone.utc)
    mission = {
        "id":              uuid.uuid4().hex,
        "user_id":         user.user_id,
        "title":           parsed["title"],
        "description":     parsed["description"] or payload.goal[:300],
        "metric":          parsed["metric"],
        "target":          parsed["target"],
        "deadline":        deadline,
        "autonomy_level":  payload.autonomy_level,
        "team_autonomy":   {},
        "teams_assigned":  teams_assigned,
        "budget_usd_cap":  payload.budget_usd_cap,
        "growth_goal_id":  None,
        "status":          "running",            # Cortex starts the mission immediately
        "raw_goal":        payload.goal,
        "created_at":      now,
        "updated_at":      now,
        "started_at":      now,
        "completed_at":    None,
    }
    await db.missions.insert_one(mission)

    # Fire initial dispatches to each team. Scout goes first — the rest
    # are queued so the loop can run scout→creator→operator→intel in order
    # once event-driven dispatch ships in Phase 2. For now they all fire
    # with `status=queued` and Phase 2's worker drains them.
    dispatches = []
    for tid in teams_assigned:
        defn = TEAM_DEFS[tid]
        addressee = defn["personas"][0]
        task = {
            "scout":        f"Find opportunities + market signals for: {parsed['title']}",
            "creator":      f"Draft campaign + creative variants for: {parsed['title']}",
            "operator":     f"Prepare distribution plan + schedule for: {parsed['title']}",
            "intelligence": f"Set up measurement + winner detection for: {parsed['title']}",
        }[tid]
        msg = {
            "id":         uuid.uuid4().hex,
            "user_id":    user.user_id,
            "from_agent": "cortex",
            "to_agent":   addressee,
            "team":       tid,
            "mission_id": mission["id"],
            "task":       task,
            "context":    {"goal": payload.goal, "target": parsed["target"]},
            "status":     "queued",
            "created_at": now,
            "updated_at": now,
        }
        await db.agent_messages.insert_one(msg)
        await db.team_dispatches.insert_one({**msg})
        dispatches.append({"team": tid, "dispatch_id": msg["id"], "lead_persona": addressee})

    progress = await compute_progress(mission)
    return {
        "mission":    {**_serialize(mission), "progress": progress},
        "dispatches": dispatches,
        "parsed":     parsed,
    }


@api.get("/cortex/summary")
async def cortex_summary(request: Request):
    """Top-line numbers Cortex surfaces on the home dashboard:
       running missions, total team dispatches today, on-track %, recent wins."""
    user = await get_current_user(request)
    running = await db.missions.count_documents({"user_id": user.user_id, "status": "running"})
    total = await db.missions.count_documents({"user_id": user.user_id})
    succeeded = await db.missions.count_documents({"user_id": user.user_id, "status": "succeeded"})

    since = datetime.now(timezone.utc) - timedelta(days=1)
    dispatches_24h = await db.team_dispatches.count_documents({
        "user_id": user.user_id, "created_at": {"$gte": since},
    })

    # On-track = running missions whose computed confidence ≥ 60.
    on_track = 0
    running_rows = await db.missions.find(
        {"user_id": user.user_id, "status": "running"}
    ).to_list(length=200)
    for m in running_rows:
        pr = await compute_progress(m)
        if pr.get("confidence", 0) >= 60:
            on_track += 1

    return {
        "running_missions":  running,
        "total_missions":    total,
        "succeeded_missions": succeeded,
        "on_track":          on_track,
        "dispatches_24h":    dispatches_24h,
    }
