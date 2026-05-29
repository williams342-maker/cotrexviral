"""LLM cost tracking + admin spend dashboard.

Every successful agent_chat turn fires `record_llm_call()` which writes a
single document to the `llm_usage` collection capturing agent + resolved
mode + model + token usage + USD cost.

Cost computation:
  • PREFERRED: token-accurate — we read `prompt_tokens` and
    `completion_tokens` from LiteLLM's `response.usage` (via
    `routes.ai.send_with_usage`) and multiply by per-million rates from
    `COST_PER_MTOK`.
  • FALLBACK: when token counts aren't available (rare), use the
    per-call averages in `COST_PER_CALL`.

Endpoint `GET /api/admin/llm-spend?days=30` returns:
  {
    days, since,
    total_calls, total_estimated_cost,
    total_tokens: {prompt, completion, total},
    by_mode:   [{mode, calls, cost, tokens}],
    by_agent:  [{agent_id, calls, cost, tokens}],
    by_model:  [{model, calls, cost, tokens}],
    top_users: [{user_id, email, calls, cost}],
    biggest_driver: {model, agent, percentage}
  }
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request

from core import db, api
from deps import require_admin

logger = logging.getLogger(__name__)


# Approximate per-CALL USD cost. Derived from public pricing × the typical
# CortexViral agent_chat shape (~1.5K input + ~500 output tokens). These
# are intentionally rough — surface them as "estimated" in the UI.
# Updated 2026-02 to match published Claude 4.x / Gemini 2.5 / GPT-5 pricing.
# Used as a fallback when LiteLLM doesn't surface token usage (rare).
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


# Token-accurate pricing — USD per 1M tokens. Used when LiteLLM gives us
# real prompt_tokens / completion_tokens (the normal path). Sources:
# Anthropic / OpenAI / Google pricing pages as of Feb 2026. When a model
# isn't listed we fall back to the per-call average above.
COST_PER_MTOK: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    "claude-opus-4-7":            (15.00, 75.00),
    "claude-opus":                (15.00, 75.00),
    "claude-sonnet-4-5":          ( 3.00, 15.00),
    "claude-sonnet":              ( 3.00, 15.00),
    "claude-haiku-4-5-20251001":  ( 1.00,  5.00),
    "claude-haiku":               ( 1.00,  5.00),
    "gemini-2.5-pro":             ( 1.25, 10.00),
    "gemini-pro":                 ( 1.25, 10.00),
    "gpt-5":                      ( 5.00, 15.00),
    "gpt-4o":                     ( 2.50, 10.00),
    "gpt-4o-mini":                ( 0.15,  0.60),
}


def _per_mtok_for(model: str) -> Optional[tuple[float, float]]:
    """Return `(input $/M, output $/M)` for the model — prefix-matches
    family names so future minor versions inherit the right rate without
    code changes. Returns None when the model isn't priced."""
    if not model:
        return None
    m = model.lower()
    if m in COST_PER_MTOK:
        return COST_PER_MTOK[m]
    for key, rates in COST_PER_MTOK.items():
        if m.startswith(key):
            return rates
    return None


