"""Marketing-funnel analytics.

Funnel stages (last N days, default 30):
  1. Visitors — distinct (ip_hash, day) tuples that pinged /api/track/visit
  2. Signups  — new users created in window
  3. Activated — users who generated ≥1 AI piece in window (i.e. usage.<month>.ai_generations > 0)
  4. Paid     — users on a paid plan (starter / growth / agency / pro / scale)
                whose created_at falls in window

This is intentionally simple cohort-aware analytics, not a per-user attribution
graph. Good enough for a founder dashboard, fast to render, no extra deps.

Endpoints:
  POST /api/track/visit       (public, anonymous)
  GET  /api/admin/funnel       (admin)
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from pydantic import BaseModel

from core import db, api
from deps import require_admin


_PAID_PLANS = ["starter", "growth", "agency", "pro", "scale"]


def _client_ip(request: Request) -> str:
    """Resolve client IP behind proxies (Emergent ingress sets x-forwarded-for)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "0.0.0.0") or "0.0.0.0"


def _hash(s: str) -> str:
    """Short stable hash — used so we never persist raw IPs / UAs."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _is_bot(ua: str) -> bool:
    ua = (ua or "").lower()
    return any(p in ua for p in (
        "bot", "crawler", "spider", "slurp", "facebookexternalhit",
        "headlesschrome", "phantomjs", "googlebot", "bingbot",
    ))


class VisitPayload(BaseModel):
    path: Optional[str] = "/"
    referrer: Optional[str] = None


@api.post("/track/visit")
async def track_visit(payload: VisitPayload, request: Request):
    """Anonymous page-view ping. Skips bots. Fire-and-forget — never throws."""
    ua = request.headers.get("user-agent", "")
    if _is_bot(ua):
        return {"ok": True, "skipped": "bot"}

    ip = _client_ip(request)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "ip_hash": _hash(ip),
        "ua_hash": _hash(ua) if ua else "",
        "path": (payload.path or "/")[:200],
        "referrer": (payload.referrer or "")[:200],
        "day": today,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.pageviews.insert_one(doc)
    except Exception:
        # Never let analytics break the user's page load
        pass
    return {"ok": True}


@api.get("/admin/funnel")
async def admin_funnel(request: Request, days: int = 30):
    """Return funnel buckets + conversion rates for the last `days`."""
    await require_admin(request)
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # 1. Visitors — distinct (ip_hash, day) tuples in the window
    visitor_pipe = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {"_id": {"ip": "$ip_hash", "day": "$day"}}},
        {"$count": "n"},
    ]
    v_res = await db.pageviews.aggregate(visitor_pipe).to_list(length=1)
    visitors = v_res[0]["n"] if v_res else 0

    # Raw page views (informational — shown next to "unique")
    raw_views = await db.pageviews.count_documents({"created_at": {"$gte": since}})

    # 2. Signups — new users in window
    signups = await db.users.count_documents({"created_at": {"$gte": since}})

    # 3. Activated — users created in window who have ≥1 AI generation
    #    across any month bucket. Match the cohort: created in window AND has usage.
    activated_pipe = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$addFields": {
            "ai_total": {
                "$sum": {
                    "$map": {
                        "input": {"$objectToArray": {"$ifNull": ["$usage", {}]}},
                        "as": "m",
                        "in": {"$ifNull": ["$$m.v.ai_generations", 0]},
                    },
                },
            },
        }},
        {"$match": {"ai_total": {"$gt": 0}}},
        {"$count": "n"},
    ]
    a_res = await db.users.aggregate(activated_pipe).to_list(length=1)
    activated = a_res[0]["n"] if a_res else 0

    # 4. Paid — users on a paid plan, created in window
    paid = await db.users.count_documents({
        "created_at": {"$gte": since},
        "plan": {"$in": _PAID_PLANS},
    })

    # Comped users (admin-gifted) — informational only, not part of funnel rates
    comped = await db.users.count_documents({
        "created_at": {"$gte": since},
        "comped": True,
    })

    def rate(num: int, denom: int) -> float:
        return round(num / denom, 4) if denom else 0.0

    return {
        "window_days": days,
        "since": since.isoformat(),
        "buckets": {
            "visitors": visitors,
            "raw_views": raw_views,
            "signups": signups,
            "activated": activated,
            "paid": paid,
            "comped": comped,
        },
        "rates": {
            "visit_to_signup": rate(signups, visitors),
            "signup_to_activated": rate(activated, signups),
            "activated_to_paid": rate(paid, activated),
            "visit_to_paid": rate(paid, visitors),
        },
    }
