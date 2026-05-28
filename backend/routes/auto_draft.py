"""Weekly auto-draft job: turns the top N trend signals into ready-to-
review drafts every Monday, dropped into the Approvals queue.

Opt-in per user. Stored on the user doc:
    users.auto_draft_trends = {
        enabled:      bool   (default False)
        platform:     str    (linkedin/twitter/instagram/tiktok/pinterest/facebook; default linkedin)
        count:        int    (how many drafts per week; default 3, range 1-5)
        last_run_at:  datetime  (used as a TTL window so re-running the
                                 cron doesn't double-fire on the same week)
    }

Endpoints:
    GET  /api/trends/auto-draft/settings   → current config
    PUT  /api/trends/auto-draft/settings   → update config

Scheduler:
    `run_weekly_auto_drafts()` registered at 08:00 UTC every Monday via
    apscheduler's CronTrigger. Each cron tick scans for opted-in users
    whose `last_run_at` is more than 6 days old, then for each user:
      1. Pick the top `count` recent trend memories by recency.
      2. Run each through `_draft_from_trend_silent()` (a server-side
         clone of the API endpoint that doesn't require a Request).
      3. Insert one `pending_approval` post into the `posts` collection
         per draft. The user gets an approval queue badge to clear out.

Idempotency is handled at multiple layers:
  • Per-user `last_run_at` window prevents same-day re-runs.
  • A `dedupe_key` on the post (`auto_draft:{trend_id}:{platform}`) is
    upserted, so even if the cron double-fires for some reason we only
    end up with one draft per (signal, platform).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.triggers.cron import CronTrigger
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    "linkedin", "twitter", "x", "instagram", "tiktok", "pinterest", "facebook",
}
MAX_DRAFTS_PER_WEEK = 5
MIN_DRAFTS_PER_WEEK = 1
RUN_COOLDOWN_DAYS = 6  # only fire if 6+ days since last run for this user


class _AutoDraftSettings(BaseModel):
    enabled:  Optional[bool] = None
    platform: Optional[str]  = Field(default=None, max_length=24)
    count:    Optional[int]  = Field(default=None, ge=MIN_DRAFTS_PER_WEEK, le=MAX_DRAFTS_PER_WEEK)


def _default_settings() -> dict:
    return {"enabled": False, "platform": "linkedin", "count": 3,
            "last_run_at": None}


@api.get("/trends/auto-draft/settings")
async def get_auto_draft_settings(request: Request):
    """Read the calling user's weekly auto-draft config. Always returns
    a fully-populated object — fields default to sensible values on
    first read so the UI can render the toggle without conditional
    logic."""
    user = await get_current_user(request)
    doc = await db.users.find_one(
        {"user_id": user.user_id}, {"_id": 0, "auto_draft_trends": 1},
    ) or {}
    settings = doc.get("auto_draft_trends") or {}
    return {**_default_settings(), **settings,
            "max_count": MAX_DRAFTS_PER_WEEK}


@api.put("/trends/auto-draft/settings")
async def set_auto_draft_settings(payload: _AutoDraftSettings, request: Request):
    """Patch the auto-draft config. Any field omitted from the request
    body is left unchanged. `platform` is strictly validated so an
    invalid value never makes it into the cron logic."""
    user = await get_current_user(request)
    update: dict = {}
    if payload.enabled is not None:
        update["auto_draft_trends.enabled"] = bool(payload.enabled)
    if payload.platform is not None:
        platform = payload.platform.lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise HTTPException(status_code=422, detail="Unsupported platform")
        update["auto_draft_trends.platform"] = platform
    if payload.count is not None:
        update["auto_draft_trends.count"] = int(payload.count)
    if update:
        await db.users.update_one(
            {"user_id": user.user_id}, {"$set": update},
        )
    return await get_auto_draft_settings(request)


async def _draft_from_trend_silent(
    user_id: str, trend_id: str, platform: str,
) -> Optional[dict]:
    """Server-side clone of `POST /api/trends/draft-post` — no Request
    or auth (the cron runs as the system; caller scopes by user_id).
    Returns `{draft, hashtags}` on success, None on any failure so the
    cron can keep going for other signals."""
    from routes.trends_engine import _PLATFORM_GUIDANCE
    from routes.agent_chat import AGENTS
    from routes.ai import _llm_for_user, send_with_usage
    from routes.model_router import resolve_user_mode
    from emergentintegrations.llm.chat import UserMessage

    signal = await db.cortex_memory.find_one(
        {"id": trend_id, "user_id": user_id, "kind": "trend"},
        {"_id": 0, "id": 1, "text": 1, "meta": 1},
    )
    if not signal:
        return None
    if platform not in _PLATFORM_GUIDANCE:
        return None

    nova = AGENTS["nova"]
    user_doc = await db.users.find_one(
        {"user_id": user_id}, {"_id": 0, "agent_prefs": 1, "brand_name": 1, "niche": 1},
    ) or {}
    user_mode = (user_doc.get("agent_prefs") or {}).get("nova", "auto")
    provider, model, task_used = resolve_user_mode(user_mode, "nova")

    brand_block = ""
    if user_doc.get("brand_name") or user_doc.get("niche"):
        brand_block = (
            f"\n\nBrand: {user_doc.get('brand_name') or 'n/a'} · "
            f"Niche: {user_doc.get('niche') or 'n/a'}"
        )

    system = nova["system"] + (
        f"\n\nYou are turning a viral signal into one shippable {platform} draft. "
        f"Format spec: {_PLATFORM_GUIDANCE[platform]} "
        "Lead with what the SIGNAL itself says, not generic advice. "
        "End your reply with a separate line: `HASHTAGS: #tag1 #tag2 #tag3`."
        + brand_block
    )
    chat = await _llm_for_user(
        user_id, f"auto-draft-{user_id}-{trend_id}", system,
        provider=provider, model=model,
    )
    try:
        raw, usage = await send_with_usage(
            chat, UserMessage(text=f"Signal:\n{signal['text']}\n\nDraft the {platform} post now."),
        )
    except Exception:
        logger.exception("auto-draft LLM call failed for user=%s trend=%s", user_id, trend_id)
        return None

    raw = (raw or "").strip()
    suggested: list[str] = []
    draft_body = raw
    for line in reversed(raw.splitlines()):
        if line.upper().startswith("HASHTAGS:"):
            tags = line.split(":", 1)[1].strip()
            suggested = [
                t if t.startswith("#") else f"#{t}"
                for t in tags.replace(",", " ").split() if t.strip("#")
            ][:8]
            draft_body = raw.replace(line, "").rstrip()
            break

    # Track LLM spend so the user's monthly spend chip stays accurate.
    try:
        from routes.llm_spend import record_llm_call
        await record_llm_call(user_id, "nova", task_used, model, usage)
    except Exception:
        pass

    return {
        "draft":    draft_body,
        "hashtags": suggested,
        "signal":   signal,
    }


async def _process_user(user_doc: dict) -> int:
    """Run the auto-draft pipeline for one user. Returns the number of
    posts queued. Each draft is upserted with a deterministic
    `dedupe_key` so the same (signal, platform) pair can't accumulate
    duplicate pending posts across cron retries."""
    user_id = user_doc["user_id"]
    cfg = user_doc.get("auto_draft_trends") or {}
    platform = cfg.get("platform") or "linkedin"
    count = max(MIN_DRAFTS_PER_WEEK, min(MAX_DRAFTS_PER_WEEK, int(cfg.get("count") or 3)))

    # Pick the most-recent trends (we don't have a global "score" since
    # gtrends + reddit use different units, so recency = relevance).
    trends = await db.cortex_memory.find(
        {"user_id": user_id, "kind": "trend"},
        {"_id": 0, "id": 1, "text": 1, "meta": 1},
    ).sort("created_at", -1).limit(count).to_list(length=count)
    if not trends:
        logger.info("auto-draft: user=%s has no trend signals — skipping", user_id)
        return 0

    queued = 0
    for t in trends:
        draft = await _draft_from_trend_silent(user_id, t["id"], platform)
        if not draft:
            continue
        # Compose final post body with hashtags appended (so the user can
        # tweak as one block in the Approvals UI).
        body = draft["draft"]
        if draft["hashtags"]:
            body = body + "\n\n" + " ".join(draft["hashtags"])

        dedupe_key = f"auto_draft:{t['id']}:{platform}"
        post = {
            "user_id":      user_id,
            "content":      body,
            "platforms":    [platform if platform != "x" else "twitter"],
            "status":       "pending_approval",
            # Schedule 24h out so if the user approves it stays scheduled
            # rather than firing immediately — gives them an editing window.
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=24),
            "source":       "auto_draft",
            "dedupe_key":   dedupe_key,
            "trend_id":     t["id"],
            "updated_at":   datetime.now(timezone.utc),
        }
        # Upsert: insert if new, overwrite content/scheduled_at if a
        # previous run already queued this signal+platform.
        await db.posts.update_one(
            {"dedupe_key": dedupe_key, "user_id": user_id},
            {
                "$set":          post,
                "$setOnInsert":  {"id": str(uuid.uuid4()),
                                  "created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        queued += 1

    return queued


async def run_weekly_auto_drafts() -> dict:
    """Cron entry point. Iterates all opted-in users with at least
    `RUN_COOLDOWN_DAYS` since their last run, processes each, and
    updates `last_run_at`. Returns a summary dict (also useful when the
    job is invoked manually in tests)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RUN_COOLDOWN_DAYS)
    query = {
        "auto_draft_trends.enabled": True,
        "$or": [
            {"auto_draft_trends.last_run_at": {"$lte": cutoff}},
            {"auto_draft_trends.last_run_at": None},
            {"auto_draft_trends.last_run_at": {"$exists": False}},
        ],
        # Don't auto-draft for paused / sign-out-everywhere'd accounts.
        "paused_at": {"$in": [None, False]},
    }
    users = await db.users.find(
        query, {"_id": 0, "user_id": 1, "auto_draft_trends": 1, "email": 1},
    ).to_list(length=10_000)
    if not users:
        return {"users_processed": 0, "drafts_queued": 0}

    total_drafts = 0
    for u in users:
        try:
            queued = await _process_user(u)
            total_drafts += queued
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"auto_draft_trends.last_run_at": datetime.now(timezone.utc),
                          "auto_draft_trends.last_run_count": queued}},
            )
            logger.info("auto-draft: user=%s queued=%d", u["user_id"], queued)
        except Exception:
            logger.exception("auto-draft failed for user=%s", u["user_id"])
    return {"users_processed": len(users), "drafts_queued": total_drafts}