def _exact_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Token-accurate cost. Returns 0 only when both counts are 0 (or
    model unknown). Numbers are exact USD up to whatever precision the
    pricing table has — typically 4 decimal places of a cent."""
    rates = _per_mtok_for(model)
    if not rates or (prompt_tokens <= 0 and completion_tokens <= 0):
        return 0.0
    in_per_mtok, out_per_mtok = rates
    return (prompt_tokens / 1_000_000.0) * in_per_mtok + \
           (completion_tokens / 1_000_000.0) * out_per_mtok


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


async def record_llm_call(
    user_id: str, agent_id: str, mode: str, model: str,
    usage: Optional[dict] = None,
) -> None:
    """Persist one row to `llm_usage`. Best-effort: never raises — an
    accounting failure must not break a successful chat reply.

    `usage` is the dict returned by `routes.ai.send_with_usage` —
    `{prompt_tokens, completion_tokens, total_tokens}`. When present we
    compute the exact USD cost; otherwise we fall back to the per-call
    average so the dashboard still shows non-zero data."""
    try:
        prompt_tokens = int((usage or {}).get("prompt_tokens") or 0)
        completion_tokens = int((usage or {}).get("completion_tokens") or 0)
        total_tokens = int((usage or {}).get("total_tokens") or prompt_tokens + completion_tokens)
        if prompt_tokens + completion_tokens > 0:
            cost = _exact_cost(model, prompt_tokens, completion_tokens)
            cost_source = "tokens"
        else:
            cost = _cost_for(model)
            cost_source = "per_call_estimate"
        await db.llm_usage.insert_one({
            "user_id":           user_id,
            "agent_id":          agent_id,
            "mode":              mode,
            "model":             model,
            "cost":              cost,
            "cost_source":       cost_source,
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      total_tokens,
            "ts":                datetime.now(timezone.utc),
        })
    except Exception:
        logger.exception("llm_usage write failed")


@api.get("/admin/llm-spend")
async def admin_llm_spend(request: Request, days: int = 30,
                          user_id: Optional[str] = None):
    """Aggregate LLM spend over the trailing `days` window. Admin-only.

    `days` is clamped to 1..365 so callers can't accidentally page through
    every row in the collection. Empty windows return zero counts rather
    than 404 — useful right after launch when no calls have happened yet.

    Pass `user_id` to scope the aggregate to a single user. Default is
    cross-tenant. Tests rely on this filter to stay deterministic.
    """
    await require_admin(request)
    days = max(1, min(365, int(days or 30)))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Build the $match: window AND (optionally) user.
    match: dict = {"ts": {"$gte": since}}
    if user_id:
        match["user_id"] = user_id

    # One $facet pipeline → all aggregates in a single round-trip. Cheaper
    # than 4 sequential queries when the dashboard auto-refreshes.
    pipeline = [
        {"$match": match},
        {"$facet": {
            "totals": [
                {"$group": {"_id": None,
                            "calls":  {"$sum": 1},
                            "cost":   {"$sum": "$cost"},
                            "prompt": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                            "completion": {"$sum": {"$ifNull": ["$completion_tokens", 0]}}}},
            ],
            "by_mode": [
                {"$group": {"_id": "$mode",
                            "calls":  {"$sum": 1},
                            "cost":   {"$sum": "$cost"},
                            "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}}}},
                {"$sort": {"cost": -1}},
            ],
            "by_agent": [
                {"$group": {"_id": "$agent_id",
                            "calls":  {"$sum": 1},
                            "cost":   {"$sum": "$cost"},
                            "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}}}},
                {"$sort": {"cost": -1}},
            ],
            "by_model": [
                {"$group": {"_id": "$model",
                            "calls":  {"$sum": 1},
                            "cost":   {"$sum": "$cost"},
                            "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}}}},
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
    total_prompt_tokens = (facets.get("totals") or [{}])[0].get("prompt", 0)
    total_completion_tokens = (facets.get("totals") or [{}])[0].get("completion", 0)

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
            {key_name: r["_id"], "calls": r["calls"], "cost": round(r["cost"], 4),
             "tokens": int(r.get("tokens") or 0)}
            for r in rows if r["_id"] is not None
        ]

    return {
        "days":                 days,
        "since":                since.isoformat(),
        "total_calls":          total_calls,
        "total_estimated_cost": round(total_cost, 4),
        "total_tokens": {
            "prompt":     int(total_prompt_tokens or 0),
            "completion": int(total_completion_tokens or 0),
            "total":      int((total_prompt_tokens or 0) + (total_completion_tokens or 0)),
        },
        "by_mode":              _shape(facets.get("by_mode") or [], "mode"),
        "by_agent":             _shape(facets.get("by_agent") or [], "agent_id"),
        "by_model":             _shape(facets.get("by_model") or [], "model"),
        "top_users":            top_users,
        "biggest_driver":       biggest,
    }



# Heuristic thresholds for the "consider switching modes" nudge.
# Tuned so a casual user never sees it (low cap) but a heavy Opus user does
# (>$2 / 30 days OR >50% of spend on Opus with at least 20 calls).
_SPEND_NUDGE_OPUS_COST_CAP    = 2.00   # USD over the trailing window
_SPEND_NUDGE_OPUS_SHARE_CAP   = 0.50   # 50% of total
_SPEND_NUDGE_OPUS_MIN_CALLS   = 20     # don't nudge brand-new users


@api.get("/ai/agent/spend-hint")
async def user_spend_hint(request: Request, days: int = 30):
    """Per-user spend nudge for AgentWorkspace. Shape:
      `{show: bool, opus_calls, opus_cost, total_cost, share, suggestion}`

    Returns `show: true` only when the user has spent meaningful money
    on Opus AND it's a large share of their total — otherwise the banner
    stays hidden so it doesn't feel naggy."""
    from deps import get_current_user
    user = await get_current_user(request)
    days = max(1, min(90, int(days or 30)))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"user_id": user.user_id, "ts": {"$gte": since}}},
        {"$group": {
            "_id":   None,
            "total": {"$sum": "$cost"},
            "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
            "opus_cost":  {"$sum": {"$cond": [{"$regexMatch": {"input": "$model", "regex": "opus", "options": "i"}}, "$cost", 0]}},
            "opus_calls": {"$sum": {"$cond": [{"$regexMatch": {"input": "$model", "regex": "opus", "options": "i"}}, 1, 0]}},
            "calls":      {"$sum": 1},
        }},
    ]
    rows = await db.llm_usage.aggregate(pipeline).to_list(length=1)
    if not rows:
        return {"show": False, "days": days, "opus_calls": 0, "opus_cost": 0,
                "total_cost": 0, "total_tokens": 0, "total_calls": 0,
                "share": 0, "suggestion": None}
    r = rows[0]
    total = float(r.get("total") or 0)
    total_tokens = int(r.get("total_tokens") or 0)
    total_calls = int(r.get("calls") or 0)
    opus_cost = float(r.get("opus_cost") or 0)
    opus_calls = int(r.get("opus_calls") or 0)
    share = (opus_cost / total) if total > 0 else 0.0

    show = (
        opus_calls >= _SPEND_NUDGE_OPUS_MIN_CALLS
        and (opus_cost >= _SPEND_NUDGE_OPUS_COST_CAP
             or share >= _SPEND_NUDGE_OPUS_SHARE_CAP)
    )
    suggestion = None
    if show:
        # Project the savings if half of the Opus calls swapped to Sonnet.
        sonnet_cost = _cost_for("claude-sonnet")
        opus_avg = _cost_for("claude-opus")
        savings = (opus_calls / 2) * (opus_avg - sonnet_cost)
        suggestion = {
            "message": (
                f"You've used Atlas in Deep mode {opus_calls} times this period "
                f"(~${opus_cost:.2f}, {int(share * 100)}% of your spend). "
                f"Switching half to Auto/Creative would save ~${max(0, savings):.2f}."
            ),
            "mode_hint": "creative",
            "estimated_savings": round(max(0, savings), 2),
        }
    return {
        "show":         show,
        "days":         days,
        "opus_calls":   opus_calls,
        "opus_cost":    round(opus_cost, 4),
        "total_cost":   round(total, 4),
        "total_tokens": total_tokens,
        "total_calls":  total_calls,
        "share":        round(share, 3),
        "suggestion":   suggestion,
    }
