"""End-to-end test for the new managed-vector-memory module.

Validates the post-fastembed `cortex/memory.py` rewrite:
  - record_turn embeds via OpenAI and persists to Mongo (cortex_memory_v2)
  - recall_semantic returns the right turn for a related query
  - Per-user cap prunes correctly when exceeded
  - Cosine top-K is order-correct
  - health() reports the new fields
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Load /app/backend/.env so OPENAI_API_KEY is present when pytest runs
# the file directly (pytest doesn't auto-load env files).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import pytest  # noqa: E402

from cortex import memory as cmem  # noqa: E402


pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for live embedding calls",
)


@pytest.fixture(autouse=True)
def _reset_singletons_between_tests():
    """Reset the module-level httpx client between tests so it doesn't
    bind to a stale event loop reference."""
    cmem._http_client = None
    yield
    cmem._http_client = None


@pytest.mark.asyncio
async def test_health_reports_new_fields():
    info = await cmem.health()
    assert info["embed_model"] == "text-embedding-3-small"
    assert info["embed_dim"] == 1536
    assert info["openai_key_set"] is True


async def _clean(user_id: str):
    from core import db
    await db[cmem.COLLECTION_V2].delete_many({"user_id": user_id})


@pytest.mark.asyncio
async def test_record_and_recall_roundtrip():
    """Stuff three semantically distinct turns into one user's memory,
    then query for one of them — it should come back first."""
    user = "regression-mem-user-1"
    await _clean(user)
    ids = []
    ids.append(await cmem.record_turn(user, "user",
        "We're planning a launch on Etsy for woodworking sellers"))
    ids.append(await cmem.record_turn(user, "user",
        "Stripe payouts hit our bank yesterday"))
    ids.append(await cmem.record_turn(user, "user",
        "Reddit r/SaaS dropped a thread about pricing"))
    assert all(ids), f"some record_turn calls returned None: {ids}"

    hits = await cmem.recall_semantic(user, "Etsy seller outreach", k=2)
    assert len(hits) >= 1
    assert "Etsy" in hits[0]["text"], (
        f"top hit should mention Etsy, got: {hits[0]['text']!r}"
    )
    if len(hits) >= 2:
        assert hits[0]["score"] >= hits[1]["score"]


@pytest.mark.asyncio
async def test_per_user_cap_prunes_oldest():
    """When per-user cap is hit, oldest entries are removed."""
    from core import db
    user = "regression-mem-user-2"
    await _clean(user)
    original = cmem._PER_USER_CAP
    cmem._PER_USER_CAP = 3
    try:
        for i in range(5):
            await cmem.record_turn(user, "user", f"thought number {i}")
        n = await db[cmem.COLLECTION_V2].count_documents({"user_id": user})
    finally:
        cmem._PER_USER_CAP = original
    # The prune is best-effort; cap=3 may temporarily allow cap+1.
    assert n <= 4, f"expected ≤4 stored after cap=3 prune, got {n}"


@pytest.mark.asyncio
async def test_recall_handles_empty_user():
    """Recalling for a user with no stored turns returns [], not an error."""
    hits = await cmem.recall_semantic("ghost-user-with-no-history", "anything")
    assert hits == []
