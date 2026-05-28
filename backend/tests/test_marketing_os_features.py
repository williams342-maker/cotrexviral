"""Tests for the Marketing OS + Campaign augmentation features.

Covers:
  - GET /api/marketing-os/runs?campaign_id=  filter
  - latest_run_* persistence on the campaign doc when a run completes
  - feedback_loop.winning_hooks_prompt_block helper behaviour

The Marketing OS chain itself is LLM-heavy and already tested via the
test_convene + test_marketing_os_chain suites. Here we focus on the
NEW orchestration glue we added in the recent sprint, mocking only at
the Mongo boundary — the helper + endpoints are exercised directly so
the LLM budget is not touched."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx
import pytest

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


# --- Helpers --------------------------------------------------------

def _create_campaign(name: str = "MOS Tests") -> dict:
    r = httpx.post(
        f"{API_URL}/api/campaigns", headers=H,
        json={"name": name, "goal": "awareness"}, timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _delete_campaign(cid: str) -> None:
    httpx.delete(f"{API_URL}/api/campaigns/{cid}", headers=H, timeout=10)


def _db():
    """Return a fresh motor handle for the test DB. Created on-demand
    so the test module doesn't drag a connection into pytest collection."""
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    return cli, cli[os.environ.get("DB_NAME", "test_database")]


async def _seed_runs(cid: str, n: int) -> list[str]:
    """Insert N completed run docs for the given campaign, oldest first.
    Returns the inserted run-ids in chronological order."""
    cli, db = _db()
    try:
        now = datetime.now(timezone.utc)
        ids = []
        for i in range(n):
            rid = str(uuid.uuid4())
            await db.marketing_os_runs.insert_one({
                "id":           rid,
                "user_id":      USER_ID,
                "brief":        f"Test brief #{i}",
                "campaign_id":  cid,
                "chain":        ["strategy", "research", "nova", "kai"],
                "summarizer":   "angela",
                "status":       "completed",
                "transcript":   [],
                "summary":      f"Test summary #{i} for {cid}",
                "created_at":   now - timedelta(days=(n - i - 1)),
                "finished_at":  now - timedelta(days=(n - i - 1)),
            })
            ids.append(rid)
        return ids
    finally:
        cli.close()


async def _cleanup_runs(cid: str) -> None:
    cli, db = _db()
    try:
        await db.marketing_os_runs.delete_many({"campaign_id": cid})
    finally:
        cli.close()


async def _seed_winning_hooks() -> list[str]:
    """Seed 3 winning_hook memory rows (2 LinkedIn, 1 Instagram) and
    return the deterministic dedupe_keys so tests can clean up reliably."""
    cli, db = _db()
    try:
        now = datetime.now(timezone.utc)
        keys = []
        seeds = [
            ("linkedin",  0.124, "[linkedin] You're not bad at marketing. You're bad at picking what to ship next.  (engagement rate: 12.4%)"),
            ("linkedin",  0.071, "[linkedin] Most SaaS landing pages talk about features. The good ones talk about pain.  (engagement rate: 7.1%)"),
            ("instagram", 0.098, "[instagram] 3 things I'd do if I was rebuilding my Insta from zero  (engagement rate: 9.8%)"),
        ]
        await db.cortex_memory.delete_many(
            {"user_id": USER_ID, "kind": "winning_hook", "dedupe_key": {"$regex": "^pytest_mos:"}},
        )
        for i, (plat, rate, text) in enumerate(seeds):
            key = f"pytest_mos:hook:{i}"
            keys.append(key)
            await db.cortex_memory.insert_one({
                "id":          str(uuid.uuid4()),
                "user_id":     USER_ID,
                "kind":        "winning_hook",
                "text":        text,
                "embedding":   [],
                "meta":        {"platform": plat, "engagement_rate": rate, "post_id": f"p{i}"},
                "created_at":  now - timedelta(days=i),
                "dedupe_key":  key,
            })
        return keys
    finally:
        cli.close()


async def _cleanup_winning_hooks() -> None:
    cli, db = _db()
    try:
        await db.cortex_memory.delete_many(
            {"user_id": USER_ID, "kind": "winning_hook", "dedupe_key": {"$regex": "^pytest_mos:"}},
        )
    finally:
        cli.close()


