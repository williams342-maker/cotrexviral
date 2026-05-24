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

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("automatex")

# --- FastAPI app + /api router ---
# Note: do NOT include the router here. routes/ modules attach to `api`,
# then server.py calls app.include_router(api) once everything is loaded.
app = FastAPI(title="Automatex API")
api = APIRouter(prefix="/api")
