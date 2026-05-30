"""Autonomous Campaign Builder — Phase C.

Turns a Creative Brief + Asset Intelligence into a complete, executable
campaign artifact bundle in a single orchestration:

    Asset → Intelligence + Review → Brief → CAMPAIGN
                                            ├── social posts (per platform)
                                            ├── email sequence (3-touch)
                                            ├── landing page outline
                                            └── creative images (via Phase B)

The text artifacts come from a SINGLE consolidated LLM tool-call
(`compose_campaign_artifacts`). One call keeps brand voice cohesive
across all surfaces — separate calls per artifact tend to drift.

Image generation is fanned out via the existing `generate-all` flow
(Phase B) as a fire-and-forget background task — the campaign is
considered complete as soon as the text artifacts land, and images
populate in over the following minute.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


_CAMPAIGN_TOOL = {
    "name": "compose_campaign_artifacts",
    "description": (
        "Produce a complete, ready-to-execute campaign artifact bundle "
        "from the brief: campaign meta + social posts (one per "
        "recommended platform, 1-3 variants each), a 3-touch email "
        "sequence, and a landing-page outline. Maintain consistent brand "
        "voice and the SAME core hook across all surfaces."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "campaign_title":   {"type": "string",
                                  "description": "Short, memorable campaign name (e.g. 'Founding Maker Program')."},
            "campaign_goal":    {"type": "string",
                                  "description": "One-sentence outcome metric (numeric where possible)."},
            "campaign_summary": {"type": "string",
                                  "description": "2-3 sentence executive overview connecting the offer, audience, and the core hook."},
            "social_posts": {
                "type": "array",
                "description": "One entry per recommended platform; each posts[] is 1-3 ready-to-post variants.",
                "items": {
                    "type": "object",
                    "properties": {
                        "platform":  {"type": "string"},
                        "format":    {"type": "string",
                                       "description": "e.g., 'square ad', 'reel', 'pin', 'carousel'."},
                        "posts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "headline":  {"type": "string"},
                                    "body":      {"type": "string",
                                                   "description": "Caption / post body, length-appropriate for the platform."},
                                    "hashtags":  {"type": "array", "items": {"type": "string"}},
                                    "cta":       {"type": "string"},
                                },
                                "required": ["body", "cta"],
                            },
                        },
                    },
                    "required": ["platform", "posts"],
                },
            },
            "email_sequence": {
                "type": "array",
                "description": "Exactly 3 emails in a nurture sequence (awareness → consideration → conversion).",
                "items": {
                    "type": "object",
                    "properties": {
                        "step":       {"type": "integer", "description": "1, 2, or 3."},
                        "purpose":    {"type": "string",
                                        "description": "e.g., 'introduce offer', 'social proof', 'final urgency'."},
                        "subject":    {"type": "string"},
                        "preheader":  {"type": "string"},
                        "body":       {"type": "string",
                                        "description": "Plain-text body, 100-250 words. Use line breaks; no HTML."},
                        "cta":        {"type": "string"},
                    },
                    "required": ["step", "subject", "body", "cta"],
                },
            },
            "landing_page": {
                "type": "object",
                "description": "Single-page conversion outline aligned with the campaign hook.",
                "properties": {
                    "headline":     {"type": "string"},
                    "subheadline":  {"type": "string"},
                    "sections": {
                        "type": "array",
                        "description": "3-5 main sections (hero, value props, social proof, FAQ, final CTA).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title":   {"type": "string"},
                                "purpose": {"type": "string"},
                                "body":    {"type": "string"},
                            },
                            "required": ["title", "body"],
                        },
                    },
                    "primary_cta":   {"type": "string"},
                    "secondary_cta": {"type": "string"},
                },
                "required": ["headline", "sections", "primary_cta"],
            },
        },
        "required": ["campaign_title", "campaign_goal", "social_posts",
                      "email_sequence", "landing_page"],
    },
}


async def build_campaign(*, brief: dict, asset_intel: Optional[dict],
                            user_id: str) -> dict:
    """End-to-end orchestrator. Persists a `cortex_campaigns` row,
    generates the text artifact bundle, and kicks off image generation
    in the background. Returns the new campaign row."""
    from core import db

    campaign_id = uuid.uuid4().hex
    base_row = {
        "id":         campaign_id,
        "user_id":    user_id,
        "brief_id":   brief.get("id"),
        "asset_id":   brief.get("asset_id"),
        "title":      "Building campaign…",
        "status":     "building",
        "steps":      [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.cortex_campaigns.insert_one(base_row)

    asyncio.create_task(_run_pipeline(campaign_id, brief, asset_intel, user_id))
    return base_row


async def _run_pipeline(campaign_id: str, brief: dict,
                          asset_intel: Optional[dict], user_id: str) -> None:
    """Background pipeline. Best-effort — errors flip status to failed
    with a reason; partial successes still land what they can."""
    from core import db

    steps: list[dict] = []

    async def _step(name: str, fn):
        s = {"name": name, "status": "running",
              "started_at": datetime.now(timezone.utc).isoformat()}
        steps.append(s)
        await db.cortex_campaigns.update_one(
            {"id": campaign_id}, {"$set": {"steps": steps}})
        try:
            out = await fn()
            s["status"] = "complete"
            s["finished_at"] = datetime.now(timezone.utc).isoformat()
            return out
        except Exception as e:
            s["status"] = "failed"
            s["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            logger.exception("campaign step %s failed for %s", name, campaign_id)
            return None
        finally:
            await db.cortex_campaigns.update_one(
                {"id": campaign_id}, {"$set": {"steps": steps}})

    # 1) Text artifact bundle.
    artifacts = await _step("compose_artifacts",
                              lambda: _compose_artifacts(brief, asset_intel, user_id))

    if artifacts:
        await _step("persist_posts",
                      lambda: _persist_posts(campaign_id, user_id, artifacts))
        await _step("persist_emails",
                      lambda: _persist_emails(campaign_id, user_id, artifacts))
        await _step("persist_landing_page",
                      lambda: _persist_landing_page(campaign_id, user_id, artifacts))
        # Stamp campaign-level meta on the row.
        await db.cortex_campaigns.update_one(
            {"id": campaign_id},
            {"$set": {
                "title":            artifacts.get("campaign_title") or "Untitled campaign",
                "goal":             artifacts.get("campaign_goal"),
                "summary":          artifacts.get("campaign_summary"),
                "updated_at":       datetime.now(timezone.utc),
            }},
        )

    # 2) Fire image generation in the background — this can take a
    # minute or two per concept; we don't block campaign completion.
    if brief.get("creative_concepts"):
        await _step("queue_images",
                      lambda: _queue_images(brief, user_id, campaign_id))

    # Final status — complete if at least artifacts landed, else failed.
    final = "complete" if artifacts else "failed"
    await db.cortex_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": final,
                   "updated_at": datetime.now(timezone.utc)}},
    )


# ----------------------------------------------------- artifact compose
async def _compose_artifacts(brief: dict, asset_intel: Optional[dict],
                                user_id: str) -> Optional[dict]:
    """Single LLM tool-call producing the full artifact bundle."""
    from cortex.llm_provider import cortex_tool_call
    from core import EMERGENT_LLM_KEY

    if not EMERGENT_LLM_KEY:
        logger.warning("campaign_builder: EMERGENT_LLM_KEY missing")
        return None

    sys_prompt = (
        "You are Cortex's Campaign Director. Given a Creative Brief, "
        "produce the complete artifact bundle a marketing team needs to "
        "launch tomorrow: campaign meta, ready-to-post social variants "
        "per channel, a 3-touch email nurture sequence, and a landing "
        "page outline. Maintain the same headline hook across surfaces. "
        "Write with the brand's tone; no generic 'engaging content' "
        "filler. Every element must be executable as-is."
    )

    ta = brief.get("target_audience") or {}
    user_text = (
        f"Campaign goal: {brief.get('campaign_goal')}\n"
        f"Offer: {brief.get('offer')}\n"
        f"Audience (primary): {ta.get('primary')}\n"
        f"Audience (secondary): {', '.join(ta.get('secondary') or [])}\n"
        f"Psychographics: {', '.join(ta.get('psychographics') or [])}\n"
        f"Messaging angles: {chr(10) + chr(10).join('  - ' + a for a in (brief.get('messaging_angles') or []))}\n"
        f"Recommended platforms: {', '.join(brief.get('recommended_platforms') or [])}\n"
        f"Existing content plan: {brief.get('content_plan')}\n"
    )
    brand = (asset_intel or {}).get("brand") or {}
    if brand.get("name") or brand.get("tone") or brand.get("value_prop"):
        user_text += (
            f"\nBrand: {brand.get('name','')} — "
            f"{brand.get('value_prop','')} | tone: {brand.get('tone','')}\n"
        )

    try:
        args, _label, _mode = await cortex_tool_call(
            system=sys_prompt,
            user_text=user_text,
            tool=_CAMPAIGN_TOOL,
            session_id=f"campaign-build-{brief.get('id')}",
            user_id=user_id or "anonymous",
            prefer="claude",
            required=["campaign_title", "social_posts",
                       "email_sequence", "landing_page"],
        )
        return args
    except Exception:
        logger.exception("campaign_builder: artifact compose failed")
        return None


# -------------------------------------------------------- persistence
async def _persist_posts(campaign_id: str, user_id: str, artifacts: dict) -> dict:
    from core import db
    n = 0
    bulk: list[dict] = []
    for group in artifacts.get("social_posts") or []:
        if not isinstance(group, dict):
            continue
        platform = (group.get("platform") or "").strip().lower()
        fmt = (group.get("format") or "").strip()
        for variant in (group.get("posts") or []):
            if not isinstance(variant, dict) or not variant.get("body"):
                continue
            bulk.append({
                "id":          uuid.uuid4().hex,
                "user_id":     user_id,
                "campaign_id": campaign_id,
                "platform":    platform,
                "format":      fmt,
                "headline":    (variant.get("headline") or "")[:280],
                "body":        variant.get("body")[:2200],
                "hashtags":    [str(h)[:60] for h in (variant.get("hashtags") or [])][:12],
                "cta":         (variant.get("cta") or "")[:140],
                "status":      "draft",
                "created_at":  datetime.now(timezone.utc),
            })
            n += 1
    if bulk:
        await db.cortex_social_posts.insert_many(bulk)
    return {"posts_written": n}


async def _persist_emails(campaign_id: str, user_id: str, artifacts: dict) -> dict:
    from core import db
    n = 0
    bulk: list[dict] = []
    for em in artifacts.get("email_sequence") or []:
        if not isinstance(em, dict) or not em.get("subject"):
            continue
        bulk.append({
            "id":          uuid.uuid4().hex,
            "user_id":     user_id,
            "campaign_id": campaign_id,
            "step":        int(em.get("step") or 0),
            "purpose":     (em.get("purpose") or "")[:120],
            "subject":     em.get("subject")[:200],
            "preheader":   (em.get("preheader") or "")[:200],
            "body":        em.get("body", "")[:4000],
            "cta":         (em.get("cta") or "")[:140],
            "status":      "draft",
            "created_at":  datetime.now(timezone.utc),
        })
        n += 1
    if bulk:
        await db.cortex_email_drafts.insert_many(bulk)
    return {"emails_written": n}


async def _persist_landing_page(campaign_id: str, user_id: str,
                                   artifacts: dict) -> dict:
    from core import db
    lp = artifacts.get("landing_page")
    if not isinstance(lp, dict) or not lp.get("headline"):
        return {"landing_page_written": 0}
    sections: list[dict] = []
    for s in (lp.get("sections") or []):
        if not isinstance(s, dict) or not s.get("body"):
            continue
        sections.append({
            "title":   (s.get("title")   or "")[:160],
            "purpose": (s.get("purpose") or "")[:160],
            "body":    s.get("body", "")[:1600],
        })
    row = {
        "id":          uuid.uuid4().hex,
        "user_id":     user_id,
        "campaign_id": campaign_id,
        "headline":    lp.get("headline")[:200],
        "subheadline": (lp.get("subheadline") or "")[:280],
        "sections":    sections,
        "primary_cta":   (lp.get("primary_cta")   or "")[:120],
        "secondary_cta": (lp.get("secondary_cta") or "")[:120],
        "status":      "draft",
        "created_at":  datetime.now(timezone.utc),
    }
    await db.cortex_landing_pages.update_one(
        {"campaign_id": campaign_id, "user_id": user_id},
        {"$set": row}, upsert=True)
    return {"landing_page_written": 1}


async def _queue_images(brief: dict, user_id: str, campaign_id: str) -> dict:
    """Fire-and-forget image generation across all brief concepts.
    Failures don't block campaign completion — the UI shows per-concept
    failed state and the user can retry."""
    from cortex.image_provider import generate_for_concept
    from cortex.asset_storage import storage
    from core import db

    concepts = brief.get("creative_concepts") or []
    asset_intel = None
    if brief.get("asset_id"):
        asset_intel = await db.cortex_asset_intelligence.find_one(
            {"asset_id": brief["asset_id"]}, {"_id": 0})

    async def _gen_one(i, concept):
        # Skip if a complete creative already exists for this concept.
        ex = await db.cortex_creatives.find_one(
            {"brief_id": brief.get("id"), "concept_index": i,
              "user_id": user_id, "status": "complete"}, {"_id": 0})
        if ex:
            return
        cid = uuid.uuid4().hex
        size = "square"
        await db.cortex_creatives.insert_one({
            "id":             cid,
            "user_id":        user_id,
            "brief_id":       brief.get("id"),
            "asset_id":       brief.get("asset_id"),
            "campaign_id":    campaign_id,
            "concept_index":  i,
            "concept_title":  concept.get("title"),
            "concept_format": concept.get("format"),
            "size":           size,
            "status":         "generating",
            "created_at":     datetime.now(timezone.utc),
            "updated_at":     datetime.now(timezone.utc),
        })
        try:
            res = await generate_for_concept(concept=concept, brief=brief,
                                                asset=asset_intel, size=size)
            key = f"{user_id}/creatives/{cid}.png"
            await storage.save(key, res["bytes"])
            await db.cortex_creatives.update_one(
                {"id": cid},
                {"$set": {"status": "complete",
                           "provider":    res["provider"],
                           "prompt":      res["prompt"],
                           "storage_key": key,
                           "width":       res["width"],
                           "height":      res["height"],
                           "updated_at":  datetime.now(timezone.utc)}},
            )
        except Exception as e:
            await db.cortex_creatives.update_one(
                {"id": cid},
                {"$set": {"status": "failed",
                           "error":  f"{type(e).__name__}: {str(e)[:240]}",
                           "updated_at": datetime.now(timezone.utc)}},
            )

    # Run with bounded parallelism (3 at a time) so we don't hammer
    # the providers when a brief has 6+ concepts.
    sem = asyncio.Semaphore(3)
    async def _bounded(i, c):
        async with sem:
            await _gen_one(i, c)

    await asyncio.gather(*[_bounded(i, c) for i, c in enumerate(concepts)],
                           return_exceptions=True)
    return {"images_queued": len(concepts)}
