"""Briefs — campaign brief proposals owned by Atlas.

Phase 3 of the Autonomous Growth Team. Moves the UX from
"user asks, agent drafts" to "agent proposes, user approves":

  1. Atlas scans open Growth Goals + recent Listening Signals.
  2. LLM call produces 1–3 brief proposals tied to the strongest signals.
  3. Each proposal lands in `proposed_briefs` with status=pending.
  4. Operator visits /dashboard/briefs to Approve / Edit / Reject.
  5. Approve → creates a real campaign + links back via resolved_into_campaign_id.

Modes (per-user runtime toggle, stored in `autopilot_settings`):
  - manual  (default) — only `POST /briefs/propose` works
  - autopilot         — daily 09:00 UTC scan runs for this user

Memory writes on reject — Atlas learns from operator rejections so the
NEXT scan doesn't propose the same kind of brief. Approved briefs aren't
written to memory (they're already proven by the resulting campaign).
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user
from routes.memory import remember

logger = logging.getLogger(__name__)


# Max briefs Atlas can propose in a single scan. Keeps the inbox sane —
# 1–3 is the sweet spot per our product spec.
MAX_BRIEFS_PER_SCAN = 3

ALLOWED_MODES = {"manual", "autopilot"}


# ---------------------------------------------------------------------
# Auto-approval helpers — Phase 5 integration
# ---------------------------------------------------------------------
async def _maybe_auto_approve(user_id: str, brief: dict) -> Optional[dict]:
    """If the user opted into auto-approve AND Atlas has budget headroom,
    spawn the campaign immediately and return the created campaign doc.
    Returns None if the brief should stay `pending` (default HITL path)."""
    settings = await db.autopilot_settings.find_one(
        {"user_id": user_id}, {"_id": 0, "auto_approve_briefs": 1},
    ) or {}
    if not settings.get("auto_approve_briefs"):
        return None

    from routes.autonomy import can_auto_approve, record_usage
    allowed, reason = await can_auto_approve("atlas", user_id)
    if not allowed:
        logger.info("brief auto-approve gated for user=%s: %s", user_id, reason)
        return None

    now = datetime.now(timezone.utc)
    campaign_doc = {
        "id":              str(uuid.uuid4()),
        "user_id":         user_id,
        "name":            brief["title"][:120],
        "goal":            "awareness",
        "custom_goal":     None,
        "audience":        None,
        "content_pillars": [],
        "kpi_targets":     {brief.get("target_metric") or "engagements": 0},
        "start_date":      now,
        "end_date":        None,
        "status":          "draft",
        "platforms":       brief.get("suggested_platforms") or [],
        "notes":           (f"Auto-approved by Atlas (Phase 5 autonomy budget).\n"
                            f"Reason: {reason}\n\n"
                            f"Hypothesis: {brief.get('hypothesis') or '—'}\n\n"
                            f"Brief body:\n{brief['body']}\n\n"
                            f"Rationale: {brief.get('rationale') or '—'}"),
        "plan_text":       None,
        "proposed_brief_id": brief["id"],
        "created_at":      now,
        "updated_at":      now,
    }
    await db.campaigns.insert_one(campaign_doc)
    # Burn one irreversible from Atlas's weekly budget.
    await record_usage("atlas", user_id, irreversible=1)
    campaign_doc.pop("_id", None)
    return campaign_doc


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
async def _gather_atlas_facts(user_id: str) -> dict:
    """Pull the same shape of facts Atlas needs to propose briefs:
       open goals (vera's domain) + recent listening signals (lyra's domain).
    Caps each list so the prompt stays compact."""
    goals = await db.growth_goals.find(
        {"user_id": user_id, "status": "active"},
        {"_id": 0, "title": 1, "description": 1, "metric": 1, "target": 1, "deadline": 1},
    ).sort("created_at", -1).to_list(length=10)

    since = datetime.now(timezone.utc) - timedelta(days=7)
    signals = await db.social_listening_signals.find(
        {"user_id": user_id, "detected_at": {"$gte": since}},
        {"_id": 0, "id": 1, "text": 1, "sentiment": 1, "signal_type": 1,
         "urgency": 1, "source": 1, "topic": 1},
    ).sort("detected_at", -1).to_list(length=20)

    # Past rejections — feed back so Atlas doesn't keep proposing the same thing.
    # We pull the last 5 reject memories Atlas's owner has written.
    reject_memories = await db.cortex_memory.find(
        {"user_id": user_id, "kind": "brief_rejected"},
        {"_id": 0, "text": 1},
    ).sort("created_at", -1).to_list(length=5)

    return {
        "goals":             goals,
        "signals":           signals,
        "reject_memories":   reject_memories,
    }


async def _llm_propose_briefs(facts: dict, max_briefs: int = MAX_BRIEFS_PER_SCAN,
                              *, user_id: Optional[str] = None) -> list[dict]:
    """One LLM call → up to N brief proposals. Falls back to a deterministic
    single-brief stub when the LLM key is missing (so the system still works
    in test envs without an API key).

    Phase 6: before calling the LLM, Atlas asks Lyra to identify the strongest
    THEME across the recent listening signals. Lyra's answer is appended to
    the prompt so Atlas can collapse redundant signals into ONE sharper brief
    instead of N noisy ones."""
    from core import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        return _fallback_briefs(facts, max_briefs)

    # Phase 6 hand-offs — Atlas consults the team before drafting briefs.
    # Best-effort; each handoff failure logs + skips, never blocks proposal.
    lyra_answer: Optional[str] = None    # signal-theme analysis
    ori_answer:  Optional[str] = None    # past-experiment recall
    rae_answer:  Optional[str] = None    # audience-fit gut check
    signals = facts.get("signals") or []
    goals   = facts.get("goals") or []
    if user_id:
        try:
            from routes.agent_messaging import query_agent

            # Atlas → Lyra: theme detection (only when ≥3 signals to merge).
            if len(signals) >= 3:
                sigs_compact = "\n".join(
                    f"  • [{s.get('sentiment','?')}|{s.get('signal_type','mention')}] "
                    f"{(s.get('text') or '')[:140]}"
                    for s in signals[:8]
                )
                r = await query_agent(
                    user_id=user_id, from_agent="atlas", to_agent="lyra",
                    query=("Given these listening signals, what's the strongest "
                           "shared theme worth ONE brief instead of multiple? "
                           "If they don't cohere, say so."),
                    context_str=sigs_compact,
                )
                if r.get("ok"):
                    lyra_answer = r.get("response")

            # Atlas → Ori: have we tested this kind of brief before? Ori
            # has the memory of `experiment_winner` rows. Asks once per
            # propose call, citing the active goals as the proxy topic.
            if goals:
                goals_compact = "\n".join(
                    f"  • {g['title']} — metric {g['metric']}"
                    for g in goals[:5]
                )
                r = await query_agent(
                    user_id=user_id, from_agent="atlas", to_agent="ori",
                    query=("Looking at these active goals, have we tested any "
                           "winning patterns in your memory I should lean into? "
                           "Cite specific learnings if you have them."),
                    context_str=goals_compact,
                )
                if r.get("ok"):
                    ori_answer = r.get("response")

            # Atlas → Rae: audience-fit gut check. Asks Rae which platform
            # mix would resonate given the goals + signals. Rae is the
            # community persona — she knows the audience texture.
            if signals or goals:
                rae_context = ""
                if goals:
                    rae_context += "Goals:\n" + "\n".join(
                        f"  • {g['title']}" for g in goals[:3]
                    )
                if signals:
                    rae_context += ("\n\nSignals:\n" + "\n".join(
                        f"  • {(s.get('text') or '')[:120]}" for s in signals[:5]
                    ))
                r = await query_agent(
                    user_id=user_id, from_agent="atlas", to_agent="rae",
                    query=("Given these goals and signals, which platform(s) will "
                           "the audience care about most this week? Be specific."),
                    context_str=rae_context.strip(),
                )
                if r.get("ok"):
                    rae_answer = r.get("response")
        except Exception as exc:
            logger.debug("Atlas hand-offs partially skipped: %s", exc)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage
        import asyncio as _asyncio
        import json as _json
        import re

        goals_str = "\n".join(
            f"  • {g['title']} — metric {g['metric']} target {g['target']}"
            for g in (facts.get("goals") or [])[:5]
        ) or "  (no active goals yet — focus on signals)"

        sigs_str = "\n".join(
            f"  • [{s.get('sentiment','neutral')}|{s.get('signal_type','mention')}|"
            f"urgency {s.get('urgency',1)}/5] {(s.get('text') or '')[:160]}"
            for s in (facts.get("signals") or [])[:8]
        ) or "  (no recent signals)"

        rejects_str = "\n".join(
            f"  • {r.get('text','')[:200]}" for r in (facts.get("reject_memories") or [])
        ) or "  (none)"

        lyra_block = ""
        if lyra_answer:
            lyra_block = (
                f"\nLYRA'S ANALYSIS OF THE SIGNALS (use this to merge redundant briefs):\n"
                f"  {lyra_answer}\n"
            )
        ori_block = ""
        if ori_answer:
            ori_block = (
                f"\nORI'S MEMORY OF PAST WINNERS (lean into these patterns when relevant):\n"
                f"  {ori_answer}\n"
            )
        rae_block = ""
        if rae_answer:
            rae_block = (
                f"\nRAE'S AUDIENCE-FIT GUT CHECK (respect this when picking platforms):\n"
                f"  {rae_answer}\n"
            )

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"atlas_propose_{datetime.now(timezone.utc).strftime('%Y%m%d%H')}",
            system_message=(
                "You are Atlas, the strategist on CortexViral's autonomous growth team. "
                "You propose campaign briefs tied to OPEN goals + RECENT signals, taking "
                "Lyra's theme analysis into account when collapsing redundant signals. "
                "Each brief is concise: a title, a 1-sentence hypothesis, a 3-sentence body, "
                "a rationale citing the source goal/signal, and a suggested platform mix. "
                "Output STRICT JSON only. Never propose more than the requested count. "
                "Skip briefs that resemble past rejections."
            ),
        ).with_model("openai", "gpt-5-mini")

        prompt = (
            f"OPEN GOALS:\n{goals_str}\n\n"
            f"RECENT LISTENING SIGNALS (last 7d):\n{sigs_str}\n"
            f"{lyra_block}{ori_block}{rae_block}\n"
            f"RECENT REJECTIONS (avoid resembling these):\n{rejects_str}\n\n"
            f"Propose UP TO {max_briefs} campaign brief(s). Output a strict JSON array. "
            "Each object MUST have exactly these keys: "
            "{\"title\": str (<=80 chars), "
            "\"hypothesis\": str (1 sentence, <=200 chars), "
            "\"body\": str (3 sentences, <=800 chars), "
            "\"rationale\": str (cite which goal/signal id, <=300 chars), "
            "\"suggested_platforms\": list[str] (subset of "
            "[\"instagram\",\"facebook\",\"linkedin\",\"tiktok\",\"x\",\"youtube\",\"pinterest\"]), "
            "\"target_metric\": str (one of [\"engagements\",\"impressions\",\"clicks\",\"reach\",\"leads\"])}. "
            "If no signals OR goals are strong enough to justify a brief, return an empty array []."
        )

        text, _ = await _asyncio.wait_for(
            send_with_usage(chat, UserMessage(text=prompt),
                            agent_id="atlas",
                            user_id=user_id,
                            model="gpt-5-mini"),
            timeout=30,
        )
        cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = _json.loads(cleaned)
        if not isinstance(parsed, list):
            raise ValueError("not a list")
        # Sanity-cap + shape-coerce
        out: list[dict] = []
        for it in parsed[:max_briefs]:
            if not isinstance(it, dict):
                continue
            out.append({
                "title":               str(it.get("title") or "").strip()[:140],
                "hypothesis":          str(it.get("hypothesis") or "").strip()[:300],
                "body":                str(it.get("body") or "").strip()[:1200],
                "rationale":           str(it.get("rationale") or "").strip()[:500],
                "suggested_platforms": [p for p in (it.get("suggested_platforms") or [])
                                         if isinstance(p, str)][:8],
                "target_metric":       str(it.get("target_metric") or "engagements").strip()[:32],
            })
        return [b for b in out if b["title"] and b["body"]]
    except Exception as exc:
        logger.warning("Atlas LLM propose failed (%s) — using fallback", exc)
        return _fallback_briefs(facts, max_briefs)


def _fallback_briefs(facts: dict, max_briefs: int) -> list[dict]:
    """Deterministic stub when the LLM is unavailable. Returns at most
    one generic brief tied to the most-recent goal — keeps the system
    functional without an API key."""
    goals = facts.get("goals") or []
    signals = facts.get("signals") or []
    if not goals and not signals:
        return []
    title_seed = (goals[0]["title"] if goals else
                  f"Engage on '{(signals[0].get('topic') or 'recent signal')}'")
    return [{
        "title":      f"Brief: {title_seed[:60]}",
        "hypothesis": "Posting on the strongest signal this week lifts engagement.",
        "body":       ("Run a 3-post mini-series across the top platforms tied to the "
                       "most recent goal/signal. Test a question-led hook on the first "
                       "post, repurpose the highest-performing variant on day 3."),
        "rationale":  (f"Tied to goal '{goals[0]['title']}'" if goals else
                       f"Tied to listening signal: {(signals[0].get('text') or '')[:120]}"),
        "suggested_platforms": ["instagram", "linkedin"],
        "target_metric":       "engagements",
    }][:max_briefs]


async def _persist_proposals(user_id: str, briefs: list[dict],
                             *, source: str = "manual") -> list[dict]:
    """Insert N briefs as `pending`. Returns the inserted rows.

    Phase 5: when `source == 'autopilot'` AND the user opted into
    `auto_approve_briefs` AND Atlas has weekly budget headroom, the
    brief is inserted as `approved` with a campaign already spawned —
    skipping the HITL inbox entirely."""
    now = datetime.now(timezone.utc)
    docs: list[dict] = []
    for b in briefs:
        bid = uuid.uuid4().hex
        doc = {
            "id":                 bid,
            "user_id":            user_id,
            "proposer_agent":     "atlas",
            "title":              b["title"],
            "hypothesis":         b.get("hypothesis"),
            "body":               b["body"],
            "rationale":          b.get("rationale"),
            "suggested_platforms": b.get("suggested_platforms") or [],
            "target_metric":      b.get("target_metric"),
            "status":             "pending",
            "source":             source,  # "manual" | "autopilot"
            "auto_approved":      False,
            "created_at":         now,
            "decided_at":         None,
            "decided_by":         None,
            "resolved_into_campaign_id": None,
            "edited_body":        None,
        }

        # Phase 5 auto-approve path — autopilot-only, opt-in, budget-gated.
        campaign = None
        if source == "autopilot":
            campaign = await _maybe_auto_approve(user_id, doc)
        if campaign:
            doc["status"]                    = "approved"
            doc["auto_approved"]             = True
            doc["decided_at"]                = now
            doc["decided_by"]                = "atlas (auto-approved by autonomy budget)"
            doc["resolved_into_campaign_id"] = campaign["id"]

        await db.proposed_briefs.insert_one(doc)
        doc.pop("_id", None)
        docs.append(doc)

    # Fire a realtime broadcast so the inbox bell badge updates instantly.
    if docs:
        try:
            from routes.realtime import broadcast_to_user
            await broadcast_to_user(user_id, "briefs_proposed", {
                "count":          len(docs),
                "brief_id":       docs[0]["id"],
                "title":          docs[0]["title"],
                "auto_approved":  sum(1 for d in docs if d.get("auto_approved")),
            })
        except Exception:
            logger.debug("briefs broadcast skipped", exc_info=True)
    return docs


# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
class ProposeRequest(BaseModel):
    max_briefs: int = Field(default=MAX_BRIEFS_PER_SCAN, ge=1, le=5)


class EditRequest(BaseModel):
    body: str = Field(..., min_length=10, max_length=1500)


class AutopilotPatch(BaseModel):
    briefs_mode: Optional[str] = None  # "manual" | "autopilot"
    auto_approve_briefs: Optional[bool] = None  # Phase 5 opt-in


# ---------------------------------------------------------------------
# HTTP API — autopilot settings
# ---------------------------------------------------------------------
@api.get("/briefs/settings")
async def get_brief_settings(request: Request):
    """Returns the user's current brief-mode + cadence info."""
    user = await get_current_user(request)
    doc = await db.autopilot_settings.find_one(
        {"user_id": user.user_id}, {"_id": 0},
    ) or {}
    return {
        "briefs_mode":         doc.get("briefs_mode", "manual"),
        "cadence_label":       "Daily at 09:00 UTC" if doc.get("briefs_mode") == "autopilot" else "Manual only",
        "auto_approve_briefs": bool(doc.get("auto_approve_briefs", False)),
        "last_scan_at":        doc.get("last_brief_scan_at"),
        "max_per_scan":        MAX_BRIEFS_PER_SCAN,
    }


