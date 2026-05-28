"""Campaign — first-class container that turns "individual posts" into
"a goal-driven multi-post sequence the team executes against."

Schema (Mongo `campaigns` collection):
    id            str   uuid
    user_id       str   indexed
    name          str
    goal          str   "leads" | "awareness" | "sales" | "retention" | "custom"
    custom_goal   str?  free-text when goal == "custom"
    audience      str
    content_pillars  list[str]   (3-5 themes the campaign rotates through)
    kpi_targets   {ctr?, engagement_rate?, leads?, sales?, impressions?}
    start_date    datetime
    end_date      datetime
    status        "draft" | "active" | "completed" | "archived"
    platforms     list[str]
    notes         str?
    plan_text     str?  Atlas-generated campaign plan (markdown)
    created_at    datetime
    updated_at    datetime

Posts → campaigns: posts.campaign_id (nullable, indexed).

Endpoints:
    GET    /api/campaigns                          list
    POST   /api/campaigns                          create
    GET    /api/campaigns/{id}                     detail + linked posts + KPI aggregates
    PATCH  /api/campaigns/{id}                     partial update
    DELETE /api/campaigns/{id}                     archive (soft delete via status)
    POST   /api/campaigns/{id}/plan                ask Atlas to (re)generate the campaign plan
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)

GOAL_OPTIONS = {"leads", "awareness", "sales", "retention", "custom"}
STATUS_OPTIONS = {"draft", "active", "completed", "archived"}
MAX_PILLARS = 6


class _CampaignCreate(BaseModel):
    name:        str            = Field(..., min_length=1, max_length=120)
    goal:        str            = Field(default="awareness", max_length=24)
    custom_goal: Optional[str]  = Field(default=None, max_length=200)
    audience:    Optional[str]  = Field(default=None, max_length=300)
    content_pillars: Optional[list[str]] = Field(default=None, max_length=MAX_PILLARS)
    kpi_targets: Optional[dict] = None
    start_date:  Optional[datetime] = None
    end_date:    Optional[datetime] = None
    platforms:   Optional[list[str]] = Field(default=None, max_length=8)
    notes:       Optional[str]  = Field(default=None, max_length=2000)


class _CampaignUpdate(BaseModel):
    name:        Optional[str]  = Field(default=None, min_length=1, max_length=120)
    goal:        Optional[str]  = Field(default=None, max_length=24)
    custom_goal: Optional[str]  = Field(default=None, max_length=200)
    audience:    Optional[str]  = Field(default=None, max_length=300)
    content_pillars: Optional[list[str]] = Field(default=None, max_length=MAX_PILLARS)
    kpi_targets: Optional[dict] = None
    start_date:  Optional[datetime] = None
    end_date:    Optional[datetime] = None
    status:      Optional[str]  = Field(default=None, max_length=24)
    platforms:   Optional[list[str]] = Field(default=None, max_length=8)
    notes:       Optional[str]  = Field(default=None, max_length=2000)


def _validate_goal(goal: str) -> str:
    g = (goal or "").lower()
    if g not in GOAL_OPTIONS:
        raise HTTPException(status_code=422, detail=f"goal must be one of {sorted(GOAL_OPTIONS)}")
    return g


def _validate_status(status: str) -> str:
    s = (status or "").lower()
    if s not in STATUS_OPTIONS:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(STATUS_OPTIONS)}")
    return s


@api.get("/campaigns")
async def list_campaigns(request: Request, status: Optional[str] = None):
    """List the calling user's campaigns. Filter by `status` if provided.
    Sort newest first — admins usually want the most recent campaign at
    the top of the dashboard."""
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id}
    if status:
        q["status"] = _validate_status(status)
    rows = await db.campaigns.find(q, {"_id": 0}).sort("created_at", -1).to_list(length=200)
    return {"campaigns": rows, "count": len(rows)}


@api.post("/campaigns")
async def create_campaign(payload: _CampaignCreate, request: Request):
    """Create a new campaign in `draft` status. Atlas can be invoked
    separately via `POST /campaigns/{id}/plan` once basic fields are set."""
    user = await get_current_user(request)
    goal = _validate_goal(payload.goal)
    now = datetime.now(timezone.utc)
    doc = {
        "id":              str(uuid.uuid4()),
        "user_id":         user.user_id,
        "name":            payload.name.strip(),
        "goal":            goal,
        "custom_goal":     payload.custom_goal,
        "audience":        payload.audience,
        "content_pillars": payload.content_pillars or [],
        "kpi_targets":     payload.kpi_targets or {},
        "start_date":      payload.start_date,
        "end_date":        payload.end_date,
        "status":          "draft",
        "platforms":       payload.platforms or [],
        "notes":           payload.notes,
        "plan_text":       None,
        "created_at":      now,
        "updated_at":      now,
    }
    await db.campaigns.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request):
    """Campaign detail + linked posts list + aggregate KPI snapshot
    (across all posts in the campaign with metrics fetched)."""
    user = await get_current_user(request)
    doc = await db.campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Linked posts (sorted by scheduled date so the user sees the timeline).
    posts = await db.posts.find(
        {"user_id": user.user_id, "campaign_id": campaign_id},
        {"_id": 0, "embedding": 0},
    ).sort("scheduled_at", 1).to_list(length=500)

    # Aggregate metrics across all published posts.
    agg = {
        "total_posts":      len(posts),
        "by_status":        {},
        "impressions":      0,
        "engagement":       0,
        "clicks":           0,
        "leads":            0,
    }
    for p in posts:
        s = p.get("status") or "draft"
        agg["by_status"][s] = agg["by_status"].get(s, 0) + 1
        m = p.get("metrics") or {}
        agg["impressions"] += int(m.get("impressions") or 0)
        agg["engagement"]  += int(m.get("engagement")  or m.get("likes") or 0)
        agg["clicks"]      += int(m.get("clicks")      or 0)
        agg["leads"]       += int(m.get("leads")       or 0)

    doc["posts"]   = posts
    doc["metrics"] = agg
    return doc


@api.patch("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, payload: _CampaignUpdate, request: Request):
    """Partial update. Any field omitted stays as-is. Goal/status are
    strictly validated."""
    user = await get_current_user(request)
    update: dict = {}
    if payload.name is not None:        update["name"] = payload.name.strip()
    if payload.goal is not None:        update["goal"] = _validate_goal(payload.goal)
    if payload.custom_goal is not None: update["custom_goal"] = payload.custom_goal
    if payload.audience is not None:    update["audience"] = payload.audience
    if payload.content_pillars is not None: update["content_pillars"] = payload.content_pillars
    if payload.kpi_targets is not None: update["kpi_targets"] = payload.kpi_targets
    if payload.start_date is not None:  update["start_date"] = payload.start_date
    if payload.end_date is not None:    update["end_date"] = payload.end_date
    if payload.status is not None:      update["status"] = _validate_status(payload.status)
    if payload.platforms is not None:   update["platforms"] = payload.platforms
    if payload.notes is not None:       update["notes"] = payload.notes

    if not update:
        raise HTTPException(status_code=422, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc)
    r = await db.campaigns.update_one(
        {"id": campaign_id, "user_id": user.user_id}, {"$set": update},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    doc = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return doc


@api.delete("/campaigns/{campaign_id}")
async def archive_campaign(campaign_id: str, request: Request):
    """Soft delete — just flip status to `archived` so analytics history
    is preserved. Hard delete is intentionally not exposed."""
    user = await get_current_user(request)
    r = await db.campaigns.update_one(
        {"id": campaign_id, "user_id": user.user_id},
        {"$set": {"status": "archived",
                  "updated_at": datetime.now(timezone.utc)}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"ok": True}


@api.post("/campaigns/{campaign_id}/plan")
async def generate_campaign_plan(campaign_id: str, request: Request):
    """Send the campaign brief to Atlas → get back a structured plan
    (audience cuts, hook angles, 30/60/90 day cadence). Stored on the
    campaign doc as `plan_text` so the frontend can render it directly.

    Atlas's response is intentionally markdown — the Campaign Detail
    page renders it as a section below the KPI cards."""
    from routes.ai import _llm_for_user, send_with_usage, _gated_user
    from routes.agent_chat import AGENTS, _FUPS_RE, _HANDOFF_RE
    from routes.model_router import resolve_user_mode
    from routes.llm_spend import record_llm_call
    from emergentintegrations.llm.chat import UserMessage

    user = await _gated_user(request)
    doc = await db.campaigns.find_one(
        {"id": campaign_id, "user_id": user.user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Campaign not found")

    atlas = AGENTS["strategy"]
    user_doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "agent_prefs": 1, "brand_name": 1, "niche": 1},
    ) or {}
    user_mode = (user_doc.get("agent_prefs") or {}).get("strategy", "auto")
    provider, model, task_used = resolve_user_mode(user_mode, "strategy")

    brand_block = ""
    if user_doc.get("brand_name") or user_doc.get("niche"):
        brand_block = (
            f"\n\nBrand: {user_doc.get('brand_name') or 'n/a'} · "
            f"Niche: {user_doc.get('niche') or 'n/a'}"
        )

    system = atlas["system"] + (
        "\n\nProduce a CAMPAIGN PLAN as markdown with these sections:\n"
        "  1. ## North-star metric — one line, quantified.\n"
        "  2. ## Audience cuts — 2-3 segments + the pain each one feels.\n"
        "  3. ## Hook angles — 5 angles (controversial, contrarian, data-driven, "
        "personal, how-to). One sentence each.\n"
        "  4. ## Cadence — week-by-week post breakdown for the campaign window.\n"
        "  5. ## Success threshold — what KPI numbers count as a win.\n"
        "Be specific. No fluff. Total length under 500 words."
        + brand_block
    )

    brief_parts = [
        f"Campaign name: {doc['name']}",
        f"Goal: {doc.get('custom_goal') or doc['goal']}",
    ]
    if doc.get("audience"):
        brief_parts.append(f"Audience: {doc['audience']}")
    if doc.get("content_pillars"):
        brief_parts.append("Content pillars: " + ", ".join(doc["content_pillars"]))
    if doc.get("platforms"):
        brief_parts.append("Platforms: " + ", ".join(doc["platforms"]))
    if doc.get("start_date") and doc.get("end_date"):
        brief_parts.append(
            f"Window: {doc['start_date'].date().isoformat()} → {doc['end_date'].date().isoformat()}"
        )
    if doc.get("kpi_targets"):
        brief_parts.append("KPI targets: " + ", ".join(
            f"{k}={v}" for k, v in doc["kpi_targets"].items() if v
        ))
    if doc.get("notes"):
        brief_parts.append("Notes: " + doc["notes"])
    brief = "\n".join(brief_parts)

    chat = await _llm_for_user(
        user.user_id, f"campaign-plan-{campaign_id}", system,
        provider=provider, model=model,
    )
    try:
        plan, usage = await send_with_usage(chat, UserMessage(text=brief))
    except Exception as e:
        if "budget" in str(e).lower():
            raise HTTPException(status_code=503, detail="LLM budget exceeded")
        raise HTTPException(status_code=502, detail=f"Plan generation failed: {str(e)[:200]}")
    plan = _FUPS_RE.sub("", plan)
    plan = _HANDOFF_RE.sub("", plan).strip()

    try:
        await record_llm_call(user.user_id, "strategy", task_used, model, usage)
    except Exception:
        pass

    await db.campaigns.update_one(
        {"id": campaign_id, "user_id": user.user_id},
        {"$set": {"plan_text": plan,
                  "updated_at": datetime.now(timezone.utc)}},
    )
    return {"plan": plan, "model": model, "mode": task_used}
