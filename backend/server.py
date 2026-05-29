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
