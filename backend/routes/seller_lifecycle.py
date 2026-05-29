"""Phase 3 — Autonomous Onboarding + Retention monitoring.

When an `interested` seller accepts (event=interested), the operator can
trigger autonomous onboarding. The onboarding pipeline runs these steps:
  1. create_account     — provision a CraftersMarket account
  2. create_storefront  — generate brand/colors/tagline
  3. import_products    — pull catalog from source (Etsy/Shopify shop URL)
  4. generate_seo       — title + description + meta tags for each product
  5. send_welcome       — kick off the welcome email/DM drip

Each step writes to `seller_onboardings.steps[]` so the UI can render a
checklist with timestamps + statuses. The pipeline is best-effort — failed
steps don't block subsequent steps from running.

Retention monitor (cron, every 6h): scans `active` sellers for
inactivity / declining performance, flags churn-risk leads back to
`unresponsive` and emits a HITL-inbox alert so the operator can launch
a recovery sequence.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)


ONBOARDING_STEPS = (
    "create_account",
    "create_storefront",
    "import_products",
    "generate_seo",
    "send_welcome",
)


# ---------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------
class OnboardingStart(BaseModel):
    lead_id: str


# ---------------------------------------------------------------------
# Onboarding pipeline (deterministic stubs — the real CraftersMarket API
# calls plug in here once the marketplace backend exposes them).
# ---------------------------------------------------------------------
async def _run_onboarding_steps(lead: dict) -> List[dict]:
    """Execute each onboarding step. Returns a list of step results that
    the caller persists onto the seller_onboardings doc."""
    results = []
    business = lead.get("business_name") or "Seller"
    niche = lead.get("niche") or "general"

    # 1. create_account
    results.append({
        "step":       "create_account",
        "status":     "ok",
        "detail":     f"Provisioned account for {business}",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    })

    # 2. create_storefront
    slug = "".join(c if c.isalnum() else "-" for c in business.lower()).strip("-") or uuid.uuid4().hex[:8]
    results.append({
        "step":       "create_storefront",
        "status":     "ok",
        "detail":     f"Storefront craftersmarket.com/shops/{slug} created",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "storefront_url": f"https://craftersmarket.example.com/shops/{slug}",
    })

    # 3. import_products — stub: copy product_categories into N placeholder products
    cats = lead.get("product_categories") or [niche]
    products = [{"sku": f"{slug}-{i+1}", "title": f"{cats[i % len(cats)].title()} item #{i+1}"}
                for i in range(min(8, len(cats) * 2))]
    results.append({
        "step":       "import_products",
        "status":     "ok",
        "detail":     f"Imported {len(products)} product placeholders",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len(products),
    })

    # 4. generate_seo — stub
    results.append({
        "step":       "generate_seo",
        "status":     "ok",
        "detail":     f"SEO metadata generated for {len(products)} products",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    })

    # 5. send_welcome
    results.append({
        "step":       "send_welcome",
        "status":     "ok",
        "detail":     "Welcome email + 3-step drip scheduled (D+1, D+3, D+7)",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    })

    return results


@api.post("/seller-onboarding/start")
async def start_onboarding(payload: OnboardingStart, request: Request):
    """Kick off autonomous onboarding for an interested lead. Idempotent —
    re-invoking on a seller already in 'active' state returns the existing
    onboarding record without re-running steps."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one({"id": payload.lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")

    # Idempotent re-run — if onboarding already ran for this lead, return
    # the existing record without re-validating the stage (the stage flip
    # to 'active' would otherwise block the second call).
    existing = await db.seller_onboardings.find_one(
        {"lead_id": payload.lead_id, "user_id": user.user_id})
    if existing and existing.get("status") == "complete":
        return {"onboarding_id": existing["id"],
                "lead_id": payload.lead_id,
                "status": "complete",
                "steps": existing.get("steps", []),
                "reused": True}

    if lead["stage"] not in ("interested", "outreached", "qualified"):
        raise HTTPException(400,
            f"Cannot onboard lead in stage '{lead['stage']}'. "
            f"Lead must be at least qualified."
        )

    # Flip to onboarding stage first so the UI updates immediately.
    now = datetime.now(timezone.utc)
    await db.seller_leads.update_one(
        {"id": payload.lead_id},
        {"$set": {"stage": "onboarding", "onboarded_at": now, "updated_at": now}},
    )

    steps = await _run_onboarding_steps(lead)
    all_ok = all(s["status"] == "ok" for s in steps)
    record = {
        "id":         uuid.uuid4().hex,
        "user_id":    user.user_id,
        "lead_id":    payload.lead_id,
        "mission_id": lead.get("mission_id"),
        "status":     "complete" if all_ok else "partial",
        "steps":      steps,
        "started_at": now,
        "completed_at": datetime.now(timezone.utc) if all_ok else None,
    }
    await db.seller_onboardings.insert_one(record)

    # Flip to active if all steps OK; otherwise leave at onboarding.
    if all_ok:
        await db.seller_leads.update_one(
            {"id": payload.lead_id},
            {"$set": {"stage": "active", "updated_at": datetime.now(timezone.utc)}},
        )

    out = {k: v for k, v in record.items() if k != "_id"}
    for k in ("started_at", "completed_at"):
        if isinstance(out.get(k), datetime):
            out[k] = out[k].isoformat()
    return out


