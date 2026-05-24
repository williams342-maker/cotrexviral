"""Admin panel: users, audit log, impersonation, stats."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response

from core import db, api, ADMIN_EMAILS
from deps import require_admin, log_admin_action
from models import User


@api.get("/admin/me")
async def admin_me(request: Request):
    user = await require_admin(request)
    return user.model_dump()


@api.get("/admin/stats")
async def admin_stats(request: Request):
    await require_admin(request)
    return {
        "total_users": await db.users.count_documents({}),
        "active_users": await db.users.count_documents({"status": {"$ne": "suspended"}}),
        "suspended_users": await db.users.count_documents({"status": "suspended"}),
        "admins": await db.users.count_documents({"is_admin": True}),
        "total_leads": await db.leads.count_documents({}),
        "total_posts": await db.posts.count_documents({}),
        "total_reports": await db.reports.count_documents({}),
        "total_channels": await db.channels.count_documents({}),
        "open_tickets": await db.tickets.count_documents({"status": "open"}),
        "answered_tickets": await db.tickets.count_documents({"status": "answered"}),
        "closed_tickets": await db.tickets.count_documents({"status": "closed"}),
    }


@api.get("/admin/users")
async def admin_list_users(request: Request, q: Optional[str] = None):
    await require_admin(request)
    query = {}
    if q:
        query = {"$or": [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]}
    users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    # attach stats
    result = []
    for u in users:
        u.setdefault("is_admin", u.get("email", "").lower() in ADMIN_EMAILS)
        u.setdefault("status", "active")
        uid = u["user_id"]
        u["stats"] = {
            "posts": await db.posts.count_documents({"user_id": uid}),
            "leads": await db.leads.count_documents({"user_id": uid}),
            "reports": await db.reports.count_documents({"user_id": uid}),
            "channels": await db.channels.count_documents({"user_id": uid}),
        }
        result.append(u)
    return result


@api.get("/admin/users/{user_id}")
async def admin_user_detail(user_id: str, request: Request):
    await require_admin(request)
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.setdefault("is_admin", u.get("email", "").lower() in ADMIN_EMAILS)
    u.setdefault("status", "active")
    return {
        "user": u,
        "stats": {
            "posts": await db.posts.count_documents({"user_id": user_id}),
            "leads": await db.leads.count_documents({"user_id": user_id}),
            "reports": await db.reports.count_documents({"user_id": user_id}),
            "channels": await db.channels.count_documents({"user_id": user_id}),
            "tickets": await db.tickets.count_documents({"user_id": user_id}),
        },
        "recent_posts": await db.posts.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5),
        "recent_leads": await db.leads.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5),
    }


@api.post("/admin/users/{user_id}/suspend")
async def admin_suspend(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"status": "suspended"}})
    await db.user_sessions.delete_many({"user_id": user_id})
    await log_admin_action(admin, "suspend_user", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/unsuspend")
async def admin_unsuspend(user_id: str, request: Request):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"status": "active"}})
    await log_admin_action(admin, "unsuspend_user", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/promote")
async def admin_promote(user_id: str, request: Request):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_admin": True}})
    await log_admin_action(admin, "promote_admin", user_id, target.get("email"))
    return {"ok": True}


@api.post("/admin/users/{user_id}/demote")
async def admin_demote(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_admin": False}})
    await log_admin_action(admin, "demote_admin", user_id, target.get("email"))
    return {"ok": True}


@api.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # cascade
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.leads.delete_many({"user_id": user_id})
    await db.posts.delete_many({"user_id": user_id})
    await db.reports.delete_many({"user_id": user_id})
    await db.channels.delete_many({"user_id": user_id})
    await db.tickets.delete_many({"user_id": user_id})
    await db.ticket_messages.delete_many({"author_id": user_id})
    await log_admin_action(admin, "delete_user", user_id, target.get("email"), {"cascaded": True})
    return {"ok": True}


@api.post("/admin/users/{user_id}/impersonate")
async def admin_impersonate(user_id: str, request: Request, response: Response):
    admin = await require_admin(request)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    current_token = request.cookies.get("session_token")
    impersonate_token = f"imp_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": impersonate_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
        "impersonated_by": admin.user_id,
        "original_token": current_token,
    })

    response.set_cookie(
        key="session_token",
        value=impersonate_token,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=2 * 60 * 60,
    )
    await log_admin_action(admin, "impersonate_user", user_id, target.get("email"))
    return {
        "ok": True,
        "impersonating": {"user_id": target["user_id"], "name": target["name"], "email": target["email"]},
    }


@api.post("/admin/stop-impersonating")
async def admin_stop_impersonate(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="No active session")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session or not session.get("original_token"):
        raise HTTPException(status_code=400, detail="Not impersonating")

    original = session["original_token"]
    # remove the impersonation session
    await db.user_sessions.delete_one({"session_token": token})
    response.set_cookie(
        key="session_token",
        value=original,
        httponly=True, secure=True, samesite="none",
        path="/", max_age=7 * 24 * 60 * 60,
    )
    return {"ok": True}


@api.get("/admin/tickets")
async def admin_list_tickets(request: Request, status: Optional[str] = None):
    await require_admin(request)
    query = {}
    if status:
        query["status"] = status
    cursor = db.tickets.find(query, {"_id": 0}).sort("updated_at", -1)
    return await cursor.to_list(500)


@api.get("/admin/audit-log")
async def admin_audit_log(request: Request, limit: int = 200):
    await require_admin(request)
    cursor = db.audit_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)
