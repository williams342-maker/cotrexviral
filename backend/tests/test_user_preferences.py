"""Backend tests for /api/user/preferences (Command Center conversation_mode).

Verifies the GET/PUT endpoints introduced for the Conversation Mode toggle.
- Defaults merge (unset → conversation_mode='fresh_every_visit')
- Persistence via PUT, GET reflects update
- Validation: bad value, unknown key, empty body
- Auth: 401 without Bearer token
"""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://social-sync-ai-1.preview.emergentagent.com").rstrip("/")
TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Use the same Mongo as backend (read from backend/.env)
def _mongo_url():
    p = "/app/backend/.env"
    url, db = None, None
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line.startswith("MONGO_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("DB_NAME="):
                db = line.split("=", 1)[1].strip().strip('"').strip("'")
    return url, db


@pytest.fixture(scope="module")
def db():
    url, name = _mongo_url()
    client = MongoClient(url)
    return client[name]


def _reset_prefs():
    """Reset the test user's preferences to default state ($unset)."""
    url, name = _mongo_url()
    client = MongoClient(url)
    client[name].users.update_one(
        {"user_id": USER_ID},
        {"$unset": {"preferences": ""}},
        upsert=False,
    )
    client.close()


@pytest.fixture(autouse=True)
def reset_before_each():
    _reset_prefs()
    yield
    _reset_prefs()


# ---------------------------------------------------------------------
# GET /api/user/preferences
# ---------------------------------------------------------------------
class TestGetPreferences:
    def test_default_when_unset(self):
        r = requests.get(f"{BASE_URL}/api/user/preferences", headers=H, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "preferences" in data
        assert data["preferences"]["conversation_mode"] == "fresh_every_visit"

    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/user/preferences", timeout=20)
        assert r.status_code == 401, r.text


# ---------------------------------------------------------------------
# PUT /api/user/preferences
# ---------------------------------------------------------------------
class TestPutPreferences:
    def test_put_resume_last_persists(self):
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         headers=H, json={"conversation_mode": "resume_last"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["preferences"]["conversation_mode"] == "resume_last"

        # GET reflects the update
        g = requests.get(f"{BASE_URL}/api/user/preferences", headers=H, timeout=20)
        assert g.status_code == 200
        assert g.json()["preferences"]["conversation_mode"] == "resume_last"

    def test_put_back_to_fresh(self):
        # First set to resume_last
        requests.put(f"{BASE_URL}/api/user/preferences",
                     headers=H, json={"conversation_mode": "resume_last"}, timeout=20)
        # Then back to fresh
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         headers=H, json={"conversation_mode": "fresh_every_visit"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["preferences"]["conversation_mode"] == "fresh_every_visit"

    def test_invalid_value_returns_422(self):
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         headers=H, json={"conversation_mode": "never"}, timeout=20)
        assert r.status_code == 422, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "never" in detail or "invalid" in detail or "conversation_mode" in detail

    def test_unknown_key_returns_422(self):
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         headers=H, json={"random_key": "v"}, timeout=20)
        assert r.status_code == 422, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "random_key" in detail or "unknown" in detail

    def test_empty_body_returns_422(self):
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         headers=H, json={}, timeout=20)
        assert r.status_code == 422, r.text

    def test_requires_auth(self):
        r = requests.put(f"{BASE_URL}/api/user/preferences",
                         json={"conversation_mode": "resume_last"},
                         headers={"Content-Type": "application/json"},
                         timeout=20)
        assert r.status_code == 401, r.text


# ---------------------------------------------------------------------
# Defaults merge — if a user has a saved value, GET still returns the
# full preferences dict (just with that key overridden).
# ---------------------------------------------------------------------
class TestDefaultsMerge:
    def test_saved_value_is_returned_merged_with_defaults(self):
        # Save resume_last
        put_r = requests.put(f"{BASE_URL}/api/user/preferences",
                             headers=H, json={"conversation_mode": "resume_last"}, timeout=20)
        assert put_r.status_code == 200
        # GET returns full dict — currently only conversation_mode key
        g = requests.get(f"{BASE_URL}/api/user/preferences", headers=H, timeout=20)
        prefs = g.json()["preferences"]
        assert prefs["conversation_mode"] == "resume_last"
        # Sanity: dict is not empty / contains the default-known keys
        assert isinstance(prefs, dict)
        assert len(prefs) >= 1
