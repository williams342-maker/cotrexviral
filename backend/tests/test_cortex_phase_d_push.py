"""Phase D — Bulk push cortex_social_posts to /posts calendar.

Strategy:
- Use campaign f4fb9522...d73c6 (13 posts, 0 pushed: 10 pushable + 3 google_ads)
  for the fresh-push and scheduled-push flows. After fresh push, those rows
  become 'already_pushed' for the rest of the run.
- Use campaign 3d579a6...a13cb (12 posts, all already pushed by smoke test)
  for the idempotency / already_pushed regression.
- Validate /posts row shape (content, platforms, media_url, source markers,
  cortex_campaign_id, cortex_post_id, status).
- Validate cortex_social_posts stamps (pushed_at, posts_id, pushed_mode,
  pushed_platform) and campaign last_pushed_* fields.
- Validate normalization: instagram_story / "instagram story" → instagram.
- Error paths: 400 missing start_at, 400 invalid mode, 404 unknown campaign,
  cross-user isolation (401/403/404).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# 13 posts, 0 pushed at suite start (10 pushable + 3 google_ads non-pushable)
FRESH_CID = "f4fb952252934d5383ae1168157d73c6"
# 13 posts, 0 pushed — used for scheduled-mode validation
FRESH_SCHED_CID = "2d546710e31b47819883100eb87d52fc"
# 12 posts, 12 pushed (idempotency regression target)
ALREADY_CID = "3d579a6bd5f04df39261d8a2779a13cb"

_PUSHABLE = {"facebook", "instagram", "instagram_story", "linkedin", "pinterest"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get_campaign(client, cid):
    r = client.get(
        f"{BASE_URL}/api/cortex/campaigns/{cid}?include=posts,creatives",
        timeout=60,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------- error paths
class TestPushErrors:
    def test_invalid_mode_returns_400(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{ALREADY_CID}/push",
            json={"mode": "publish_now"}, timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_scheduled_without_start_at_returns_400(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{ALREADY_CID}/push",
            json={"mode": "scheduled"}, timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_unknown_campaign_returns_404(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/nope_{uuid.uuid4().hex}/push",
            json={"mode": "draft"}, timeout=30,
        )
        assert r.status_code == 404

    def test_cross_user_isolation(self):
        bad = requests.Session()
        bad.headers.update({"Authorization": "Bearer not_a_real_token_xyz",
                            "Content-Type": "application/json"})
        r = bad.post(
            f"{BASE_URL}/api/cortex/campaigns/{ALREADY_CID}/push",
            json={"mode": "draft"}, timeout=30,
        )
        # Either rejected at auth (401/403) or row not owned → 404.
        assert r.status_code in (401, 403, 404)


# ---------------------------------------------------- idempotency
class TestIdempotency:
    """ALREADY_CID has 12 pushed posts; re-push should produce pushed=0,
    every post should appear in skipped with reason 'already_pushed'."""

    def test_repush_returns_already_pushed(self, client):
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{ALREADY_CID}/push",
            json={"mode": "draft"}, timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["counts"]["pushed"] == 0
        skipped = data["skipped"]
        # 12 posts -> every one should be skipped already_pushed.
        already = [s for s in skipped if s["reason"] == "already_pushed"]
        assert len(already) == 12, (
            f"expected 12 already_pushed entries; got "
            f"pushed={data['counts']}, skipped={skipped}"
        )
        # Each skipped already_pushed row carries the posts_id from prior run.
        for s in already:
            assert s.get("posts_id")
            assert s.get("id")


# ---------------------------------------------------- fresh draft push
class TestFreshDraftPush:
    """FRESH_CID starts with 0 pushed; first push should materialise
    10 pushable rows + skip 3 google_ads. Subsequent tests inspect
    the resulting /posts rows."""

    @pytest.fixture(scope="class")
    def push_result(self, client):
        # Snapshot pushable platforms beforehand so we can compare.
        before = _get_campaign(client, FRESH_CID)
        before_posts = before["social_posts"]
        # Reset guard: only run if 0 pushed beforehand, else skip
        # (suite may have re-ordered or been re-run).
        already_pushed = [p for p in before_posts if p.get("pushed_at")]
        if already_pushed:
            pytest.skip(
                f"FRESH_CID already had {len(already_pushed)} pushed posts — "
                "fresh-push case can't run; idempotency test covers re-push."
            )

        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{FRESH_CID}/push",
            json={"mode": "draft"}, timeout=60,
        )
        assert r.status_code == 200, r.text
        return r.json(), before_posts

    def test_push_counts(self, push_result):
        data, before = push_result
        # Expect 10 pushed (3 fb-ish + ... summing pushable) and 3 skipped
        # (google_ads non-pushable). Compute dynamically to avoid hardcoding.
        def _norm(p):
            n = "_".join((p.get("platform") or "").strip().lower().split())
            if n == "instagram_story":
                return "instagram_story"
            return n
        pushable_count = sum(1 for p in before
                             if _norm(p) in _PUSHABLE)
        nonpushable_count = len(before) - pushable_count
        assert data["counts"]["pushed"] == pushable_count, data
        # Every non-pushable should be in skipped with platform_not_pushable.
        not_pushable = [s for s in data["skipped"]
                        if s["reason"] == "platform_not_pushable"]
        assert len(not_pushable) == nonpushable_count, data["skipped"]

    def test_instagram_story_normalized_to_instagram(self, push_result):
        data, before = push_result
        # Any 'instagram story' (with space) in before → should land
        # as platform='instagram' in pushed list.
        story_ids = {p["id"] for p in before
                     if (p.get("platform") or "").strip().lower()
                     .replace(" ", "_") == "instagram_story"}
        if not story_ids:
            pytest.skip("no instagram_story rows in this campaign")
        pushed_story = [x for x in data["pushed"]
                        if x["cortex_post_id"] in story_ids]
        assert pushed_story, "expected instagram_story posts in pushed list"
        for x in pushed_story:
            assert x["platform"] == "instagram", \
                f"expected normalization to 'instagram', got {x['platform']}"

    def test_posts_rows_shape(self, client, push_result):
        data, _ = push_result
        if not data["pushed"]:
            pytest.skip("nothing pushed to verify shape")
        # GET /posts and find the pushed rows by cortex_post_id markers.
        r = client.get(f"{BASE_URL}/api/posts?limit=200", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("posts", body)
        if not isinstance(rows, list):
            pytest.skip(f"unexpected /api/posts shape: {type(body)}")
        pushed_ids = {p["posts_id"] for p in data["pushed"]}
        found = [r for r in rows if r.get("id") in pushed_ids]
        assert found, (
            f"none of the pushed posts_ids {pushed_ids} surfaced in "
            f"/api/posts (returned {len(rows)} rows)"
        )
        for row in found:
            assert row["status"] == "draft"
            assert row.get("source") == "cortex_campaign_push"
            assert row.get("cortex_campaign_id") == FRESH_CID
            assert row.get("cortex_post_id")
            assert isinstance(row.get("platforms"), list) and \
                   len(row["platforms"]) == 1
            assert row["platforms"][0] in _PUSHABLE
            assert isinstance(row.get("content"), str) and row["content"]

    def test_cortex_post_stamped(self, client, push_result):
        data, _ = push_result
        if not data["pushed"]:
            pytest.skip()
        after = _get_campaign(client, FRESH_CID)
        pushed_cortex_ids = {p["cortex_post_id"] for p in data["pushed"]}
        stamped = [p for p in after["social_posts"]
                   if p["id"] in pushed_cortex_ids]
        assert len(stamped) == len(pushed_cortex_ids)
        for p in stamped:
            assert p.get("pushed_at")
            assert p.get("posts_id")
            assert p.get("pushed_mode") == "draft"
            assert p.get("pushed_platform") in _PUSHABLE

    def test_campaign_last_pushed_stamp(self, client, push_result):
        data, _ = push_result
        if not data["pushed"]:
            pytest.skip()
        r = client.get(f"{BASE_URL}/api/cortex/campaigns/{FRESH_CID}",
                       timeout=30)
        camp = r.json()
        assert camp.get("last_pushed_at")
        assert camp.get("last_pushed_mode") == "draft"
        assert camp.get("last_pushed_count") == data["counts"]["pushed"]

    def test_second_push_is_idempotent(self, client, push_result):
        data, _ = push_result
        if not data["pushed"]:
            pytest.skip()
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{FRESH_CID}/push",
            json={"mode": "draft"}, timeout=60,
        )
        assert r.status_code == 200
        d2 = r.json()
        assert d2["counts"]["pushed"] == 0
        already = [s for s in d2["skipped"] if s["reason"] == "already_pushed"]
        assert len(already) == data["counts"]["pushed"]


# ---------------------------------------------------- scheduled mode
class TestScheduledPush:
    """We don't have a pristine fresh campaign with unpushed posts after
    the draft test runs — but we can validate the scheduled-mode INPUT
    contract (400 paths above) and that re-running scheduled mode on
    an already-pushed campaign returns the already_pushed skip set
    (proving the scheduled branch is reachable & gated identically)."""

    def test_scheduled_with_start_at_no_op_already_pushed(self, client):
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{ALREADY_CID}/push",
            json={"mode": "scheduled", "start_at": start, "cadence_hours": 6},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["counts"]["pushed"] == 0
        for s in data["skipped"]:
            assert s["reason"] in ("already_pushed", "platform_not_pushable")

    def test_scheduled_fresh_push_spreads_by_cadence(self, client):
        """Fresh-push FRESH_SCHED_CID in scheduled mode and verify
        scheduled_at increments by cadence_hours per item."""
        # Guard: skip if already pushed.
        before = _get_campaign(client, FRESH_SCHED_CID)
        already = [p for p in before["social_posts"] if p.get("pushed_at")]
        if already:
            pytest.skip(
                f"FRESH_SCHED_CID has {len(already)} already-pushed posts; "
                "scheduled fresh-push case can't run cleanly."
            )

        start_dt = datetime.now(timezone.utc).replace(microsecond=0) + \
            timedelta(hours=2)
        start = start_dt.isoformat()
        cadence = 6
        r = client.post(
            f"{BASE_URL}/api/cortex/campaigns/{FRESH_SCHED_CID}/push",
            json={"mode": "scheduled", "start_at": start,
                  "cadence_hours": cadence},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        pushed = data["pushed"]
        assert pushed, f"expected pushed list, got {data}"

        # Each pushed entry has scheduled_at and status='scheduled'.
        for x in pushed:
            assert x["status"] == "scheduled"
            assert x.get("scheduled_at")

        # scheduled_at values should be start + N * cadence for N=0..len-1.
        sched_times = sorted(
            datetime.fromisoformat(x["scheduled_at"].replace("Z", "+00:00"))
            for x in pushed
        )
        for i, t in enumerate(sched_times):
            expected = start_dt + timedelta(hours=cadence * i)
            # Tolerate microsec/server-clock jitter — within 2s.
            assert abs((t - expected).total_seconds()) < 2, (
                f"slot {i}: got {t.isoformat()}, expected {expected.isoformat()}"
            )

        # cortex_social_posts.pushed_mode should be 'scheduled' now.
        after = _get_campaign(client, FRESH_SCHED_CID)
        pushed_cortex_ids = {p["cortex_post_id"] for p in pushed}
        stamped = [p for p in after["social_posts"]
                   if p["id"] in pushed_cortex_ids]
        for p in stamped:
            assert p.get("pushed_mode") == "scheduled"