@api.put("/briefs/settings")
async def update_brief_settings(payload: AutopilotPatch, request: Request):
    user = await get_current_user(request)
    set_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.briefs_mode is not None:
        if payload.briefs_mode not in ALLOWED_MODES:
            raise HTTPException(status_code=400,
                                detail=f"briefs_mode must be one of {sorted(ALLOWED_MODES)}")
        set_fields["briefs_mode"] = payload.briefs_mode
    if payload.auto_approve_briefs is not None:
        set_fields["auto_approve_briefs"] = bool(payload.auto_approve_briefs)
    if len(set_fields) == 1:
        raise HTTPException(status_code=400, detail="No fields to update")
    now = datetime.now(timezone.utc)
    await db.autopilot_settings.update_one(
        {"user_id": user.user_id},
        {"$set": set_fields,
         "$setOnInsert": {"user_id": user.user_id, "created_at": now}},
        upsert=True,
    )
    return await get_brief_settings(request)


# ---------------------------------------------------------------------
# HTTP API — briefs CRUD
# ---------------------------------------------------------------------
@api.post("/briefs/propose")
async def propose_briefs(payload: ProposeRequest, request: Request):
    """Manual trigger — Atlas scans + proposes immediately. Returns the
    list of newly-created briefs (could be empty if no strong signals).
    Persists `last_brief_scan_at` even on empty result so the UI can
    show 'last checked X mins ago'."""
    user = await get_current_user(request)
    facts = await _gather_atlas_facts(user.user_id)
    briefs = await _llm_propose_briefs(facts, max_briefs=payload.max_briefs, user_id=user.user_id)
    saved = await _persist_proposals(user.user_id, briefs, source="manual")
    await db.autopilot_settings.update_one(
        {"user_id": user.user_id},
        {"$set": {"last_brief_scan_at": datetime.now(timezone.utc)},
         "$setOnInsert": {"user_id": user.user_id, "briefs_mode": "manual",
                          "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"items": saved, "count": len(saved)}


@api.get("/briefs")
async def list_briefs(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query: dict = {"user_id": user.user_id}
    if status:
        query["status"] = status
    docs = await db.proposed_briefs.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    pending = [b for b in docs if b["status"] == "pending"]
    approved = [b for b in docs if b["status"] == "approved"]
    rejected = [b for b in docs if b["status"] == "rejected"]
    # Avg time-to-decision (minutes) across decided briefs in the window.
    decided = [b for b in docs if b.get("decided_at") and b.get("created_at")]
    avg_decision_minutes = 0
    if decided:
        diffs = []
        for b in decided:
            ca = b["created_at"]
            da = b["decided_at"]
            if isinstance(ca, datetime) and isinstance(da, datetime):
                if ca.tzinfo is None: ca = ca.replace(tzinfo=timezone.utc)
                if da.tzinfo is None: da = da.replace(tzinfo=timezone.utc)
                diffs.append((da - ca).total_seconds() / 60)
        avg_decision_minutes = round(sum(diffs) / len(diffs), 1) if diffs else 0
    return {
        "items":               docs,
        "count":               len(docs),
        "pending_count":       len(pending),
        "approved_count":      len(approved),
        "rejected_count":      len(rejected),
        "avg_decision_minutes": avg_decision_minutes,
    }


@api.get("/briefs/{brief_id}")
async def get_brief(brief_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.proposed_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Brief not found")
    return doc


@api.post("/briefs/{brief_id}/approve")
async def approve_brief(brief_id: str, request: Request):
    """Approve → creates a campaign from the brief + flips status to
    `approved`. Returns the created campaign + the resolved brief."""
    user = await get_current_user(request)
    brief = await db.proposed_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id, "status": "pending"},
        {"_id": 0},
    )
    if not brief:
        raise HTTPException(status_code=404, detail="Pending brief not found")

    now = datetime.now(timezone.utc)
    body = brief.get("edited_body") or brief["body"]
    campaign_doc = {
        "id":              str(uuid.uuid4()),
        "user_id":         user.user_id,
        "name":            brief["title"][:120],
        "goal":            "awareness",
        "custom_goal":     None,
        "audience":        None,
        "content_pillars": [],
        "kpi_targets":     {brief.get("target_metric") or "engagements": 0},
        "start_date":      now,
        "end_date":        None,
        "status":          "draft",
        "platforms":       brief.get("suggested_platforms") or [],
        "notes":           f"From proposed brief #{brief_id[:8]}.\n\n"
                           f"Hypothesis: {brief.get('hypothesis') or '—'}\n\n"
                           f"Brief body:\n{body}\n\n"
                           f"Rationale: {brief.get('rationale') or '—'}",
        "plan_text":       None,
        "proposed_brief_id": brief_id,  # cross-ref back
        "created_at":      now,
        "updated_at":      now,
    }
    await db.campaigns.insert_one(campaign_doc)

    await db.proposed_briefs.update_one(
        {"id": brief_id},
        {"$set": {
            "status":                    "approved",
            "decided_at":                now,
            "decided_by":                getattr(user, "email", None) or user.user_id,
            "resolved_into_campaign_id": campaign_doc["id"],
        }},
    )
    # Phase 5: stamp Atlas's ledger so manual approvals also count toward
    # the weekly irreversible cap (consistency with auto-approve path).
    from routes.autonomy import record_usage
    await record_usage("atlas", user.user_id, irreversible=1)
    updated = await db.proposed_briefs.find_one({"id": brief_id}, {"_id": 0})
    return {"brief": updated, "campaign": {k: v for k, v in campaign_doc.items() if k != "_id"}}


@api.post("/briefs/{brief_id}/reject")
async def reject_brief(brief_id: str, request: Request):
    """Reject → flip status + write a `brief_rejected` memory row so
    Atlas avoids similar proposals in the next scan."""
    user = await get_current_user(request)
    brief = await db.proposed_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id, "status": "pending"},
        {"_id": 0},
    )
    if not brief:
        raise HTTPException(status_code=404, detail="Pending brief not found")
    now = datetime.now(timezone.utc)

    memory_text = (
        f"Operator rejected Atlas's brief titled '{brief['title']}'. "
        f"Hypothesis was: {brief.get('hypothesis') or '—'}. "
        f"Avoid proposing similar briefs in future scans."
    )
    mem_id = await remember(
        user.user_id, kind="brief_rejected", text=memory_text,
        meta={"brief_id": brief_id, "title": brief["title"],
              "suggested_platforms": brief.get("suggested_platforms")},
        dedupe_key=f"brief_rejected:{brief_id}",
    )

    await db.proposed_briefs.update_one(
        {"id": brief_id},
        {"$set": {
            "status":     "rejected",
            "decided_at": now,
            "decided_by": getattr(user, "email", None) or user.user_id,
            "memory_id":  mem_id,
        }},
    )
    return await db.proposed_briefs.find_one({"id": brief_id}, {"_id": 0})


@api.patch("/briefs/{brief_id}/edit")
async def edit_brief(brief_id: str, payload: EditRequest, request: Request):
    """Operator-edited body — preserves the original for audit + stamps
    `edited_body`. Approve will use the edited version when present."""
    user = await get_current_user(request)
    brief = await db.proposed_briefs.find_one(
        {"id": brief_id, "user_id": user.user_id, "status": "pending"},
        {"_id": 0},
    )
    if not brief:
        raise HTTPException(status_code=404, detail="Pending brief not found")
    await db.proposed_briefs.update_one(
        {"id": brief_id},
        {"$set": {"edited_body": payload.body.strip(),
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return await db.proposed_briefs.find_one({"id": brief_id}, {"_id": 0})


@api.delete("/briefs/{brief_id}")
async def delete_brief(brief_id: str, request: Request):
    user = await get_current_user(request)
    res = await db.proposed_briefs.delete_one({"id": brief_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Brief not found")
    return {"ok": True}


# ---------------------------------------------------------------------
# Autopilot scanner — invoked from the scheduler
# ---------------------------------------------------------------------
async def run_autopilot_scan() -> dict:
    """Iterates over users with `briefs_mode=autopilot` and runs Atlas.

    Anti-spam: skip a user if their last scan was less than 20 hours
    ago (handles double-firing during deploys / restarts). Errors per
    user are logged but never propagate — one bad user's LLM error
    must not poison the entire cron."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=20)
    total_briefs = 0
    users_processed = 0
    users_skipped = 0

    cursor = db.autopilot_settings.find(
        {"briefs_mode": "autopilot"},
        {"_id": 0, "user_id": 1, "last_brief_scan_at": 1},
    )
    async for s in cursor:
        uid = s["user_id"]
        last = s.get("last_brief_scan_at")
        if isinstance(last, datetime):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last >= cutoff:
                users_skipped += 1
                continue
        try:
            facts = await _gather_atlas_facts(uid)
            briefs = await _llm_propose_briefs(facts, max_briefs=MAX_BRIEFS_PER_SCAN, user_id=uid)
            saved = await _persist_proposals(uid, briefs, source="autopilot")
            total_briefs += len(saved)
            users_processed += 1
            await db.autopilot_settings.update_one(
                {"user_id": uid},
                {"$set": {"last_brief_scan_at": now}},
            )
        except Exception:
            logger.exception("autopilot scan failed for user_id=%s", uid)
    summary = {
        "users_processed": users_processed,
        "users_skipped":   users_skipped,
        "total_briefs":    total_briefs,
        "ran_at":          now,
    }
    logger.info("briefs autopilot scan complete — %s", summary)
    return summary


def register_brief_autopilot_job(scheduler) -> None:
    """Daily 09:00 UTC scan. Idempotent — only adds the job if missing."""
    from apscheduler.triggers.cron import CronTrigger
    if scheduler.get_job("brief_autopilot_daily"):
        return
    scheduler.add_job(
        run_autopilot_scan,
        trigger=CronTrigger(hour=9, minute=0),
        id="brief_autopilot_daily",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
