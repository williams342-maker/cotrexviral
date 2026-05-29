"""Performance metrics — time-series writer + rollup compute.

Schema lives in `models_normalized.py` (see `PerformanceMetric` and
`PerformanceRollup`). This module is the runtime layer:

  • `record_metric(...)` — upserts ONE day-row keyed by
    `(variant_id, platform, date)`. Re-importable: same key updates
    in place, never double-counts (unique compound index enforces).

  • `recompute_rollup(variant_id)` — rebuilds the rollup row for a
    single variant from its time-series rows. Called inline after
    every `record_metric` so the dashboard reads are always fresh.

  • `record_metrics_from_post_refresh(post, vendor_metrics)` — the
    hook called from `routes/analytics.py::_refresh_post` after the
    6h cron has fetched fresh engagement for a post. Fans out one
    daily row per `(variant, platform)` tuple.

Phase 1 wires this onto the existing 6-hour analytics refresh —
every time we fetch fresh engagement for a post, we ALSO stamp a
daily time-series row for each of its variants. This makes the new
tables a passive mirror of the old `posts.metrics`; no source-of-
truth change yet (that's Phase 2).

Naming note: `routes/performance.py` already exists as the (mocked)
generic dashboard endpoint. This module deliberately uses
`perf_metrics` to avoid the conflict — it's a pure helper module,
not an API surface.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from core import db

logger = logging.getLogger(__name__)


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


async def record_metric(
    *,
    variant_id: str,
    content_item_id: str,
    brand_id: str,
    user_id: str,
    platform: str,
    date: Optional[str] = None,
    campaign_id: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> dict:
    """Upsert a single daily metric row. The compound unique index on
    `(variant_id, platform, date)` makes this idempotent — calling
    twice with the same key updates the existing row in place rather
    than creating a duplicate."""
    raw_payload = raw_payload or {}
    date = date or _today_str()

    impressions = _safe_int(raw_payload.get("impressions") or raw_payload.get("views"))
    reach       = _safe_int(raw_payload.get("reach"))
    clicks      = _safe_int(raw_payload.get("clicks") or raw_payload.get("link_clicks"))
    likes       = _safe_int(raw_payload.get("likes") or raw_payload.get("reactions"))
    comments    = _safe_int(raw_payload.get("comments") or raw_payload.get("comment_count"))
    shares      = _safe_int(raw_payload.get("shares") or raw_payload.get("reposts"))
    saves       = _safe_int(raw_payload.get("saves") or raw_payload.get("bookmarks"))
    engagements = likes + comments + shares + saves
    ctr         = round(clicks / impressions, 4) if impressions > 0 else 0.0

    doc_set = {
        "brand_id":        brand_id,
        "user_id":         user_id,
        "variant_id":      variant_id,
        "content_item_id": content_item_id,
        "campaign_id":     campaign_id,
        "platform":        platform,
        "date":            date,
        "impressions":     impressions,
        "reach":           reach,
        "clicks":          clicks,
        "engagements":     engagements,
        "likes":           likes,
        "comments":        comments,
        "shares":          shares,
        "saves":           saves,
        "ctr":             ctr,
        "raw_payload":     raw_payload,
        "fetched_at":      datetime.now(timezone.utc),
    }
    await db.performance_metrics.update_one(
        {"variant_id": variant_id, "platform": platform, "date": date},
        {"$set": doc_set, "$setOnInsert": {"id": uuid.uuid4().hex}},
        upsert=True,
    )
    await recompute_rollup(variant_id)
    return doc_set


async def recompute_rollup(variant_id: str) -> Optional[dict]:
    """Aggregate time-series rows for this variant into the rollup
    row. No-op if the variant has no metrics yet."""
    rows = await db.performance_metrics.find(
        {"variant_id": variant_id},
        {"_id": 0, "date": 1, "platform": 1, "impressions": 1, "reach": 1,
         "clicks": 1, "engagements": 1, "content_item_id": 1,
         "brand_id": 1, "user_id": 1},
    ).to_list(length=10_000)
    if not rows:
        return None

    head = rows[0]
    today = datetime.now(timezone.utc).date()
    cutoff_7  = (today - timedelta(days=7)).isoformat()
    cutoff_30 = (today - timedelta(days=30)).isoformat()

    def _sum_window(filter_fn):
        impr = sum(r["impressions"] for r in rows if filter_fn(r))
        rch  = sum(r["reach"] for r in rows if filter_fn(r))
        clk  = sum(r["clicks"] for r in rows if filter_fn(r))
        eng  = sum(r["engagements"] for r in rows if filter_fn(r))
        n    = sum(1 for r in rows if filter_fn(r))
        return {
            "impressions": impr,
            "reach":       rch,
            "clicks":      clk,
            "engagements": eng,
            "ctr":         round(clk / impr, 4) if impr else 0.0,
            "samples":     n,
        }

    rollup = {
        "variant_id":      variant_id,
        "content_item_id": head["content_item_id"],
        "brand_id":        head["brand_id"],
        "user_id":         head["user_id"],
        "platform":        max(set(r["platform"] for r in rows),
                               key=lambda p: sum(1 for r in rows if r["platform"] == p)),
        "last_7d":         _sum_window(lambda r: r["date"] >= cutoff_7),
        "last_30d":        _sum_window(lambda r: r["date"] >= cutoff_30),
        "all_time":        _sum_window(lambda r: True),
        "updated_at":      datetime.now(timezone.utc),
    }
    await db.performance_rollups.update_one(
        {"variant_id": variant_id},
        {"$set": rollup},
        upsert=True,
    )
    return rollup


async def record_metrics_from_post_refresh(post: dict, vendor_metrics: dict) -> int:
    """Hook called from `routes/analytics.py::_refresh_post` after the
    6h cron has fetched fresh engagement for a post. We fan out one
    daily row per `(variant, platform)` tuple.

    Returns the count of metric rows written/updated. Errors are
    logged but never raised; the engagement refresh job must NOT die
    because the normalized layer hiccuped."""
    variant_ids = post.get("variant_ids") or []
    if not variant_ids or not post.get("brand_id"):
        return 0

    variants = await db.content_variants.find(
        {"id": {"$in": variant_ids}},
        {"_id": 0, "id": 1, "platform": 1},
    ).to_list(length=20)
    by_platform: dict[str, list[str]] = {}
    for v in variants:
        by_platform.setdefault(v["platform"], []).append(v["id"])

    written = 0
    for platform, payload in vendor_metrics.items():
        if not isinstance(payload, dict):
            continue
        targets = by_platform.get(platform, [])
        for vid in targets:
            try:
                await record_metric(
                    variant_id=vid,
                    content_item_id=post["content_item_id"],
                    brand_id=post["brand_id"],
                    user_id=post["user_id"],
                    platform=platform,
                    campaign_id=post.get("campaign_id"),
                    raw_payload=payload,
                )
                written += 1
            except Exception:
                logger.exception(
                    "record_metric failed for variant=%s platform=%s",
                    vid, platform,
                )
    return written


# ---------------------------------------------------------------------
# Dashboard API — reads from `performance_rollups` for fast loads,
# falls back to live aggregation of `performance_metrics` when finer
# granularity is requested.
# ---------------------------------------------------------------------
from fastapi import Request, Query, HTTPException     # noqa: E402
from core import api                                  # noqa: E402
from deps import get_current_user                     # noqa: E402
from routes.brands import get_user_brand_id           # noqa: E402


@api.get("/attribution/overview")
async def attribution_overview(request: Request, campaign_id: Optional[str] = Query(None)):
    """High-level attribution: roll up every variant for the user
    (or filtered to one campaign) into per-platform totals + the
    top 5 content_items by engagement.

    Used by the new "Performance" tab on CampaignDetail (when
    campaign_id is set) and the future global dashboard (when it
    isn't)."""
    user = await get_current_user(request)
    brand_id = await get_user_brand_id(user.user_id)
    if not brand_id:
        # Shouldn't happen post-Phase-1, but defensive.
        raise HTTPException(status_code=404, detail="No brand for user")

    match: dict = {"brand_id": brand_id}
    if campaign_id:
        # Filter via content_items first so we resolve the variant set.
        item_ids = await db.content_items.distinct(
            "id", {"brand_id": brand_id, "campaign_id": campaign_id},
        )
        if not item_ids:
            return {
                "campaign_id":      campaign_id,
                "brand_id":         brand_id,
                "platforms":        {},
                "top_items":        [],
                "windows":          {"last_7d": _empty_window(), "last_30d": _empty_window(), "all_time": _empty_window()},
                "variants_tracked": 0,
            }
        match["content_item_id"] = {"$in": item_ids}

    rollups = await db.performance_rollups.find(match, {"_id": 0}).to_list(length=2000)

    # Per-platform breakdown across all rollups in scope.
    by_platform: dict[str, dict] = {}
    windows = {"last_7d": _empty_window(), "last_30d": _empty_window(), "all_time": _empty_window()}
    for r in rollups:
        p = r.get("platform") or "unknown"
        slot = by_platform.setdefault(p, _empty_window())
        for w in ("last_7d", "last_30d", "all_time"):
            window_data = r.get(w) or _empty_window()
            for k in ("impressions", "reach", "clicks", "engagements", "samples"):
                windows[w][k] += window_data.get(k, 0)
            if w == "all_time":
                for k in ("impressions", "reach", "clicks", "engagements", "samples"):
                    slot[k] += window_data.get(k, 0)

    # Recompute CTR after summation (can't average ctrs across rollups).
    for w in ("last_7d", "last_30d", "all_time"):
        impr = windows[w]["impressions"]
        windows[w]["ctr"] = round(windows[w]["clicks"] / impr, 4) if impr else 0.0
    for slot in by_platform.values():
        impr = slot["impressions"]
        slot["ctr"] = round(slot["clicks"] / impr, 4) if impr else 0.0

    # Top content_items by engagement (last_30d).
    item_totals: dict[str, dict] = {}
    for r in rollups:
        cid = r.get("content_item_id")
        if not cid:
            continue
        bucket = item_totals.setdefault(cid, {"content_item_id": cid, "engagements": 0, "impressions": 0})
        w = r.get("last_30d") or {}
        bucket["engagements"] += w.get("engagements", 0)
        bucket["impressions"] += w.get("impressions", 0)
    top_items_raw = sorted(item_totals.values(), key=lambda b: b["engagements"], reverse=True)[:5]
    # Enrich with title for the UI.
    if top_items_raw:
        items = await db.content_items.find(
            {"id": {"$in": [t["content_item_id"] for t in top_items_raw]}},
            {"_id": 0, "id": 1, "title": 1, "campaign_id": 1},
        ).to_list(length=10)
        title_map = {i["id"]: i for i in items}
        for t in top_items_raw:
            meta = title_map.get(t["content_item_id"], {})
            t["title"] = meta.get("title", "(untitled)")
            t["campaign_id"] = meta.get("campaign_id")

    return {
        "campaign_id":      campaign_id,
        "brand_id":         brand_id,
        "platforms":        by_platform,
        "windows":          windows,
        "top_items":        top_items_raw,
        "variants_tracked": len(rollups),
    }


def _empty_window() -> dict:
    return {"impressions": 0, "reach": 0, "clicks": 0, "engagements": 0, "ctr": 0.0, "samples": 0}


@api.get("/attribution/timeseries")
async def attribution_timeseries(
    request: Request,
    campaign_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=180),
):
    """Daily totals across `days` for the current user (or a
    specific campaign). Used by the dashboard's line chart."""
    user = await get_current_user(request)
    brand_id = await get_user_brand_id(user.user_id)
    if not brand_id:
        raise HTTPException(status_code=404, detail="No brand for user")

    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    match: dict = {"brand_id": brand_id, "date": {"$gte": cutoff}}
    if campaign_id:
        match["campaign_id"] = campaign_id

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"date": "$date", "platform": "$platform"},
            "impressions": {"$sum": "$impressions"},
            "engagements": {"$sum": "$engagements"},
            "clicks":      {"$sum": "$clicks"},
        }},
        {"$sort": {"_id.date": 1}},
    ]
    rows = await db.performance_metrics.aggregate(pipeline).to_list(length=5000)
    series = [{
        "date":        r["_id"]["date"],
        "platform":    r["_id"]["platform"],
        "impressions": r["impressions"],
        "engagements": r["engagements"],
        "clicks":      r["clicks"],
    } for r in rows]
    return {"series": series, "days": days, "campaign_id": campaign_id}