# Tiny helper so we can run an async expression inside a sync test
# function without juggling event loops at each call site.
def await_run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===================================================================
# 1) /marketing-os/runs campaign_id filter
# ===================================================================
class TestRunsCampaignFilter:
    def test_auth_required(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/runs", timeout=10)
        assert r.status_code == 401

    def test_filter_returns_only_target_campaign(self):
        c_a = _create_campaign("MOS filter A")
        c_b = _create_campaign("MOS filter B")
        try:
            asyncio.get_event_loop().run_until_complete(_seed_runs(c_a["id"], 3))
            asyncio.get_event_loop().run_until_complete(_seed_runs(c_b["id"], 2))
            # Without filter we should see at least 5 (both campaigns).
            r_all = httpx.get(f"{API_URL}/api/marketing-os/runs?limit=20", headers=H, timeout=10)
            assert r_all.status_code == 200
            assert r_all.json()["count"] >= 5

            # With filter we should see exactly the campaign's runs.
            r_a = httpx.get(f"{API_URL}/api/marketing-os/runs?campaign_id={c_a['id']}", headers=H, timeout=10)
            assert r_a.status_code == 200
            data_a = r_a.json()
            assert data_a["count"] == 3
            for row in data_a["runs"]:
                assert row["campaign_id"] == c_a["id"]

            r_b = httpx.get(f"{API_URL}/api/marketing-os/runs?campaign_id={c_b['id']}", headers=H, timeout=10)
            assert r_b.json()["count"] == 2
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup_runs(c_a["id"]))
            asyncio.get_event_loop().run_until_complete(_cleanup_runs(c_b["id"]))
            _delete_campaign(c_a["id"])
            _delete_campaign(c_b["id"])

    def test_filter_returns_empty_for_unknown_campaign(self):
        r = httpx.get(
            f"{API_URL}/api/marketing-os/runs?campaign_id={uuid.uuid4()}",
            headers=H, timeout=10,
        )
        assert r.status_code == 200
        assert r.json() == {"runs": [], "count": 0}

    def test_filter_respects_user_scope(self):
        """Filter must NOT leak runs across users. Seed a run with a
        different user_id and ensure it's invisible to the test user."""
        camp = _create_campaign("MOS scope")
        cli, db = _db()
        other_run = {
            "id":          str(uuid.uuid4()),
            "user_id":     "user_someone_else",
            "brief":       "private brief",
            "campaign_id": camp["id"],  # same id, different user
            "status":      "completed",
            "summary":     "should never appear",
            "created_at":  datetime.now(timezone.utc),
        }
        try:
            asyncio.get_event_loop().run_until_complete(db.marketing_os_runs.insert_one(other_run))
            r = httpx.get(
                f"{API_URL}/api/marketing-os/runs?campaign_id={camp['id']}",
                headers=H, timeout=10,
            )
            assert r.status_code == 200
            for row in r.json()["runs"]:
                assert row.get("user_id") in (None, USER_ID)
                assert row["summary"] != "should never appear"
        finally:
            asyncio.get_event_loop().run_until_complete(
                db.marketing_os_runs.delete_one({"id": other_run["id"]}),
            )
            cli.close()
            _delete_campaign(camp["id"])


# ===================================================================
# 2) latest_run_* persistence on the campaign doc
# ===================================================================
class TestLatestRunPin:
    def test_campaign_doc_returns_latest_run_fields_when_set(self):
        """We can't run the full 5-role chain here (LLM cost), so we
        emulate what `run_marketing_os` writes: a `$set` of latest_run_*
        fields on the campaign doc — then verify GET surfaces them."""
        camp = _create_campaign("MOS latest pin")
        cli, db = _db()
        rid = str(uuid.uuid4())
        try:
            now = datetime.now(timezone.utc)
            asyncio.get_event_loop().run_until_complete(db.campaigns.update_one(
                {"id": camp["id"], "user_id": USER_ID},
                {"$set": {
                    "latest_run_id":      rid,
                    "latest_run_summary": "PINNED summary text from the most recent OS run.",
                    "latest_run_at":      now,
                }},
            ))
            r = httpx.get(f"{API_URL}/api/campaigns/{camp['id']}", headers=H, timeout=10)
            assert r.status_code == 200
            d = r.json()
            assert d["latest_run_id"] == rid
            assert d["latest_run_summary"].startswith("PINNED summary")
            assert d["latest_run_at"] is not None
        finally:
            cli.close()
            _delete_campaign(camp["id"])

    def test_campaign_doc_omits_latest_run_when_never_run(self):
        camp = _create_campaign("MOS no runs")
        try:
            r = httpx.get(f"{API_URL}/api/campaigns/{camp['id']}", headers=H, timeout=10)
            assert r.status_code == 200
            d = r.json()
            # Either absent OR null — both are acceptable; what we care
            # about is the absence of stale stub strings.
            assert not d.get("latest_run_summary")
        finally:
            _delete_campaign(camp["id"])


