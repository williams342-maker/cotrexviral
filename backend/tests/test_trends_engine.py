"""Trend Ingestion Engine tests — covers Reddit OAuth scaffolding,
graceful skip when unconfigured, Google Trends ingestion, and the
seeds / status endpoints."""
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


def _clear_user_trends():
    """Wipe any trend memories from prior runs so counts are deterministic."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.cortex_memory.delete_many({"user_id": USER_ID, "kind": "trend"})

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        loop.run_until_complete(go())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(go())


class TestTrendsStatus:
    def test_status_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/trends/status", timeout=10)
        assert r.status_code == 401

    def test_status_reports_sources(self):
        r = httpx.get(f"{API_URL}/api/trends/status", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        # Both keys are always present so the frontend can render uniformly.
        assert set(body.keys()) == {"reddit", "gtrends"}
        for src in body.values():
            assert "configured" in src and isinstance(src["configured"], bool)
            assert "note" in src
        # gtrends never requires creds.
        assert body["gtrends"]["configured"] is True


class TestTrendsSeeds:
    def test_seeds_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/trends/seeds", timeout=10)
        assert r.status_code == 401

    def test_seeds_returns_defaults(self):
        r = httpx.get(f"{API_URL}/api/trends/seeds", headers=H, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["subreddits"], list)
        assert isinstance(body["keywords"], list)
        # Even with no niche set we should fall back to the default sub list.
        assert len(body["subreddits"]) > 0


class TestTrendsIngest:
    def test_ingest_requires_auth(self):
        r = httpx.post(f"{API_URL}/api/trends/ingest", json={}, timeout=10)
        assert r.status_code == 401

    def test_ingest_skips_reddit_gracefully_when_unconfigured(self):
        """The whole point of this fix: ingest must succeed (not 500/403)
        even when REDDIT_CLIENT_ID isn't set. Reddit count should be 0
        and `reddit_configured` should reflect the env state."""
        _clear_user_trends()
        r = httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"keywords": ["marketing"], "subreddits": ["marketing"]},
            timeout=45,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        # If creds aren't set in this env, Reddit must be skipped, not crashed.
        assert isinstance(body["reddit_configured"], bool)
        if body["reddit_configured"] is False:
            assert body["reddit"] == 0
            assert body["subreddits"] == []
        # Google Trends should always work (pytrends has no key).
        assert isinstance(body["gtrends"], int)
        assert "keywords" in body and "marketing" in body["keywords"]

    def test_ingest_persists_watchlist(self):
        """Passing subreddits/keywords should persist them on the user doc
        so the 6h background job picks them up."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def fetch():
            return await db.users.find_one({"user_id": USER_ID}, {"_id": 0})

        httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"subreddits": ["SaaS", "marketing"], "keywords": ["ai", "growth"]},
            timeout=45,
        ).raise_for_status()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
            doc = loop.run_until_complete(fetch())
        except RuntimeError:
            doc = asyncio.new_event_loop().run_until_complete(fetch())

        assert doc.get("niche_subreddits") == ["SaaS", "marketing"]
        assert doc.get("niche_keywords") == ["ai", "growth"]


class TestTrendsRecent:
    def test_recent_requires_auth(self):
        r = httpx.get(f"{API_URL}/api/trends/recent", timeout=10)
        assert r.status_code == 401

    def test_recent_returns_after_ingest(self):
        """After a successful ingest with at least one source returning
        rows, `/trends/recent` should surface them."""
        _clear_user_trends()
        ingest = httpx.post(
            f"{API_URL}/api/trends/ingest", headers=H,
            json={"keywords": ["coffee"], "subreddits": []},
            timeout=45,
        )
        assert ingest.status_code == 200
        body = ingest.json()
        # Only assert if gtrends produced something this run (rate limits, etc.)
        if body.get("gtrends", 0) > 0:
            r = httpx.get(f"{API_URL}/api/trends/recent?limit=10", headers=H, timeout=10)
            assert r.status_code == 200
            data = r.json()
            assert data["count"] >= 1
            assert any(t.get("kind") == "trend" for t in data["trends"])


class TestRedditOAuthScaffolding:
    """Light-weight unit tests on the helpers (no network)."""

    def test_reddit_configured_false_when_creds_missing(self, monkeypatch):
        """When REDDIT_CLIENT_ID/SECRET are blank the helper must report
        the source as unavailable rather than attempting a doomed call."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import trends_engine as te

        monkeypatch.setattr(te, "REDDIT_CLIENT_ID", "")
        monkeypatch.setattr(te, "REDDIT_CLIENT_SECRET", "")
        assert te._reddit_configured() is False

    def test_reddit_token_returns_none_when_unconfigured(self, monkeypatch):
        """`_reddit_app_token` must short-circuit without doing a network
        request when creds aren't present (otherwise every ingest tick
        would burn an HTTP roundtrip for nothing)."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import trends_engine as te

        monkeypatch.setattr(te, "REDDIT_CLIENT_ID", "")
        monkeypatch.setattr(te, "REDDIT_CLIENT_SECRET", "")
        result = asyncio.new_event_loop().run_until_complete(te._reddit_app_token())
        assert result is None
