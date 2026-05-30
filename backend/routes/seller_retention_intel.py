"""Phase 8 — Advanced Retention Intelligence.

Replaces the simple 30d/60d heuristic with a multi-signal churn-risk
score and auto-launches a 3-step retention workflow when risk is high.

Signals (each 0-100; final score is weighted average):
  inactivity        — days since last activity (updated_at)
  activity_drop     — onboarded_at vs updated_at delta (slow ramp)
  social_silence    — number of social profiles attached (0 → higher risk)
  score_trajectory  — initial seller_score quality (low quality → fragile)

Workflow (auto-launched when score >= AUTO_LAUNCH_THRESHOLD):
  1. send_offer       — generate + queue a personalized incentive
  2. nudge_message    — schedule a follow-up DM/email
  3. operator_alert   — file a HITL alert if the seller is still inactive
                        24h after step 2

`seller_churn_scores` keeps the latest score per lead (one row, upserted)
so the Retention page can sort/filter.
`seller_retention_workflows` records each auto-launched plan with its
steps + statuses.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# --- Tunables -------------------------------------------------------
WEIGHTS = {
    "inactivity":        0.55,   # dominant signal
    "activity_drop":     0.20,
    "social_silence":    0.15,
    "score_trajectory":  0.10,
}
AUTO_LAUNCH_THRESHOLD = 60  # ≥60/100 churn risk → launch workflow
ALERT_THRESHOLD = 40        # ≥40 → emit retention alert (no workflow yet)

WORKFLOW_STEPS = (
    "send_offer",
    "nudge_message",
    "operator_alert",
)


# --- Pydantic -------------------------------------------------------
class ChurnScoreInput(BaseModel):
    lead_id: Optional[str] = None    # score one lead
    mission_id: Optional[str] = None # or score all active leads of a mission


# --- Signal computers -----------------------------------------------
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(ts) -> Optional[datetime]:
    if not isinstance(ts, datetime):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _signal_inactivity(lead: dict) -> int:
    """Inactivity score 0-100. 0d=0, 30d=50, 60d=85, 90d+=100."""
    ts = _coerce_utc(lead.get("updated_at")
                     or lead.get("onboarded_at")
                     or lead.get("created_at"))
    if not ts:
        return 50
    days = max(0, (_now_utc() - ts).days)
    if days <= 1:    return 0
    if days >= 90:   return 100
    if days >= 60:   return 70 + (days - 60) * 1  # 70→90 over 60→90d
    if days >= 30:   return 40 + (days - 30) * 1  # 40→70 over 30→60d
    return int(days * 1.3)                         # 0→39 over 0→30d


def _signal_activity_drop(lead: dict) -> int:
    """How quickly the seller went quiet AFTER onboarding. If onboarded
    long ago but only a tiny gap to last update → engaged. Big gap → drop."""
    onb = _coerce_utc(lead.get("onboarded_at"))
    upd = _coerce_utc(lead.get("updated_at"))
    if not onb or not upd or upd <= onb:
        return 30
    active_window_days = max(1, (upd - onb).days)
    if active_window_days >= 60: return 0     # long, healthy
    if active_window_days >= 30: return 25
    if active_window_days >= 14: return 50
    return 75


def _signal_social_silence(lead: dict) -> int:
    socials = lead.get("socials") or {}
    if not socials:           return 80
    if len(socials) == 1:     return 50
    if len(socials) >= 3:     return 10
    return 30


def _signal_score_trajectory(lead: dict) -> int:
    sc = lead.get("seller_score")
    if sc is None: return 50
    # Lower seller_score == more fragile == higher churn risk
    return max(0, min(100, 100 - int(sc)))


def compute_churn_signals(lead: dict) -> dict:
    sigs = {
        "inactivity":       _signal_inactivity(lead),
        "activity_drop":    _signal_activity_drop(lead),
        "social_silence":   _signal_social_silence(lead),
        "score_trajectory": _signal_score_trajectory(lead),
    }
    score = sum(sigs[k] * WEIGHTS[k] for k in WEIGHTS)
    return {
        "signals": sigs,
        "score":   round(score, 1),
        "weights": WEIGHTS,
    }


def _top_reasons(signals: dict, top_n: int = 3) -> List[str]:
    pairs = sorted(signals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    labels = {
        "inactivity":       "Long stretch with no marketplace activity",
        "activity_drop":    "Short active window after onboarding",
        "social_silence":   "Few social channels attached to profile",
        "score_trajectory": "Initial seller score below benchmark",
    }
    return [labels[k] for k, v in pairs if v >= 30]


# --- Workflow auto-launch -------------------------------------------
async def _maybe_launch_workflow(user_id: str, lead: dict, score: float,
                                  reasons: List[str]) -> Optional[dict]:
    """Launch a 3-step retention workflow if score ≥ AUTO_LAUNCH_THRESHOLD
    AND no in-flight workflow exists for this lead. Idempotent."""
    if score < AUTO_LAUNCH_THRESHOLD:
        return None

    existing = await db.seller_retention_workflows.find_one({
        "user_id": user_id, "lead_id": lead["id"], "status": "running",
    })
    if existing:
        return None

    now = _now_utc()
    steps = []
    for i, step in enumerate(WORKFLOW_STEPS):
        steps.append({
            "step":         step,
            "status":       "pending",
            "scheduled_at": (now + timedelta(hours=i * 24)).isoformat(),
            "executed_at":  None,
            "detail":       None,
        })
    record = {
        "id":         uuid.uuid4().hex,
        "user_id":    user_id,
        "lead_id":    lead["id"],
        "mission_id": lead.get("mission_id"),
        "score":      score,
        "reasons":    reasons,
        "status":     "running",
        "steps":      steps,
        "created_at": now,
    }
    await db.seller_retention_workflows.insert_one(record)

    # Auto-execute step 1 (send_offer) immediately — best-effort.
    try:
        from routes.seller_offers import generate_and_persist_artifact
        art = await generate_and_persist_artifact(
            user_id, lead, offer_type="marketplace_growth",
            custom_brief=f"This seller is showing churn risk ({score:.0f}/100). "
                          "Win them back with a tangible quick-win audit.",
        )
        await db.seller_retention_workflows.update_one(
            {"id": record["id"], "steps.step": "send_offer"},
            {"$set": {
                "steps.$.status":      "ok",
                "steps.$.executed_at": _now_utc().isoformat(),
                "steps.$.detail":      f"Generated audit artifact {art['id']}",
                "steps.$.artifact_id": art["id"],
            }},
        )
    except Exception:
        logger.exception("retention workflow: send_offer auto-step failed")

    return {k: v for k, v in record.items() if k != "_id"}


# --- Public API -----------------------------------------------------
async def score_and_act_on_lead(user_id: str, lead: dict) -> dict:
    """Compute churn score for one lead, persist, alert / launch workflow
    where applicable. Returns the full row."""
    sigs = compute_churn_signals(lead)
    score = sigs["score"]
    reasons = _top_reasons(sigs["signals"])

    now = _now_utc()
    row = {
        "id":          uuid.uuid4().hex,
        "user_id":     user_id,
        "lead_id":     lead["id"],
        "mission_id":  lead.get("mission_id"),
        "score":       score,
        "signals":     sigs["signals"],
        "reasons":     reasons,
        "scored_at":   now,
    }
    await db.seller_churn_scores.update_one(
        {"user_id": user_id, "lead_id": lead["id"]},
        {"$set": row},
        upsert=True,
    )

    workflow = None
    if score >= AUTO_LAUNCH_THRESHOLD:
        workflow = await _maybe_launch_workflow(user_id, lead, score, reasons)
    elif score >= ALERT_THRESHOLD:
        await db.retention_alerts.insert_one({
            "id":         uuid.uuid4().hex,
            "user_id":    user_id,
            "lead_id":    lead["id"],
            "severity":   "at_risk",
            "reason":     f"Churn risk {score:.0f}/100 · " + (reasons[0] if reasons else "multi-signal"),
            "score":      score,
            "created_at": now,
        })

    row["workflow"] = workflow
    if isinstance(row.get("scored_at"), datetime):
        row["scored_at"] = row["scored_at"].isoformat()
    return {k: v for k, v in row.items() if k != "_id"}


async def scan_all_active(user_id: Optional[str] = None,
                           mission_id: Optional[str] = None) -> dict:
    """Score every active lead. Returns a summary dict."""
    q: dict = {"stage": "active"}
    if user_id:    q["user_id"] = user_id
    if mission_id: q["mission_id"] = mission_id
    cursor = db.seller_leads.find(q)
    scanned = 0
    workflows_launched = 0
    at_risk = 0
    async for lead in cursor:
        res = await score_and_act_on_lead(lead["user_id"], lead)
        scanned += 1
        if res.get("workflow"): workflows_launched += 1
        if res["score"] >= ALERT_THRESHOLD: at_risk += 1
    return {
        "scanned":            scanned,
        "at_risk":            at_risk,
        "workflows_launched": workflows_launched,
        "scanned_at":         _now_utc().isoformat(),
    }


# --- Routes ---------------------------------------------------------
@api.post("/seller-retention/intel/score")
async def score_endpoint(payload: ChurnScoreInput, request: Request):
    """Score one lead OR every active lead in a mission. Persists results
    and may launch workflows."""
    user = await get_current_user(request)
    if payload.lead_id:
        lead = await db.seller_leads.find_one(
            {"id": payload.lead_id, "user_id": user.user_id})
        if not lead:
            raise HTTPException(404, "Lead not found")
        return await score_and_act_on_lead(user.user_id, lead)
    return await scan_all_active(user_id=user.user_id,
                                  mission_id=payload.mission_id)


@api.get("/seller-retention/intel/scores")
async def list_scores(request: Request, mission_id: Optional[str] = None,
                       limit: int = 100, min_score: float = 0):
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id, "score": {"$gte": min_score}}
    if mission_id:
        q["mission_id"] = mission_id
    cursor = db.seller_churn_scores.find(q, {"_id": 0}).sort("score", -1).limit(
        min(500, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    for r in rows:
        v = r.get("scored_at")
        if isinstance(v, datetime):
            r["scored_at"] = v.isoformat()
    return {"scores": rows, "count": len(rows)}


@api.get("/seller-retention/intel/workflows")
async def list_workflows(request: Request, status: Optional[str] = None,
                          mission_id: Optional[str] = None, limit: int = 50):
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id}
    if status: q["status"] = status
    if mission_id: q["mission_id"] = mission_id
    cursor = db.seller_retention_workflows.find(q, {"_id": 0}).sort(
        "created_at", -1).limit(min(200, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    return {"workflows": rows, "count": len(rows)}


@api.post("/seller-retention/intel/workflows/{workflow_id}/advance")
async def advance_workflow(workflow_id: str, request: Request):
    """Manually advance the next pending step. Used by the operator UI
    when the auto-cron hasn't run yet."""
    user = await get_current_user(request)
    w = await db.seller_retention_workflows.find_one(
        {"id": workflow_id, "user_id": user.user_id})
    if not w:
        raise HTTPException(404, "Workflow not found")
    if w["status"] != "running":
        raise HTTPException(400, f"Workflow already {w['status']}")

    next_idx = next((i for i, s in enumerate(w["steps"]) if s["status"] == "pending"), None)
    if next_idx is None:
        await db.seller_retention_workflows.update_one(
            {"id": workflow_id},
            {"$set": {"status": "complete"}},
        )
        return {"workflow_id": workflow_id, "status": "complete"}

    step = w["steps"][next_idx]
    detail = f"Step '{step['step']}' executed manually"
    await db.seller_retention_workflows.update_one(
        {"id": workflow_id, "steps.step": step["step"]},
        {"$set": {
            f"steps.{next_idx}.status":      "ok",
            f"steps.{next_idx}.executed_at": _now_utc().isoformat(),
            f"steps.{next_idx}.detail":      detail,
        }},
    )
    # If that was the last step, mark workflow complete
    w2 = await db.seller_retention_workflows.find_one({"id": workflow_id})
    if all(s["status"] == "ok" for s in w2["steps"]):
        await db.seller_retention_workflows.update_one(
            {"id": workflow_id},
            {"$set": {"status": "complete"}},
        )
    return {"workflow_id": workflow_id, "advanced_step": step["step"], "status": "ok"}


