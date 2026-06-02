"""Asset Intelligence — LLM-driven marketing extraction + review.

Two tool-calls per asset (both via the promoted `cortex_tool_call`
wrapper — 95%+ success rate, schema-strict):

  1. `extract_intelligence()` → structured marketing data:
       products[], services[], audience[], pain_points[], offers[],
       keywords[], competitors[], brand{}, summary

  2. `generate_review()` → marketing review with 6 scores + actions:
       scores{overall, copy, visual, cta, audience_fit, conversion},
       strengths[], weaknesses[], recommended_changes[],
       suggested_campaigns[]

After both succeed, a memory-write hook records the asset summary into
Cortex's strategic memory so future chat conversations can recall
"the trade-show flyer the user uploaded last week."

The functions are independent — `generate_review` can run without
`extract_intelligence` (and vice versa), so the pipeline degrades
gracefully if one tool-call fails.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------- extraction
_INTEL_TOOL = {
    "name": "record_marketing_intelligence",
    "description": (
        "Extract structured marketing intelligence from the asset's text "
        "content. Every field is required (use empty arrays if the asset "
        "genuinely has none of that signal). Be specific — pull verbatim "
        "product names, real audience descriptors, actual price points."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "summary":      {"type": "string",
                              "description": "1-2 sentence executive summary of what this asset is and what it's selling."},
            "brand": {
                "type": "object",
                "description": "Brand identity surfaced from the asset.",
                "properties": {
                    "name":         {"type": "string"},
                    "tagline":      {"type": "string"},
                    "tone":         {"type": "string", "description": "e.g., professional, playful, artisanal."},
                    "value_prop":   {"type": "string", "description": "Core differentiator in one sentence."},
                },
            },
            "products":    {"type": "array", "items": {"type": "string"},
                             "description": "Concrete products mentioned (verbatim names when possible)."},
            "services":    {"type": "array", "items": {"type": "string"}},
            "audience":    {"type": "array", "items": {"type": "string"},
                             "description": "Target audience segments — be specific (e.g., 'homeowners with garden workshops', not 'consumers')."},
            "pain_points": {"type": "array", "items": {"type": "string"}},
            "offers":      {"type": "array", "items": {"type": "string"},
                             "description": "Pricing, promos, guarantees, bundles."},
            "keywords":    {"type": "array", "items": {"type": "string"},
                             "description": "SEO + paid-search keywords this asset signals."},
            "competitors": {"type": "array", "items": {"type": "string"},
                             "description": "Brands/products positioned against or alongside."},
            "ctas":        {"type": "array", "items": {"type": "string"},
                             "description": "Calls-to-action present in the asset (e.g., 'Shop Now', 'Book a Demo')."},
        },
        "required": ["summary", "brand", "products", "services", "audience",
                      "pain_points", "offers", "keywords", "ctas"],
    },
}


_REVIEW_TOOL = {
    "name": "record_marketing_review",
    "description": (
        "Score this asset across 6 marketing dimensions (0-100), call out "
        "concrete strengths and weaknesses, and propose specific changes. "
        "Be a tough, direct consultant — don't soft-pedal scores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "description": "Six 0-100 scores. Overall is a weighted blend the model determines.",
                "properties": {
                    "overall":      {"type": "integer", "minimum": 0, "maximum": 100},
                    "copy":         {"type": "integer", "minimum": 0, "maximum": 100,
                                      "description": "Headline + body strength, clarity, persuasion."},
                    "visual":       {"type": "integer", "minimum": 0, "maximum": 100,
                                      "description": "Composition, contrast, hierarchy, brand consistency."},
                    "cta":          {"type": "integer", "minimum": 0, "maximum": 100,
                                      "description": "CTA clarity, urgency, prominence, friction."},
                    "audience_fit": {"type": "integer", "minimum": 0, "maximum": 100,
                                      "description": "How well the asset speaks to its intended audience."},
                    "conversion":   {"type": "integer", "minimum": 0, "maximum": 100,
                                      "description": "Likely real-world conversion potential as-is."},
                },
                "required": ["overall", "copy", "visual", "cta", "audience_fit", "conversion"],
            },
            "strengths":            {"type": "array", "items": {"type": "string"},
                                       "description": "3-5 concrete strengths. Specific, not generic."},
            "weaknesses":           {"type": "array", "items": {"type": "string"},
                                       "description": "3-5 concrete weaknesses with reasons."},
            "recommended_changes":  {"type": "array", "items": {"type": "string"},
                                       "description": "3-6 specific, actionable changes (e.g., 'Rewrite headline to lead with the Made-in-USA proof point')."},
            "suggested_campaigns":  {"type": "array", "items": {"type": "string"},
                                       "description": "2-4 campaign angles this asset could anchor (e.g., 'Father's Day gift campaign for veterans')."},
        },
        "required": ["scores", "strengths", "weaknesses",
                      "recommended_changes", "suggested_campaigns"],
    },
}


# -------------------------------------------------------- orchestrator
async def analyze_asset(asset: dict, extracted: dict) -> dict:
    """Run the full Phase-A1 pipeline for one asset:
        1) extract_intelligence  ┐  run in parallel — review only needs
        2) generate_review       ┘  the extracted text, so passing
                                    intel=None avoids the dependency
                                    that previously forced a sequential
                                    waterfall.
        3) write to Cortex Memory
       Returns the persisted records (intelligence, review) so the caller
       can return them in the upload response."""
    user_id = asset.get("user_id")
    asset_id = asset.get("id")

    # Run both LLM tool-calls concurrently. Review previously used
    # intel as optional context for its prompt; dropping that here is
    # the only quality trade-off, and it's small because review still
    # reads the asset's full extracted text.
    intel, review = await asyncio.gather(
        extract_intelligence(asset, extracted),
        generate_review(asset, extracted, None),
        return_exceptions=False,
    )

    # Persist into Cortex Memory so future chat conversations can recall
    # this asset's gist. Best-effort — never raises into the pipeline.
    try:
        from cortex.memory import record_turn
        memo = _compose_memory_text(asset, intel)
        if memo:
            await record_turn(user_id, "asset", memo,
                                meta={"asset_id": asset_id,
                                       "kind":     asset.get("kind"),
                                       "name":     asset.get("name")})
    except Exception:
        logger.exception("asset_intelligence: memory write failed (non-fatal)")

    return {"intelligence": intel, "review": review}


async def extract_intelligence(asset: dict, extracted: dict) -> Optional[dict]:
    """LLM tool-call: structured marketing extraction."""
    from cortex.llm_provider import cortex_tool_call
    from core import EMERGENT_LLM_KEY

    if not EMERGENT_LLM_KEY:
        return _heuristic_intelligence(asset, extracted)

    sys_prompt = (
        "You are Cortex's Marketing Intelligence engine. Read the asset's "
        "content and extract everything a marketer would need to build "
        "campaigns from it: brand identity, products/services, target "
        "audience, pain points, offers, keywords, CTAs, competitors. "
        "Be specific — pull verbatim names, real audience descriptors. "
        "Empty arrays are acceptable when the asset genuinely lacks that "
        "signal; do not invent."
    )
    user_text = _build_prompt_payload(asset, extracted)

    try:
        args, label, mode = await cortex_tool_call(
            system=sys_prompt,
            user_text=user_text,
            tool=_INTEL_TOOL,
            session_id=f"asset-intel-{asset.get('id')}",
            user_id=asset.get("user_id") or "anonymous",
            prefer="claude",
            required=["summary", "products", "audience"],
        )
        if args:
            return _normalize_intelligence(args, label, mode)
    except Exception:
        logger.exception("asset_intelligence: extract tool-call failed")
    return _heuristic_intelligence(asset, extracted)


async def generate_review(asset: dict, extracted: dict,
                            intel: Optional[dict]) -> Optional[dict]:
    """LLM tool-call: 6-axis marketing review with scores + actions."""
    from cortex.llm_provider import cortex_tool_call
    from core import EMERGENT_LLM_KEY

    if not EMERGENT_LLM_KEY:
        return _heuristic_review(asset, extracted)

    sys_prompt = (
        "You are Cortex's Marketing Review engine — a tough, direct "
        "growth consultant. Score the asset 0-100 across overall / copy / "
        "visual / CTA / audience_fit / conversion. Be concrete in strengths "
        "and weaknesses. Recommend specific changes that would move the "
        "scores meaningfully. Don't soft-pedal — operators need honest "
        "feedback."
    )
    user_text = _build_review_payload(asset, extracted, intel)

    try:
        args, label, mode = await cortex_tool_call(
            system=sys_prompt,
            user_text=user_text,
            tool=_REVIEW_TOOL,
            session_id=f"asset-review-{asset.get('id')}",
            user_id=asset.get("user_id") or "anonymous",
            prefer="claude",
            required=["scores", "strengths", "weaknesses", "recommended_changes"],
        )
        if args:
            return _normalize_review(args, label, mode)
    except Exception:
        logger.exception("asset_intelligence: review tool-call failed")
    return _heuristic_review(asset, extracted)


# ------------------------------------------------------------ helpers
def _build_prompt_payload(asset: dict, extracted: dict) -> str:
    """Compose the user message for the extraction tool-call."""
    kind = asset.get("kind") or "asset"
    parts = [
        f"Asset kind: {kind}",
        f"Asset name: {asset.get('name') or '(untitled)'}",
    ]
    meta = extracted.get("meta") or {}
    if meta.get("url"):
        parts.append(f"Source URL: {meta['url']}")
    if meta.get("title"):
        parts.append(f"Page title: {meta['title']}")
    if meta.get("page_count"):
        parts.append(f"PDF pages: {meta['page_count']}")
    if meta.get("slide_count"):
        parts.append(f"PPTX slides: {meta['slide_count']}")
    if meta.get("duration_s"):
        parts.append(f"Video duration: {meta['duration_s']:.0f}s")
    if meta.get("width") and meta.get("height"):
        parts.append(f"Image dimensions: {meta['width']}x{meta['height']}")

    text = extracted.get("text") or ""
    if text:
        parts.append("\n--- ASSET CONTENT ---\n")
        parts.append(text)
    elif kind == "image":
        parts.append("\n(image asset — no extractable text; reason from "
                      "the dimensions, filename, and any visible signals)")
    elif kind == "video":
        parts.append("\n(video asset — transcript may be empty if the "
                      "clip was silent; reason from filename and duration)")

    return "\n".join(parts)


def _build_review_payload(asset: dict, extracted: dict,
                            intel: Optional[dict]) -> str:
    parts = [_build_prompt_payload(asset, extracted)]
    if intel:
        parts.append("\n--- EXTRACTED INTELLIGENCE (use as context) ---")
        if intel.get("summary"):
            parts.append(f"Summary: {intel['summary']}")
        if intel.get("brand", {}).get("name"):
            parts.append(f"Brand: {intel['brand']['name']}")
        if intel.get("products"):
            parts.append(f"Products: {', '.join(intel['products'][:6])}")
        if intel.get("audience"):
            parts.append(f"Audience: {', '.join(intel['audience'][:4])}")
        if intel.get("ctas"):
            parts.append(f"Detected CTAs: {', '.join(intel['ctas'][:4])}")
    return "\n".join(parts)


def _compose_memory_text(asset: dict, intel: Optional[dict]) -> str:
    """Short string written to Cortex Memory so future chat turns can
    recall this asset semantically."""
    if not intel:
        return f"Uploaded asset: {asset.get('name')} ({asset.get('kind')})."
    parts = [f"Asset uploaded: {asset.get('name')} ({asset.get('kind')}). "
              f"{intel.get('summary') or ''}"]
    if intel.get("products"):
        parts.append(f"Products: {', '.join(intel['products'][:5])}.")
    if intel.get("audience"):
        parts.append(f"Audience: {', '.join(intel['audience'][:3])}.")
    if intel.get("offers"):
        parts.append(f"Offers: {', '.join(intel['offers'][:3])}.")
    return " ".join(parts).strip()


def _normalize_intelligence(data: dict, label: str, mode: str) -> dict:
    """Clamp shapes + add source metadata."""
    out = {
        "id":          uuid.uuid4().hex,
        "summary":     _trim(data.get("summary"), 600),
        "brand":       _normalize_brand(data.get("brand") or {}),
        "products":    _str_list(data.get("products"), 12, 120),
        "services":    _str_list(data.get("services"), 8, 120),
        "audience":    _str_list(data.get("audience"), 8, 160),
        "pain_points": _str_list(data.get("pain_points"), 6, 160),
        "offers":      _str_list(data.get("offers"), 6, 160),
        "keywords":    _str_list(data.get("keywords"), 16, 60),
        "competitors": _str_list(data.get("competitors"), 8, 120),
        "ctas":        _str_list(data.get("ctas"), 6, 80),
        "source":      f"llm:{label}:{mode}",
        "created_at":  datetime.now(timezone.utc),
    }
    return out


def _normalize_brand(b: dict) -> dict:
    return {
        "name":       _trim(b.get("name"), 120),
        "tagline":    _trim(b.get("tagline"), 200),
        "tone":       _trim(b.get("tone"), 80),
        "value_prop": _trim(b.get("value_prop"), 220),
    }


def _normalize_review(data: dict, label: str, mode: str) -> dict:
    scores = data.get("scores") or {}
    def _clamp(v):
        try:
            return max(0, min(100, int(v)))
        except Exception:
            return 0
    return {
        "id":     uuid.uuid4().hex,
        "scores": {
            "overall":      _clamp(scores.get("overall")),
            "copy":         _clamp(scores.get("copy")),
            "visual":       _clamp(scores.get("visual")),
            "cta":          _clamp(scores.get("cta")),
            "audience_fit": _clamp(scores.get("audience_fit")),
            "conversion":   _clamp(scores.get("conversion")),
        },
        "strengths":           _str_list(data.get("strengths"), 6, 240),
        "weaknesses":          _str_list(data.get("weaknesses"), 6, 240),
        "recommended_changes": _str_list(data.get("recommended_changes"), 8, 280),
        "suggested_campaigns": _str_list(data.get("suggested_campaigns"), 5, 200),
        "source":     f"llm:{label}:{mode}",
        "created_at": datetime.now(timezone.utc),
    }


def _str_list(v, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        s = _trim(item, max_chars)
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _trim(s, limit: int) -> str:
    if s is None:
        return ""
    return str(s).strip()[:limit]


# ---------------------------------------------------- heuristic fallbacks
def _heuristic_intelligence(asset: dict, extracted: dict) -> dict:
    """Used when the LLM is unavailable. Provides a non-empty record so
    the UI never renders a blank intelligence pane."""
    text = (extracted.get("text") or "")[:400]
    return {
        "id":          uuid.uuid4().hex,
        "summary":     (text[:200] or f"{asset.get('kind')} asset — analysis pending."),
        "brand":       _normalize_brand({}),
        "products":    [], "services": [], "audience": [],
        "pain_points": [], "offers": [], "keywords": [],
        "competitors": [], "ctas": [],
        "source":      "heuristic",
        "created_at":  datetime.now(timezone.utc),
    }


def _heuristic_review(asset: dict, extracted: dict) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "scores": {
            "overall": 50, "copy": 50, "visual": 50,
            "cta": 50, "audience_fit": 50, "conversion": 50,
        },
        "strengths":           ["Asset uploaded — review pending LLM availability."],
        "weaknesses":          [],
        "recommended_changes": [],
        "suggested_campaigns": [],
        "source":     "heuristic",
        "created_at": datetime.now(timezone.utc),
    }
