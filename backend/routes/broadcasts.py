"""Admin broadcasts: site-wide banner messages."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from core import db, api
from deps import get_current_user, require_admin, log_admin_action
from models import BroadcastCreate, BroadcastUpdate


@api.post("/admin/broadcasts")
async def create_broadcast(payload: BroadcastCreate, request: Request):
    admin = await require_admin(request)
    doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title,
        "body": payload.body,
        "severity": payload.severity,
        "active": payload.active,
        "created_by": admin.user_id,
        "created_by_name": admin.name,
        "created_at": datetime.now(timezone.utc),
    }
    await db.broadcasts.insert_one(doc)
    await log_admin_action(admin, "create_broadcast", details={"title": payload.title, "severity": payload.severity})
    doc.pop("_id", None)
    return doc


@api.get("/admin/broadcasts")
async def admin_list_broadcasts(request: Request):
    await require_admin(request)
    cursor = db.broadcasts.find({}, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(200)


@api.patch("/admin/broadcasts/{broadcast_id}")
async def admin_update_broadcast(broadcast_id: str, payload: BroadcastUpdate, request: Request):
    admin = await require_admin(request)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    res = await db.broadcasts.update_one({"id": broadcast_id}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    await log_admin_action(admin, "update_broadcast", details={"broadcast_id": broadcast_id, "updates": updates})
    return {"ok": True}


@api.delete("/admin/broadcasts/{broadcast_id}")
async def admin_delete_broadcast(broadcast_id: str, request: Request):
    admin = await require_admin(request)
    res = await db.broadcasts.delete_one({"id": broadcast_id})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    await log_admin_action(admin, "delete_broadcast", details={"broadcast_id": broadcast_id})
    return {"ok": True}


@api.get("/broadcasts/active")
async def list_active_broadcasts(request: Request):
    """Public to logged-in users — shows currently active broadcasts."""
    await get_current_user(request)
    cursor = db.broadcasts.find({"active": True}, {"_id": 0}).sort("created_at", -1).limit(5)
    return await cursor.to_list(5)
