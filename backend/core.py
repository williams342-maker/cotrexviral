"""Shared core: env, Mongo client, logger, app + router."""
from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --- Mongo ---
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# --- Env ---
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
]
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://cortexviral.com")

# LinkedIn OAuth (filled by user after registering a LinkedIn Developer app)
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

# TikTok OAuth (filled by user after registering a TikTok Developer app —
# note: TikTok uses 'client_key' instead of 'client_id')
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
# Optional: override the OAuth redirect URI (e.g. for preview-pod testing).
# When set, it MUST exactly match one of the redirect URIs registered in the
# TikTok app. When empty, we derive it from PUBLIC_SITE_URL.
TIKTOK_REDIRECT_URI_OVERRIDE = os.environ.get("TIKTOK_REDIRECT_URI", "")

# Meta OAuth (shared app for Facebook Pages + Instagram Graph API).
# Register at https://developers.facebook.com → "Add Facebook Login" + "Add
# Instagram Platform". Use the SAME app for both (Instagram Business Login
# is layered on top of Facebook Login).
META_APP_ID = os.environ.get("META_APP_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v22.0")
# Optional override (same purpose as the TikTok one — useful for preview pods).
META_REDIRECT_URI_OVERRIDE = os.environ.get("META_REDIRECT_URI", "")

# Pinterest OAuth (v5 API). Register at https://developers.pinterest.com.
# Trial access works for OAuth + reading boards; Pin creation may be
# rate-limited until you upgrade to Standard access (free, manual review).
PINTEREST_APP_ID = os.environ.get("PINTEREST_APP_ID", "")
PINTEREST_APP_SECRET = os.environ.get("PINTEREST_APP_SECRET", "")
PINTEREST_REDIRECT_URI_OVERRIDE = os.environ.get("PINTEREST_REDIRECT_URI", "")
# Set to https://api-sandbox.pinterest.com to test against Pinterest's sandbox
# without affecting real boards. Defaults to production v5 API.
PINTEREST_API_BASE = os.environ.get("PINTEREST_API_BASE", "https://api.pinterest.com")

# Phase 4 — strict normalized reads.
# When True, the content_layer read helpers DROP the lenient fallback to
# `db.posts` for un-mirrored stragglers. Flip this to "true" after the
# admin overview `/admin/content-layer/health` shows zero drift sustained
# for a week. Default False so existing prod environments behave like
# Phase 3 until the operator explicitly opts in.
STRICT_NORMALIZED_READS = os.environ.get("STRICT_NORMALIZED_READS", "false").lower() == "true"

# Stripe billing
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
# When True (default), the webhook REQUIRES a valid signature. Set to "false"
# only in local dev where you're using the Stripe CLI without signing.
STRIPE_WEBHOOK_STRICT = os.environ.get("STRIPE_WEBHOOK_STRICT", "true").lower() != "false"

# Mailgun transactional email
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN", "")
MAILGUN_BASE_URL = os.environ.get("MAILGUN_BASE_URL", "https://api.mailgun.net")
MAILGUN_FROM = os.environ.get("MAILGUN_FROM", "")

# Mailtrap (primary; Mailgun is the fallback)
MAILTRAP_TOKEN = os.environ.get("MAILTRAP_TOKEN", "")
MAILTRAP_FROM = os.environ.get("MAILTRAP_FROM", "")
MAILTRAP_API_URL = os.environ.get("MAILTRAP_API_URL", "https://send.api.mailtrap.io/api/send")

# Lead-notification recipients (comma-separated emails)
LEADS_NOTIFY_EMAILS = [
    e.strip() for e in os.environ.get("LEADS_NOTIFY_EMAILS", "").split(",") if e.strip()
]

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("automatex")

# --- FastAPI app + /api router ---
# Note: do NOT include the router here. routes/ modules attach to `api`,
# then server.py calls app.include_router(api) once everything is loaded.
app = FastAPI(title="Automatex API")
api = APIRouter(prefix="/api")