# ===================================================================
# 3) feedback_loop.winning_hooks_prompt_block helper
# ===================================================================
class TestWinningHooksPromptBlock:
    def test_returns_empty_when_no_hooks(self):
        """Brand-new user (no winners) should get a "" so call-sites
        can safely concatenate the block onto a prompt unconditionally."""
        # Make sure no test hooks linger from a prior run.
        asyncio.get_event_loop().run_until_complete(_cleanup_winning_hooks())
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.feedback_loop import winning_hooks_prompt_block
        block = asyncio.get_event_loop().run_until_complete(
            winning_hooks_prompt_block("user_nobody_seeded", limit=3),
        )
        assert block == ""

    def test_returns_sorted_block_with_seeded_hooks(self):
        asyncio.get_event_loop().run_until_complete(_seed_winning_hooks())
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from routes.feedback_loop import winning_hooks_prompt_block
            block = asyncio.get_event_loop().run_until_complete(
                winning_hooks_prompt_block(USER_ID, limit=3),
            )
            assert "<winning_hooks>" in block and "</winning_hooks>" in block
            # Engagement rates should appear in descending order — the
            # 12.4% LinkedIn winner is rendered FIRST.
            idx_top = block.find("12.4%")
            idx_mid = block.find("9.8%")
            idx_bot = block.find("7.1%")
            assert 0 < idx_top < idx_mid < idx_bot
            # Clean text: no [platform] prefix, no "(engagement rate: …)" tail.
            assert "[linkedin] You're" not in block
            assert "(engagement rate" not in block
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup_winning_hooks())

    def test_platform_filter_restricts_results(self):
        asyncio.get_event_loop().run_until_complete(_seed_winning_hooks())
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from routes.feedback_loop import winning_hooks_prompt_block
            li_block = asyncio.get_event_loop().run_until_complete(
                winning_hooks_prompt_block(USER_ID, platform="linkedin", limit=5),
            )
            # Should include both LinkedIn winners but NOT the Instagram one.
            assert "12.4%" in li_block
            assert "7.1%" in li_block
            assert "9.8%" not in li_block

            ig_block = asyncio.get_event_loop().run_until_complete(
                winning_hooks_prompt_block(USER_ID, platform="instagram", limit=5),
            )
            assert "9.8%" in ig_block
            assert "12.4%" not in ig_block
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup_winning_hooks())

    def test_limit_caps_results(self):
        asyncio.get_event_loop().run_until_complete(_seed_winning_hooks())
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from routes.feedback_loop import winning_hooks_prompt_block
            block = asyncio.get_event_loop().run_until_complete(
                winning_hooks_prompt_block(USER_ID, limit=1),
            )
            # Only the top winner should be present.
            assert "12.4%" in block
            assert "9.8%" not in block
            assert "7.1%" not in block
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup_winning_hooks())


