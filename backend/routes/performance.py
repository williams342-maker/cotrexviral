"""Performance analytics (currently mocked synthetic data)."""
from datetime import datetime, timedelta, timezone

from fastapi import Request, Query

from core import api
from deps import get_current_user


import random as _rand


def _mock_series(days: int, base: int = 50, volatility: int = 30):
    _rand.seed(days)
    return [max(0, base + _rand.randint(-volatility, volatility)) for _ in range(days)]


PERFORMANCE_RANGES = {"24h": 24, "48h": 48, "7d": 7, "30d": 30, "60d": 60, "90d": 90, "year": 365, "lastyear": 365}


@api.get("/performance/overview")
async def performance_overview(request: Request, period: str = Query("24h", alias="range")):
    await get_current_user(request)
    points = PERFORMANCE_RANGES.get(period, 24)
    sessions = _mock_series(points, 80, 50)
    revenue = _mock_series(points + 1, 25, 30)
    total_sessions = sum(sessions)
    total_revenue = sum(revenue)
    prev_sessions = max(1, int(total_sessions * _rand.uniform(0.85, 1.35)))
    prev_revenue = max(1, int(total_revenue * _rand.uniform(0.85, 1.30)))

    def pct(now, prev):
        return round((now - prev) / prev * 100, 1) if prev else 0

    is_hourly = period in ("24h", "48h")
    labels = []
    now = datetime.now(timezone.utc)
    for i in range(points):
        labels.append(
            (now - timedelta(hours=points - 1 - i)).strftime("%I%p").lstrip("0").lower()
            if is_hourly
            else (now - timedelta(days=points - 1 - i)).strftime("%b %d")
        )

    return {
        "range": period,
        "metrics": [
            {"key": "sessions", "label": "Sessions", "value": total_sessions, "change_pct": pct(total_sessions, prev_sessions), "color": "sky"},
            {"key": "revenue", "label": "Stripe Revenue", "value": f"${total_revenue:,}", "change_pct": pct(total_revenue, prev_revenue), "color": "violet"},
        ],
        "series": [
            {"key": "sessions", "label": "Sessions", "color": "#1B7BFF", "data": sessions},
            {"key": "revenue", "label": "Stripe Revenue", "color": "#7C3AED", "data": revenue[:points]},
        ],
        "labels": labels,
    }


@api.get("/performance/sources")
async def performance_sources(request: Request, period: str = Query("24h", alias="range")):
    await get_current_user(request)
    _rand.seed(hash(period))
    sources = [
        ("fb / paid", "facebook"),
        ("(direct) / (none)", "direct"),
        ("(not set) / (not set)", None),
        ("google / organic", "google"),
        ("instagram / referral", "instagram"),
        ("linkedin / referral", "linkedin"),
        ("tiktok / paid", "tiktok"),
    ]
    rows = []
    for name, kind in sources:
        n = _rand.randint(1, 35)
        prev = max(1, n + _rand.randint(-15, 15))
        rows.append({"source": name, "kind": kind, "now": n, "prev": prev, "change_pct": round((n - prev) / prev * 100, 1)})
    rows.sort(key=lambda r: r["now"], reverse=True)
    return rows


@api.get("/performance/pages")
async def performance_pages(request: Request, period: str = Query("24h", alias="range")):
    await get_current_user(request)
    _rand.seed(hash(period) + 1)
    pages = ["/", "/shop", "/dashboard", "/login", "/admin", "/admin/users", "/community", "/listings/new", "/blog", "/pricing", "/contact", "/about"]
    rows = []
    for p in pages:
        n = _rand.randint(0, 55)
        prev = max(0, n + _rand.randint(-20, 20))
        change = round((n - prev) / prev * 100, 1) if prev else (100.0 if n else 0.0)
        rows.append({"page": p, "now": n, "prev": prev, "change_pct": change})
    rows.sort(key=lambda r: r["now"], reverse=True)
    return rows[:10]
