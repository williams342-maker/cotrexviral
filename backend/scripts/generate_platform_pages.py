"""SEO Sprint v1 · Round 3 — content generator for 6 platform pages.

Each platform gets a dedicated page positioning CortexViral as the AI
marketing brain for that specific channel:
    /instagram-marketing-ai
    /facebook-marketing-ai
    /linkedin-marketing-ai
    /reddit-marketing-ai
    /youtube-marketing-ai
    /tiktok-marketing-ai

Each page renders through the same `SeoLandingTemplate` as Round 2 but
its JSON content lives under `/app/frontend/src/pages/platform-ai/content/`.
Word budget is ~1000 body words (6 sections × ~140-180 words) plus the
FAQ block.

Run:
    cd /app/backend && python -m scripts.generate_platform_pages
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("platform_pages")


OUT_DIR = Path("/app/frontend/src/pages/platform-ai/content")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- specs
SPECS = [
    {
        "slug": "instagram-marketing-ai",
        "title": "Instagram Marketing AI | CortexViral",
        "meta": (
            "Plan, generate, and publish Instagram content with AI. "
            "CortexViral turns Reels hooks, carousels, captions, and "
            "Stories into a coordinated growth engine."
        ),
        "h1_lead": "Instagram marketing,",
        "h1_accent": "on autopilot.",
        "kicker": "Instagram Marketing AI",
        "primary_kw": "Instagram marketing AI",
        "platform": "Instagram",
        "platform_specifics": (
            "Native formats: Reels (9:16 video, 90s max), carousels (up "
            "to 10 slides), Stories (24h), single-image posts. Algorithm "
            "weights Reels watch-time, saves/shares > likes, profile "
            "visits. Hashtag relevance has decayed; topic-graph + "
            "captions matter more in 2026."
        ),
        "audience": "creators, e-commerce brands, and lifestyle businesses on Instagram",
    },
    {
        "slug": "facebook-marketing-ai",
        "title": "Facebook Marketing AI | CortexViral",
        "meta": (
            "Run Facebook marketing with AI: pages, groups, Reels, ads, "
            "and Messenger flows. CortexViral plans the content and "
            "schedules it across audiences."
        ),
        "h1_lead": "Facebook marketing,",
        "h1_accent": "agent-driven.",
        "kicker": "Facebook Marketing AI",
        "primary_kw": "Facebook marketing AI",
        "platform": "Facebook",
        "platform_specifics": (
            "Native formats: Page posts (text + image/video), Reels, "
            "Stories, Groups (community-driven reach), Marketplace, and "
            "ad creatives across Feed/Reels/Stories placements. Algorithm "
            "rewards Groups + meaningful interactions; organic reach on "
            "Page posts is low without spend, so Reels + Group seeding "
            "are the levers."
        ),
        "audience": "local businesses, community-driven brands, and ecommerce sellers using Facebook + Meta Ads",
    },
    {
        "slug": "linkedin-marketing-ai",
        "title": "LinkedIn Marketing AI | CortexViral",
        "meta": (
            "Build LinkedIn presence with AI. CortexViral drafts founder "
            "posts, carousel PDFs, newsletter editions, and DM sequences "
            "that drive real B2B pipeline."
        ),
        "h1_lead": "LinkedIn marketing,",
        "h1_accent": "founder-led at scale.",
        "kicker": "LinkedIn Marketing AI",
        "primary_kw": "LinkedIn marketing AI",
        "platform": "LinkedIn",
        "platform_specifics": (
            "Native formats: text posts (most reach), document carousels "
            "(PDF), short video, newsletters, polls, articles. Algorithm "
            "rewards dwell time + reply velocity in first 60 minutes. "
            "Personal profiles outperform company pages by 3-5×."
        ),
        "audience": "B2B founders, SaaS operators, agencies, and consultants pursuing inbound pipeline",
    },
    {
        "slug": "reddit-marketing-ai",
        "title": "Reddit Marketing AI | CortexViral",
        "meta": (
            "Reach Reddit communities with AI that knows the rules. "
            "CortexViral drafts on-tone posts, monitors subreddit "
            "sentiment, and times comments for max upvotes."
        ),
        "h1_lead": "Reddit marketing,",
        "h1_accent": "without getting banned.",
        "kicker": "Reddit Marketing AI",
        "primary_kw": "Reddit marketing AI",
        "platform": "Reddit",
        "platform_specifics": (
            "Native formats: text posts, link posts, image/video posts, "
            "comments. Each subreddit has its own rules + tone — generic "
            "promotional content gets removed instantly. The 9:1 value-"
            "to-promo rule still holds. Karma and account age gate "
            "many subreddits."
        ),
        "audience": "indie founders, SaaS teams, and niche brands seeking high-intent traffic from Reddit",
    },
    {
        "slug": "youtube-marketing-ai",
        "title": "YouTube Marketing AI | CortexViral",
        "meta": (
            "Grow on YouTube with AI scripting, thumbnail testing, "
            "Shorts ideation, and SEO-rich descriptions. CortexViral "
            "manages every step of the channel."
        ),
        "h1_lead": "YouTube marketing,",
        "h1_accent": "long-form and Shorts.",
        "kicker": "YouTube Marketing AI",
        "primary_kw": "YouTube marketing AI",
        "platform": "YouTube",
        "platform_specifics": (
            "Native formats: long-form videos (8-20 min sweet spot), "
            "Shorts (60s vertical), live streams, community posts. "
            "Algorithm optimizes CTR × watch-time. Thumbnail + title is "
            "70% of the battle. Shorts feed siloed from long-form."
        ),
        "audience": "creators, course businesses, and content-led companies investing in YouTube",
    },
    {
        "slug": "tiktok-marketing-ai",
        "title": "TikTok Marketing AI | CortexViral",
        "meta": (
            "Trend-aware TikTok marketing AI. CortexViral identifies "
            "rising sounds, drafts scroll-stopping hooks, and schedules "
            "Reels-class posts on the For You curve."
        ),
        "h1_lead": "TikTok marketing,",
        "h1_accent": "tuned to the For You curve.",
        "kicker": "TikTok Marketing AI",
        "primary_kw": "TikTok marketing AI",
        "platform": "TikTok",
        "platform_specifics": (
            "Native formats: 9:16 short-form video (15s sweet spot, up "
            "to 10 min). Algorithm = relentless interest-graph; first "
            "2 seconds determine fate. Sound trends + duets/stitches "
            "drive distribution. Hashtag relevance ≈ medium; on-screen "
            "captions are critical (sound-off viewing)."
        ),
        "audience": "creators, DTC brands, and consumer apps running viral TikTok motion",
    },
]


ALL_SLUGS = [s["slug"] for s in SPECS]
SLUG_TITLES = {s["slug"]: s["kicker"] for s in SPECS}
SLUG_TITLES["marketing-os"] = "AI Marketing Operating System"

SCHEMA = {
    "hero_subhead": "single-paragraph subhead under the H1 — 30–45 words, uses primary keyword once",
    "hero_bullets": "array of 4 short benefit bullets, 4–8 words each",
    "sections": (
        "array of 6 sections. Each: "
        "{kicker: 2–4 words, heading: 4–10 words, "
        " body: 130–180 words written tight with concrete numbers + "
        " platform-specific mechanics — NO em-dashes in prose; "
        " bullets: optional 3–5 punchy bullets}"
    ),
    "comparison": (
        "{title, left: {label='Posting manually', items[]}, "
        "right: {label='CortexViral + this platform', items[]}}; 4–5 "
        "items per side, 6–14 words each."
    ),
    "internal_links": (
        "array of EXACTLY 3 — MUST include 'marketing-os' as the first "
        "link, plus 2 OTHER platform slugs from the list. "
        "Each: {slug, title, blurb 12–20 words}"
    ),
    "faq": (
        "array of 5 questions tightly themed around the primary keyword "
        "+ that specific platform. Each: {q (8–18 words), a (60–110 "
        "words). Answers must stand alone — they get pulled into Schema.org FAQPage.}"
    ),
    "final_cta_heading": "8–14 word closing CTA",
    "final_cta_body": "20–35 word closing paragraph",
}


def _build_prompt(spec: dict) -> str:
    sibling_platforms = [s for s in ALL_SLUGS if s != spec["slug"]]
    sibling_options = (
        "  - marketing-os → AI Marketing Operating System (REQUIRED first link)\n"
        + "\n".join(f"  - {s} → {SLUG_TITLES[s]}" for s in sibling_platforms)
    )
    return (
        f"Write the long-form content for the CortexViral SEO landing "
        f"page at /{spec['slug']}.\n\n"
        f"CONTEXT\n"
        f"-------\n"
        f"CortexViral is an AI Marketing Operating System. The platform "
        f"has a Cortex orchestrator (Claude/GPT routed through Emergent), "
        f"Mission-driven execution, four agent teams (Scout, Creator, "
        f"Operator, Intelligence), an Asset Upload Center, an Autonomous "
        f"Campaign Builder, Direct Social Publishing with bulk and "
        f"auto-scheduling on optimal windows, and autonomy levels L0–L5.\n\n"
        f"TARGET PAGE — focused on {spec['platform']}\n"
        f"-----------\n"
        f"slug: /{spec['slug']}\n"
        f"H1: {spec['h1_lead']} {spec['h1_accent']}\n"
        f"primary keyword: {spec['primary_kw']}\n"
        f"audience: {spec['audience']}\n\n"
        f"PLATFORM SPECIFICS YOU MUST WEAVE IN\n"
        f"{spec['platform_specifics']}\n\n"
        f"WORD BUDGET\n"
        f"Total long-form body (sum of section bodies) should land "
        f"between 900 and 1300 words.\n\n"
        f"INTERNAL LINKS — pick exactly 3 (FIRST must be marketing-os):\n"
        + sibling_options +
        f"\n\nVOICE\n"
        f"Confident, founder-led, no fluff. Concrete numbers + "
        f"platform-specific mechanics (formats, algo behavior, posting "
        f"cadence). Sentences mostly 8–18 words. NO em-dashes in prose. "
        f"NO 'In conclusion'. NO 'fast-paced world'. Address the reader "
        f"as 'you'. Mention the platform name by its proper casing.\n\n"
        f"OUTPUT FORMAT\n"
        f"-------------\n"
        f"Return STRICT JSON matching this schema:\n\n"
        + json.dumps(SCHEMA, indent=2)
    )


SYSTEM_PROMPT = (
    "You are a senior SEO copywriter working inside CortexViral, an AI "
    "Marketing Operating System. Your pages must rank for the platform "
    "keyword, sound like they were written by an operator who actually "
    "uses that platform, and convert. Return STRICT JSON only. No prose "
    "outside the JSON. No markdown fences."
)


async def _generate_one(spec: dict) -> dict:
    from cortex.llm_provider import cortex_chat

    user_text = _build_prompt(spec)
    logger.info("→ generating /%s …", spec["slug"])
    text, label = await cortex_chat(
        system=SYSTEM_PROMPT,
        user_text=user_text,
        session_id=f"platform-{spec['slug']}",
        user_id="seo-gen",
        prefer="claude",
        json_mode=True,
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        data = json.loads(repair_json(text))

    data["__meta__"] = {
        "slug":       spec["slug"],
        "title":      spec["title"],
        "meta":       spec["meta"],
        "h1_lead":    spec["h1_lead"],
        "h1_accent":  spec["h1_accent"],
        "kicker":     spec["kicker"],
        "primary_kw": spec["primary_kw"],
        "platform":   spec["platform"],
        "generated_by": label,
    }
    body_words = sum(len((s.get("body") or "").split())
                      for s in (data.get("sections") or []))
    logger.info("   slug=/%s · model=%s · body=%d words · sections=%d · faq=%d",
                spec["slug"], label, body_words,
                len(data.get("sections") or []),
                len(data.get("faq") or []))
    return data


async def main():
    for spec in SPECS:
        out_file = OUT_DIR / f"{spec['slug']}.json"
        if os.environ.get("SEO_SKIP_EXISTING") == "1" and out_file.exists():
            logger.info("⊘ skipping /%s (exists, SEO_SKIP_EXISTING=1)", spec["slug"])
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
