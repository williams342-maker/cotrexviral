"""CortexViral / Automatex backend — application bootstrap.

The actual route logic lives in /app/backend/routes/*.py. This file just
imports the route modules (which register themselves on the shared `api`
router or `app` instance), includes the router, and configures middleware.

If you need to add a new domain, create routes/<name>.py and add it to the
import list below. No other change to server.py is required.
"""
from starlette.middleware.cors import CORSMiddleware

from core import app, api, client, logger  # noqa: F401  (logger imported for side-effect)

# Import each route module so its decorators register on the shared `api`/`app`.
# Order matters only for routes that hit `app` directly (sitemap, scheduler events).
from routes import (  # noqa: F401
    auth,
    leads,
    ai,
    channels,
    performance,
    activity,
    dashboard,
    support,
    admin,
    broadcasts,
    scheduler,   # registers @app.on_event startup/shutdown
    health,      # depends on routes.scheduler internals; import after it
    seo,         # registers @app.get on root paths (/sitemap.xml etc.)
    oauth_linkedin,  # LinkedIn OAuth + live posting
    oauth_tiktok,    # TikTok OAuth + Content Posting API
    billing,         # Stripe subscriptions + webhook
    trends,          # Live TikTok trending hashtag feed
    ab_lab,          # A/B Hook Lab — variant generation + scoring
    funnel,          # Marketing funnel analytics
    email,           # Mailgun transactional emails
    onboarding,      # New-user onboarding profile capture
    magic_link,      # Admin-create user + passwordless claim flow
    admin_settings,  # Master signup toggle + per-platform on/off
    admin_seller_os, # Admin · Seller-OS inspector + email-log viewer + test-send
    sendgrid_webhook, # SendGrid Event Webhook → seller_outreach_events bridge
    account,         # User self-serve account deletion (GDPR / Meta review)
    oauth_meta,      # Facebook + Instagram OAuth (shared Meta app)
    oauth_pinterest, # Pinterest API v5 OAuth + publish
    password_auth,   # Email + password login + reset (alongside Google Auth)
    agent_chat,      # In-dashboard per-agent chat (Nova/Sam/Kai/Angela)
    analytics,       # Per-post metrics refresh (Pinterest live; others TODO)
    memory,          # Vector memory system (brand profile, posts, agent context)
    approvals,       # Human-in-the-loop approval workflow
    trends_engine,   # Reddit + Google Trends → memory ingestion
    llm_spend,       # Estimated LLM cost tracking + admin spend dashboard
    auto_draft,      # Weekly Monday auto-draft from top trend signals
    campaigns,       # Campaigns — first-class container for multi-post goals
    feedback_loop,   # Self-improving loop: published metrics → memory rows
    marketing_os,    # Marketing OS — 5-role chain + Command Center dashboard
    realtime,        # WebSocket fanout: real-time HITL inbox
    perf_metrics,    # Performance metrics — time-series + rollup + attribution API
    content_layer_admin,  # Phase 3 — drift / mirror coverage health endpoint
    meta_deletion,   # Meta data-deletion-callback webhook + status page
    app_config,      # DB-backed runtime config (rotate keys without redeploy)
    agent_personas,  # Autonomous Growth Team — persona roster
    standups,        # Weekly Standup generator (Monday-morning artifact)
    listening,       # Social Listening Engine (Lyra's signals)
    growth_goals,    # Durable OKRs owned by Vera
    oauth_youtube,   # YouTube OAuth (Google) — channel upload + read scopes
    experiments,     # Head-to-head variant testing (Ori) — Phase 4 of Growth Team
    briefs,          # Atlas brief proposals + autopilot scanner — Phase 3 of Growth Team
    autonomy,        # Per-agent weekly budget caps — Phase 5 of Growth Team
    agent_messaging, # Agent ↔ Agent pub-sub bus — Phase 6 of Growth Team
    uploads,         # Compose video uploads (YouTube)
    digests,         # Sunday Week-in-Review digest
    metered_billing, # Cortex Autopilot SKU — metered Stripe billing on agent_usage_ledger
    missions,        # Mission-driven autonomous marketing OS
    teams,           # 4 agent-team façade endpoints (Scout/Creator/Operator/Intelligence)
    cortex,          # Master orchestrator — single entry-point for user goals
    cortex_console,  # AI Command Center — conversational chat + briefing + execute
    cortex_conversations,  # Multi-thread conversation history (list/get/new)
    cortex_memory,   # Hybrid memory (Mongo strategy + Qdrant semantic) + exec log
    cortex_plan_actions,  # Plan-card actions: cancel + email-to-inbox
    cortex_stream,   # SSE-streamed Cortex chat (phase events)
    cortex_active_missions,  # Active Mission Rail — live status per running mission
    cortex_analysis_jobs,    # Active Work rail — long-running analysis with job IDs
    cortex_recommendation_bridge,  # Proactive recommendation layer (finding → action)
    cortex_assets,          # Asset Upload Center (Phase A1 — upload + intel + review)
    cortex_creatives,       # Image Generation (Phase B — Gemini + OpenAI providers)
    cortex_optimization,     # OODA loop endpoints: status, log, run-now
    cortex_onboarding,       # AI-guided first-run onboarding mission (replaces tour)
    mission_loop,    # Event-driven relay: scout→creator→operator→intelligence
    seller_leads,        # Seller Acquisition OS — leads pipeline
    seller_discovery,    # Seller Acquisition OS — Discovery Scout
    seller_qualification, # Seller Acquisition OS — Qualification Engine
    seller_outreach,     # Seller Acquisition OS — Personalized Outreach Engine
    seller_lifecycle,    # Seller Acquisition OS — Onboarding + Retention monitor
    seller_offers,       # Seller Acquisition OS · Phase 4 — AI offer artifact generator
    seller_retention_intel,  # Seller Acquisition OS · Phase 8 — Churn-risk + workflows
)


# Wire the /api router after every route module has had a chance to attach.
app.include_router(api)


# Provision Stripe products on startup (idempotent — only creates missing ones).
@app.on_event("startup")
async def _provision_stripe():
    try:
        await billing.ensure_stripe_products()
    except Exception:
        logger.exception("Stripe product provisioning failed (continuing)")


# Run the data-model normalization migration on startup. Idempotent —
# `needs_migration()` is a cheap check; the heavy backfill only fires
# the first time a deploy lands on an un-migrated cluster.
@app.on_event("startup")
async def _run_normalize_migration():
    try:
        from migrations.normalize_001 import needs_migration, migrate_now
        if await needs_migration():
            logger.info("normalize_001: starting backfill on startup")
            result = await migrate_now()
            logger.info("normalize_001: backfill done — %s", result)
        else:
            logger.debug("normalize_001: no backfill needed")
    except Exception:
        logger.exception("normalize_001 migration failed (app still booting)")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Close the Mongo connection on shutdown. (Scheduler shuts itself down via
# its own @app.on_event("shutdown") in routes/scheduler.py.)
@app.on_event("shutdown")
async def close_mongo():
    client.close()