# ===================================================================
# 4) Misc — schema / endpoint sanity
# ===================================================================
class TestRolesEndpoint:
    def test_roles_returns_canonical_five(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/roles", headers=H, timeout=10)
        assert r.status_code == 200
        roles = r.json()["roles"]
        assert [r["role"] for r in roles] == [
            "strategy", "intelligence", "content", "distribution", "analytics",
        ]
        # Each role must declare its agent + color so the UI strip renders.
        for r in roles:
            assert r.get("agent_id") and r.get("label") and r.get("color")


class TestDashboardEndpointShape:
    def test_dashboard_returns_expected_keys(self):
        r = httpx.get(f"{API_URL}/api/marketing-os/dashboard", headers=H, timeout=10)
        assert r.status_code == 200
        d = r.json()
        for key in ("roles", "stats", "campaigns", "signals", "approvals", "runs", "wins"):
            assert key in d, f"dashboard payload missing {key}"
        for key in ("campaigns_active", "pending_approvals", "signals_hot", "recent_wins"):
            assert key in d["stats"]


# ===================================================================
# 5) /memory/promote-hook — promotes a winning_hook into brand_voice
# ===================================================================
class TestPromoteHookToBrandVoice:
    def test_auth_required(self):
        r = httpx.post(
            f"{API_URL}/api/memory/promote-hook",
            json={"hook_id": "x"}, timeout=10,
        )
        assert r.status_code == 401

    def test_promote_creates_brand_voice_row(self):
        cli, db = _db()
        # Seed exactly one winning_hook for the user.
        keys = asyncio.get_event_loop().run_until_complete(_seed_winning_hooks())
        try:
            # Grab the seeded hook's id.
            row = asyncio.get_event_loop().run_until_complete(
                db.cortex_memory.find_one(
                    {"user_id": USER_ID, "dedupe_key": keys[0]},
                ),
            )
            assert row is not None
            hook_id = row["id"]

            r = httpx.post(
                f"{API_URL}/api/memory/promote-hook", headers=H,
                json={"hook_id": hook_id}, timeout=10,
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["ok"] is True
            new_id = payload["id"]

            # The new brand_voice row exists with the correct shape.
            bv = asyncio.get_event_loop().run_until_complete(
                db.cortex_memory.find_one({"id": new_id, "user_id": USER_ID}),
            )
            assert bv is not None
            assert bv["kind"] == "brand_voice"
            assert (bv.get("meta") or {}).get("source_hook_id") == hook_id
            # The cleaned hook text was embedded, not the original raw row.
            assert "[linkedin]" not in bv["text"]
            assert "(engagement rate" not in bv["text"]

            # Second promotion is idempotent (single dedupe key — no
            # duplicate row created). `remember()` regenerates the
            # internal `id` on each upsert, so we assert ROW COUNT
            # rather than equal-ids.
            r2 = httpx.post(
                f"{API_URL}/api/memory/promote-hook", headers=H,
                json={"hook_id": hook_id}, timeout=10,
            )
            assert r2.status_code == 200
            count = await_run(db.cortex_memory.count_documents({
                "user_id":             USER_ID,
                "kind":                "brand_voice",
                "meta.source_hook_id": hook_id,
            }))
            assert count == 1, f"expected 1 brand_voice row, got {count}"
        finally:
            asyncio.get_event_loop().run_until_complete(_cleanup_winning_hooks())
            asyncio.get_event_loop().run_until_complete(
                db.cortex_memory.delete_many({"user_id": USER_ID, "kind": "brand_voice", "meta.source_hook_id": {"$exists": True}}),
            )
            cli.close()

    def test_promote_unknown_hook_404(self):
        r = httpx.post(
            f"{API_URL}/api/memory/promote-hook", headers=H,
            json={"hook_id": "nope-not-real"}, timeout=10,
        )
        assert r.status_code == 404

    def test_promote_other_users_hook_404(self):
        """The route filters by user_id — even if I know another user's
        hook id, the lookup must return 404."""
        cli, db = _db()
        other_id = str(uuid.uuid4())
        asyncio.get_event_loop().run_until_complete(db.cortex_memory.insert_one({
            "id":         other_id,
            "user_id":    "user_someone_else",
            "kind":       "winning_hook",
            "text":       "[linkedin] private hook  (engagement rate: 10%)",
            "embedding":  [],
            "meta":       {"platform": "linkedin", "engagement_rate": 0.1},
            "created_at": datetime.now(timezone.utc),
            "dedupe_key": f"pytest_mos:other:{other_id}",
        }))
        try:
            r = httpx.post(
                f"{API_URL}/api/memory/promote-hook", headers=H,
                json={"hook_id": other_id}, timeout=10,
            )
            assert r.status_code == 404
        finally:
            asyncio.get_event_loop().run_until_complete(
                db.cortex_memory.delete_one({"id": other_id}),
            )
            cli.close()
