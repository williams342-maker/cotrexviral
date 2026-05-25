"""Series-aware cancel + shift tests for recurring scheduled posts."""
import os
import asyncio
import httpx
from datetime import datetime, timedelta, timezone

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _cleanup():
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.posts.delete_many({
            "user_id": USER_ID,
            "content": {"$regex": "^SERIES_TEST"},
        })
    asyncio.get_event_loop().run_until_complete(go())


def _make_series(n=4, prefix="SERIES_TEST series_a"):
    """Create a 4-week recurring scheduled post starting 2 days from now."""
    start = datetime.now(timezone.utc) + timedelta(days=2)
    r = httpx.post(
        f"{API_URL}/api/channels/publish",
        headers=H,
        json={
            "content": prefix,
            "platforms": ["instagram"],
            "scheduled_at": start.isoformat(),
            "repeat_weeks": n,
        },
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    # Fetch the actual posts so the test has their IDs + dates
    sched = httpx.get(
        f"{API_URL}/api/posts/scheduled",
        headers=H,
        params={"start": start.isoformat(),
                "end": (start + timedelta(weeks=n + 1)).isoformat()},
        timeout=10,
    )
    series = sorted(
        [p for p in sched.json() if p.get("recurrence_group_id") == body["recurrence_group_id"]],
        key=lambda p: p["scheduled_at"],
    )
    return body["recurrence_group_id"], series


class TestSeriesCancel:
    def setup_method(self):
        _cleanup()

    def teardown_method(self):
        _cleanup()

    def test_default_scope_only_deletes_one(self):
        _, series = _make_series(n=4)
        first_id = series[0]["id"]
        r = httpx.delete(
            f"{API_URL}/api/posts/scheduled/{first_id}",
            headers=H, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["deleted"] == 1
        assert r.json()["scope"] == "only"

        # 3 remaining
        sched = httpx.get(f"{API_URL}/api/posts/scheduled", headers=H, timeout=10)
        remaining = [p for p in sched.json() if p["content"] == "SERIES_TEST series_a"]
        assert len(remaining) == 3

    def test_scope_future_keeps_past(self):
        gid, series = _make_series(n=5)
        # Cancel from the 3rd instance onwards (3 future, 2 prior kept)
        anchor = series[2]
        r = httpx.delete(
            f"{API_URL}/api/posts/scheduled/{anchor['id']}",
            headers=H, params={"scope": "future"}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["deleted"] == 3
        assert r.json()["scope"] == "future"

        sched = httpx.get(f"{API_URL}/api/posts/scheduled", headers=H, timeout=10)
        remaining = [p for p in sched.json()
                     if p.get("recurrence_group_id") == gid]
        assert len(remaining) == 2
        # The two remaining are the first two instances
        remaining_ids = {p["id"] for p in remaining}
        assert remaining_ids == {series[0]["id"], series[1]["id"]}

    def test_scope_all_deletes_entire_series(self):
        gid, series = _make_series(n=4)
        r = httpx.delete(
            f"{API_URL}/api/posts/scheduled/{series[0]['id']}",
            headers=H, params={"scope": "all"}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["deleted"] == 4

        sched = httpx.get(f"{API_URL}/api/posts/scheduled", headers=H, timeout=10)
        remaining = [p for p in sched.json()
                     if p.get("recurrence_group_id") == gid]
        assert remaining == []

    def test_rejects_unknown_scope(self):
        _, series = _make_series(n=2)
        r = httpx.delete(
            f"{API_URL}/api/posts/scheduled/{series[0]['id']}",
            headers=H, params={"scope": "bogus"}, timeout=10,
        )
        assert r.status_code == 400

    def test_non_recurring_post_ignores_scope(self):
        # Create a one-off scheduled post (no repeat_weeks)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        p = httpx.post(
            f"{API_URL}/api/channels/publish",
            headers=H,
            json={
                "content": "SERIES_TEST one_off",
                "platforms": ["tiktok"],
                "scheduled_at": future.isoformat(),
            },
            timeout=15,
        )
        post_id = p.json()["id"]
        r = httpx.delete(
            f"{API_URL}/api/posts/scheduled/{post_id}",
            headers=H, params={"scope": "future"}, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["deleted"] == 1
        assert r.json()["scope"] == "only"  # downgraded


class TestSeriesShift:
    def setup_method(self):
        _cleanup()

    def teardown_method(self):
        _cleanup()

    def test_shifts_all_members_by_delta(self):
        gid, series = _make_series(n=3, prefix="SERIES_TEST shift_a")
        original_dates = [p["scheduled_at"] for p in series]

        r = httpx.patch(
            f"{API_URL}/api/posts/series/{gid}",
            headers=H,
            json={"delta_days": 2},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 3
        assert r.json()["delta_days"] == 2

        # Refetch and confirm each instance is shifted +2 days.
        sched = httpx.get(f"{API_URL}/api/posts/scheduled", headers=H, timeout=10)
        new_series = sorted(
            [p for p in sched.json() if p.get("recurrence_group_id") == gid],
            key=lambda p: p["scheduled_at"],
        )
        for i, p in enumerate(new_series):
            orig = datetime.fromisoformat(original_dates[i].replace("Z", "+00:00"))
            new = datetime.fromisoformat(p["scheduled_at"].replace("Z", "+00:00"))
            delta = (new - orig).total_seconds() / 86400
            assert 1.99 < delta < 2.01, f"Expected +2d shift, got {delta}"

    def test_shifts_only_anchor_and_future(self):
        gid, series = _make_series(n=4, prefix="SERIES_TEST shift_b")
        anchor = series[2]
        original_first_two = [series[0]["scheduled_at"], series[1]["scheduled_at"]]

        r = httpx.patch(
            f"{API_URL}/api/posts/series/{gid}",
            headers=H,
            json={"delta_days": 7, "anchor_post_id": anchor["id"]},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["updated"] == 2  # only anchor + 1 future member

        sched = httpx.get(f"{API_URL}/api/posts/scheduled", headers=H, timeout=10)
        new_series = sorted(
            [p for p in sched.json() if p.get("recurrence_group_id") == gid],
            key=lambda p: p["scheduled_at"],
        )
        # First two unchanged
        assert new_series[0]["scheduled_at"] == original_first_two[0]
        assert new_series[1]["scheduled_at"] == original_first_two[1]

    def test_zero_delta_noop(self):
        gid, _ = _make_series(n=3, prefix="SERIES_TEST shift_zero")
        r = httpx.patch(
            f"{API_URL}/api/posts/series/{gid}",
            headers=H,
            json={"delta_days": 0},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["updated"] == 0

    def test_404_on_unknown_group(self):
        r = httpx.patch(
            f"{API_URL}/api/posts/series/no-such-group",
            headers=H,
            json={"delta_days": 1},
            timeout=10,
        )
        assert r.status_code == 404

    def test_rejects_huge_delta(self):
        gid, _ = _make_series(n=2, prefix="SERIES_TEST shift_big")
        r = httpx.patch(
            f"{API_URL}/api/posts/series/{gid}",
            headers=H,
            json={"delta_days": 5000},
            timeout=10,
        )
        assert r.status_code == 400
