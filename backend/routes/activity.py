"""Activity feed — chronological mixed-source events for the dashboard timeline."""

from fastapi import Request

from core import db, api
from deps import get_current_user
from routes.content_layer import list_posts_via_normalized


@api.get("/activity")
async def activity_feed(request: Request, limit: int = 30):
    user = await get_current_user(request)
    # Phase 4 — read via the normalized content_items index. Lenient
    # fallback included by default until STRICT_NORMALIZED_READS env flips.
    posts = await list_posts_via_normalized(user.user_id, limit=10)
    leads = await db.leads.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    reports = await db.reports.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    items = []
    for p in posts:
        items.append({"type": "post", "id": p["id"], "title": (p.get("content") or "")[:120], "platforms": p.get("platforms", []), "status": p.get("status"), "at": p["created_at"]})
    for lead in leads:
        items.append({"type": "lead", "id": lead["id"], "title": f"New lead from {lead.get('agent_id', 'agent')}", "subtitle": lead.get("email"), "at": lead["created_at"]})
    for r in reports:
        items.append({"type": "report", "id": r["id"], "title": f"{r.get('type', 'report').replace('_', ' ').title()}: {r.get('title') or r.get('url') or 'untitled'}", "at": r["created_at"]})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


@api.get("/posts")
async def list_posts(request: Request):
    user = await get_current_user(request)
    # Phase 4 — normalized-layer read with the original 100-item cap.
    return await list_posts_via_normalized(user.user_id, limit=100)
