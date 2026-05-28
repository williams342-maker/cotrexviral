"""LLM cost tracking + admin spend dashboard.

Every successful agent_chat turn fires `record_llm_call()` which writes a
single document to the `llm_usage` collection with the agent + resolved
mode + model + an *estimated* per-call USD cost. We don't ship a token
counter (the SDK doesn't surface tokens reliably across providers), so
costs are approximations based on published per-call averages for typical
1-2K input / 500-token output. Clearly labelled as "estimated" in the UI.

Endpoint `GET /api/admin/llm-spend?days=30` returns:
  {
    days, since,
    total_calls, total_estimated_cost,
    by_mode:   [{mode, calls, cost}],
    by_agent:  [{agent_id, calls, cost}],
    by_model:  [{model, calls, cost}],
    top_users: [{user_id, email, calls, cost}],
    biggest_driver: {model, agent, percentage}  # the single largest cost contributor
  }
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request

from core import db, api
from deps import require_admin

logger = logging.getLogger(__name__)


# Approximate per-CALL USD cost. Derived from public pricing × the typical
# CortexViral agent_chat shape (~1.5K input + ~500 output tokens). These
# are intentionally rough — surface them as "estimated" in the UI.
# Updated 2026-02 to match published Claude 4.x / Gemini 2.5 / GPT-5 pricing.
COST_PER_CALL: dict[str, float] = {
    # Anthropic Claude family
    "claude-opus-4-7":            0.0450,
    "claude-opus":                0.0450,
    "claude-sonnet-4-5":          0.0120,
    "claude-sonnet":              0.0120,
    "claude-haiku-4-5-20251001":  0.0012,
    "claude-haiku":               0.0012,
    # Google Gemini
    "gemini-2.5-pro":             0.0080,
    "gemini-pro":                 0.0080,
    # OpenAI
    "gpt-5":                      0.0200,
    "gpt-4o":                     0.0050,
    "gpt-4o-mini":                0.0005,
}
# Fallback for unknown models — assume a mid-tier rate so admins still see
# something on the dashboard instead of $0.
DEFAULT_COST_PER_CALL = 0.0100


def _cost_for(model: str) -> float:
    """Look up the estimated per-call cost. Prefix-matches on family name
    so `claude-sonnet-4-5-20250929` (or any future minor version) hits the
    `claude-sonnet` row without us having to add every variant."""
    if not model:
        return DEFAULT_COST_PER_CALL
    m = model.lower()
    if m in COST_PER_CALL:
        return COST_PER_CALL[m]
    for key, cost in COST_PER_CALL.items():
        if m.startswith(key):
            return cost
    return DEFAULT_COST_PER_CALL


async def record_llm_call(user_id: str, agent_id: str, mode: str, model: str) -> None:
    """Persist one row to `llm_usage`. Best-effort: never raises — an
    accounting failure must not break a successful chat reply."""
    try:
        await db.llm_usage.insert_one({
            "user_id":  user_id,
            "agent_id": agent_id,
            "mode":     mode,
            "model":    model,
            "cost":     _cost_for(model),
            "ts":       datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("llm_usage write failed")


@api.get("/admin/llm-spend")
async def admin_llm_spend(request: Request, days: int = 30):
    """Aggregate LLM spend over the trailing `days` window. Admin-only.

    `days` is clamped to 1..365 so callers can't accidentally page through
    every row in the collection. Empty windows return zero counts rather
    than 404 — useful right after launch when no calls have happened yet.
    """
    await require_admin(request)
    days = max(1, min(365, int(days or 30)))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # One $facet pipeline → all aggregates in a single round-trip. Cheaper
    # than 4 sequential queries when the dashboard auto-refreshes.
    pipeline = [
        {"$match": {"ts": {"$gte": since}}},
        {"$facet": {
            "totals": [
                {"$group": {"_id": None,
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
            ],
            "by_mode": [
                {"$group": {"_id": "$mode",
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
                {"$sort": {"cost": -1}},
            ],
            "by_agent": [
                {"$group": {"_id": "$agent_id",
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
                {"$sort": {"cost": -1}},
            ],
            "by_model": [
                {"$group": {"_id": "$model",
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
                {"$sort": {"cost": -1}},
            ],
            "by_user": [
                {"$group": {"_id": "$user_id",
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
                {"$sort": {"cost": -1}},
                {"$limit": 10},
            ],
            "by_model_agent": [
                {"$group": {"_id": {"model": "$model", "agent": "$agent_id"},
                            "calls": {"$sum": 1},
                            "cost":  {"$sum": "$cost"}}},
                {"$sort": {"cost": -1}},
                {"$limit": 1},
            ],
        }},
    ]
    cursor = db.llm_usage.aggregate(pipeline)
    rows = await cursor.to_list(length=1)
    facets = rows[0] if rows else {}

    total_calls = (facets.get("totals") or [{}])[0].get("calls", 0)
    total_cost  = (facets.get("totals") or [{}])[0].get("cost", 0.0)

    # Hydrate top-user rows with email so the admin doesn't see opaque
    # `user_xxxxx` strings.
    top_users = []
    user_rows = facets.get("by_user") or []
    if user_rows:
        ids = [r["_id"] for r in user_rows]
        users = await db.users.find(
            {"user_id": {"$in": ids}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(length=len(ids))
        umap = {u["user_id"]: u for u in users}
        for r in user_rows:
            u = umap.get(r["_id"], {})
            top_users.append({
                "user_id": r["_id"],
                "email":   u.get("email"),
                "name":    u.get("name"),
                "calls":   r["calls"],
                "cost":    round(r["cost"], 4),
            })

    # Biggest cost driver — the single (model, agent) pair eating the most
    # budget. Powers the "X% of cost is Opus from Atlas" callout.
    biggest = None
    ma = (facets.get("by_model_agent") or [None])[0]
    if ma and total_cost > 0:
        biggest = {
            "model":      ma["_id"]["model"],
            "agent":      ma["_id"]["agent"],
            "calls":      ma["calls"],
            "cost":       round(ma["cost"], 4),
            "percentage": round(100.0 * ma["cost"] / total_cost, 1),
        }

    def _shape(rows, key_name):
        return [
            {key_name: r["_id"], "calls": r["calls"], "cost": round(r["cost"], 4)}
            for r in rows if r["_id"] is not None
        ]

    return {
        "days":                 days,
        "since":                since.isoformat(),
        "total_calls":          total_calls,
        "total_estimated_cost": round(total_cost, 4),
        "by_mode":              _shape(facets.get("by_mode") or [], "mode"),
        "by_agent":             _shape(facets.get("by_agent") or [], "agent_id"),
        "by_model":             _shape(facets.get("by_model") or [], "model"),
        "top_users":            top_users,
        "biggest_driver":       biggest,
    }
