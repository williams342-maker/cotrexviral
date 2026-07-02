"""Persistence helpers for the ai_runs collection."""
from datetime import datetime, timezone


def _clean(doc: dict | None) -> dict | None:
    if not doc:
        return None
    doc.pop("_id", None)
    return doc


async def create_run(db, document: dict) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        **document,
        "status": "running",
        "result": {},
        "error_message": None,
        "approval_status": document.get("approval_status", "not_required"),
        "executed": False,
        "created_at": now,
        "updated_at": now,
    }
    await db.ai_runs.insert_one(row)
    return _clean(row)


async def finish_run(db, run_id: str, **updates) -> dict:
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.ai_runs.update_one({"run_id": run_id}, {"$set": updates})
    return _clean(await db.ai_runs.find_one({"run_id": run_id}))


async def list_runs(db, user_id: str, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit or 50), 100))
    cursor = db.ai_runs.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_run(db, user_id: str, run_id: str) -> dict | None:
    return _clean(await db.ai_runs.find_one(
        {"user_id": user_id, "run_id": run_id}, {"_id": 0}
    ))

