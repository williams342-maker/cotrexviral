"""Social Listening Engine — Lyra's domain.

Captures brand + competitor mentions across configured sources, classifies
sentiment + topic, and surfaces high-priority signals to the standup +
the listening dashboard.

In this initial phase the ingestion is **pluggable**: we expose two
write paths,

  1. POST /api/listening/signals  — manual ingest (admin or webhook)
  2. POST /api/listening/synthesize — LLM-generated demo signals so the
     UI has real-looking data before external integrations are wired

Future phases will plug in real source connectors (Reddit RSS, Twitter
search API, Mention.com webhook, etc.) — they'll all just call the same
`record_signal()` helper.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db, EMERGENT_LLM_KEY
from deps import get_current_user

logger = logging.getLogger(__name__)


VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}
VALID_SIGNAL_TYPES = {"brand_mention", "competitor_mention", "trend", "complaint", "praise", "question"}


# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------
class SignalIn(BaseModel):
    source:       str        # e.g. "reddit", "twitter", "manual", "mention.com"
    source_url:   Optional[str] = None
    text:         str
    author:       Optional[str] = None
    sentiment:    Optional[str] = "neutral"
    signal_type:  Optional[str] = "brand_mention"
    topic:        Optional[str] = None
    urgency:      Optional[int] = 2     # 1=low … 5=crisis
    engagement:   Optional[int] = 0     # likes/upvotes/retweets — source-dependent


class SynthesizeIn(BaseModel):
    brand:        str = "CortexViral"
    competitors:  list[str] = []
    n_signals:    int = 6


# ---------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------
async def record_signal(user_id: str, payload: dict) -> dict:
    """Insert one normalized signal row + return it."""
    now = datetime.now(timezone.utc)
    sentiment = (payload.get("sentiment") or "neutral").lower()
    if sentiment not in VALID_SENTIMENTS:
        sentiment = "neutral"
    sig_type = (payload.get("signal_type") or "brand_mention").lower()
    if sig_type not in VALID_SIGNAL_TYPES:
        sig_type = "brand_mention"

    doc = {
        "id":          uuid.uuid4().hex,
        "user_id":     user_id,
        "source":      payload.get("source") or "unknown",
        "source_url":  payload.get("source_url"),
        "text":        (payload.get("text") or "").strip()[:2000],
        "author":      payload.get("author"),
        "sentiment":   sentiment,
        "signal_type": sig_type,
        "topic":       payload.get("topic"),
        "urgency":     int(payload.get("urgency") or 2),
        "engagement":  int(payload.get("engagement") or 0),
        "detected_at": now,
        "created_at":  now,
    }
    await db.social_listening_signals.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------
@api.post("/listening/signals")
async def ingest_signal(payload: SignalIn, request: Request):
    """Manual / webhook ingestion of a single listening signal."""
    user = await get_current_user(request)
    return await record_signal(user.user_id, payload.model_dump())


@api.get("/listening/signals")
async def list_signals(
    request: Request,
    sentiment: Optional[str] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
    days: int = 30,
):
    """Filtered feed for Lyra's listening dashboard."""
    user = await get_current_user(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query: dict = {"user_id": user.user_id, "detected_at": {"$gte": since}}
    if sentiment:
        query["sentiment"] = sentiment
    if signal_type:
        query["signal_type"] = signal_type
    items = await db.social_listening_signals.find(
        query, {"_id": 0},
    ).sort("detected_at", -1).limit(limit).to_list(limit)
    return {"items": items, "count": len(items)}


@api.get("/listening/stats")
async def listening_stats(request: Request, days: int = 7):
    """Aggregates for the dashboard hero row: total signals, by sentiment,
    by signal_type, and an urgency-weighted score."""
    user = await get_current_user(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total = await db.social_listening_signals.count_documents(
        {"user_id": user.user_id, "detected_at": {"$gte": since}},
    )

    pipeline_sentiment = [
        {"$match": {"user_id": user.user_id, "detected_at": {"$gte": since}}},
        {"$group": {"_id": "$sentiment", "n": {"$sum": 1}}},
    ]
    by_sentiment = {d["_id"] or "neutral": d["n"] async for d in
                    db.social_listening_signals.aggregate(pipeline_sentiment)}

    pipeline_type = [
        {"$match": {"user_id": user.user_id, "detected_at": {"$gte": since}}},
        {"$group": {"_id": "$signal_type", "n": {"$sum": 1}}},
    ]
    by_type = {d["_id"] or "brand_mention": d["n"] async for d in
               db.social_listening_signals.aggregate(pipeline_type)}

    # Urgency-weighted "needs attention" score — sums (urgency × 1) for
    # negative + urgency × 0.5 for mixed in the last 7 days.
    attention_pipeline = [
        {"$match": {"user_id": user.user_id, "detected_at": {"$gte": since},
                    "sentiment": {"$in": ["negative", "mixed"]}}},
        {"$group": {"_id": None,
                    "score": {"$sum": {"$cond": [
                        {"$eq": ["$sentiment", "negative"]},
                        "$urgency",
                        {"$multiply": ["$urgency", 0.5]},
                    ]}}}},
    ]
    score = 0
    async for r in db.social_listening_signals.aggregate(attention_pipeline):
        score = round(float(r.get("score") or 0), 1)

    return {
        "window_days":      days,
        "total":            total,
        "by_sentiment":     by_sentiment,
        "by_signal_type":   by_type,
        "attention_score":  score,
        "alert_threshold":  10.0,
        "alert_triggered":  score >= 10.0,
    }


@api.post("/listening/synthesize")
async def synthesize_signals(payload: SynthesizeIn, request: Request):
    """LLM-generated demo signals — gets the dashboard populated before
    real source connectors are wired. The LLM is instructed to write
    realistic-looking social mentions (Reddit, Twitter, niche forums)
    that match the brand + competitors. Stored as `source=synthetic`
    so they can be filtered out later if needed."""
    user = await get_current_user(request)

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="LLM key not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from routes.ai import send_with_usage
    import json as _json
    import re

    n = max(1, min(int(payload.n_signals), 10))
    competitors_str = ", ".join(payload.competitors) if payload.competitors else "(none)"

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"listening_synth_{uuid.uuid4().hex[:8]}",
        system_message=(
            "You are a social listening engine generating REALISTIC-LOOKING "
            "social mentions that might appear in a brand's listening feed. "
            "These are for demo purposes — they should feel like real Reddit, "
            "Twitter, and forum posts. Mix positive, negative, neutral. Vary "
            "the urgency. Some about the brand, some about competitors, some "
            "trend chatter. Output STRICT JSON only — an array of objects."
        ),
    ).with_model("openai", "gpt-5-mini")

    prompt = (
        f"Generate {n} listening signals for brand '{payload.brand}' "
        f"vs competitors [{competitors_str}].\n\n"
        "Output strictly as a JSON array. Each object has these keys exactly:\n"
        "  source        (one of: reddit, twitter, instagram_comment, forum, blog)\n"
        "  text          (max 200 chars, realistic-sounding)\n"
        "  author        (made-up handle like @growth_nerd or u/marketingdad)\n"
        "  sentiment     (positive | negative | neutral | mixed)\n"
        "  signal_type   (brand_mention | competitor_mention | trend | complaint | praise | question)\n"
        "  topic         (one-word topic tag e.g. 'pricing', 'feature-request')\n"
        "  urgency       (1=low, 2=normal, 3=watch, 4=high, 5=crisis)\n"
        "  engagement    (integer 0-500)\n"
        "  source_url    (a plausible-looking URL, can be fictional)\n\n"
        "Output ONLY the JSON array. No prose, no markdown fences."
    )

    text, _ = await send_with_usage(chat, UserMessage(text=prompt))
    # Strip code fences if any
    cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        items = _json.loads(cleaned)
        assert isinstance(items, list)
    except Exception as exc:
        logger.warning("Listening synth: parse failed: %s — raw=%s", exc, (text or "")[:300])
        raise HTTPException(status_code=502, detail="Listening synth: LLM returned invalid JSON")

    saved = []
    for it in items[:n]:
        if not isinstance(it, dict) or not it.get("text"):
            continue
        it["source"] = it.get("source") or "synthetic"
        sig = await record_signal(user.user_id, it)
        saved.append(sig)
    return {"created": len(saved), "items": saved}
