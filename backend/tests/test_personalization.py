"""User-context personalization tests for AI generation."""
import os
import asyncio
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _set_profile(profile: dict):
    """Patch the test user's onboarding profile fields."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.users.update_one({"user_id": USER_ID}, {"$set": profile})
    asyncio.get_event_loop().run_until_complete(go())


def _clear_profile():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.users.update_one(
            {"user_id": USER_ID},
            {"$unset": {"brand_name": 1, "website": 1, "niche": 1,
                        "goals": 1, "platforms": 1, "challenge": 1}},
        )
    asyncio.get_event_loop().run_until_complete(go())


class TestContextBlockBuilder:
    def test_empty_profile_returns_empty_string(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.ai import _user_context_block
        _clear_profile()
        block = asyncio.get_event_loop().run_until_complete(
            _user_context_block(USER_ID)
        )
        assert block == ""

    def test_populated_profile_includes_all_fields(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.ai import _user_context_block
        _set_profile({
            "brand_name": "Iron Pulse",
            "website": "https://ironpulse.fit",
            "niche": "Fitness",
            "goals": ["Generate leads"],
            "platforms": ["TikTok"],
            "challenge": "Our hooks are too generic.",
        })
        block = asyncio.get_event_loop().run_until_complete(
            _user_context_block(USER_ID)
        )
        assert "USER CONTEXT" in block
        assert "Iron Pulse" in block
        assert "ironpulse.fit" in block
        assert "Fitness" in block
        assert "Generate leads" in block
        assert "TikTok" in block
        assert "generic" in block
        assert "tailor your output" in block.lower()
        _clear_profile()

    def test_long_challenge_is_truncated(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.ai import _user_context_block
        _set_profile({
            "brand_name": "X", "website": "x.com", "niche": "SaaS",
            "challenge": "Lorem ipsum " * 200,  # ~2400 chars
        })
        block = asyncio.get_event_loop().run_until_complete(
            _user_context_block(USER_ID)
        )
        assert "STATED CHALLENGE:" in block
        # Truncated to 280 chars per the impl
        assert "Lorem ipsum " * 200 not in block
        _clear_profile()


class TestPersonalizedGeneration:
    def test_generate_post_references_brand_when_set(self):
        """End-to-end: when a Fitness brand profile is in place, the AI output
        should contain at least one Fitness-niche signal. We assert against
        a small list rather than a specific word to keep the test stable."""
        _set_profile({
            "brand_name": "Iron Pulse Coaching",
            "website": "https://ironpulse.fit",
            "niche": "Fitness",
            "goals": ["Generate leads"],
            "platforms": ["TikTok"],
        })
        r = httpx.post(
            f"{API_URL}/api/ai/generate-post", headers=H,
            json={"platform": "tiktok", "tone": "energetic",
                  "topic": "a hook about discipline"},
            timeout=90,
        )
        r.raise_for_status()
        body = r.json()
        text = " ".join(str(v) for v in body.values() if v).lower()
        fitness_signals = [
            "gym", "fitness", "train", "workout", "muscle", "rep", "coach",
            "iron pulse", "athlete", "lift", "discipline blueprint",
        ]
        hits = [s for s in fitness_signals if s in text]
        assert len(hits) >= 1, (
            f"Expected at least one Fitness-niche signal in output. Got: {text[:400]}"
        )
        _clear_profile()
