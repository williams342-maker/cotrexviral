"""A/B Hook Lab — generates and scores hook variations.

POST /api/ai/ab-variations
    body: {seed: str, platform?: str, count?: int}
    → {variants: [{text, score, breakdown: {curiosity, specificity, pattern_interrupt, emotional_charge, brevity}, why}]}

Each variation is scored on 5 axes (0-20 each, total 0-100):
  • curiosity_gap     — does it create a "I need to know what's next" hook?
  • specificity       — does it use a concrete number / detail / name?
  • pattern_interrupt — does it break the scroll's expected rhythm?
  • emotional_charge  — does it surface a strong feeling (anger / awe / curiosity / FOMO)?
  • brevity           — under 12 words is best; longer hooks lose points.

All scoring is done by the LLM in the SAME call as generation — so the
score reflects the model's own assessment of each variant, not a separate
client-side fake score. Gated to Growth+ via assert_has_feature.
"""
import json
import re

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, logger
from deps import get_current_user
from routes.plans import assert_has_feature, assert_can_generate_ai, record_ai_generation
from routes.ai import _llm_for_user, send_with_usage
from emergentintegrations.llm.chat import UserMessage


class ABLabRequest(BaseModel):
    seed: str
    platform: str = "tiktok"
    count: int = 5


def _safe_lab_json(raw: str) -> list[dict] | None:
    """Parse the LLM payload and clamp/normalise each variant."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    variants = data.get("variants") if isinstance(data, dict) else None
    if not isinstance(variants, list):
        return None

    cleaned: list[dict] = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        text = str(v.get("text", "")).strip().strip('"').strip("'")
        if not text:
            continue
        breakdown_in = v.get("breakdown") or {}
        breakdown = {}
        total_from_breakdown = 0
        for k in ("curiosity_gap", "specificity", "pattern_interrupt", "emotional_charge", "brevity"):
            try:
                x = int(breakdown_in.get(k, 0))
            except (TypeError, ValueError):
                x = 0
            x = max(0, min(20, x))
            breakdown[k] = x
            total_from_breakdown += x
        # Prefer explicit score if model returned one; else use the sum.
        try:
            score = int(v.get("score", total_from_breakdown))
        except (TypeError, ValueError):
            score = total_from_breakdown
        score = max(0, min(100, score))

        cleaned.append({
            "text": text[:280],
            "score": score,
            "breakdown": breakdown,
            "why": str(v.get("why", "")).strip()[:200] or None,
        })
    # Sort high → low; cap variants at the requested count (safety).
    cleaned.sort(key=lambda x: x["score"], reverse=True)
    return cleaned or None


@api.post("/ai/ab-variations")
async def ab_variations(payload: ABLabRequest, request: Request):
    user = await get_current_user(request)
    await assert_has_feature(user.user_id, "ab_variations")
    await assert_can_generate_ai(user.user_id)

    seed = (payload.seed or "").strip()
    if not seed:
        raise HTTPException(status_code=400, detail="seed is required")
    count = max(2, min(8, payload.count or 5))
    platform = (payload.platform or "tiktok").lower()[:16]

    system = (
        "You are CortexViral's Hook Lab. Given a hook idea, you generate hook "
        "VARIATIONS and score each on real viral-hook criteria. "
        "Each variation MUST be a different hook archetype (e.g. curiosity-gap, "
        "contrarian, listicle, pattern-interrupt, POV, statistic-led). "
        "Keep each variation under 14 words and platform-appropriate.\n\n"
        "Scoring axes (0-20 each, total 0-100):\n"
        "  • curiosity_gap — leaves the viewer wanting the next sentence\n"
        "  • specificity — concrete number / detail / proper noun\n"
        "  • pattern_interrupt — breaks the scroll's expected rhythm\n"
        "  • emotional_charge — strong feeling (anger / awe / FOMO / vindication)\n"
        "  • brevity — shorter = better (12 words sweet spot)\n\n"
        "Respond ONLY in valid JSON:\n"
        '{"variants":[{"text":"<the hook>","score":<int 0-100>,'
        '"breakdown":{"curiosity_gap":<0-20>,"specificity":<0-20>,'
        '"pattern_interrupt":<0-20>,"emotional_charge":<0-20>,"brevity":<0-20>},'
        '"why":"<1 sentence reason this scored where it did>"}]}'
    )

    chat = await _llm_for_user(user.user_id, f"ablab-{user.user_id}", system)
    prompt = (
        f"Platform: {platform}\n"
        f"Seed idea: {seed}\n"
        f"Generate {count} hook variations — each a DIFFERENT archetype. "
        "Then score each. Highest-scoring variant first."
    )
    raw, _usage = await send_with_usage(
        chat, UserMessage(text=prompt),
        agent_id="nova", user_id=user.user_id, model="gpt-5",
    )
    variants = _safe_lab_json(raw)
    if not variants:
        logger.warning("A/B Hook Lab: LLM produced unparseable payload")
        raise HTTPException(status_code=502, detail="Hook Lab couldn't generate variants right now — try again")

    await record_ai_generation(user.user_id, "ab_variations")
    return {"variants": variants[:count], "seed": seed, "platform": platform}
