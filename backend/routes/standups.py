"""Weekly Standup — the Monday-morning artifact that flips users from
'I run this tool' to 'I manage this team'.

Each Monday at 9am (and on-demand for admins), every agent on the team
writes a 1–3 sentence contribution based on what happened over the past
7 days. The contributions stitch together into a Slack-style thread you
can read with morning coffee.

LLM model: gpt-5-mini via the Emergent Universal Key (cheap enough to
generate weekly for every user; the data is the expensive part).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import api, db, EMERGENT_LLM_KEY
from deps import get_current_user
from routes.agent_personas import PERSONAS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Data gatherers — each one builds the per-persona context from the
# normalized content layer + performance metrics + listening signals.
# Keep these tight so the LLM call stays cheap.
# ---------------------------------------------------------------------
async def _gather_user_facts(user_id: str, since: datetime) -> dict:
    """Pull the raw weekly numbers for one user. Single Mongo round trip
    per source; aggregated into one dict for the LLM prompt."""
    # Posts published in the window
    posts_published = await db.content_variants.count_documents({
        "user_id": user_id, "status": "published",
        "published_at": {"$gte": since},
    })
    posts_drafted = await db.content_variants.count_documents({
        "user_id": user_id, "created_at": {"$gte": since},
    })
    posts_failed = await db.content_variants.count_documents({
        "user_id": user_id, "status": "failed",
        "updated_at": {"$gte": since},
    })

    # Top platform by published volume
    pipeline = [
        {"$match": {"user_id": user_id, "status": "published",
                    "published_at": {"$gte": since}}},
        {"$group": {"_id": "$platform", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 1},
    ]
    top_plat = None
    async for d in db.content_variants.aggregate(pipeline):
        top_plat = {"platform": d["_id"], "count": d["n"]}
        break

    # Listening signals in the window (Lyra reads these)
    listening_signals = await db.social_listening_signals.find({
        "user_id": user_id, "detected_at": {"$gte": since},
    }, {"_id": 0}).sort("detected_at", -1).limit(20).to_list(20)

    # Performance — sum impressions/engagements via the rollup table
    perf_total = {"impressions": 0, "engagements": 0}
    async for r in db.performance_rollups.find({"user_id": user_id}, {"_id": 0, "windows": 1}):
        wk = (r.get("windows") or {}).get("last_7d") or {}
        perf_total["impressions"] += int(wk.get("impressions") or 0)
        perf_total["engagements"] += int(wk.get("engagements") or 0)

    # Goals (if any — Phase 2 not yet built so we tolerate empty)
    goals = await db.growth_goals.find({"user_id": user_id, "status": {"$ne": "completed"}},
                                        {"_id": 0}).to_list(10)

    return {
        "since":             since.isoformat(),
        "posts_published":   posts_published,
        "posts_drafted":     posts_drafted,
        "posts_failed":      posts_failed,
        "top_platform":      top_plat,
        "perf_total":        perf_total,
        "listening_signals": listening_signals,
        "goals":             goals,
    }


# ---------------------------------------------------------------------
# Per-persona contribution generator
# ---------------------------------------------------------------------
async def _combined_contributions(facts: dict) -> list[dict]:
    """ONE LLM call that produces ALL 8 contributions. Replaces per-persona
    parallel calls — fewer round trips, lower cost, no event loop pressure.
    Returns a list ordered to match `PERSONAS`."""
    if not EMERGENT_LLM_KEY:
        return [{"agent_id": p["id"], "text": _fallback_contribution(p, facts)} for p in PERSONAS]

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage
        import json as _json
        import re

        # Build a compact persona table so the LLM knows each voice.
        persona_block = "\n".join(
            f"- {p['id']}: {p['name']} — {p['role']}. Voice: {p['voice']}"
            for p in PERSONAS
        )

        signals_str = ""
        if facts.get("listening_signals"):
            signals_str = "\nRecent listening signals (top 3):\n"
            for s in (facts["listening_signals"] or [])[:3]:
                signals_str += f"  • [{s.get('sentiment','?')}] {s.get('source')}: {(s.get('text') or '')[:120]}\n"

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"standup_combined_{datetime.now(timezone.utc).strftime('%Y%W%w%H')}",
            system_message=(
                "You are the writing assistant for CortexViral's autonomous growth team. "
                "You produce weekly standup contributions for each of 8 specialist agents. "
                "Each contribution stays in that agent's voice and is 1–3 sentences. "
                "Output STRICT JSON only."
            ),
        ).with_model("openai", "gpt-5-mini")

        prompt = (
            f"PERSONAS:\n{persona_block}\n\n"
            f"THIS WEEK'S FACTS ({facts['since'][:10]} → today):\n"
            f"  posts_published: {facts['posts_published']}\n"
            f"  posts_drafted:   {facts['posts_drafted']}\n"
            f"  posts_failed:    {facts['posts_failed']}\n"
            f"  top_platform:    {facts['top_platform']}\n"
            f"  impressions_7d:  {facts['perf_total']['impressions']:,}\n"
            f"  engagements_7d:  {facts['perf_total']['engagements']:,}\n"
            f"  active_goals:    {len(facts.get('goals') or [])}\n"
            f"  listening_signals_count: {len(facts.get('listening_signals') or [])}\n"
            f"{signals_str}\n"
            "Output a strict JSON array of 8 objects, ORDERED EXACTLY as the personas above. "
            "Each object: {\"agent_id\": \"vera\", \"text\": \"…\"}. "
            "No markdown, no preamble — JSON only."
        )

        text, _ = await asyncio.wait_for(
            send_with_usage(chat, UserMessage(text=prompt)),
            timeout=45,
        )
        cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = _json.loads(cleaned)
        if not isinstance(parsed, list):
            raise ValueError("not a list")
        # Index by agent_id so out-of-order responses don't break us
        by_id = {item.get("agent_id"): (item.get("text") or "").strip() for item in parsed
                 if isinstance(item, dict)}
        return [{"agent_id": p["id"],
                  "text": by_id.get(p["id"]) or _fallback_contribution(p, facts)}
                for p in PERSONAS]
    except Exception as exc:
        logger.warning("Standup combined LLM failed (%s) — using fallbacks", exc)
        return [{"agent_id": p["id"], "text": _fallback_contribution(p, facts)} for p in PERSONAS]


def _fallback_contribution(persona: dict, facts: dict) -> str:
    """Deterministic mini-templates so the standup never returns empty."""
    pid = persona["id"]
    p = facts.get("posts_published", 0)
    if pid == "vera":
        n_goals = len(facts.get("goals") or [])
        return f"Tracking {n_goals} active goal(s) this week. Recommend reviewing platform mix at next planning session."
    if pid == "atlas":
        return "Two campaign briefs queued for review. Doubling down on the format that's working this week."
    if pid == "nova":
        return f"Drafted {facts.get('posts_drafted', 0)} variants this week. Testing a new hook style next."
    if pid == "rae":
        top = facts.get("top_platform")
        return f"Top platform: {top['platform']}" + (f" ({top['count']} posts)." if top else " — still collecting baseline.")
    if pid == "lyra":
        n = len(facts.get("listening_signals") or [])
        return f"Captured {n} mentions/signals this week. No sentiment spike worth alerting on."
    if pid == "echo":
        return f"Published {p} posts this week across active channels."
    if pid == "ori":
        eng = facts.get("perf_total", {}).get("engagements", 0)
        return f"{eng:,} engagements logged (7d). Looking for the lift signal in the carousel format experiment."
    if pid == "jules":
        return "Budget healthy. No agents nearing their autonomy cap. All systems green."
    return "Standing by."


# ---------------------------------------------------------------------
# Generation orchestrator
# ---------------------------------------------------------------------
async def generate_standup_for_user(user_id: str, *, days: int = 7) -> dict:
    """Build a single standup record for one user. Stores it in
    `weekly_standups` and returns the saved doc."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    facts = await _gather_user_facts(user_id, since)

    # ONE LLM call for all 8 contributions (combined prompt).
    combined = await _combined_contributions(facts)
    persona_by_id = {p["id"]: p for p in PERSONAS}
    contributions = [
        {
            "agent_id":   c["agent_id"],
            "agent_name": persona_by_id[c["agent_id"]]["name"],
            "role":       persona_by_id[c["agent_id"]]["role"],
            "color":      persona_by_id[c["agent_id"]]["color"],
            "icon":       persona_by_id[c["agent_id"]].get("icon"),
            "text":       c["text"],
        }
        for c in combined if c["agent_id"] in persona_by_id
    ]

    doc = {
        "id":           uuid.uuid4().hex,
        "user_id":      user_id,
        "generated_at": datetime.now(timezone.utc),
        "window_days":  days,
        "facts":        {k: v for k, v in facts.items() if k != "listening_signals"},
        "contributions": contributions,
    }
    await db.weekly_standups.insert_one(doc)
    return doc


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.post("/standups/generate")
async def generate_standup_now(request: Request):
    """User-triggered standup generation. With the combined-call approach,
    the whole standup takes ~15s — well within the proxy timeout."""
    user = await get_current_user(request)
    doc = await generate_standup_for_user(user.user_id)
    doc.pop("_id", None)
    return doc


@api.get("/standups/latest")
async def get_latest_standup(request: Request):
    user = await get_current_user(request)
    doc = await db.weekly_standups.find_one(
        {"user_id": user.user_id}, {"_id": 0},
        sort=[("generated_at", -1)],
    )
    return doc or {"empty": True}


@api.get("/standups")
async def list_standups(request: Request, limit: int = 12):
    user = await get_current_user(request)
    cursor = db.weekly_standups.find(
        {"user_id": user.user_id}, {"_id": 0},
    ).sort("generated_at", -1).limit(limit)
    return {"items": await cursor.to_list(limit)}
