"""Admin broadcasts: site-wide banner messages + optional email blasts."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from core import db, api, logger
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


# -----------------------------------------------------------------------------
# Email blast — fire the broadcast to all matching users via Mailtrap.
# -----------------------------------------------------------------------------
class BroadcastEmailRequest(BaseModel):
    plans: Optional[list[str]] = None   # e.g. ["growth", "agency"]; None → all users
    include_comped: bool = True
    dry_run: bool = False               # if True, only count recipients; don't send


@api.post("/admin/broadcasts/{broadcast_id}/email")
async def email_broadcast(broadcast_id: str, payload: BroadcastEmailRequest, request: Request):
    """Send the broadcast as an email to all (or a filtered subset of) users.

    Idempotency: we mark the broadcast doc with `emailed_at`. Re-sending is
    explicitly allowed (admin might fix copy and re-blast), but each send logs
    a counted audit-log entry so you can see the history.
    Throttling: emails are sent sequentially with a 50ms gap to stay polite
    against Mailtrap's rate-limit; for our user counts (<10k) this is well
    inside the request timeout."""
    admin = await require_admin(request)
    bcast = await db.broadcasts.find_one({"id": broadcast_id}, {"_id": 0})
    if not bcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    # Build the recipient query.
    q: dict = {"status": "active", "email": {"$regex": r"^.+@.+\..+$"}}
    if payload.plans:
        valid = {"free", "starter", "growth", "agency", "pro", "scale"}
        plans = [p for p in payload.plans if p in valid]
        if not plans:
            raise HTTPException(status_code=400, detail="No valid plans in filter")
        q["plan"] = {"$in": plans}
    if not payload.include_comped:
        q["comped"] = {"$ne": True}

    recipients_count = await db.users.count_documents(q)
    if payload.dry_run:
        return {"ok": True, "would_send_to": recipients_count, "dry_run": True}

    if recipients_count == 0:
        return {"ok": True, "sent": 0, "failed": 0, "note": "No users matched the filter"}

    # Import here to avoid circular import at module load.
    from routes.email import send_broadcast_email

    sent = 0
    failed = 0
    cursor = db.users.find(q, {"_id": 0, "email": 1, "name": 1, "user_id": 1})
    async for u in cursor:
        try:
            res = await send_broadcast_email(
                to=u["email"],
                name=u.get("name") or "",
                title=bcast["title"],
                body=bcast["body"],
                severity=bcast.get("severity", "info"),
            )
            if res.get("sent"):
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception("Broadcast email failed for %s", u.get("email"))
            failed += 1
        # tiny gap to stay polite against API rate-limit
        await asyncio.sleep(0.05)

    # Record on the broadcast for the UI.
    await db.broadcasts.update_one(
        {"id": broadcast_id},
        {"$set": {
            "emailed_at": datetime.now(timezone.utc),
            "emailed_by": admin.user_id,
            "emailed_recipients": recipients_count,
            "emailed_sent": sent,
            "emailed_failed": failed,
            "emailed_filter": {"plans": payload.plans, "include_comped": payload.include_comped},
        }},
    )
    await log_admin_action(
        admin, "email_broadcast", details={
            "broadcast_id": broadcast_id, "recipients": recipients_count,
            "sent": sent, "failed": failed,
            "filter": {"plans": payload.plans, "include_comped": payload.include_comped},
        },
    )
    return {"ok": True, "recipients": recipients_count, "sent": sent, "failed": failed}

    cursor = db.broadcasts.find({"active": True}, {"_id": 0}).sort("created_at", -1).limit(5)
    return await cursor.to_list(5)
