"""Creative Brief Generator — Phase A2.

Sits on top of `cortex.asset_intelligence`: once an asset's intelligence
+ review are in place, synthesize a STRATEGIC campaign brief that turns
the raw signals into an executable plan.

Brief shape (8 structured fields, all schema-strict via tool-call):

  • campaign_goal         — one-sentence outcome ("3x weekly site sessions...")
  • target_audience       — { primary, secondary[], psychographics[] }
  • offer                 — the headline hook (value prop the campaign rallies on)
  • messaging_angles      — 3-5 angles to test
  • recommended_platforms — channels ranked by fit
  • content_plan          — per-platform format / frequency / concept
  • creative_concepts     — specific image/video/ad ideas
  • confidence            — Cortex's confidence in the brief (0-100)

The brief is generated automatically when an asset completes analysis,
and stored in `cortex_creative_briefs`. Users can regenerate via the
explicit endpoint.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


_BRIEF_TOOL = {
    "name": "record_creative_brief",
    "description": (
        "Generate a complete, executable marketing campaign brief from "
        "the extracted intelligence. Be specific — name actual platforms, "
        "real audience descriptors, concrete creative concepts. Avoid "
        "generic phrases like 'engaging content' or 'broad audience'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "campaign_goal":   {"type": "string",
                                 "description": "One-sentence campaign outcome (e.g., 'Generate 250 custom-quote requests from homeowners and gift-buyers over 60 days')."},
            "target_audience": {
                "type": "object",
                "description": "Who this campaign is for.",
                "properties": {
                    "primary":         {"type": "string",
                                          "description": "Primary segment in one sentence — be specific."},
                    "secondary":       {"type": "array", "items": {"type": "string"},
                                          "description": "Adjacent audience segments worth testing (2-4)."},
                    "psychographics":  {"type": "array", "items": {"type": "string"},
                                          "description": "Values, motivations, behaviors that distinguish this audience (3-5)."},
                },
                "required": ["primary"],
            },
            "offer":           {"type": "string",
                                 "description": "Headline hook the campaign rallies on (e.g., 'Free 24-hour custom-design quote — no obligation')."},
            "messaging_angles": {"type": "array", "items": {"type": "string"},
                                  "description": "3-5 distinct angles to test. Each should be a tweet-length positioning statement."},
            "recommended_platforms": {"type": "array", "items": {"type": "string"},
                                        "description": "Channels ranked by fit. Pull from: facebook, instagram, instagram_story, pinterest, linkedin, tiktok, youtube, youtube_shorts, email, blog, google_ads, x. Return 3-6."},
            "content_plan": {
                "type": "array",
                "description": "What content to make per platform (3-6 entries).",
                "items": {
                    "type": "object",
                    "properties": {
                        "platform":  {"type": "string"},
                        "format":    {"type": "string",
                                       "description": "e.g., 'square ad', 'reel', 'pin', 'carousel', 'long-form post'."},
                        "frequency": {"type": "string",
                                       "description": "e.g., '3 posts/week for 6 weeks'."},
                        "concept":   {"type": "string",
                                       "description": "One-sentence concept brief for this content stream."},
                    },
                    "required": ["platform", "format", "concept"],
                },
            },
            "creative_concepts": {
                "type": "array",
                "description": "3-5 concrete creative ideas the asset team should execute.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string",
                                          "description": "Short name for the concept (e.g., 'Workshop-to-Door')."},
                        "description": {"type": "string",
                                          "description": "What the creative shows / says, in 1-2 sentences."},
                        "format":      {"type": "string",
                                          "description": "'image' | 'video' | 'carousel' | 'reel' | 'short' | 'graphic'"},
                    },
                    "required": ["title", "description"],
                },
            },
            "confidence":      {"type": "integer", "minimum": 0, "maximum": 100,
                                 "description": "Cortex's confidence in this brief, 0-100."},
        },
        "required": ["campaign_goal", "target_audience", "offer",
                      "messaging_angles", "recommended_platforms",
                      "content_plan", "creative_concepts", "confidence"],
    },
}


# ------------------------------------------------------------ orchestrator
async def generate_brief(asset: dict, intelligence: Optional[dict],
                            review: Optional[dict] = None) -> Optional[dict]:
    """LLM tool-call: synthesize the full creative brief. Returns the
    normalized brief dict, or None on hard failure (caller handles the
    `failed` state in the UI)."""
    from cortex.llm_provider import cortex_tool_call
    from core import EMERGENT_LLM_KEY

    if not EMERGENT_LLM_KEY:
        return _heuristic_brief(asset, intelligence)

    sys_prompt = (
        "You are Cortex's Creative Strategy Director. Read the extracted "
        "marketing intelligence and turn it into an EXECUTABLE campaign "
        "brief a marketing team could run with tomorrow. Be specific, "
        "concrete, and decisive. Name real platforms, real audience "
        "segments, real creative ideas. Avoid generic phrases like "
        "'engaging content' or 'broad audience'. Every output must be "
        "something the team can act on directly."
    )

    user_text = _compose_prompt(asset, intelligence, review)

    try:
        args, label, mode = await cortex_tool_call(
            system=sys_prompt,
            user_text=user_text,
            tool=_BRIEF_TOOL,
            session_id=f"creative-brief-{asset.get('id')}",
            user_id=asset.get("user_id") or "anonymous",
            prefer="claude",
            required=["campaign_goal", "target_audience", "offer",
                       "messaging_angles", "recommended_platforms",
                       "creative_concepts"],
        )
        if args:
            return _normalize(args, label, mode)
    except Exception:
        logger.exception("creative_brief: tool-call failed for asset %s",
                          asset.get("id"))
    return _heuristic_brief(asset, intelligence)


def _compose_prompt(asset: dict, intel: Optional[dict],
                      review: Optional[dict]) -> str:
    parts = [
        f"Asset: {asset.get('name')} ({asset.get('kind')})",
    ]
    if asset.get("source_url"):
        parts.append(f"Source: {asset['source_url']}")
    if intel:
        if intel.get("summary"):
            parts.append(f"\nSummary: {intel['summary']}")
        brand = intel.get("brand") or {}
        if brand.get("name"):
            parts.append(f"Brand: {brand['name']}")
        if brand.get("value_prop"):
            parts.append(f"Value prop: {brand['value_prop']}")
        if brand.get("tone"):
            parts.append(f"Tone: {brand['tone']}")
        if intel.get("products"):
            parts.append(f"Products: {', '.join(intel['products'][:8])}")
        if intel.get("services"):
            parts.append(f"Services: {', '.join(intel['services'][:6])}")
        if intel.get("audience"):
            parts.append(f"Audience signals: {', '.join(intel['audience'][:6])}")
        if intel.get("pain_points"):
            parts.append(f"Pain points: {', '.join(intel['pain_points'][:4])}")
        if intel.get("offers"):
            parts.append(f"Existing offers: {', '.join(intel['offers'][:4])}")
        if intel.get("keywords"):
            parts.append(f"Keywords: {', '.join(intel['keywords'][:10])}")
        if intel.get("competitors"):
            parts.append(f"Competitors: {', '.join(intel['competitors'][:4])}")
        if intel.get("ctas"):
            parts.append(f"Detected CTAs: {', '.join(intel['ctas'][:4])}")
    if review:
        scores = review.get("scores") or {}
        parts.append(f"\nMarketing review snapshot — overall {scores.get('overall')}/100 "
                      f"(copy {scores.get('copy')}, visual {scores.get('visual')}, "
                      f"cta {scores.get('cta')}, audience {scores.get('audience_fit')}, "
                      f"conversion {scores.get('conversion')}).")
        if review.get("suggested_campaigns"):
            parts.append(f"Already-surfaced campaign angles: "
                          f"{', '.join(review['suggested_campaigns'][:3])}")
    return "\n".join(parts)


# ------------------------------------------------------------ normalize
def _normalize(data: dict, label: str, mode: str) -> dict:
    ta = data.get("target_audience") or {}
    return {
        "id":            uuid.uuid4().hex,
        "campaign_goal": _trim(data.get("campaign_goal"), 320),
        "target_audience": {
            "primary":        _trim(ta.get("primary"), 260),
            "secondary":      _strs(ta.get("secondary"), 5, 160),
            "psychographics": _strs(ta.get("psychographics"), 6, 160),
        },
        "offer":            _trim(data.get("offer"), 240),
        "messaging_angles": _strs(data.get("messaging_angles"), 6, 220),
        "recommended_platforms": _strs(data.get("recommended_platforms"), 8, 32),
        "content_plan":     _content_plan(data.get("content_plan")),
        "creative_concepts": _concepts(data.get("creative_concepts")),
        "confidence":       _clamp_int(data.get("confidence"), 70),
        "source":           f"llm:{label}:{mode}",
        "created_at":       datetime.now(timezone.utc),
    }


def _content_plan(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items[:8]:
        if not isinstance(it, dict):
            continue
        platform = _trim(it.get("platform"), 32)
        concept = _trim(it.get("concept"), 280)
        if not platform or not concept:
            continue
        out.append({
            "platform":  platform,
            "format":    _trim(it.get("format"),    60),
            "frequency": _trim(it.get("frequency"), 80),
            "concept":   concept,
        })
    return out


def _concepts(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items[:6]:
        if not isinstance(it, dict):
            continue
        title = _trim(it.get("title"), 80)
        desc = _trim(it.get("description"), 320)
        if not title or not desc:
            continue
        out.append({
            "title":       title,
            "description": desc,
            "format":      _trim(it.get("format"), 24),
        })
    return out


def _heuristic_brief(asset: dict, intel: Optional[dict]) -> dict:
    """Fallback shown only when the LLM is unreachable. Keeps the panel
    renderable instead of leaving a permanent loading state."""
    products = (intel or {}).get("products") or []
    audience = (intel or {}).get("audience") or []
    return {
        "id":            uuid.uuid4().hex,
        "campaign_goal": "Brief generation pending — LLM unavailable. Retry to synthesize.",
        "target_audience": {
            "primary":         audience[0] if audience else "Audience extraction pending.",
            "secondary":       audience[1:3],
            "psychographics":  [],
        },
        "offer":            (products[0] if products else asset.get("name", "")),
        "messaging_angles": [],
        "recommended_platforms": [],
        "content_plan":     [],
        "creative_concepts": [],
        "confidence":       0,
        "source":           "heuristic",
        "created_at":       datetime.now(timezone.utc),
    }


def _strs(v, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for it in v:
        s = _trim(it, max_chars)
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _trim(s, limit: int) -> str:
    if s is None:
        return ""
    return str(s).strip()[:limit]


def _clamp_int(v, default: int) -> int:
    try:
        return max(0, min(100, int(v)))
    except Exception:
        return default
