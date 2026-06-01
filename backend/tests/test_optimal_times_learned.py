"""Regression test for the per-user learned posting-times feature.

Validates `POST /api/ai/optimal-times`:
  - Without enough history → returns heuristic slots (source='heuristic')
  - After seeding ≥6 published posts in a clear weekday+hour pattern,
    the endpoint switches to learned slots that reflect that pattern.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pytest
from httpx import ASGITransport, AsyncClient

from server import app


TEST_USER_ID = "test-learned-times-user"
SESSION_TOKEN = "test-learned-times-sess"


@pytest.fixture(autouse=True)
async def _bootstrap_user_and_clean():
    """Create the test session + user docs, clean up posts between
    runs."""
    from core import db
    now = datetime.now(timezone.utc)
    await db.user_sessions.update_one(
        {"session_token": SESSION_TOKEN},
        {"$set": {"session_token": SESSION_TOKEN, "user_id": TEST_USER_ID,
                   "expires_at": now + timedelta(days=1)}},
        upsert=True,
    )
    await db.users.update_one(
        {"user_id": TEST_USER_ID},
        {"$set": {"user_id": TEST_USER_ID, "email": "learned@cortex.test",
                   "name": "Learned Times Test",
                   "created_at": now}},
        upsert=True,
    )
    await db.posts.delete_many({"user_id": TEST_USER_ID})
    yield
    await db.posts.delete_many({"user_id": TEST_USER_ID})


async def _seed_posts(platform: str, weekday: int, hour: int, n: int):
    """Drop `n` published posts on the given weekday+hour, all in the
    last 30 days, all with positive engagement."""
    from core import db
    base = datetime.now(timezone.utc)
    docs = []
    for i in range(n):
        d = base - timedelta(days=i * 2)
        # Shift d onto the target weekday + hour
        delta_days = (weekday - d.weekday()) % 7
        d = d + timedelta(days=delta_days)
        d = d.replace(hour=hour, minute=0, second=0, microsecond=0)
        docs.append({
            "id": f"learned-post-{platform}-{i}",
            "user_id":      TEST_USER_ID,
            "platform":     platform,
            "status":       "published",
            "published_at": d,
            "metrics":      {"likes": 50 + i, "comments": 10},
        })
    await db.posts.insert_many(docs)


async def _call(platforms: list[str]) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/api/ai/optimal-times",
            json={"platforms": platforms},
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
        )
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
    return r.json()


@pytest.mark.asyncio
async def test_heuristic_fallback_when_no_history():
    data = await _call(["instagram"])
    assert data["learned_support"]["instagram"]["uses_learned"] is False
    assert data["learned_support"]["instagram"]["post_count"] == 0
    for slot in data["slots"]["instagram"]:
        assert slot["source"] == "heuristic"


@pytest.mark.asyncio
async def test_learned_path_after_threshold_seeded():
    # 8 LinkedIn posts on Tuesdays at 9am, all with engagement.
    await _seed_posts("linkedin", weekday=1, hour=9, n=8)

    data = await _call(["linkedin"])
    sup = data["learned_support"]["linkedin"]
    assert sup["post_count"] >= 6, sup
    assert sup["uses_learned"] is True, sup

    # The top recommended slot for linkedin should be a `learned` one
    # and its weekday/hour should match the seeded pattern.
    learned_slots = [s for s in data["slots"]["linkedin"]
                      if s["source"] == "learned"]
    assert learned_slots, "expected at least one learned slot"
    top = learned_slots[0]
    assert top["day"] == "Tue", top
    assert top["hour"] == 9, top
    assert top["support_posts"] >= 6
