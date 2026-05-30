"""Real-time HITL inbox — WebSocket fanout for paused/resolved runs.

Why this module exists
----------------------
The HITL gate (part 50) lets users pause a Marketing OS run before
Distribution publishes. Today the only way to *discover* a paused run
is to refresh the Command Center activity feed. Polling is brittle
(staleness window, wasted API calls) and the 24h email reminder is the
backstop, not the realtime channel.

This module provides:

  • `/api/ws/hitl-inbox` — authenticated WebSocket endpoint. The
    frontend opens this once per session and stays connected.
  • `broadcast_to_user(user_id, event, data)` — async helper that
    `routes/marketing_os.py` calls whenever a run transitions to
    `awaiting_approval` or `resolved`. Pushes a JSON frame to every
    connected socket for that user (multiple tabs all stay in sync).

Auth — the session_token cookie is sent automatically by the browser
on the WS handshake, but we also accept `?token=` query param so
non-browser clients (curl scripts, tests) can connect. We never put
the token in the URL after handshake — query-param tokens vanish from
proxy logs once the upgrade completes.

Connection lifecycle
--------------------
  open  → authenticate → register in `_LIVE_CONNECTIONS[user_id]`
  loop  → wait for client pings (heartbeat); ignore other messages
  close → unregister from the registry

The frontend hook handles reconnect with exponential backoff so a
backend restart or a network blip self-heals.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect, status

from core import api, db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection registry — process-local. With a single uvicorn worker (our
# current deployment) this is all we need. For multi-worker scale-out we'd
# wire this through Redis pub/sub; flagged in the migration notes below.
# ---------------------------------------------------------------------------
_LIVE_CONNECTIONS: dict[str, set[WebSocket]] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def _register(user_id: str, ws: WebSocket) -> None:
    async with _REGISTRY_LOCK:
        _LIVE_CONNECTIONS.setdefault(user_id, set()).add(ws)


async def _unregister(user_id: str, ws: WebSocket) -> None:
    async with _REGISTRY_LOCK:
        bucket = _LIVE_CONNECTIONS.get(user_id)
        if not bucket:
            return
        bucket.discard(ws)
        if not bucket:
            _LIVE_CONNECTIONS.pop(user_id, None)


async def broadcast_to_user(user_id: str, event: str, data: dict) -> int:
    """Best-effort push of `{event, data, at}` JSON to every WS this
    user has open. Returns the number of sockets that actually received
    the frame; dead sockets are pruned. Failures are logged but never
    raised — the caller's primary job (persisting the run) must not be
    blocked on a WS hiccup."""
    bucket = list(_LIVE_CONNECTIONS.get(user_id) or [])
    if not bucket:
        return 0
    frame = json.dumps({
        "event": event,
        "data":  data,
        "at":    datetime.now(timezone.utc).isoformat(),
    })
    delivered = 0
    dead: list[WebSocket] = []
    for ws in bucket:
        try:
            await ws.send_text(frame)
            delivered += 1
        except Exception as e:
            logger.debug("ws send failed for user=%s: %s", user_id, e)
            dead.append(ws)
    for ws in dead:
        await _unregister(user_id, ws)
    return delivered


# ---------------------------------------------------------------------------
# Token resolution for the WS handshake. Accepts (in order of preference):
#   1. `?token=...` query parameter   — easiest for tests / scripts
#   2. `session_token` cookie         — what the browser sends naturally
#   3. `Authorization: Bearer ...`    — header path; some clients prefer this
# Returns the User dict or None if no valid session.
# ---------------------------------------------------------------------------
async def _auth_websocket(ws: WebSocket) -> dict | None:
    token = ws.query_params.get("token")
    if not token:
        token = ws.cookies.get("session_token")
    if not token:
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        return None

    session = await db.user_sessions.find_one(
        {"session_token": token}, {"_id": 0, "user_id": 1,
                                       "expires_at": 1, "single_use": 1},
    )
    if not session:
        return None
    # WS tickets are single-use — consume on first auth so a replay
    # over an expired ticket fails cleanly.
    if session.get("single_use"):
        await db.user_sessions.delete_one({"session_token": token})

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None

    user = await db.users.find_one(
        {"user_id": session["user_id"], "status": {"$ne": "suspended"}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1},
    )
    return user


# ---------------------------------------------------------------------------
# WebSocket endpoint.
# Note the route doesn't use the `@api.websocket` shortcut because at
# the time of writing FastAPI's APIRouter exposed `.websocket()` only
# on the top-level app, not the prefixed router. We mount it directly
# under the `/api/ws/...` path on the global `app`.
# ---------------------------------------------------------------------------
from core import app   # noqa: E402  (intentional after registry decl)


@app.websocket("/api/ws/hitl-inbox")
async def hitl_inbox_ws(ws: WebSocket):
    user = await _auth_websocket(ws)
    if not user:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="unauthorized")
        return

    await ws.accept()
    user_id: str = user["user_id"]
    await _register(user_id, ws)

    # Send an immediate snapshot of currently-paused runs so a fresh
    # connection doesn't have to wait for a state change to discover
    # what's in the queue.
    try:
        cursor = db.marketing_os_runs.find(
            {"user_id": user_id, "status": "awaiting_approval"},
            {"_id": 0, "id": 1, "brief": 1, "campaign_id": 1, "created_at": 1,
             "skip_distribution": 1, "transcript": 1},
        ).sort("created_at", -1).limit(20)
        paused = []
        async for r in cursor:
            # Hide transcript bodies — too noisy for the inbox. Just
            # send the count so the UI can show "3 agents finished".
            r["transcript_len"] = len(r.pop("transcript", []) or [])
            if isinstance(r.get("created_at"), datetime):
                r["created_at"] = r["created_at"].isoformat()
            paused.append(r)
        await ws.send_text(json.dumps({
            "event": "snapshot",
            "data":  {"paused": paused},
            "at":    datetime.now(timezone.utc).isoformat(),
        }))
    except Exception:
        logger.exception("ws snapshot failed for user=%s", user_id)

    try:
        # Idle loop — client sends `ping` every ~25s, we reply `pong`.
        # Anything else is logged and ignored. We don't need to read
        # frequently; the broadcaster pushes from elsewhere.
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}, "at": datetime.now(timezone.utc).isoformat()}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws loop crashed for user=%s", user_id)
    finally:
        await _unregister(user_id, ws)


# ---------------------------------------------------------------------------
# Admin helper — useful for testing in pytest and for the future
# "connected users" admin dashboard.
# ---------------------------------------------------------------------------
def live_connection_count(user_id: str | None = None) -> int:
    if user_id is None:
        return sum(len(s) for s in _LIVE_CONNECTIONS.values())
    return len(_LIVE_CONNECTIONS.get(user_id) or [])
