"""Read-only user context assembly for AI prompts."""


async def build_memory_context(db, user_id: str, supplied: dict | None = None) -> dict:
    profile = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0, "brand_name": 1, "website": 1, "niche": 1,
            "goals": 1, "platforms": 1, "challenge": 1,
        },
    ) or {}
    return {
        "profile": profile,
        "request_context": supplied or {},
    }