# --- Scheduler registration ---------------------------------------------------
# We don't auto-start here; the main scheduler bootstrap in `scheduler.py`
# calls `register_auto_draft_job(scheduler)` so this module stays import-
# safe (no apscheduler side-effects at import time).
def register_auto_draft_job(scheduler) -> None:
    """Attach the weekly cron to an existing apscheduler instance.
    Runs every Monday at 08:00 UTC. Idempotent across worker restarts
    thanks to the per-user `last_run_at` window."""
    scheduler.add_job(
        run_weekly_auto_drafts,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="UTC"),
        id="weekly_auto_drafts",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


@api.post("/trends/auto-draft/run-now")
async def auto_draft_run_now(request: Request):
    """Manual trigger — runs the same pipeline as the cron, but only
    for the calling user. Lets users dry-run their config and see the
    drafts appear in Approvals immediately instead of waiting for
    Monday. Respects the cooldown window (returns 429 if last run was
    within the cooldown)."""
    user = await get_current_user(request)
    doc = await db.users.find_one(
        {"user_id": user.user_id},
        {"_id": 0, "user_id": 1, "auto_draft_trends": 1},
    )
    cfg = (doc or {}).get("auto_draft_trends") or {}
    if not cfg.get("enabled"):
        raise HTTPException(status_code=422, detail="Auto-draft is not enabled for your account")
    last = cfg.get("last_run_at")
    if last:
        # MongoDB strips tzinfo on read; coerce back to UTC so the
        # `datetime.now(utc) - last` subtraction doesn't crash with
        # "can't subtract offset-naive and offset-aware datetimes".
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last
        if elapsed < timedelta(days=RUN_COOLDOWN_DAYS):
            remaining = timedelta(days=RUN_COOLDOWN_DAYS) - elapsed
            raise HTTPException(
                status_code=429,
                detail=f"Cooldown active — try again in {remaining.days}d {remaining.seconds // 3600}h",
            )
    queued = await _process_user({"user_id": user.user_id,
                                  "auto_draft_trends": cfg})
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"auto_draft_trends.last_run_at": datetime.now(timezone.utc),
                  "auto_draft_trends.last_run_count": queued}},
    )
    return {"ok": True, "drafts_queued": queued}