@api.get("/seller-onboarding/{lead_id}")
async def get_onboarding(lead_id: str, request: Request):
    user = await get_current_user(request)
    rec = await db.seller_onboardings.find_one(
        {"lead_id": lead_id, "user_id": user.user_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "No onboarding record for this lead")
    for k in ("started_at", "completed_at"):
        if isinstance(rec.get(k), datetime):
            rec[k] = rec[k].isoformat()
    return rec


# ---------------------------------------------------------------------
# Retention monitor — cron job
# ---------------------------------------------------------------------
INACTIVITY_DAYS = 30
CHURN_RISK_DAYS = 60


async def scan_retention_signals() -> dict:
    """Per-user scan: for every `active` seller, evaluate inactivity +
    declining-performance heuristics. Tag at-risk sellers + emit a
    retention alert into the existing HITL inbox.

    Phase 3 heuristics (stub-friendly):
      • If last activity > 30 days → flag 'inactive'
      • If last activity > 60 days → flip stage to 'unresponsive' (churn-risk)

    Returns a summary dict for logging."""
    cutoff_inactive = datetime.now(timezone.utc) - timedelta(days=INACTIVITY_DAYS)
    cutoff_churn    = datetime.now(timezone.utc) - timedelta(days=CHURN_RISK_DAYS)

    flagged_inactive = 0
    flagged_churn    = 0

    cursor = db.seller_leads.find({"stage": "active"})
    async for lead in cursor:
        # Heuristic: use `updated_at` as the freshness proxy until we wire
        # real activity signals (listings created, sales). When this lands
        # the field can become e.g. `last_sale_at`.
        ts = lead.get("updated_at") or lead.get("onboarded_at") or lead.get("created_at")
        if not isinstance(ts, datetime):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff_churn:
            await db.seller_leads.update_one(
                {"id": lead["id"]},
                {"$set": {"stage": "churned", "updated_at": datetime.now(timezone.utc)}},
            )
            flagged_churn += 1
            # Persist a retention alert
            await db.retention_alerts.insert_one({
                "id":         uuid.uuid4().hex,
                "user_id":    lead["user_id"],
                "lead_id":    lead["id"],
                "severity":   "churn",
                "reason":     f"No activity > {CHURN_RISK_DAYS} days",
                "created_at": datetime.now(timezone.utc),
            })
        elif ts < cutoff_inactive:
            await db.retention_alerts.insert_one({
                "id":         uuid.uuid4().hex,
                "user_id":    lead["user_id"],
                "lead_id":    lead["id"],
                "severity":   "inactive",
                "reason":     f"No activity > {INACTIVITY_DAYS} days",
                "created_at": datetime.now(timezone.utc),
            })
            flagged_inactive += 1

    return {"flagged_inactive": flagged_inactive, "flagged_churn": flagged_churn,
            "scanned_at": datetime.now(timezone.utc).isoformat()}


@api.post("/seller-retention/scan")
async def run_retention_scan(request: Request):
    """Manual trigger — same scan as the cron job."""
    await get_current_user(request)
    summary = await scan_retention_signals()
    return summary


@api.get("/seller-retention/alerts")
async def list_alerts(request: Request, limit: int = 50, mission_id: Optional[str] = None):
    user = await get_current_user(request)
    q: dict = {"user_id": user.user_id}
    cursor = db.retention_alerts.find(q, {"_id": 0}).sort("created_at", -1).limit(min(200, max(1, limit)))
    rows = await cursor.to_list(length=limit)
    # Filter by mission_id by joining through seller_leads (cheap because alerts are small).
    if mission_id:
        lead_ids = set()
        async for ld in db.seller_leads.find(
            {"user_id": user.user_id, "mission_id": mission_id},
            {"_id": 0, "id": 1},
        ):
            lead_ids.add(ld["id"])
        rows = [r for r in rows if r["lead_id"] in lead_ids]
    for r in rows:
        v = r.get("created_at")
        if isinstance(v, datetime):
            r["created_at"] = v.isoformat()
    return {"alerts": rows, "count": len(rows)}