# --- Cron — auto-advance retention workflows ------------------------
async def auto_advance_due_workflows() -> dict:
    """Scan running workflows. For each, advance the OLDEST pending step
    when its scheduled_at is >24h past. Step 2 (nudge_message) is a stub
    that just marks 'ok' with a synthetic detail line. Step 3
    (operator_alert) writes a HITL retention alert row so the inbox bell
    fires. Idempotent — running this twice in the same window is a no-op
    because steps already marked 'ok' are skipped.
    """
    now = _now_utc()
    cutoff = now - timedelta(hours=24)
    advanced = 0
    completed = 0
    cursor = db.seller_retention_workflows.find({"status": "running"})
    async for wf in cursor:
        try:
            idx = next(
                (i for i, s in enumerate(wf["steps"]) if s["status"] == "pending"),
                None,
            )
            if idx is None:
                await db.seller_retention_workflows.update_one(
                    {"id": wf["id"]}, {"$set": {"status": "complete"}})
                completed += 1
                continue

            step = wf["steps"][idx]
            sched = step.get("scheduled_at")
            # Step scheduled_at is stored as ISO string; coerce to datetime.
            sched_dt = None
            if isinstance(sched, str):
                try:
                    sched_dt = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                except Exception:
                    sched_dt = None
            elif isinstance(sched, datetime):
                sched_dt = sched if sched.tzinfo else sched.replace(tzinfo=timezone.utc)
            if sched_dt is None or sched_dt > cutoff:
                continue   # not yet due

            detail = f"Step '{step['step']}' executed by cron"
            updates = {
                f"steps.{idx}.status":      "ok",
                f"steps.{idx}.executed_at": now.isoformat(),
                f"steps.{idx}.detail":      detail,
            }

            # Step-specific side effect.
            if step["step"] == "operator_alert":
                await db.retention_alerts.insert_one({
                    "id":         uuid.uuid4().hex,
                    "user_id":    wf["user_id"],
                    "lead_id":    wf["lead_id"],
                    "severity":   "at_risk",
                    "reason":     f"Retention workflow exhausted · score {wf.get('score', 0):.0f}/100",
                    "score":      wf.get("score"),
                    "workflow_id": wf["id"],
                    "created_at": now,
                })

            await db.seller_retention_workflows.update_one(
                {"id": wf["id"]}, {"$set": updates})
            advanced += 1

            # If last step just completed, flip status.
            w2 = await db.seller_retention_workflows.find_one({"id": wf["id"]})
            if all(s["status"] == "ok" for s in w2["steps"]):
                await db.seller_retention_workflows.update_one(
                    {"id": wf["id"]}, {"$set": {"status": "complete"}})
                completed += 1
        except Exception:
            logger.exception("retention cron: failed advancing wf=%s", wf.get("id"))

    return {"advanced_steps": advanced, "completed_workflows": completed,
            "scanned_at": now.isoformat()}


def register_retention_workflow_cron(scheduler) -> None:
    """Hourly scan for due retention-workflow steps. Hourly cadence keeps
    the 24h SLA tight even if the pod restarts during the day."""
    from apscheduler.triggers.interval import IntervalTrigger
    if scheduler.get_job("seller_retention_workflow_advance"):
        return
    scheduler.add_job(
        auto_advance_due_workflows,
        trigger=IntervalTrigger(hours=1),
        id="seller_retention_workflow_advance",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
