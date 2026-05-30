"""Admin panel: users, audit log, impersonation, stats."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response

from core import db, api, ADMIN_EMAILS
from deps import require_admin, log_admin_action
from models import AdminSetPlanRequest, User
from routes.content_layer import list_posts_via_normalized
from routes.plans import ENTITLEMENTS


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
        "total_posts": await db.content_items.count_documents({}),  # Phase 5 — normalized count
        "total_reports": await db.reports.count_documents({}),
        "total_channels": await db.channels.count_documents({}),
        "open_tickets": await db.tickets.count_documents({"status": "open"}),
        "answered_tickets": await db.tickets.count_documents({"status": "answered"}),
        "closed_tickets": await db.tickets.count_documents({"status": "closed"}),
        # Subscription distribution
        "users_free": await db.users.count_documents({"$or": [{"plan": "free"}, {"plan": {"$exists": False}}]}),
        "users_starter": await db.users.count_documents({"plan": "starter"}),
        "users_growth": await db.users.count_documents({"plan": "growth"}),
        "users_agency": await db.users.count_documents({"plan": "agency"}),
        "users_legacy": await db.users.count_documents({"plan": {"$in": ["pro", "scale"]}}),
        "trialing_subs": await db.users.count_documents({"subscription_status": "trialing"}),
        "past_due_subs": await db.users.count_documents({"subscription_status": "past_due"}),
        # Seller Acquisition OS — cross-user totals (Phase 1-8).
        "seller_leads_total":     await db.seller_leads.count_documents({}),
        "seller_leads_qualified": await db.seller_leads.count_documents({"stage": "qualified"}),
        "seller_leads_outreached":await db.seller_leads.count_documents({"stage": "outreached"}),
        "seller_leads_active":    await db.seller_leads.count_documents({"stage": "active"}),
        "seller_leads_churned":   await db.seller_leads.count_documents({"stage": "churned"}),
        "seller_workflows_running":  await db.seller_retention_workflows.count_documents({"status": "running"}),
        "seller_workflows_complete": await db.seller_retention_workflows.count_documents({"status": "complete"}),
        "seller_artifacts_total":    await db.seller_offer_artifacts.count_documents({}),
        "seller_missions_active":    await db.missions.count_documents(
            {"mission_type": "seller_acquisition", "status": {"$nin": ["complete", "archived"]}}),
    }


@api.get("/admin/ai-usage")
async def admin_ai_usage(request: Request, months: int = 6, limit: int = 20):
    """Per-tenant AI generation analytics. Returns:
      - global_by_month: total AI generations per YYYY-MM bucket (last `months`)
      - top_users: top `limit` users by current-month usage
      - breakdown_by_kind: counts per generation type (post / blog / video_script / etc.)
    """
    await require_admin(request)
    now = datetime.now(timezone.utc)

    # Build the list of last N months as YYYY-MM strings
    month_keys = []
    y, m = now.year, now.month
    for _ in range(months):
        month_keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_keys.reverse()  # chronological order

    # Aggregate globally per month
    global_by_month = []
    breakdown_by_kind: dict[str, int] = {}
    for mk in month_keys:
        pipeline = [
            {"$project": {"_id": 0, "bucket": f"$usage.{mk}"}},
            {"$match": {"bucket": {"$exists": True}}},
            {"$group": {
                "_id": None,
                "ai_generations": {"$sum": {"$ifNull": ["$bucket.ai_generations", 0]}},
                "buckets": {"$push": "$bucket"},
            }},
        ]
        agg = await db.users.aggregate(pipeline).to_list(length=1)
        total = agg[0]["ai_generations"] if agg else 0
        global_by_month.append({"month": mk, "ai_generations": total})

        # Add this month's kinds to breakdown
        if agg:
            for bucket in agg[0]["buckets"]:
                kinds = (bucket or {}).get("kinds") or {}
                for kind, count in kinds.items():
                    breakdown_by_kind[kind] = breakdown_by_kind.get(kind, 0) + count

    # Top users for the current month
    current_mk = month_keys[-1]
    top_pipe = [
        {"$match": {f"usage.{current_mk}.ai_generations": {"$gt": 0}}},
        {"$project": {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "plan": 1,
            "subscription_status": 1,
            "ai_generations": f"$usage.{current_mk}.ai_generations",
            "kinds": f"$usage.{current_mk}.kinds",
        }},
        {"$sort": {"ai_generations": -1}},
        {"$limit": limit},
    ]
    top_users = await db.users.aggregate(top_pipe).to_list(length=limit)

    # Sort breakdown by count desc
    breakdown_sorted = sorted(breakdown_by_kind.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "current_month": current_mk,
        "global_by_month": global_by_month,
        "top_users": top_users,
        "breakdown_by_kind": [{"kind": k, "count": c} for k, c in breakdown_sorted],
        "totals": {
            "this_month": global_by_month[-1]["ai_generations"] if global_by_month else 0,
            "last_n_months": sum(m["ai_generations"] for m in global_by_month),
        },
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
        u.setdefault("plan", "free")
        u.setdefault("comped", False)
        u.setdefault("website", "")
        u.setdefault("brand_name", "")
        u.setdefault("niche", "")
        uid = u["user_id"]
        u["stats"] = {
            "posts": await db.content_items.count_documents({"user_id": uid}),  # Phase 5 — normalized
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
            "posts": await db.content_items.count_documents({"user_id": user_id}),  # Phase 5 — normalized
            "leads": await db.leads.count_documents({"user_id": user_id}),
            "reports": await db.reports.count_documents({"user_id": user_id}),
            "channels": await db.channels.count_documents({"user_id": user_id}),
            "tickets": await db.tickets.count_documents({"user_id": user_id}),
        },
        "recent_posts": await list_posts_via_normalized(user_id, limit=5),
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


@api.post("/admin/users/{user_id}/plan")
async def admin_set_plan(user_id: str, payload: AdminSetPlanRequest, request: Request):
    """Manually override a user's plan tier. When `comped=True` (default), the
    Stripe webhook will not downgrade this user — useful for influencers, beta
    testers, support cases, or fixing billing discrepancies."""
    admin = await require_admin(request)
    if payload.plan not in ENTITLEMENTS:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.plan}'")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    prev_plan = target.get("plan", "free")
    update = {
        "plan": payload.plan,
        "comped": payload.comped,
        "comped_by": admin.user_id if payload.comped else None,
        "comped_reason": payload.reason if payload.comped else None,
        "comped_at": datetime.now(timezone.utc) if payload.comped else None,
        "updated_at": datetime.now(timezone.utc),
    }
    # If switching to free without comp flag, clear comp metadata
    if not payload.comped:
        update["comped_by"] = None
        update["comped_reason"] = None
        update["comped_at"] = None
    await db.users.update_one({"user_id": user_id}, {"$set": update})
    await log_admin_action(
        admin, "set_user_plan", user_id, target.get("email"),
        {"from": prev_plan, "to": payload.plan, "comped": payload.comped, "reason": payload.reason},
    )

    # Fire gift-plan email when newly comping a user to a paid tier.
    if (
        payload.comped
        and payload.plan != "free"
        and (prev_plan != payload.plan or not target.get("comped"))
        and target.get("email")
    ):
        from routes.email import send_gift_plan_email, fire
        fire(send_gift_plan_email(
            to=target["email"],
            name=target.get("name") or "",
            plan=payload.plan,
            reason=payload.reason,
        ))

    return {"ok": True, "plan": payload.plan, "comped": payload.comped}


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



@api.post("/admin/migrations/normalize/run")
async def admin_run_normalize_migration(request: Request):
    """One-shot trigger for the data-model normalization migration.
    Idempotent — safe to call from a deploy hook or the admin UI when
    a startup hook didnt complete (e.g. mid-deploy timeout)."""
    admin = await require_admin(request)
    from migrations.normalize_001 import migrate_now
    result = await migrate_now()
    await log_admin_action(admin, "migration.normalize_001", details=result)
    return {"ok": True, "result": result}


@api.get("/admin/migrations/normalize/status")
async def admin_normalize_status(request: Request):
    await require_admin(request)
    from migrations.normalize_001 import MIGRATION_ID, needs_migration
    state = await db["_migration_state"].find_one({"_id": MIGRATION_ID}, {"_id": 0})
    return {
        "id":              MIGRATION_ID,
        "needs_migration": await needs_migration(),
        "last_run":        state,
        "counts": {
            "users":             await db.users.count_documents({"status": {"$ne": "deleted"}}),
            "brands":            await db.brands.count_documents({}),
            "campaigns_no_brand": await db.campaigns.count_documents({"brand_id": {"$exists": False}}),
            "posts_no_brand":     await db.posts.count_documents({"brand_id": {"$exists": False}}),
            "content_items":     await db.content_items.count_documents({}),
            "content_variants":  await db.content_variants.count_documents({}),
        },
    }

