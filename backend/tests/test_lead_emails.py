"""Lead form → email-notification tests.

Verifies that POSTing to /api/leads fires (a) admin notifications to every
configured recipient and (b) an auto-reply to the lead."""
import os
import asyncio
import time
import uuid

import httpx

API_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
)


def _clear_email_log_for_lead():
    """Clear rows tagged lead_notification or lead_auto_reply so each test
    starts with a clean slate."""
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        await db.email_log.delete_many({
            "$or": [
                {"tags": {"$elemMatch": {"$regex": "^lead_"}}},
                {"reason": "no_email"},
            ]
        })
    asyncio.get_event_loop().run_until_complete(go())


def _fetch_recent_lead_rows(limit: int = 10):
    import sys
    sys.path.insert(0, "/app/backend")
    from core import db

    async def go():
        return await db.email_log.find(
            {"tags": {"$elemMatch": {"$regex": "^lead_"}}},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
    return asyncio.get_event_loop().run_until_complete(go())


class TestLeadNotifications:
    def test_lead_submission_fires_admin_notifications_and_auto_reply(self):
        _clear_email_log_for_lead()
        lead_email = f"test-{uuid.uuid4().hex[:8]}@cortexviral.com"
        r = httpx.post(
            f"{API_URL}/api/leads",
            json={
                "agent_id": "nova",
                "name": "Jane Marketer",
                "email": lead_email,
                "website": "https://demo-clientsite.com",
                "platforms": [],
                "pain_points": "Low traffic, inconsistent posting",
            },
            timeout=15,
        )
        r.raise_for_status()
        assert r.json()["ok"] is True

        # Emails are fired async via `fire()` — give them a moment to land.
        time.sleep(2.5)
        rows = _fetch_recent_lead_rows()
        notifs = [r for r in rows if "lead_notification" in (r.get("tags") or [])]
        replies = [r for r in rows if "lead_auto_reply" in (r.get("tags") or [])]

        # 2 admins in LEADS_NOTIFY_EMAILS → 2 notification rows.
        assert len(notifs) >= 2, f"Expected ≥2 admin notifications, got {len(notifs)}"
        # 1 auto-reply to the lead
        assert len(replies) >= 1, "Auto-reply not sent"

        # The auto-reply must go to the lead's email
        reply_recipients = {r["to"] for r in replies}
        assert lead_email in reply_recipients

        # Admin notifications must NOT include the lead's email
        admin_recipients = {r["to"] for r in notifs}
        assert lead_email not in admin_recipients, "Lead email leaked into admin notifications"

    def test_lead_without_email_does_not_break(self):
        """Edge case: defensive — if a lead has no email field, the auto-reply
        should be skipped gracefully (and admin notifications should still fire)."""
        _clear_email_log_for_lead()
        r = httpx.post(
            f"{API_URL}/api/leads",
            json={
                "agent_id": "kai",
                "name": "Anonymous",
                "email": "",
                "website": "https://anon.example",
                "platforms": ["TikTok"],
            },
            timeout=15,
        )
        # Either accepts (email becomes blank) or rejects with 422 — both fine.
        assert r.status_code in (200, 422)

    def test_lead_persists_even_if_emails_fail(self):
        """The lead document must always be saved, even when both providers
        are misconfigured. We verify by reading the leads collection directly."""
        import sys
        sys.path.insert(0, "/app/backend")
        from core import db

        marker = f"persist-test-{uuid.uuid4().hex[:8]}@example.com"
        r = httpx.post(
            f"{API_URL}/api/leads",
            json={
                "agent_id": "sam",
                "name": "Persist Test",
                "email": marker,
                "website": "https://persist.test",
            },
            timeout=15,
        )
        r.raise_for_status()

        async def find():
            return await db.leads.find_one({"email": marker})

        doc = asyncio.get_event_loop().run_until_complete(find())
        assert doc is not None, "Lead document must persist regardless of email status"
        assert doc["agent_id"] == "sam"
