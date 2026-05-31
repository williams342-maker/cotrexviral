"""SEO Sprint v1 · Round 4 — generator for /insights blog content.

Produces 10 long-form SEO articles. Each article maps 1-to-1 with the
spec's seed-list and is keyword-matched to either a Round 2/3 landing
page (so the article becomes a high-funnel feeder) or to a category we
own conceptually.

Output:
    /app/frontend/src/pages/insights/content/<slug>.json

Word target: ~1,400–1,800 body words per article. Articles render via
`InsightsArticleTemplate.jsx` with `Article` + `Person` (author) +
`BreadcrumbList` + `FAQPage` schemas.

Run:
    cd /app/backend && python -m scripts.generate_insights
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("insights")


OUT_DIR = Path("/app/frontend/src/pages/insights/content")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# Categories used for the index-page filter chips.
CATEGORIES = {
    "playbooks":   "Playbooks",
    "strategy":    "Strategy",
    "operations":  "Operations",
    "automation":  "Automation",
    "intelligence":"Intelligence",
}


# Authors keyed by `slug` — schema.org/Person uses {name, jobTitle, url, image, sameAs}.
AUTHORS = {
    "cortex_team": {
        "name": "The CortexViral Team",
        "jobTitle": "Marketing OS Engineers",
        "url": "https://cortexviral.com/agents",
    },
    "scout":       {"name": "Scout Agent", "jobTitle": "Lead Researcher", "url": "https://cortexviral.com/agents"},
    "intel":       {"name": "Intelligence Agent", "jobTitle": "Competitive Strategist", "url": "https://cortexviral.com/agents"},
    "operator":    {"name": "Operator Agent", "jobTitle": "Execution Lead", "url": "https://cortexviral.com/agents"},
    "creator":     {"name": "Creator Agent", "jobTitle": "Content Strategist", "url": "https://cortexviral.com/agents"},
}


# 10 seed articles. Each entry is the prompt context for one Claude call.
SEED = [
    {
        "slug": "how-to-recruit-etsy-sellers",
        "title": "How to Recruit Etsy Sellers (Without Spamming Their Inbox)",
        "dek": "A founder-level playbook for finding, qualifying, and earning the trust of high-fit Etsy sellers — with the exact filters and outreach patterns we use inside CortexViral.",
        "category": "playbooks",
        "author": "scout",
        "primary_kw": "Recruit Etsy sellers",
        "related_kws": ["Etsy seller outreach", "marketplace recruiting", "indie maker outreach"],
        "related_landing": "seller-acquisition",
        "angle": "Concrete tactics for marketplace teams running seller acquisition. Cover sourcing (Etsy categories, review counts, badge filters), qualification (3-band confidence model), and outreach (referencing real listings, never templated copy).",
    },
    {
        "slug": "ai-marketing-operating-systems-explained",
        "title": "AI Marketing Operating Systems, Explained",
        "dek": "What an AI Marketing OS actually is, how it differs from a 'tool stack', and why category leaders are consolidating onto one orchestrated platform.",
        "category": "strategy",
        "author": "cortex_team",
        "primary_kw": "AI Marketing Operating System",
        "related_kws": ["Marketing OS", "Marketing automation platform"],
        "related_landing": "marketing-os",
        "angle": "Define the category. Contrast OS-thinking (orchestrator + agent teams + missions) vs SaaS-tool-thinking (point tools you have to glue). Reference the Cortex orchestrator, autonomy levels L0-L5, and mission-driven execution.",
    },
    {
        "slug": "reddit-marketing-automation",
        "title": "Reddit Marketing Automation That Doesn't Get You Banned",
        "dek": "Most automation tools get throttled or banned on Reddit within a week. Here's how to use AI on Reddit while respecting every subreddit's rules.",
        "category": "automation",
        "author": "operator",
        "primary_kw": "Reddit marketing automation",
        "related_kws": ["Reddit marketing AI", "subreddit growth", "AI Reddit posts"],
        "related_landing": "reddit-marketing-ai",
        "angle": "Walk through Reddit-safe AI workflows: AI for drafting + human approval, the 9:1 value-to-promo rule, subreddit-rule scanning before posting, karma + account-age gating, comment-timing optimization. Reference Reddit Marketing AI page.",
    },
    {
        "slug": "marketplace-growth-strategies",
        "title": "Marketplace Growth Strategies for the Next Two Years",
        "dek": "The supply-side flywheels that defensible marketplaces run, and how AI is changing the seller-acquisition math.",
        "category": "strategy",
        "author": "intel",
        "primary_kw": "Marketplace growth strategies",
        "related_kws": ["Marketplace seller acquisition", "two-sided marketplaces"],
        "related_landing": "seller-acquisition",
        "angle": "Strategic angle: supply curation > supply abundance, vertical specialization, AI-powered onboarding, retention-driven recruiting. Real numbers from Etsy / TaskRabbit / Faire-style marketplaces.",
    },
    {
        "slug": "campaign-planning-frameworks",
        "title": "Campaign Planning Frameworks That Actually Ship",
        "dek": "Why most campaign plans never launch, and the lightweight frameworks we use inside CortexViral to compress 'brief to live' from three weeks to eleven minutes.",
        "category": "operations",
        "author": "creator",
        "primary_kw": "Campaign planning framework",
        "related_kws": ["AI campaign generator", "Marketing campaign planning"],
        "related_landing": "ai-campaign-generator",
        "angle": "Practical frameworks: the 1-page creative brief, the channel-fit matrix, the auto-schedule heuristic. Mention the Autonomous Campaign Builder and how Cortex picks optimal posting windows.",
    },
    {
        "slug": "ai-competitive-intelligence",
        "title": "AI Competitive Intelligence for Marketing Teams",
        "dek": "How to run a weekly competitor sweep with AI — what to track, what to ignore, and how to convert findings into next-week actions.",
        "category": "intelligence",
        "author": "intel",
        "primary_kw": "AI competitive intelligence",
        "related_kws": ["Competitor analysis AI", "Marketing competitive intelligence"],
        "related_landing": "competitor-analysis",
        "angle": "The Intelligence team's actual playbook: storefront crawl → assortment, pricing, engagement scoring → 1-page brief with 3 concrete actions. Why most competitor dashboards rot.",
    },
    {
        "slug": "social-media-automation-guide",
        "title": "The Social Media Automation Guide (2026 Edition)",
        "dek": "What to automate, what to keep human-in-the-loop, and how to schedule across Instagram, TikTok, LinkedIn, YouTube, Reddit, and Facebook from one queue.",
        "category": "automation",
        "author": "operator",
        "primary_kw": "Social media automation",
        "related_kws": ["Multi-channel social automation", "AI social publishing"],
        "related_landing": "marketing-os",
        "angle": "End-to-end view of multi-platform automation. Cover platform-specific quirks (algo behavior), bulk publishing as drafts, auto-scheduling on heuristic optimal times, and the 3-channel rule for accounts under 10k followers.",
    },
    {
        "slug": "asset-analysis-for-marketers",
        "title": "Asset Analysis for Marketers: Turning Decks into Campaigns",
        "dek": "Most marketing teams sit on folders of PDFs, decks, and demo videos that never become content. Here's how AI converts them into campaign-ready briefs in seconds.",
        "category": "operations",
        "author": "creator",
        "primary_kw": "Marketing asset analysis",
        "related_kws": ["PDF marketing analysis", "Creative analysis AI"],
        "related_landing": "asset-analysis",
        "angle": "Walk through the Asset Upload Center: PDF/PPTX/Video/URL inputs, Whisper transcription for video, hero-slide extraction for PPTX, intelligence layer that outputs audience / positioning / hook angles, then one-click campaign generation.",
    },
    {
        "slug": "multi-channel-campaign-management",
        "title": "Multi-Channel Campaign Management Without the Spreadsheets",
        "dek": "Coordinating a launch across six channels used to mean a 200-row tracking sheet. With an AI Marketing OS, every channel ships from one mission card.",
        "category": "operations",
        "author": "operator",
        "primary_kw": "Multi-channel campaign management",
        "related_kws": ["Cross-channel marketing", "Campaign coordination"],
        "related_landing": "ai-campaign-generator",
        "angle": "How CortexViral's Mission model replaces the spreadsheet: 1 brief → composed across 6+ channels → scheduled on per-platform optimal windows → tracked in one timeline. Reference auto-scheduling on FYP-style windows.",
    },
    {
        "slug": "seller-acquisition-playbook",
        "title": "The Seller Acquisition Playbook: Discovery to Onboarded",
        "dek": "A step-by-step playbook for running seller acquisition like a sales motion — sourcing, qualification, outreach, and onboarding — using AI to compress the cycle by 5x.",
        "category": "playbooks",
        "author": "scout",
        "primary_kw": "Seller acquisition playbook",
        "related_kws": ["Marketplace seller acquisition", "AI seller outreach"],
        "related_landing": "seller-acquisition",
        "angle": "Full-funnel seller acquisition: ICP definition, source list (Etsy, Shopify storefronts, Instagram), 3-band confidence scoring, review queue (human approval before send), Prospect Intelligence Cards, lifecycle tracking. Reference the new Recommended Action surfacing.",
    },
]


# JSON content schema each prompt must emit.
SCHEMA = {
    "lede": "single-paragraph lede that hooks the reader — 40–70 words",
    "key_takeaways": "array of 4 punchy single-sentence takeaways the reader gets — 10–18 words each",
    "sections": (
        "array of 6–7 long-form sections. Each: "
        "{heading: 4–10 words, body: 200–300 words of confident, founder-level "
        " prose with concrete numbers, anecdotes, and platform-specific "
        " mechanics — NO em-dashes in prose; "
        " bullets: optional 3–5 punchy bullets}"
    ),
    "pull_quote": "1 standout pull-quote — 12–25 words — that captures the article's core thesis",
    "related_articles": (
        "array of EXACTLY 3 of the OTHER 9 slugs to link to. "
        "Each: {slug, title (use the spec's title), blurb 14–22 words}"
    ),
    "related_landing_blurb": (
        "20–30 word teaser that contextually links to the related landing "
        "page in the article body (do not include a URL — the template "
        "wraps it as a link)."
    ),
    "faq": (
        "array of 4 questions tightly themed around the primary keyword. "
        "Each: {q (8–18 words), a (60–110 words). Answers must stand alone — "
        "they get pulled into Schema.org FAQPage.}"
    ),
    "final_takeaway": "60–110 word closing paragraph that reinforces the thesis and points forward",
}


SLUG_TITLES = {a["slug"]: a["title"] for a in SEED}


def _build_prompt(spec: dict) -> str:
    sibling_options = [
        f"  - {s} → {SLUG_TITLES[s]}"
        for s in SLUG_TITLES if s != spec["slug"]
    ]
    return (
        f"Write the long-form content for the CortexViral /insights "
        f"article at /insights/{spec['slug']}.\n\n"
        f"CONTEXT\n"
        f"-------\n"
        f"CortexViral is an AI Marketing Operating System. The platform "
        f"has a Cortex orchestrator (Claude/GPT via Emergent), Mission-"
        f"driven execution, agent teams (Scout, Creator, Operator, "
        f"Intelligence), an Asset Upload Center, an Autonomous Campaign "
        f"Builder, Direct Social Publishing with auto-scheduling, a "
        f"Seller Acquisition Engine with 3-band confidence scoring + "
        f"Review Queue + Prospect Intelligence Cards, and autonomy "
        f"levels L0–L5.\n\n"
        f"ARTICLE\n"
        f"-------\n"
        f"title: {spec['title']}\n"
        f"dek (subtitle, do not regenerate): {spec['dek']}\n"
        f"primary keyword: {spec['primary_kw']}\n"
        f"related keywords: {', '.join(spec['related_kws'])}\n"
        f"category: {spec['category']}\n"
        f"angle: {spec['angle']}\n"
        f"this article should naturally cross-link to "
        f"/{spec['related_landing']}\n\n"
        f"WORD BUDGET\n"
        f"Total long-form body (sum of all section bodies) should land "
        f"between 1300 and 1800 words.\n\n"
        f"RELATED-ARTICLE OPTIONS — pick exactly 3 of these (other 9 slugs):\n"
        + "\n".join(sibling_options) +
        f"\n\nVOICE\n"
        f"Confident, founder-led, no fluff. Concrete numbers. Real "
        f"examples. Sentences mostly 10–22 words. NO em-dashes in prose "
        f"(use a comma or a period). NO 'In conclusion'. NO 'fast-paced "
        f"world'. Address the reader as 'you'. Reference CortexViral "
        f"by name 1–3 times throughout, naturally.\n\n"
        f"OUTPUT FORMAT\n"
        f"-------------\n"
        f"Return STRICT JSON matching this schema:\n\n"
        + json.dumps(SCHEMA, indent=2)
    )


SYSTEM_PROMPT = (
    "You are a senior marketing editor at CortexViral — an AI Marketing "
    "Operating System. Your articles must rank for the primary keyword, "
    "convert curious readers into platform trials, and read like an "
    "operator who has actually run the playbook. Return STRICT JSON "
    "only. No prose outside the JSON. No markdown fences."
)


async def _generate_one(spec: dict) -> dict:
    from cortex.llm_provider import cortex_chat

    user_text = _build_prompt(spec)
    logger.info("→ generating /insights/%s …", spec["slug"])
    text, label = await cortex_chat(
        system=SYSTEM_PROMPT,
        user_text=user_text,
        session_id=f"insights-{spec['slug']}",
        user_id="seo-gen",
        prefer="claude",
        json_mode=True,
    )
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        data = json.loads(repair_json(text))

    # Stamp metadata.
    data["__meta__"] = {
        "slug":              spec["slug"],
        "title":             spec["title"],
        "dek":               spec["dek"],
        "category":          spec["category"],
        "category_label":    CATEGORIES.get(spec["category"], spec["category"]),
        "author":            AUTHORS.get(spec["author"], AUTHORS["cortex_team"]),
        "primary_kw":        spec["primary_kw"],
        "related_landing":   spec["related_landing"],
        "published_at":      datetime.now(timezone.utc).isoformat(),
        "read_minutes":      _est_read_minutes(data),
        "generated_by":      label,
    }
    body_words = sum(len((s.get("body") or "").split())
                      for s in (data.get("sections") or []))
    logger.info("   slug=%s · model=%s · body=%d words · sections=%d",
                spec["slug"], label, body_words,
                len(data.get("sections") or []))
    return data


def _est_read_minutes(data: dict) -> int:
    words = sum(len((s.get("body") or "").split())
                for s in (data.get("sections") or []))
    return max(3, round(words / 230))


async def main():
    for spec in SEED:
        out_file = OUT_DIR / f"{spec['slug']}.json"
        if os.environ.get("SEO_SKIP_EXISTING") == "1" and out_file.exists():
            logger.info("⊘ skipping %s (SEO_SKIP_EXISTING=1)", spec["slug"])
            continue
        try:
            content = await _generate_one(spec)
        except Exception:
            logger.exception("✗ generation FAILED for %s", spec["slug"])
            continue
        out_file.write_text(json.dumps(content, indent=2, ensure_ascii=False))
        logger.info("✓ wrote %s", out_file)


if __name__ == "__main__":
    asyncio.run(main())
