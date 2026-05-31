"""SEO Sprint v1 · Round 2 — content generator for 5 core landing pages.

Each spec (slug, h1, target_keywords, blurb) feeds Claude Sonnet 4.5 through
`cortex_chat` (Emergent LLM key) and asks for STRICT JSON matching our
`SeoLandingTemplate` content schema. Outputs land at:

    /app/frontend/src/pages/landing-os/content/<slug>.json

Run:
    cd /app/backend && python -m scripts.generate_seo_landings

Idempotent: re-running overwrites the JSON files. Word counts are
enforced at the prompt level + sanity-checked post-generation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Make `cortex.*` and `core` importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("seo_landings")


OUT_DIR = Path("/app/frontend/src/pages/landing-os/content")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- specs
SPECS = [
    {
        "slug": "marketing-os",
        "title": "AI Marketing Operating System | CortexViral",
        "meta": (
            "CortexViral is an AI Marketing Operating System that plans "
            "campaigns, generates content, recruits sellers, and executes "
            "growth workflows from one command center."
        ),
        "h1_lead": "The AI Marketing",
        "h1_accent": "Operating System.",
        "kicker": "Marketing OS",
        "primary_kw": "AI Marketing Operating System",
        "keywords": [
            "AI Marketing Operating System",
            "Marketing OS",
            "Marketing automation platform",
            "Unified marketing platform",
            "AI marketing platform",
        ],
        "audience": "growth teams, founders, and agency operators",
        "angle": (
            "Position CortexViral as a unified operating system (not just "
            "another point-tool) that replaces a stack of 8–12 marketing "
            "SaaS products with one orchestrated brain. Emphasize Cortex "
            "(the orchestrator), Mission-driven execution, and event-driven "
            "agent loops."
        ),
    },
    {
        "slug": "seller-acquisition",
        "title": "AI Seller Acquisition Software | CortexViral",
        "meta": (
            "Find, qualify, and onboard high-fit marketplace sellers with AI. "
            "CortexViral discovers Etsy, Shopify, and indie sellers — then "
            "scores, drafts personalized outreach, and tracks every reply."
        ),
        "h1_lead": "Seller Acquisition,",
        "h1_accent": "fully automated.",
        "kicker": "Seller Acquisition Engine",
        "primary_kw": "Seller acquisition software",
        "keywords": [
            "Seller acquisition software",
            "Etsy seller outreach",
            "Marketplace growth software",
            "AI seller discovery",
            "Maker recruiting tool",
        ],
        "audience": "marketplaces, B2B platforms, and agencies recruiting indie sellers",
        "angle": (
            "Show how the platform replaces manual seller scouting + "
            "spreadsheet outreach with an end-to-end engine: Discovery → "
            "3-band confidence scoring → Review queue (human-in-the-loop) → "
            "Personalized audit-attached outreach → Lifecycle tracking. "
            "Reference the Recommended Action surfacing + Prospect "
            "Intelligence Cards."
        ),
    },
    {
        "slug": "ai-campaign-generator",
        "title": "AI Marketing Campaign Generator | CortexViral",
        "meta": (
            "Generate full marketing campaigns — social posts, email sequences, "
            "and landing pages — from a single creative brief. CortexViral's "
            "AI campaign builder ships in minutes, not weeks."
        ),
        "h1_lead": "AI Campaigns,",
        "h1_accent": "brief to launch.",
        "kicker": "Campaign Builder",
        "primary_kw": "AI campaign generator",
        "keywords": [
            "AI Campaign Generator",
            "Marketing campaign AI",
            "Campaign planning software",
            "Multi-channel campaign builder",
            "AI marketing assistant",
        ],
        "audience": "marketing managers, in-house teams, and consultancies",
        "angle": (
            "Frame the Autonomous Campaign Builder: upload a brief (PDF/"
            "PPTX/video/URL) → Cortex extracts intelligence → composes a "
            "campaign bundle (10+ social posts, email sequence, landing "
            "page hero) → schedules across optimal posting windows. "
            "Show before/after time savings: 3 weeks → 11 minutes."
        ),
    },
    {
        "slug": "competitor-analysis",
        "title": "AI Competitor Analysis Software | CortexViral",
        "meta": (
            "Track competitor positioning, pricing, content velocity, and "
            "social engagement with AI. CortexViral surfaces three concrete "
            "moves to beat your category every week."
        ),
        "h1_lead": "Competitive intelligence,",
        "h1_accent": "weekly, automated.",
        "kicker": "Competitor Analysis",
        "primary_kw": "Competitor analysis AI",
        "keywords": [
            "Competitor Analysis AI",
            "Competitive Intelligence Software",
            "AI competitor tracking",
            "Marketing competitor analysis",
            "Brand monitoring AI",
        ],
        "audience": "founders and CMOs operating in crowded categories",
        "angle": (
            "Walk through the Intelligence team's competitor sweep: public-"
            "storefront crawl → assortment / pricing / engagement scoring "
            "→ 1-page strategic brief with 3 concrete next-week actions. "
            "Highlight that this runs autonomously every week without a "
            "human analyst."
        ),
    },
    {
        "slug": "asset-analysis",
        "title": "AI Marketing Asset Analysis | CortexViral",
        "meta": (
            "Drop a PDF, PPTX, video, or URL — get marketing-grade analysis "
            "in seconds. CortexViral extracts positioning, audience, hooks, "
            "and converts every asset into a campaign-ready brief."
        ),
        "h1_lead": "Drop an asset.",
        "h1_accent": "Get a campaign.",
        "kicker": "Asset Intelligence",
        "primary_kw": "Marketing asset analysis",
        "keywords": [
            "Marketing Asset Analysis",
            "Creative Analysis AI",
            "PDF Marketing Analysis",
            "Video marketing analysis",
            "PPTX to campaign",
        ],
        "audience": "agencies, founders, and content teams sitting on a folder of slide decks and PDFs",
        "angle": (
            "Show how the Asset Upload Center turns inert collateral into "
            "actionable marketing fuel: PDF/PPTX text + slide extraction, "
            "video → Whisper transcription + cost calc, URL scrape + "
            "hero-image extraction, intelligence layer (audience, "
            "positioning, hook angles), one-click campaign generation. "
            "Mention the 50MB limit and pricing transparency."
        ),
    },
]


# ---------------------------------------------------------------- schema
# JSON the LLM MUST emit. We render it with React via SeoLandingTemplate.
SCHEMA = {
    "hero_subhead": "single-paragraph subhead under the H1 — 35–55 words, sells the page idea, uses primary keyword once naturally",
    "hero_bullets": "array of 4 short benefit bullets, 4–8 words each — verb-led, no fluff",
    "sections": (
        "array of 6 long-form sections. Each: "
        "{kicker: short eyebrow (2–4 words), heading: 4–10 words, "
        " body: 150–220 words written confidently with concrete numbers/"
        "examples — NO em-dashes from prose, dashes inside compounds are "
        "fine; bullets: optional array of 3–5 punchy bullets}"
    ),
    "comparison": (
        "{title: 6–10 words, left: {label, items[]}, right: {label, items[]}} "
        "to contrast 'Old way / Without CortexViral' vs 'CortexViral way'. "
        "Each side has 4–6 items, 6–14 words each."
    ),
    "internal_links": (
        "array of EXACTLY 3 of the OTHER 4 slugs to link to. "
        "Each: {slug, title, blurb (12–20 words)}"
    ),
    "faq": (
        "array of 6 questions tightly themed around the primary keyword. "
        "Each: {q (8–18 words), a (60–110 words). Answers must be useful "
        "even out of context, since they are pulled into Schema.org FAQPage.}"
    ),
    "final_cta_heading": "8–14 word closing CTA headline",
    "final_cta_body": "20–35 word closing paragraph",
}


# All 5 slugs — used to seed internal-link options for each prompt.
ALL_SLUGS = [s["slug"] for s in SPECS]
SLUG_TITLES = {
    "marketing-os":          "AI Marketing Operating System",
    "seller-acquisition":    "AI Seller Acquisition Engine",
    "ai-campaign-generator": "AI Campaign Generator",
    "competitor-analysis":   "AI Competitor Analysis",
    "asset-analysis":        "AI Marketing Asset Analysis",
}


def _build_prompt(spec: dict) -> str:
    """User-message prompt for one page."""
    sibling_options = [
        f"  - {s} → {SLUG_TITLES[s]}"
        for s in ALL_SLUGS if s != spec["slug"]
    ]
    return (
        f"Write the long-form content for the CortexViral SEO landing "
        f"page at /{spec['slug']}.\n\n"
        f"CONTEXT\n"
        f"-------\n"
        f"CortexViral is an AI Marketing Operating System. The platform "
        f"has: a Cortex orchestrator (Claude/GPT routed through "
        f"Emergent), Mission-driven execution, four agent teams (Scout, "
        f"Creator, Operator, Intelligence), an Asset Upload Center "
        f"(PDF/PPTX/Video/URL), an Autonomous Campaign Builder, "
        f"Direct Social Publishing (bulk + auto-schedule), a Seller "
        f"Acquisition Engine with 3-band confidence scoring + Review "
        f"Queue, autonomy levels L0–L5, and a Recommended Action layer "
        f"that surfaces the highest-leverage next move.\n\n"
        f"TARGET PAGE\n"
        f"-----------\n"
        f"slug: /{spec['slug']}\n"
        f"H1: {spec['h1_lead']} {spec['h1_accent']}\n"
        f"primary keyword: {spec['primary_kw']}\n"
        f"all target keywords: {', '.join(spec['keywords'])}\n"
        f"audience: {spec['audience']}\n"
        f"angle: {spec['angle']}\n\n"
        f"WORD BUDGET\n"
        f"-----------\n"
        f"Total long-form body (sum of all section bodies) MUST be "
        f"between 1500 and 1900 words. FAQ answers (separately) add "
        f"another ~450 words.\n\n"
        f"INTERNAL LINK OPTIONS — pick exactly 3 of these:\n"
        + "\n".join(sibling_options) +
        f"\n\nVOICE\n"
        f"-----\n"
        f"Confident, founder-led, no fluff. Concrete numbers. Real "
        f"examples. Sentences mostly 8–18 words. NO em-dashes in prose "
        f"(use a comma or a period). NO 'In conclusion'. NO 'In today's "
        f"fast-paced world'. Address the reader as 'you'.\n\n"
        f"OUTPUT FORMAT\n"
        f"-------------\n"
        f"Return STRICT JSON matching this schema (descriptions of each "
        f"field follow):\n\n"
        + json.dumps(SCHEMA, indent=2)
    )


SYSTEM_PROMPT = (
    "You are a senior SEO copywriter working inside CortexViral, an AI "
    "Marketing Operating System. Every page you produce must rank, "
    "convert, and read like a real product page written by a smart "
    "operator — not generic AI mush. Return STRICT JSON only. No "
    "prose outside the JSON. No markdown fences."
)


# --------------------------------------------------------------- driver
async def _generate_one(spec: dict) -> dict:
    from cortex.llm_provider import cortex_chat

    user_text = _build_prompt(spec)
    logger.info("→ generating /%s (primary_kw=%r) …",
                spec["slug"], spec["primary_kw"])
    text, label = await cortex_chat(
        system=SYSTEM_PROMPT,
        user_text=user_text,
        session_id=f"seo-landing-{spec['slug']}",
        user_id="seo-gen",
        prefer="claude",
        json_mode=True,
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Salvage via json_repair if Claude tucked the JSON behind any
        # accidental prose. json_repair is already a project dep
        # (handoff: campaign_builder).
        from json_repair import repair_json
        data = json.loads(repair_json(text))

    # Stamp the spec metadata onto the content so the React template
    # has everything in one bag.
    data["__meta__"] = {
        "slug":      spec["slug"],
        "title":     spec["title"],
        "meta":      spec["meta"],
        "h1_lead":   spec["h1_lead"],
        "h1_accent": spec["h1_accent"],
        "kicker":    spec["kicker"],
        "primary_kw": spec["primary_kw"],
        "keywords":  spec["keywords"],
        "generated_by": label,
    }

    # Word-count sanity (informational only; we don't reject).
    body_words = sum(
        len((s.get("body") or "").split())
        for s in (data.get("sections") or [])
    )
    logger.info("   slug=/%s · model=%s · body=%d words · sections=%d · faq=%d",
                spec["slug"], label, body_words,
                len(data.get("sections") or []),
                len(data.get("faq") or []))
    if body_words < 1300:
        logger.warning("   ↘ word count %d below 1300 — page will still "
                       "render but consider re-rolling.", body_words)
    return data


async def main():
    for spec in SPECS:
        out_file = OUT_DIR / f"{spec['slug']}.json"
        if os.environ.get("SEO_SKIP_EXISTING") == "1" and out_file.exists():
            logger.info("⊘ skipping /%s (file exists, SEO_SKIP_EXISTING=1)",
                        spec["slug"])
            continue
        try:
            content = await _generate_one(spec)
        except Exception:
            logger.exception("✗ generation FAILED for /%s", spec["slug"])
            continue
        out_file.write_text(json.dumps(content, indent=2, ensure_ascii=False))
        logger.info("✓ wrote %s", out_file)


if __name__ == "__main__":
    asyncio.run(main())
