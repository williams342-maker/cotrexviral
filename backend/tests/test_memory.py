"""Tests for the memory system v1 (vector recall)."""
import asyncio
import os
import secrets
import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
ADMIN_TOKEN = "test_session_1779636592168"
H = {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}


def _admin_user_id():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        sess = await db.user_sessions.find_one({"session_token": ADMIN_TOKEN}, {"_id": 0})
        return sess["user_id"] if sess else None
    return asyncio.get_event_loop().run_until_complete(go())


def _wipe_test_memories(prefix: str):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.cortex_memory.delete_many({"text": {"$regex": f"^{prefix}"}})
    asyncio.get_event_loop().run_until_complete(go())


class TestEmbedding:
    def test_embed_text_returns_384_dim(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.memory import embed_text

        vec = asyncio.get_event_loop().run_until_complete(embed_text("hello world"))
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert all(isinstance(x, float) for x in vec[:10])

    def test_embed_blank_returns_empty(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.memory import embed_text

        vec = asyncio.get_event_loop().run_until_complete(embed_text(""))
        assert vec == []

    def test_semantic_similarity(self):
        """Two semantically related sentences should have higher cosine
        similarity than two unrelated ones."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.memory import embed_text, _cosine

        a = asyncio.get_event_loop().run_until_complete(embed_text("My brand sells organic skincare for sensitive skin."))
        b = asyncio.get_event_loop().run_until_complete(embed_text("We make natural skincare products for delicate complexions."))
        c = asyncio.get_event_loop().run_until_complete(embed_text("The Roman Empire fell in 476 CE due to political fragmentation."))

        sim_ab = _cosine(a, b)
        sim_ac = _cosine(a, c)
        assert sim_ab > sim_ac, f"Related (a-b)={sim_ab:.3f} should beat unrelated (a-c)={sim_ac:.3f}"
        assert sim_ab > 0.5  # bge-small-en-v1.5 should easily clear this


class TestMemoryAPI:
    def test_requires_auth(self):
        for url in [
            (f"{API_URL}/api/memory/list", "GET"),
            (f"{API_URL}/api/memory/search", "POST"),
            (f"{API_URL}/api/memory/remember", "POST"),
            (f"{API_URL}/api/memory/reindex", "POST"),
        ]:
            r = httpx.request(url[1], url[0], json={"query": "x", "text": "x"}, timeout=10)
            assert r.status_code == 401, f"{url[0]} returned {r.status_code}"

    def test_remember_then_search(self):
        nonce = secrets.token_hex(4)
        text = f"MEMTEST-{nonce} Our unique selling point is sub-2-hour delivery in Brooklyn."
        try:
            r = httpx.post(
                f"{API_URL}/api/memory/remember",
                headers=H, json={"text": text, "kind": "manual"}, timeout=30,
            )
            assert r.status_code == 200, r.text
            mem_id = r.json()["id"]

            # Search with a semantically related (NOT exact) query
            s = httpx.post(
                f"{API_URL}/api/memory/search",
                headers=H,
                json={"query": "How fast can we deliver to NYC?", "k": 5},
                timeout=30,
            )
            assert s.status_code == 200
            results = s.json()["results"]
            ids = [r["id"] for r in results]
            assert mem_id in ids, f"Just-stored memory not in top-5 results: {ids}"

            # Delete + verify it's gone
            d = httpx.delete(f"{API_URL}/api/memory/{mem_id}", headers=H, timeout=10)
            assert d.status_code == 200

            s2 = httpx.post(
                f"{API_URL}/api/memory/search",
                headers=H,
                json={"query": "How fast can we deliver to NYC?", "k": 5},
                timeout=30,
            )
            assert mem_id not in [r["id"] for r in s2.json()["results"]]
        finally:
            _wipe_test_memories(f"MEMTEST-{nonce}")

    def test_dedupe_key_overwrites(self):
        """Same dedupe_key should overwrite, not duplicate."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db
        from routes.memory import remember

        user_id = _admin_user_id()
        nonce = secrets.token_hex(4)
        try:
            async def run():
                id1 = await remember(user_id, "manual", f"MEMTEST-{nonce} version one",
                                     dedupe_key=f"memtest-{nonce}")
                id2 = await remember(user_id, "manual", f"MEMTEST-{nonce} version two",
                                     dedupe_key=f"memtest-{nonce}")
                rows = await db.cortex_memory.find(
                    {"user_id": user_id, "dedupe_key": f"memtest-{nonce}"},
                ).to_list(length=10)
                return rows

            rows = asyncio.get_event_loop().run_until_complete(run())
            assert len(rows) == 1, f"Expected 1 deduped row, got {len(rows)}"
            assert "version two" in rows[0]["text"]
        finally:
            _wipe_test_memories(f"MEMTEST-{nonce}")

    def test_search_respects_kinds_filter(self):
        nonce = secrets.token_hex(4)
        try:
            httpx.post(f"{API_URL}/api/memory/remember", headers=H,
                       json={"text": f"MEMTEST-{nonce} brand fact ABC", "kind": "brand_profile"}, timeout=30)
            httpx.post(f"{API_URL}/api/memory/remember", headers=H,
                       json={"text": f"MEMTEST-{nonce} casual note ABC", "kind": "manual"}, timeout=30)

            r = httpx.post(
                f"{API_URL}/api/memory/search",
                headers=H,
                json={"query": f"MEMTEST-{nonce} ABC", "k": 5, "kinds": ["brand_profile"]},
                timeout=30,
            )
            assert r.status_code == 200
            kinds_seen = {row["kind"] for row in r.json()["results"]}
            assert kinds_seen == {"brand_profile"} or kinds_seen == set(), kinds_seen
        finally:
            _wipe_test_memories(f"MEMTEST-{nonce}")


class TestPromptInjection:
    def test_memories_to_prompt_block_format(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.memory import memories_to_prompt_block

        block = memories_to_prompt_block([
            {"kind": "brand_profile", "text": "Eco-friendly yoga brand for moms.", "meta": {}},
            {"kind": "post", "text": "Top-performing TikTok post about back pain.",
             "meta": {"platform": "tiktok", "engagement": "impr=10k saves=500"}},
        ])
        assert "<memory>" in block
        assert "</memory>" in block
        assert "Eco-friendly yoga" in block
        assert "[post, tiktok, engagement=impr=10k saves=500]" in block

    def test_empty_memories_returns_empty_block(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes.memory import memories_to_prompt_block

        assert memories_to_prompt_block([]) == ""


class TestReindex:
    def test_reindex_endpoint_runs(self):
        r = httpx.post(f"{API_URL}/api/memory/reindex", headers=H, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "indexed" in body and isinstance(body["indexed"], int)
