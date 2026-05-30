"""Phase D refinement — single-post push endpoint + P1 verifications.

Tested endpoints:
- POST /api/cortex/campaigns/{cid}/posts/{pid}/push    (NEW)
- GET  /api/cortex/console/conversations               (P1 verify)
- POST /api/cortex/console/conversations/new           (P1 verify)
- POST /api/cortex/console/chat                        (multi-thread persistence)
- POST /api/cortex/optimization/{finding_id}/apply     (P1 verify)

Approach:
- For the single-push fresh-push path we temporarily $unset pushed_at on
  a known pushed cortex_social_posts row, then re-stamp at teardown.
- Uses already-complete campaign 3d579a6bd5f04df39261d8a2779a13cb
  (12 pushed + 0 google_ads) and 960b69244447430e87bbafc3373620d4
  (13 posts incl. 3 google_ads — used to test 422 non-pushable path).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Campaign with 12 already-pushed pushable posts (idempotency + fresh-push via $unset).
PUSHED_CID = "3d579a6bd5f04df39261d8a2779a13cb"
# Campaign with 3 google_ads (non-pushable) — for 422.
WITH_GADS_CID = "960b69244447430e87bbafc3373620d4"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


@pytest.fixture(scope="module")
def mongo():
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mc[os.environ.get("DB_NAME", "test_database")]
    yield db
    mc.close()


# ---------------------------------------------------- helpers
def _get_pushable_post(db, cid):
    return db.cortex_social_posts.find_one(
        {"campaign_id": cid, "user_id": USER_ID,
         "platform": {"$in": ["facebook", "instagram", "linkedin", "pinterest"]}},
        {"_id": 0})


def _get_google_ads_post(db, cid):
    return db.cortex_social_posts.find_one(
        {"campaign_id": cid, "user_id": USER_ID,
         "platform": {"$in": ["google ads", "google_ads", "email", "blog", "x"]}},
        {"_id": 0})


# ---------------------------------------------------- error paths
class TestSinglePushErrors:
    def test_404_unknown_post(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/nope_{uuid.uuid4().hex}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_404_unknown_campaign(self, client, mongo):
        # need an existing post id but mismatched campaign
        p = _get_pushable_post(mongo, PUSHED_CID)
        assert p
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/no_camp_{uuid.uuid4().hex}/posts/{p['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_400_invalid_mode(self, client, mongo):
        p = _get_pushable_post(mongo, PUSHED_CID)
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
            json={"mode": "publish_now"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_400_scheduled_without_scheduled_at(self, client, mongo):
        p = _get_pushable_post(mongo, PUSHED_CID)
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
            json={"mode": "scheduled"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_422_non_pushable_platform(self, client, mongo):
        gp = _get_google_ads_post(mongo, WITH_GADS_CID)
        if not gp:
            pytest.skip("no google_ads post available")
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{WITH_GADS_CID}/posts/{gp['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 422, r.text

    def test_cross_user_isolation(self, mongo):
        p = _get_pushable_post(mongo, PUSHED_CID)
        bad = requests.Session()
        bad.headers.update({"Authorization": "Bearer not_a_real_token_xyz",
                            "Content-Type": "application/json"})
        r = bad.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code in (401, 403, 404), r.text

    def test_409_incomplete_campaign(self, client, mongo):
        # Temporarily flip a campaign to draft status, ensure 409, then restore.
        before = mongo.cortex_campaigns.find_one(
            {"id": PUSHED_CID, "user_id": USER_ID}, {"_id": 0, "status": 1})
        assert before and before.get("status") == "complete"
        mongo.cortex_campaigns.update_one(
            {"id": PUSHED_CID, "user_id": USER_ID},
            {"$set": {"status": "in_progress"}})
        try:
            p = _get_pushable_post(mongo, PUSHED_CID)
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
                json={"mode": "draft"}, timeout=30)
            assert r.status_code == 409, r.text
        finally:
            mongo.cortex_campaigns.update_one(
                {"id": PUSHED_CID, "user_id": USER_ID},
                {"$set": {"status": "complete"}})

    def test_404_soft_deleted_campaign(self, client, mongo):
        # Temporarily soft-delete, expect 404, then restore.
        p = _get_pushable_post(mongo, PUSHED_CID)
        now = datetime.now(timezone.utc)
        mongo.cortex_campaigns.update_one(
            {"id": PUSHED_CID, "user_id": USER_ID},
            {"$set": {"deleted_at": now}})
        try:
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
                json={"mode": "draft"}, timeout=30)
            assert r.status_code == 404, r.text
        finally:
            mongo.cortex_campaigns.update_one(
                {"id": PUSHED_CID, "user_id": USER_ID},
                {"$unset": {"deleted_at": ""}})


# ---------------------------------------------------- idempotency on pushed row
class TestIdempotency:
    def test_already_pushed_returns_already_pushed_flag(self, client, mongo):
        p = _get_pushable_post(mongo, PUSHED_CID)
        assert p.get("pushed_at"), "fixture row must be already pushed"
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{p['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("already_pushed") is True
        assert d.get("posts_id") == p.get("posts_id")
        assert d.get("platform")
        assert d.get("pushed_at")


# ---------------------------------------------------- fresh push (draft + scheduled)
class TestFreshSinglePush:
    """Temporarily $unset pushed_at on a row, do a fresh push, then verify
    the response shape, /posts row, and cortex_social_posts stamps."""

    @pytest.fixture
    def fresh_row(self, mongo):
        row = mongo.cortex_social_posts.find_one(
            {"campaign_id": PUSHED_CID, "user_id": USER_ID,
             "platform": {"$in": ["facebook", "instagram", "linkedin", "pinterest"]}},
            {"_id": 0})
        assert row
        original = {
            "pushed_at": row.get("pushed_at"),
            "posts_id": row.get("posts_id"),
            "pushed_mode": row.get("pushed_mode"),
            "pushed_platform": row.get("pushed_platform"),
        }
        mongo.cortex_social_posts.update_one(
            {"id": row["id"], "user_id": USER_ID},
            {"$unset": {"pushed_at": "", "posts_id": "",
                        "pushed_mode": "", "pushed_platform": ""}})
        yield row
        # Restore stamps.
        mongo.cortex_social_posts.update_one(
            {"id": row["id"], "user_id": USER_ID},
            {"$set": {k: v for k, v in original.items() if v is not None}})

    def test_draft_fresh_push(self, client, mongo, fresh_row):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{fresh_row['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("posts_id")
        assert d.get("platform")
        assert d.get("status") == "draft"
        assert d.get("scheduled_at") is None
        # cleanup the /posts row we just created
        try:
            mongo.posts.delete_one({"id": d["posts_id"], "user_id": USER_ID})
        except Exception:
            pass

    def test_draft_fresh_push_persists_posts_row(self, client, mongo, fresh_row):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{fresh_row['id']}/push",
            json={"mode": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        post = mongo.posts.find_one({"id": d["posts_id"]}, {"_id": 0})
        assert post is not None
        assert post["status"] == "draft"
        assert post["user_id"] == USER_ID
        assert post["cortex_campaign_id"] == PUSHED_CID
        assert post["cortex_post_id"] == fresh_row["id"]
        assert post["source"] == "cortex_campaign_push"
        assert isinstance(post["platforms"], list) and len(post["platforms"]) == 1
        # Stamp on cortex_social_posts
        cp = mongo.cortex_social_posts.find_one({"id": fresh_row["id"]}, {"_id": 0})
        assert cp.get("pushed_at")
        assert cp.get("posts_id") == d["posts_id"]
        assert cp.get("pushed_mode") == "draft"
        # Cleanup
        mongo.posts.delete_one({"id": d["posts_id"], "user_id": USER_ID})

    def test_scheduled_fresh_push(self, client, mongo, fresh_row):
        sched_dt = (datetime.now(timezone.utc) + timedelta(hours=3)
                    ).replace(microsecond=0)
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{fresh_row['id']}/push",
            json={"mode": "scheduled", "scheduled_at": sched_dt.isoformat()},
            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("status") == "scheduled"
        assert d.get("scheduled_at"), d
        # cleanup
        mongo.posts.delete_one({"id": d["posts_id"], "user_id": USER_ID})


# ---------------------------------------------------- creative override
class TestCreativeOverride:
    def test_creative_override_uses_supplied_media(self, client, mongo):
        # Find any complete creative belonging to user; if absent, skip.
        creative = mongo.cortex_creatives.find_one(
            {"user_id": USER_ID, "status": "complete",
             "storage_key": {"$exists": True, "$ne": None},
             "deleted_at": {"$exists": False}}, {"_id": 0})
        if not creative:
            pytest.skip("no complete creative with storage_key available")

        row = mongo.cortex_social_posts.find_one(
            {"campaign_id": PUSHED_CID, "user_id": USER_ID,
             "platform": {"$in": ["facebook", "instagram", "linkedin", "pinterest"]}},
            {"_id": 0})
        original_stamps = {k: row.get(k) for k in
                           ("pushed_at", "posts_id", "pushed_mode", "pushed_platform")}
        mongo.cortex_social_posts.update_one(
            {"id": row["id"]}, {"$unset": {"pushed_at": "", "posts_id": "",
                                            "pushed_mode": "", "pushed_platform": ""}})
        try:
            r = client.post(
                f"{BASE_URL}/api/cortex/campaigns/{PUSHED_CID}/posts/{row['id']}/push",
                json={"mode": "draft", "creative_id": creative["id"]},
                timeout=30)
            assert r.status_code == 200, r.text
            d = r.json()
            post = mongo.posts.find_one({"id": d["posts_id"]}, {"_id": 0})
            assert post is not None
            # storage_key from chosen creative should be embedded in media_url.
            assert post.get("media_url"), f"expected media_url, got: {post}"
            assert creative["storage_key"] in (post.get("media_url") or ""), \
                f"media_url={post.get('media_url')} does not include override key {creative['storage_key']}"
            mongo.posts.delete_one({"id": d["posts_id"], "user_id": USER_ID})
        finally:
            mongo.cortex_social_posts.update_one(
                {"id": row["id"]},
                {"$set": {k: v for k, v in original_stamps.items() if v is not None}})


# ---------------------------------------------------- P1 verifications
class TestConversationsEndpoint:
    def test_list_returns_items(self, client):
        r = client.get(f"{BASE_URL}/api/cortex/console/conversations", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data, f"expected 'items' key, got {data}"
        assert isinstance(data["items"], list)
        # Validate shape if there are items
        for it in data["items"][:3]:
            assert "id" in it
            # title may be auto-generated; last_message may be empty/none
            assert "title" in it or "last_message" in it

    def test_create_new_conversation_and_persist_chat(self, client, mongo):
        r = client.post(f"{BASE_URL}/api/cortex/console/conversations/new",
                        json={}, timeout=30)
        assert r.status_code == 200, r.text
        new_conv = r.json()
        conv_id = new_conv.get("conversation_id") or new_conv.get("id")
        assert conv_id, new_conv

        # Send a chat message under that conversation_id and confirm persistence.
        msg = f"TEST_phase_d_single_push_{uuid.uuid4().hex[:8]}"
        r2 = client.post(f"{BASE_URL}/api/cortex/console/chat",
                         json={"message": msg, "conversation_id": conv_id},
                         timeout=120)
        assert r2.status_code == 200, r2.text

        # Verify the message landed in cortex_conversations under conv_id
        count = mongo.cortex_conversations.count_documents(
            {"user_id": USER_ID, "conversation_id": conv_id,
             "message": {"$regex": "TEST_phase_d_single_push_"}})
        assert count >= 1, "chat message not persisted under conversation_id"

        # Cleanup test conversation + meta
        mongo.cortex_conversations.delete_many(
            {"user_id": USER_ID, "conversation_id": conv_id})
        mongo.cortex_conversation_meta.delete_one(
            {"user_id": USER_ID, "conversation_id": conv_id})


class TestOptimizationApply:
    def test_apply_qualification_bottleneck_and_idempotency(self, client, mongo):
        # Seed a finding owned by USER_ID with a known APPLY_ACTIONS kind.
        finding_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        mongo.cortex_optimization_log.insert_one({
            "id":             finding_id,
            "user_id":        USER_ID,
            "kind":           "qualification_bottleneck",
            "bottleneck":     "TEST_qual",
            "hypothesis":     "test hypothesis",
            "recommendation": "Lower threshold",
            "confidence":     0.8,
            "autonomy_level": 2,
            "created_at":     now,
        })
        try:
            # First apply.
            r = client.post(
                f"{BASE_URL}/api/cortex/optimization/{finding_id}/apply",
                json={}, timeout=30)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d.get("applied") is True or d.get("action_taken") in ("queued", "launched")

            # Repeat → already_applied.
            r2 = client.post(
                f"{BASE_URL}/api/cortex/optimization/{finding_id}/apply",
                json={}, timeout=30)
            assert r2.status_code == 200, r2.text
            d2 = r2.json()
            assert d2.get("already_applied") is True
            assert d2.get("applied_at")

            # Confirm the finding row has applied_at + applied_action_id stamped.
            row = mongo.cortex_optimization_log.find_one(
                {"id": finding_id, "user_id": USER_ID}, {"_id": 0})
            assert row.get("applied_at")
            assert row.get("applied_action_id")
        finally:
            mongo.cortex_optimization_log.delete_one(
                {"id": finding_id, "user_id": USER_ID})
