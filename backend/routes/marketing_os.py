"""Marketing OS — the "autonomous marketing operating system" layer.

This module is the orchestration + dashboard surface for the new
"Marketing Command Center" UX. It deliberately re-uses the existing
agent infrastructure (Convene SSE pipeline, llm_spend, memory, trends,
campaigns, feedback_loop) instead of introducing a new framework — the
business value is the *5-role canonical chain* + the unified dashboard
endpoint, not a swap of the runtime.

Five canonical roles (mapped to existing agents):
    Strategy      → Atlas   (strategy)
    Intelligence  → Iris    (research)
    Content       → Nova    (nova)
    Distribution  → Kai     (kai)
    Analytics     → Angela  (angela)

Endpoints:
    GET   /api/marketing-os/dashboard            consolidated Command Center payload
    GET   /api/marketing-os/signals              opportunity signals, ranked by virality
    POST  /api/marketing-os/run/stream           SSE — runs the 5-role chain
    GET   /api/marketing-os/runs                 history of recent runs

A "run" is persisted to the `marketing_os_runs` collection so the
activity feed and post-mortems work without re-running the LLM chain.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The canonical 5-role chain
# ---------------------------------------------------------------------------
CANONICAL_ROLES: list[dict] = [
    {"role": "strategy",     "agent_id": "strategy", "label": "Strategy",     "color": "blue"},
    {"role": "intelligence", "agent_id": "research", "label": "Intelligence", "color": "indigo"},
    {"role": "content",      "agent_id": "nova",     "label": "Content",     "color": "emerald"},
    {"role": "distribution", "agent_id": "kai",      "label": "Distribution", "color": "rose"},
    {"role": "analytics",    "agent_id": "angela",   "label": "Analytics",   "color": "violet"},
]
ROLE_CHAIN_AGENT_IDS = [r["agent_id"] for r in CANONICAL_ROLES[:-1]]  # last = summarizer
ROLE_SUMMARIZER_AGENT_ID = CANONICAL_ROLES[-1]["agent_id"]


# ---------------------------------------------------------------------------
# Dashboard — single roundtrip for the Command Center page
# ---------------------------------------------------------------------------
@api.get("/marketing-os/dashboard")
async def os_dashboard(request: Request):
    """Consolidated payload for the Marketing Command Center.

    Single endpoint so the page loads in one round-trip and the user sees
    a fully-populated UI without staggered loading states.

    Shape:
      stats:        {campaigns_active, pending_approvals, signals_hot, recent_wins}
      campaigns:    last 10 campaigns + status
      signals:      top 8 opportunity signals (virality_score desc)
      approvals:    first 5 pending-approval posts
      runs:         last 5 marketing-os run docs
      wins:         last 5 winning_hook memory rows
    """
    user = await get_current_user(request)
    uid = user.user_id

    now = datetime.now(timezone.utc)
    # Fan out all aggregations in parallel — they're independent.
    campaigns_task = db.campaigns.find(
        {"user_id": uid}, {"_id": 0, "plan_text": 0},
    ).sort("updated_at", -1).limit(10).to_list(length=10)

    signals_task = db.cortex_memory.find(
        {"user_id": uid, "kind": "trend"},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1).limit(80).to_list(length=80)

    approvals_task = db.posts.find(
        {"user_id": uid, "status": "pending_approval"}, {"_id": 0, "embedding": 0},
    ).sort("scheduled_at", 1).limit(5).to_list(length=5)

    runs_task = db.marketing_os_runs.find(
        {"user_id": uid}, {"_id": 0, "transcript": 0},
    ).sort("created_at", -1).limit(5).to_list(length=5)

    wins_task = db.cortex_memory.find(
        {"user_id": uid, "kind": "winning_hook"},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1).limit(5).to_list(length=5)

    counts_task_active = db.campaigns.count_documents(
        {"user_id": uid, "status": "active"},
    )
    counts_task_pending = db.posts.count_documents(
        {"user_id": uid, "status": "pending_approval"},
    )

    (campaigns, signals_raw, approvals, runs, wins,
     active_camp_count, pending_count) = await asyncio.gather(
        campaigns_task, signals_task, approvals_task, runs_task, wins_task,
        counts_task_active, counts_task_pending,
    )

    # Rank signals by virality (fall back to created_at when score absent
    # — e.g. legacy memories ingested before the signal refactor shipped).
    def _sig_score(row: dict) -> int:
        return int(((row.get("meta") or {}).get("signal") or {}).get("virality_score") or 0)
    signals_raw.sort(key=_sig_score, reverse=True)
    signals_top = signals_raw[:8]
    signals_hot = sum(1 for s in signals_raw if _sig_score(s) >= 75)

    return {
        "roles":     CANONICAL_ROLES,
        "stats": {
            "campaigns_active":  active_camp_count,
            "pending_approvals": pending_count,
            "signals_hot":       signals_hot,
            "recent_wins":       len(wins),
        },
        "campaigns": campaigns,
        "signals":   signals_top,
        "approvals": approvals,
        "runs":      runs,
        "wins":      wins,
        "fetched_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Signals — ranked feed for the Opportunity Signals card
# ---------------------------------------------------------------------------
@api.get("/marketing-os/signals")
async def list_signals(request: Request, limit: int = 20):
    """Opportunity signals for the calling user, ranked by virality_score
    (highest first). Falls back to created_at when score is missing."""
    user = await get_current_user(request)
    limit = max(1, min(100, int(limit or 20)))
    rows = await db.cortex_memory.find(
        {"user_id": user.user_id, "kind": "trend"},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1).limit(200).to_list(length=200)

    def _score(r: dict) -> int:
        return int(((r.get("meta") or {}).get("signal") or {}).get("virality_score") or 0)
    rows.sort(key=_score, reverse=True)
    return {"signals": rows[:limit], "count": min(limit, len(rows))}


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------
@api.get("/marketing-os/runs")
async def list_runs(request: Request, limit: int = 20):
    user = await get_current_user(request)
    limit = max(1, min(100, int(limit or 20)))
    rows = await db.marketing_os_runs.find(
        {"user_id": user.user_id}, {"_id": 0, "transcript": 0},
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return {"runs": rows, "count": len(rows)}


@api.get("/marketing-os/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.marketing_os_runs.find_one(
        {"id": run_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return doc


# ---------------------------------------------------------------------------
# Run the canonical 5-role chain (Strategy → Intelligence → Content →
# Distribution; Analytics synthesizes). SSE — same shape as convene.
# ---------------------------------------------------------------------------
class _RunRequest(BaseModel):
    brief:    str = Field(..., min_length=1, max_length=4000)
    # Optional override: a smaller subset of the chain to run (e.g.
    # ["strategy", "content"]). When omitted, the full chain runs.
    roles:    Optional[list[str]] = Field(default=None, max_length=5)
    mode:     Optional[str] = Field(default=None, max_length=24)
    # If set, the run is linked to an existing campaign and the brief is
    # enriched with the campaign goal/audience/pillars.
    campaign_id: Optional[str] = Field(default=None, max_length=64)


def _sse(event: str, data: dict) -> str:
    import json
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@api.post("/marketing-os/run/stream")
async def run_marketing_os(payload: _RunRequest, request: Request):
    """SSE stream — run the canonical 5-role marketing chain on a brief.

    Event vocabulary mirrors `/ai/agent/convene/stream` (`started`,
    `agent_started`, `agent_done`, `summarizing`, `complete`, `error`)
    so the existing Convene UI components can render this stream with
    minimal changes.

    The chain runs:
      Strategy (Atlas)  → Intelligence (Iris) → Content (Nova) →
      Distribution (Kai) → Analytics (Angela synthesises)

    On success, persists a `marketing_os_runs` row with the full
    transcript + summary so the Command Center activity feed has a
    historical record.
    """
    from routes.ai import _gated_user
    from routes.agent_chat import _convene, _AGENT_LOOKUP, _ConveneRequest

    user = await _gated_user(request)

    # Resolve optional role subset → agent-id chain.
    if payload.roles:
        agent_chain: list[str] = []
        for r in payload.roles:
            key = r.strip().lower()
            # Accept either role name ("strategy") or agent id ("nova").
            role_match = next(
                (cr for cr in CANONICAL_ROLES if cr["role"] == key or cr["agent_id"] == key),
                None,
            )
            if not role_match:
                raise HTTPException(status_code=422, detail=f"Unknown role: {r}")
            agent_chain.append(role_match["agent_id"])
        # Dedupe + ensure summarizer isn't in the chain (it'd run twice).
        seen: set[str] = set()
        agent_chain = [a for a in agent_chain if not (a in seen or seen.add(a))]
        if not agent_chain:
            raise HTTPException(status_code=422, detail="At least one role required")
        summarizer_id = (
            ROLE_SUMMARIZER_AGENT_ID
            if agent_chain[-1] != ROLE_SUMMARIZER_AGENT_ID
            else "strategy"
        )
        chain_for_run = [a for a in agent_chain if a != summarizer_id]
        if not chain_for_run:
            chain_for_run = [agent_chain[0]]
    else:
        chain_for_run = list(ROLE_CHAIN_AGENT_IDS)  # strategy → research → nova → kai
        summarizer_id = ROLE_SUMMARIZER_AGENT_ID    # angela synthesises

    # Optional campaign enrichment — pull the campaign doc and prepend
    # its goal/audience/pillars to the brief so the chain has context.
    brief_text = payload.brief.strip()
    campaign_id = None
    if payload.campaign_id:
        camp = await db.campaigns.find_one(
            {"id": payload.campaign_id, "user_id": user.user_id},
            {"_id": 0, "name": 1, "goal": 1, "audience": 1, "content_pillars": 1, "platforms": 1},
        )
        if not camp:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign_id = camp.get("name") and payload.campaign_id
        ctx_parts = [f"Campaign: {camp.get('name')}", f"Goal: {camp.get('goal')}"]
        if camp.get("audience"):
            ctx_parts.append(f"Audience: {camp['audience']}")
        if camp.get("content_pillars"):
            ctx_parts.append("Pillars: " + ", ".join(camp["content_pillars"]))
        if camp.get("platforms"):
            ctx_parts.append("Platforms: " + ", ".join(camp["platforms"]))
        brief_text = "\n".join(ctx_parts) + "\n\nBrief:\n" + brief_text

    # If the chain includes Nova (Content role) — which is the default —
    # inject the user's top winning hooks into the brief so the content
    # step doesn't have to rely on embedding retrieval to find them.
    # Constrained by platform when the campaign declares one; otherwise
    # cross-platform.
    if "nova" in chain_for_run:
        try:
            from routes.feedback_loop import winning_hooks_prompt_block
            # If the campaign declared exactly ONE platform, scope to it
            # (cleaner signal); otherwise pull globally.
            single_platform = ""
            if payload.campaign_id:
                camp_doc = await db.campaigns.find_one(
                    {"id": payload.campaign_id, "user_id": user.user_id},
                    {"_id": 0, "platforms": 1},
                ) or {}
                plats = camp_doc.get("platforms") or []
                if len(plats) == 1:
                    single_platform = plats[0]
            wb = await winning_hooks_prompt_block(
                user.user_id, platform=single_platform, limit=3,
            )
            if wb:
                brief_text += wb
        except Exception:
            logger.exception("winning-hooks injection failed (continuing)")

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    # Build a Convene-shaped payload so we can lean on the existing engine.
    convene_payload = _ConveneRequest(
        message=brief_text,
        agents=chain_for_run,
        summarizer=summarizer_id,
        mode=payload.mode,
    )

    async def event_stream():
        # Frame the first event with our run metadata so the UI can
        # display the persistent run_id (lets the user re-open the
        # transcript later from the activity feed).
        yield _sse("os_started", {
            "run_id":    run_id,
            "roles":     CANONICAL_ROLES,
            "chain":     chain_for_run,
            "summarizer": summarizer_id,
        })

        transcript: list[dict] = []
        summary_text = ""
        last_model = ""
        last_mode = ""
        try:
            async for ev, data in _convene(
                user, chain_for_run, summarizer_id, convene_payload,
            ):
                # Convene emits ("started", ...) — rename to keep the
                # outer "os_started" we already emitted, but pass everything
                # else through unchanged.
                if ev == "started":
                    continue
                if ev == "agent_done":
                    transcript.append({
                        "agent_id":   data.get("agent_id"),
                        "agent_name": data.get("agent_name"),
                        "answer":     data.get("answer"),
                    })
                if ev == "complete":
                    summary_text = data.get("summary") or ""
                    last_model = data.get("model") or ""
                    last_mode = data.get("mode") or ""
                yield _sse(ev, data)
        except Exception as e:
            yield _sse("error", {"message": str(e)[:300]})
            try:
                await db.marketing_os_runs.insert_one({
                    "id":          run_id,
                    "user_id":     user.user_id,
                    "brief":       payload.brief[:1500],
                    "campaign_id": campaign_id,
                    "chain":       chain_for_run,
                    "summarizer":  summarizer_id,
                    "status":      "failed",
                    "error":       str(e)[:500],
                    "transcript":  transcript,
                    "summary":     "",
                    "created_at":  started_at,
                    "finished_at": datetime.now(timezone.utc),
                })
            except Exception:
                logger.exception("Failed to persist failed run %s", run_id)
            return

        # Persist the completed run.
        try:
            await db.marketing_os_runs.insert_one({
                "id":          run_id,
                "user_id":     user.user_id,
                "brief":       payload.brief[:1500],
                "campaign_id": campaign_id,
                "chain":       chain_for_run,
                "summarizer":  summarizer_id,
                "status":      "completed",
                "transcript":  transcript,
                "summary":     summary_text,
                "model":       last_model,
                "mode":        last_mode,
                "created_at":  started_at,
                "finished_at": datetime.now(timezone.utc),
            })
        except Exception:
            logger.exception("Failed to persist run %s", run_id)

        # If the run was tied to a campaign, pin the latest summary onto
        # the campaign doc so the detail page surfaces "what the team
        # last said about this campaign" without an extra fetch.
        if campaign_id and summary_text:
            try:
                await db.campaigns.update_one(
                    {"id": campaign_id, "user_id": user.user_id},
                    {"$set": {
                        "latest_run_id":      run_id,
                        "latest_run_summary": summary_text[:1200],
                        "latest_run_at":      datetime.now(timezone.utc),
                        "updated_at":         datetime.now(timezone.utc),
                    }},
                )
            except Exception:
                logger.exception("Failed to pin run %s onto campaign %s", run_id, campaign_id)

        yield _sse("os_persisted", {"run_id": run_id})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.get("/marketing-os/roles")
async def list_roles(request: Request):
    """Public catalogue of the 5 canonical Marketing OS roles."""
    await get_current_user(request)
    return {"roles": CANONICAL_ROLES}
