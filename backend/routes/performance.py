"""Performance analytics — REAL Mongo-backed aggregates per user.

Prior versions of this module returned `_mock_series` — synthetic
random-walk data — for every request. That was actively misleading:
users saw fake "sessions" and "revenue" trends on every dashboard load.
This rewrite backs the endpoints with real data from the collections we
actually own:

  • Posts published/scheduled  ← `posts` collection (per-user, real)
  • Stripe revenue             ← `payment_transactions` (per-user, real)
  • Traffic sessions           ← NOT AVAILABLE (no analytics pixel yet)

For fields we can't compute (e.g. site traffic), we return `null` and
a `not_configured` marker so the frontend can render an honest empty
state instead of a fabricated chart.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from fastapi import Request, Query

from core import db, api
from deps import get_current_user


# Range → (bucket_count, bucket_unit). "24h"/"48h" → hourly buckets,
# everything else → daily buckets.
PERFORMANCE_RANGES: Dict[str, Tuple[int, str]] = {
    "24h":      (24,  "hour"),
    "48h":      (48,  "hour"),
    "7d":       (7,   "day"),
    "30d":      (30,  "day"),
    "60d":      (60,  "day"),
    "90d":      (90,  "day"),
    "year":     (365, "day"),
    "lastyear": (365, "day"),
}


def _range_window(now: datetime, points: int, unit: str) -> List[datetime]:
    """Return the list of bucket-start timestamps (oldest first)."""
    delta = timedelta(hours=1) if unit == "hour" else timedelta(days=1)
    origin = (now.replace(minute=0, second=0, microsecond=0)
               if unit == "hour"
               else now.replace(hour=0, minute=0, second=0, microsecond=0))
    return [origin - delta * (points - 1 - i) for i in range(points)]


def _bucket_index(when: datetime, buckets: List[datetime], unit: str) -> int:
    """Return the bucket index for `when`, or -1 if out of range."""
    if unit == "hour":
        step = timedelta(hours=1)
    else:
        step = timedelta(days=1)
    for i, start in enumerate(buckets):
        if start <= when < start + step:
            return i
    return -1


def _fmt_label(when: datetime, unit: str) -> str:
    if unit == "hour":
        return when.strftime("%I%p").lstrip("0").lower()
    return when.strftime("%b %d")


def _pct(now: int | float, prev: int | float) -> float:
    if not prev:
        return 100.0 if now else 0.0
    return round((now - prev) / prev * 100, 1)


# --------------------------------------------------------------------------
# /performance/overview
# --------------------------------------------------------------------------
@api.get("/performance/overview")
async def performance_overview(request: Request,
                                 period: str = Query("24h", alias="range")):
    """Return real per-user metrics + time-series."""
    user = await get_current_user(request)
    points, unit = PERFORMANCE_RANGES.get(period, PERFORMANCE_RANGES["24h"])
    now = datetime.now(timezone.utc)
    window_start = now - (timedelta(hours=points) if unit == "hour"
                          else timedelta(days=points))
    # Previous window (same duration, immediately before) for change_pct.
    prev_window_start = window_start - (
        timedelta(hours=points) if unit == "hour" else timedelta(days=points)
    )

    buckets = _range_window(now, points, unit)

    # ---- Posts published/scheduled in this window ----
    posts_series = [0] * points
    prev_posts_total = 0
    cursor = db.posts.find(
        {"user_id": user.user_id,
         "created_at": {"$gte": prev_window_start}},
        {"_id": 0, "created_at": 1},
    )
    async for row in cursor:
        ts = row.get("created_at")
        if not ts:
            continue
        # Motor gives us naive UTC datetimes from BSON — normalize.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < window_start:
            prev_posts_total += 1
            continue
        idx = _bucket_index(ts, buckets, unit)
        if idx >= 0:
            posts_series[idx] += 1
    posts_total = sum(posts_series)

    # ---- Stripe revenue in this window (cents → dollars) ----
    revenue_series = [0] * points
    prev_revenue_total = 0
    cursor = db.payment_transactions.find(
        {"user_id": user.user_id,
         "created_at": {"$gte": prev_window_start},
         "status": {"$in": ["paid", "succeeded", "complete"]}},
        {"_id": 0, "created_at": 1, "amount": 1, "currency": 1},
    )
    async for row in cursor:
        ts = row.get("created_at")
        if not ts:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        amt = row.get("amount") or 0
        # payment_transactions stores amount in cents for Stripe events.
        dollars = int(amt / 100) if amt >= 100 else int(amt)
        if ts < window_start:
            prev_revenue_total += dollars
            continue
        idx = _bucket_index(ts, buckets, unit)
        if idx >= 0:
            revenue_series[idx] += dollars
    revenue_total = sum(revenue_series)

    return {
        "range": period,
        "metrics": [
            {"key":        "posts",
             "label":      "Posts published",
             "value":      posts_total,
             "change_pct": _pct(posts_total, prev_posts_total),
             "color":      "sky",
             "source":     "real"},
            {"key":        "revenue",
             "label":      "Stripe Revenue",
             "value":      f"${revenue_total:,}",
             "change_pct": _pct(revenue_total, prev_revenue_total),
             "color":      "violet",
             "source":     "real"},
            {"key":        "sessions",
             "label":      "Site Sessions",
             "value":      None,
             "change_pct": None,
             "color":      "amber",
             "source":     "not_configured",
             "note":       (
                 "Install the CortexViral analytics pixel on your site to "
                 "populate this metric — until then it stays honest and empty."
             )},
        ],
        "series": [
            {"key":   "posts",
             "label": "Posts",
             "color": "#1B7BFF",
             "data":  posts_series,
             "source": "real"},
            {"key":   "revenue",
             "label": "Stripe Revenue",
             "color": "#7C3AED",
             "data":  revenue_series,
             "source": "real"},
        ],
        "labels": [_fmt_label(b, unit) for b in buckets],
    }


# --------------------------------------------------------------------------
# /performance/sources  — top platforms by post volume (no fake traffic)
# --------------------------------------------------------------------------
@api.get("/performance/sources")
async def performance_sources(request: Request,
                                period: str = Query("24h", alias="range")):
    """Return real per-platform post volume in the current window +
    prior-window baseline for change_pct. This replaces the old
    random-walk `sources` table (which faked GA-style referrers)."""
    user = await get_current_user(request)
    points, unit = PERFORMANCE_RANGES.get(period, PERFORMANCE_RANGES["24h"])
    now = datetime.now(timezone.utc)
    window = timedelta(hours=points) if unit == "hour" else timedelta(days=points)
    window_start = now - window
    prev_window_start = window_start - window

    # Aggregate posts by platform in both windows.
    cur_counts: Dict[str, int] = {}
    prev_counts: Dict[str, int] = {}
    cursor = db.posts.find(
        {"user_id":    user.user_id,
         "created_at": {"$gte": prev_window_start}},
        {"_id": 0, "created_at": 1, "platforms": 1},
    )
    async for row in cursor:
        ts = row.get("created_at")
        if not ts:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        target = cur_counts if ts >= window_start else prev_counts
        for plat in row.get("platforms") or []:
            target[plat] = target.get(plat, 0) + 1

    rows: List[Dict[str, Any]] = []
    for plat, count in cur_counts.items():
        prev = prev_counts.get(plat, 0)
        rows.append({
            "source":     plat,
            "kind":       plat,
            "now":        count,
            "prev":       prev,
            "change_pct": _pct(count, prev),
            "source_kind": "real",
        })
    rows.sort(key=lambda r: r["now"], reverse=True)
    return rows


# --------------------------------------------------------------------------
# /performance/pages  — placeholder empty state until traffic pixel lands
# --------------------------------------------------------------------------
@api.get("/performance/pages")
async def performance_pages(request: Request,
                              period: str = Query("24h", alias="range")):
    """Top pages requires a site analytics pixel. Until that ships,
    return an empty list with a `not_configured` envelope so the UI
    can render an honest empty state instead of fabricated pageviews."""
    await get_current_user(request)
    return {
        "rows":   [],
        "source": "not_configured",
        "note":   (
            "Install the CortexViral analytics pixel on your site to "
            "populate top-page metrics."
        ),
    }
