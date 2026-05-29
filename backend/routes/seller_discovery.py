"""Discovery Scout — surfaces seller candidates for a Mission.

Each source is a pluggable adapter. The Scout dispatches the mission's
niche+location query at every enabled source, dedupes by (source,
external_id), and writes new rows to `seller_leads` at stage='discovered'.

Source adapters (Phase 1)
~~~~~~~~~~~~~~~~~~~~~~~~~
- google_search   — uses the existing internal web fetch helper.
- etsy / shopify / instagram / pinterest / facebook / tiktok / reddit /
  google_maps    — return DETERMINISTIC FIXTURE SEEDS for now so the rest
                   of the pipeline (qualification, outreach, onboarding)
                   can be built + tested end-to-end without external API
                   credentials. Each fixture is clearly tagged so it can
                   be swapped to a live adapter without schema change.

Each adapter returns a list of `SellerLeadCreate`-compatible dicts.

The Scout is exposed via:
   POST /api/seller-discovery/run   — manual trigger (also called by Cortex)
   GET  /api/seller-discovery/sources — adapter health
"""
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Callable, Awaitable

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user
from routes.seller_leads import SOURCES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------
class DiscoveryRun(BaseModel):
    mission_id:   str
    niche:        str                  # "woodworking", "laser engraving"
    location:     Optional[str] = None
    sources:      Optional[List[str]] = None  # default = all
    max_per_source: int = 25


# ---------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------
async def _adapter_google_search(niche: str, location: Optional[str],
                                  limit: int) -> List[dict]:
    """Phase 1 stub: returns deterministic fixtures derived from the
    niche string. Live integration plugs in the existing web_search_tool
    later; the contract (return shape) is what callers depend on."""
    # Deterministic count based on niche so repeated runs are stable
    # for tests AND the UI shows the right number of cards.
    digest = int(hashlib.md5(niche.encode()).hexdigest(), 16)
    n = min(limit, max(5, digest % 12 + 4))
    out = []
    for i in range(n):
        biz = f"{niche.title()} Co. #{i + 1}"
        out.append({
            "business_name":      biz,
            "website":            f"https://{re.sub(r'[^a-z0-9]+', '-', niche.lower()).strip('-')}-co-{i+1}.example.com",
            "source":             "google_search",
            "platform":           "website",
            "niche":              niche,
            "location":           location,
            "socials":            {"instagram": f"@{niche.replace(' ', '')}_{i+1}"},
            "product_categories": [niche],
            "estimated_activity": ["high", "medium", "low"][i % 3],
            "raw_signal":         {"rank": i + 1, "query": niche, "source": "google_search_fixture"},
        })
    return out


def _make_marketplace_adapter(source: str, biz_suffix: str):
    """Factory — generates a niche-keyed fixture adapter for marketplace
    sources (Etsy, Shopify, Instagram, etc.). All marketplace adapters
    follow the same shape so the rest of the pipeline doesn't care which
    source produced a lead."""
    async def adapter(niche: str, location: Optional[str], limit: int) -> List[dict]:
        digest = int(hashlib.md5(f"{source}:{niche}".encode()).hexdigest(), 16)
        n = min(limit, max(3, digest % 10 + 3))
        rows = []
        for i in range(n):
            slug = re.sub(r"[^a-z0-9]+", "-", niche.lower()).strip("-")
            biz = f"{niche.title()} {biz_suffix} #{i + 1}"
            rows.append({
                "business_name":     biz,
                "website":           f"https://{source}.example.com/shop/{slug}-{i+1}",
                "source":            source,
                "platform":          source,
                "niche":             niche,
                "location":          location,
                "socials":           {source: f"@{slug}_{source}_{i+1}"},
                "product_categories": [niche, f"{niche} accessories"],
                "estimated_activity": ["high", "medium", "low"][(i + digest) % 3],
                "raw_signal":        {"index": i, "source_fixture": True, "source": source},
            })
        return rows
    return adapter


# Source registry — Phase 1 fixtures. Each adapter has the same signature
# so we can swap fixtures for live HTTP later without changing the loop.
ADAPTERS: dict[str, Callable[[str, Optional[str], int], Awaitable[List[dict]]]] = {
    "google_search": _adapter_google_search,
    "etsy":         _make_marketplace_adapter("etsy", "Studio"),
    "shopify":      _make_marketplace_adapter("shopify", "Shop"),
    "instagram":    _make_marketplace_adapter("instagram", "Creator"),
    "pinterest":    _make_marketplace_adapter("pinterest", "Curator"),
    "facebook":     _make_marketplace_adapter("facebook", "Page"),
    "tiktok":       _make_marketplace_adapter("tiktok", "Maker"),
    "reddit":       _make_marketplace_adapter("reddit", "Community"),
    "google_maps":  _make_marketplace_adapter("google_maps", "Local Biz"),
}


