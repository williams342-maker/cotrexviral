"""Cortex conversation-history endpoints.

Adds ChatGPT-style multi-thread support to the Command Center:

  - GET  /api/cortex/console/conversations          → list past threads (titled, grouped)
  - GET  /api/cortex/console/conversations/{id}     → full message list for one thread
  - POST /api/cortex/console/conversations/new      → start a fresh thread, returns conversation_id

Backwards-compat note: existing `cortex_conversations` docs may not
have a `conversation_id` field. We bucket them into a single "legacy"
thread on first read so nothing is lost.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from core import api, db
from deps import get_current_user

logger = logging.getLogger(__name__)

LEGACY_ID = "legacy"   # bucket for pre-multi-thread rows


@api.get("/cortex/console/conversations")
async def list_conversations(request: Request, limit: int = 30):
    """List the user's conversation threads, newest first. Each item:
    { id, title, last_message, message_count, updated_at }."""
    user = await get_current_user(request)
    limit = max(1, min(int(limit), 100))

    # Aggregate cortex_conversations by `conversation_id` (or LEGACY_ID).
    pipeline = [
        {"$match": {"user_id": user.user_id}},
        {"$addFields": {
            "conv": {"$ifNull": ["$conversation_id", LEGACY_ID]},
        }},
        {"$sort": {"created_at": 1}},
        {"$group": {
            "_id": "$conv",
            "first_user_msg": {"$first": {
                "$cond": [{"$eq": ["$role", "user"]}, "$message", None],
            }},
            "last_message":  {"$last":  "$message"},
            "last_at":       {"$last":  "$created_at"},
            "first_at":      {"$first": "$created_at"},
            "message_count": {"$sum": 1},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": limit},
    ]
    items: list[dict] = []
    async for r in db.cortex_conversations.aggregate(pipeline):
        # Title = first user message (truncated). Falls back to a date.
        title = r.get("first_user_msg") or "Conversation"
        title = str(title).strip().split("\n")[0][:60] or "Conversation"
        items.append({
            "id":            r["_id"],
            "title":         title,
            "auto_title":    title,
            "pinned":        False,
            "last_message":  str(r.get("last_message") or "")[:120],
            "message_count": int(r.get("message_count") or 0),
            "updated_at":    _iso(r.get("last_at")),
            "created_at":    _iso(r.get("first_at")),
        })

    # Merge sidecar meta (custom titles, pinned flags).
    if items:
        ids = [it["id"] for it in items]
        meta_cur = db.cortex_conversation_meta.find(
            {"user_id": user.user_id, "conversation_id": {"$in": ids}},
            {"_id": 0})
        meta_by_id: dict[str, dict] = {m["conversation_id"]: m async for m in meta_cur}
        for it in items:
            m = meta_by_id.get(it["id"])
            if m:
                if m.get("title"):  it["title"]  = m["title"]
                if m.get("pinned"): it["pinned"] = True

    # Pinned to the top.
    items.sort(key=lambda x: (0 if x.get("pinned") else 1,
                                -(_dt_ord(x.get("updated_at")))))
    return {"items": items, "count": len(items)}


def _dt_ord(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


@api.get("/cortex/console/conversations/{conv_id}")
async def get_conversation(conv_id: str, request: Request, limit: int = 200):
    """Full message thread for one conversation_id."""
    user = await get_current_user(request)
    # Build the right filter: when conv_id == LEGACY_ID, match rows
    # without a conversation_id field.
    match: dict
    if conv_id == LEGACY_ID:
        match = {"user_id": user.user_id,
                  "$or": [{"conversation_id": {"$exists": False}},
                          {"conversation_id": None},
                          {"conversation_id": LEGACY_ID}]}
    else:
        match = {"user_id": user.user_id, "conversation_id": conv_id}

    cur = db.cortex_conversations.find(match, {"_id": 0})\
                                  .sort("created_at", 1).limit(int(limit))
    turns: list[dict] = []
    async for r in cur:
        ts = r.get("created_at")
        if isinstance(ts, datetime):
            r["created_at"] = ts.isoformat()
        turns.append(r)
    if not turns:
        raise HTTPException(404, "Conversation not found")
    return {"id": conv_id, "turns": turns, "count": len(turns)}


@api.post("/cortex/console/conversations/new")
async def new_conversation(request: Request):
    """Mint a fresh conversation_id. The frontend will start sending
    new chat turns with this ID so they group into a new thread.
    No mongo write needed — IDs are server-side guids that the chat
    endpoint persists on first message."""
    user = await get_current_user(request)
    cid = uuid.uuid4().hex
    return {"conversation_id": cid, "created_for": user.user_id,
            "created_at": datetime.now(timezone.utc).isoformat()}


# -------- rename / pin / delete -------------------------------------
from pydantic import BaseModel, Field

class ConvPatchPayload(BaseModel):
    title:  Optional[str] = Field(None, max_length=120)
    pinned: Optional[bool] = None


@api.patch("/cortex/console/conversations/{conv_id}")
async def patch_conversation(conv_id: str, payload: ConvPatchPayload,
                              request: Request):
    """Rename or pin a conversation. Patches are stored on a sidecar
    `cortex_conversation_meta` collection (1 row per conv_id) so we
    don't touch the underlying message rows."""
    user = await get_current_user(request)
    if conv_id == LEGACY_ID:
        raise HTTPException(400, "Cannot edit the legacy bucket")
    if payload.title is None and payload.pinned is None:
        raise HTTPException(400, "Nothing to update")
    update: dict = {"updated_at": datetime.now(timezone.utc)}
    if payload.title is not None:
        update["title"] = payload.title.strip()[:120]
    if payload.pinned is not None:
        update["pinned"] = bool(payload.pinned)
    await db.cortex_conversation_meta.update_one(
        {"user_id": user.user_id, "conversation_id": conv_id},
        {"$set": update,
         "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"updated": True, "conversation_id": conv_id, **{
        k: v for k, v in update.items() if k != "updated_at"}}


@api.delete("/cortex/console/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request):
    """Delete a conversation's messages + sidecar meta row."""
    user = await get_current_user(request)
    if conv_id == LEGACY_ID:
        raise HTTPException(400, "Refusing to delete the legacy bucket")
    res = await db.cortex_conversations.delete_many(
        {"user_id": user.user_id, "conversation_id": conv_id})
    await db.cortex_conversation_meta.delete_many(
        {"user_id": user.user_id, "conversation_id": conv_id})
    return {"deleted": True, "removed_messages": res.deleted_count}


# ---------------------------------------------------------- helpers
def _iso(v) -> Optional[str]:
    if isinstance(v, datetime):
        return v.isoformat()
    return v if isinstance(v, str) else None