# ---------------------------------------------------------------------
# Helpers — dedupe + persist
# ---------------------------------------------------------------------
async def _persist_leads(user_id: str, mission_id: str,
                          rows: List[dict]) -> List[str]:
    """Insert leads, deduping by (mission_id, business_name, source).
    Returns the list of inserted lead IDs."""
    import uuid
    inserted = []
    now = datetime.now(timezone.utc)
    for r in rows:
        existing = await db.seller_leads.find_one({
            "user_id":       user_id,
            "mission_id":    mission_id,
            "business_name": r["business_name"],
            "source":        r["source"],
        })
        if existing:
            continue
        doc = {
            "id":                 uuid.uuid4().hex,
            "user_id":            user_id,
            "mission_id":         mission_id,
            "business_name":      r["business_name"],
            "website":            r.get("website"),
            "source":             r["source"],
            "platform":           r.get("platform"),
            "niche":              r.get("niche"),
            "location":           r.get("location"),
            "socials":            r.get("socials") or {},
            "product_categories": r.get("product_categories") or [],
            "estimated_activity": r.get("estimated_activity"),
            "raw_signal":         r.get("raw_signal") or {},
            "stage":              "discovered",
            "seller_score":       None,
            "score_breakdown":    None,
            "qualified_at":       None,
            "outreached_at":      None,
            "responded_at":       None,
            "onboarded_at":       None,
            "created_at":         now,
            "updated_at":         now,
            "discovered_at":      now,
        }
        await db.seller_leads.insert_one(doc)
        inserted.append(doc["id"])
    return inserted


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@api.post("/seller-discovery/run")
async def run_discovery(payload: DiscoveryRun, request: Request):
    """Trigger a Discovery pass across the requested sources for a Mission.

    Returns counts per-source so the operator can see which adapters had
    coverage. The returned `lead_ids` are the NEW rows; existing rows that
    deduped get counted in `skipped_existing` but not returned.
    """
    user = await get_current_user(request)
    mission = await db.missions.find_one(
        {"id": payload.mission_id, "user_id": user.user_id})
    if not mission:
        raise HTTPException(404, "Mission not found")

    sources = payload.sources or list(ADAPTERS.keys())
    for s in sources:
        if s not in ADAPTERS:
            raise HTTPException(400, f"Unknown source: {s}")

    # Run all adapters in parallel — each is cheap (fixtures) but we want
    # the live HTTP integration later to also fan out.
    results = await asyncio.gather(
        *[ADAPTERS[s](payload.niche, payload.location, payload.max_per_source)
          for s in sources],
        return_exceptions=True,
    )

    per_source: dict = {}
    all_rows: List[dict] = []
    for s, res in zip(sources, results):
        if isinstance(res, Exception):
            logger.warning("discovery: adapter %s raised %s", s, res)
            per_source[s] = {"discovered": 0, "error": str(res)}
            continue
        per_source[s] = {"discovered": len(res)}
        all_rows.extend(res)

    inserted_ids = await _persist_leads(user.user_id, payload.mission_id, all_rows)

    # Audit log
    await db.discovery_runs.insert_one({
        "id":          __import__("uuid").uuid4().hex,
        "user_id":     user.user_id,
        "mission_id":  payload.mission_id,
        "niche":       payload.niche,
        "location":    payload.location,
        "sources":     sources,
        "per_source":  per_source,
        "inserted":    len(inserted_ids),
        "candidates":  len(all_rows),
        "created_at":  datetime.now(timezone.utc),
    })

    return {
        "mission_id":      payload.mission_id,
        "sources":         sources,
        "candidates":      len(all_rows),
        "inserted":        len(inserted_ids),
        "skipped_existing": len(all_rows) - len(inserted_ids),
        "per_source":      per_source,
        "lead_ids":        inserted_ids,
    }


@api.get("/seller-discovery/sources")
async def list_sources(request: Request):
    """Adapter registry — used by the Discovery UI to render toggles."""
    await get_current_user(request)
    return {"sources": list(ADAPTERS.keys())}


@api.get("/seller-discovery/runs/{mission_id}")
async def list_runs(mission_id: str, request: Request, limit: int = 20):
    user = await get_current_user(request)
    cursor = db.discovery_runs.find(
        {"user_id": user.user_id, "mission_id": mission_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(min(100, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    return {"runs": rows, "count": len(rows)}
