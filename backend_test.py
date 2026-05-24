"""
Backend test suite for Admin and Support endpoints
Tests all 27 test cases as specified in the review request
"""
import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://social-sync-ai-1.preview.emergentagent.com/api"

# Test user tokens (from MongoDB setup)
ADMIN_TOKEN = "admin_session_1779639613774"
U1_TOKEN = "u1_session_1779639613774"
U2_TOKEN = "u2_session_1779639613774"
ADMIN_ID = "user_admin1779639613774"
U1_ID = "user_one1779639613774"
U2_ID = "user_two1779639613774"

# Test results tracking
passed = 0
failed = 0
test_results = []

def test(name, func):
    """Run a test and track results"""
    global passed, failed
    try:
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print('='*60)
        func()
        print(f"✅ PASSED: {name}")
        test_results.append({"name": name, "status": "PASSED", "error": None})
        passed += 1
    except AssertionError as e:
        print(f"❌ FAILED: {name}")
        print(f"   Error: {str(e)}")
        test_results.append({"name": name, "status": "FAILED", "error": str(e)})
        failed += 1
    except Exception as e:
        print(f"❌ ERROR: {name}")
        print(f"   Exception: {str(e)}")
        test_results.append({"name": name, "status": "ERROR", "error": str(e)})
        failed += 1

def get(path, token=None, params=None):
    """Helper for GET requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params)
    print(f"GET {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

def post(path, token=None, data=None, expect_cookie=False):
    """Helper for POST requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post(f"{BASE_URL}{path}", headers=headers, json=data)
    print(f"POST {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
        except:
            print(f"Response: {r.text[:500]}")
    if expect_cookie:
        print(f"Cookies: {r.cookies.get_dict()}")
    return r

def delete(path, token=None):
    """Helper for DELETE requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.delete(f"{BASE_URL}{path}", headers=headers)
    print(f"DELETE {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

# Global variables for test data
ticket_id = None
chat_session_id = None
impersonate_cookie = None

# ==================== SUPPORT TESTS (User 1) ====================

def test_1_faq():
    """GET /api/support/faq — public, returns array of 8 articles"""
    r = get("/support/faq")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    assert len(data) == 8, f"Expected 8 articles, got {len(data)}"
    assert all("id" in a and "title" in a and "body" in a for a in data), "Missing required fields"

def test_2_chat_first():
    """POST /api/support/chat — first message"""
    global chat_session_id
    r = post("/support/chat", token=U1_TOKEN, data={"message": "How do I generate a newsletter?"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "reply" in data, "Missing reply field"
    assert "session_id" in data, "Missing session_id field"
    assert "Content Studio" in data["reply"] or "newsletter" in data["reply"].lower(), "Reply doesn't mention Content Studio or newsletter"
    chat_session_id = data["session_id"]
    print(f"Chat session ID: {chat_session_id}")

def test_3_chat_followup():
    """POST /api/support/chat — follow-up with session_id"""
    assert chat_session_id, "No session_id from previous test"
    r = post("/support/chat", token=U1_TOKEN, data={"message": "What about video scripts?", "session_id": chat_session_id})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "reply" in data, "Missing reply field"
    assert "video" in data["reply"].lower() or "script" in data["reply"].lower(), "Reply doesn't mention video scripts"

def test_4_create_ticket():
    """POST /api/support/tickets — create ticket"""
    global ticket_id
    r = post("/support/tickets", token=U1_TOKEN, data={
        "subject": "Cannot connect Instagram",
        "message": "I clicked connect but nothing happens"
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "id" in data, "Missing id field"
    assert data.get("status") == "open", f"Expected status 'open', got {data.get('status')}"
    ticket_id = data["id"]
    print(f"Ticket ID: {ticket_id}")

def test_5_list_tickets():
    """GET /api/support/tickets — list user's tickets"""
    r = get("/support/tickets", token=U1_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    assert len(data) >= 1, "Expected at least 1 ticket"
    assert any(t["id"] == ticket_id for t in data), "Created ticket not in list"

def test_6_get_ticket():
    """GET /api/support/tickets/{id} — get ticket detail"""
    assert ticket_id, "No ticket_id from previous test"
    r = get(f"/support/tickets/{ticket_id}", token=U1_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "ticket" in data, "Missing ticket field"
    assert "messages" in data, "Missing messages field"
    assert len(data["messages"]) == 1, f"Expected 1 message, got {len(data['messages'])}"
    assert data["messages"][0]["message"] == "I clicked connect but nothing happens", "First message doesn't match"

def test_7_add_ticket_message():
    """POST /api/support/tickets/{id}/message — user adds message"""
    assert ticket_id, "No ticket_id from previous test"
    r = post(f"/support/tickets/{ticket_id}/message", token=U1_TOKEN, data={
        "message": "Also tried in Chrome incognito"
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify status is still "open" (user reply doesn't change status)
    r2 = get(f"/support/tickets/{ticket_id}", token=U1_TOKEN)
    ticket_data = r2.json()
    assert ticket_data["ticket"]["status"] == "open", f"Expected status 'open', got {ticket_data['ticket']['status']}"

# ==================== ADMIN TESTS ====================

def test_8_admin_me():
    """GET /api/admin/me — returns admin user"""
    r = get("/admin/me", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("is_admin") == True, "Expected is_admin: true"
    assert data.get("email") == "williams342@gmail.com", "Wrong admin email"

def test_9_admin_stats():
    """GET /api/admin/stats — returns all count fields"""
    r = get("/admin/stats", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    required_fields = ["total_users", "active_users", "suspended_users", "admins", 
                      "total_leads", "total_posts", "total_reports", "total_channels",
                      "open_tickets", "answered_tickets", "closed_tickets"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
        assert isinstance(data[field], int), f"Field {field} should be int"

def test_10_admin_list_users():
    """GET /api/admin/users — returns array with stats"""
    r = get("/admin/users", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    assert len(data) >= 3, f"Expected at least 3 users, got {len(data)}"
    
    # Check that all test users are present
    user_ids = [u["user_id"] for u in data]
    assert ADMIN_ID in user_ids, "Admin user not in list"
    assert U1_ID in user_ids, "User 1 not in list"
    assert U2_ID in user_ids, "User 2 not in list"
    
    # Check stats structure
    for user in data:
        assert "stats" in user, "Missing stats field"
        assert all(k in user["stats"] for k in ["posts", "leads", "reports", "channels"]), "Missing stats fields"

def test_11_admin_search_users():
    """GET /api/admin/users?q=user1 — filtered list"""
    r = get("/admin/users", token=ADMIN_TOKEN, params={"q": "user1"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    # Should find user1@test.dev
    assert any("user1" in u.get("email", "").lower() or "user one" in u.get("name", "").lower() for u in data), "Search didn't find user1"

def test_12_admin_user_detail():
    """GET /api/admin/users/{U1_ID} — returns user detail"""
    r = get(f"/admin/users/{U1_ID}", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "user" in data, "Missing user field"
    assert "stats" in data, "Missing stats field"
    assert "recent_posts" in data, "Missing recent_posts field"
    assert "recent_leads" in data, "Missing recent_leads field"
    assert data["user"]["user_id"] == U1_ID, "Wrong user returned"

def test_13_admin_suspend():
    """POST /api/admin/users/{U1_ID}/suspend — suspends user"""
    r = post(f"/admin/users/{U1_ID}/suspend", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify user is suspended
    r2 = get(f"/admin/users/{U1_ID}", token=ADMIN_TOKEN)
    user_data = r2.json()
    assert user_data["user"]["status"] == "suspended", "User not suspended"
    
    # Verify U1's session is deleted (should get 401)
    r3 = get("/auth/me", token=U1_TOKEN)
    assert r3.status_code == 401, f"Expected 401 for suspended user's token, got {r3.status_code}"

def test_14_admin_unsuspend():
    """POST /api/admin/users/{U1_ID}/unsuspend — unsuspends user"""
    r = post(f"/admin/users/{U1_ID}/unsuspend", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify user is active
    r2 = get(f"/admin/users/{U1_ID}", token=ADMIN_TOKEN)
    user_data = r2.json()
    assert user_data["user"]["status"] == "active", "User not active"

def test_15_admin_promote():
    """POST /api/admin/users/{U2_ID}/promote — promotes to admin"""
    r = post(f"/admin/users/{U2_ID}/promote", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify user is admin
    r2 = get(f"/admin/users/{U2_ID}", token=ADMIN_TOKEN)
    user_data = r2.json()
    assert user_data["user"]["is_admin"] == True, "User not promoted to admin"

def test_16_admin_demote():
    """POST /api/admin/users/{U2_ID}/demote — demotes from admin"""
    r = post(f"/admin/users/{U2_ID}/demote", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify user is not admin
    r2 = get(f"/admin/users/{U2_ID}", token=ADMIN_TOKEN)
    user_data = r2.json()
    assert user_data["user"]["is_admin"] == False, "User still admin"

def test_17_admin_suspend_self():
    """POST /api/admin/users/{ADMIN_ID}/suspend — should return 400"""
    r = post(f"/admin/users/{ADMIN_ID}/suspend", token=ADMIN_TOKEN)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    data = r.json()
    assert "yourself" in data.get("detail", "").lower(), "Wrong error message"

def test_18_admin_demote_self():
    """POST /api/admin/users/{ADMIN_ID}/demote — should return 400"""
    r = post(f"/admin/users/{ADMIN_ID}/demote", token=ADMIN_TOKEN)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    data = r.json()
    assert "yourself" in data.get("detail", "").lower(), "Wrong error message"

def test_19_admin_impersonate():
    """POST /api/admin/users/{U2_ID}/impersonate — impersonate user"""
    global impersonate_cookie
    r = post(f"/admin/users/{U2_ID}/impersonate", token=ADMIN_TOKEN, expect_cookie=True)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    assert "impersonating" in data, "Missing impersonating field"
    assert data["impersonating"]["user_id"] == U2_ID, "Wrong user being impersonated"
    
    # Get the new session token from cookies
    impersonate_cookie = r.cookies.get("session_token")
    assert impersonate_cookie, "No session_token cookie returned"
    print(f"Impersonate token: {impersonate_cookie}")
    
    # Verify /api/auth/me returns User Two's data
    r2 = get("/auth/me", token=impersonate_cookie)
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    me_data = r2.json()
    assert me_data["user_id"] == U2_ID, f"Expected User Two's ID, got {me_data.get('user_id')}"
    assert me_data["name"] == "User Two", f"Expected 'User Two', got {me_data.get('name')}"

def test_20_admin_stop_impersonate():
    """POST /api/admin/stop-impersonating — restore admin"""
    assert impersonate_cookie, "No impersonate cookie from previous test"
    r = post("/admin/stop-impersonating", token=impersonate_cookie, expect_cookie=True)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Get restored cookie
    restored_cookie = r.cookies.get("session_token")
    assert restored_cookie, "No session_token cookie returned"
    
    # Verify it's the admin again
    r2 = get("/auth/me", token=restored_cookie)
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    me_data = r2.json()
    assert me_data["user_id"] == ADMIN_ID, f"Expected admin ID, got {me_data.get('user_id')}"

def test_21_admin_list_tickets():
    """GET /api/admin/tickets — list all tickets"""
    r = get("/admin/tickets", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    assert len(data) >= 1, "Expected at least 1 ticket"
    assert any(t["id"] == ticket_id for t in data), "Test ticket not in admin list"

def test_22_admin_filter_tickets():
    """GET /api/admin/tickets?status=open — filtered tickets"""
    r = get("/admin/tickets", token=ADMIN_TOKEN, params={"status": "open"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    # All returned tickets should have status "open"
    assert all(t["status"] == "open" for t in data), "Non-open tickets in filtered list"

def test_23_admin_reply_ticket():
    """POST /api/support/tickets/{ticket_id}/message as ADMIN — status becomes 'answered'"""
    assert ticket_id, "No ticket_id from previous test"
    r = post(f"/support/tickets/{ticket_id}/message", token=ADMIN_TOKEN, data={
        "message": "Hi, we're looking into this."
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify status changed to "answered"
    r2 = get(f"/support/tickets/{ticket_id}", token=ADMIN_TOKEN)
    ticket_data = r2.json()
    assert ticket_data["ticket"]["status"] == "answered", f"Expected status 'answered', got {ticket_data['ticket']['status']}"

def test_24_admin_close_ticket():
    """POST /api/support/tickets/{ticket_id}/close — status becomes 'closed'"""
    assert ticket_id, "No ticket_id from previous test"
    r = post(f"/support/tickets/{ticket_id}/close", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify status is "closed"
    r2 = get(f"/support/tickets/{ticket_id}", token=ADMIN_TOKEN)
    ticket_data = r2.json()
    assert ticket_data["ticket"]["status"] == "closed", f"Expected status 'closed', got {ticket_data['ticket']['status']}"

def test_25_admin_delete_user():
    """DELETE /api/admin/users/{U2_ID} — cascades delete"""
    r = delete(f"/admin/users/{U2_ID}", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify user is gone
    r2 = get(f"/admin/users/{U2_ID}", token=ADMIN_TOKEN)
    assert r2.status_code == 404, f"Expected 404, got {r2.status_code}"
    
    # Verify U2's session is gone (should get 401)
    r3 = get("/auth/me", token=U2_TOKEN)
    assert r3.status_code == 401, f"Expected 401 for deleted user's token, got {r3.status_code}"

def test_26_admin_delete_self():
    """DELETE /api/admin/users/{ADMIN_ID} — should return 400"""
    r = delete(f"/admin/users/{ADMIN_ID}", token=ADMIN_TOKEN)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    data = r.json()
    assert "yourself" in data.get("detail", "").lower(), "Wrong error message"

def test_27_non_admin_access():
    """GET /api/admin/me with U1_TOKEN — should be 403"""
    # First, recreate U1's session since it was deleted during suspend test
    import pymongo
    mongo_client = pymongo.MongoClient("mongodb://localhost:27017")
    db = mongo_client["test_database"]
    from datetime import datetime, timedelta
    db.user_sessions.insert_one({
        "user_id": U1_ID,
        "session_token": U1_TOKEN,
        "expires_at": datetime.utcnow() + timedelta(days=7),
        "created_at": datetime.utcnow()
    })
    
    r = get("/admin/me", token=U1_TOKEN)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    data = r.json()
    assert "admin" in data.get("detail", "").lower(), "Wrong error message"

# ==================== CLEANUP ====================

def cleanup():
    """Delete all test users and related data"""
    print("\n" + "="*60)
    print("CLEANUP: Deleting test users and data")
    print("="*60)
    
    import pymongo
    mongo_client = pymongo.MongoClient("mongodb://localhost:27017")
    db = mongo_client["test_database"]
    
    # Delete test users
    result = db.users.delete_many({"user_id": {"$in": [ADMIN_ID, U1_ID, U2_ID]}})
    print(f"Deleted {result.deleted_count} users")
    
    # Delete sessions
    result = db.user_sessions.delete_many({"user_id": {"$in": [ADMIN_ID, U1_ID, U2_ID]}})
    print(f"Deleted {result.deleted_count} sessions")
    
    # Delete tickets
    result = db.tickets.delete_many({"user_id": {"$in": [ADMIN_ID, U1_ID, U2_ID]}})
    print(f"Deleted {result.deleted_count} tickets")
    
    # Delete ticket messages
    result = db.ticket_messages.delete_many({"author_id": {"$in": [ADMIN_ID, U1_ID, U2_ID]}})
    print(f"Deleted {result.deleted_count} ticket messages")
    
    # Delete support chat logs
    result = db.support_chat_log.delete_many({"user_id": {"$in": [ADMIN_ID, U1_ID, U2_ID]}})
    print(f"Deleted {result.deleted_count} chat logs")
    
    print("✅ Cleanup complete")

# ==================== RUN ALL TESTS ====================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("BACKEND TEST SUITE: Admin + Support Endpoints")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin Token: {ADMIN_TOKEN}")
    print(f"User 1 Token: {U1_TOKEN}")
    print(f"User 2 Token: {U2_TOKEN}")
    
    # Support tests (User 1)
    test("1. GET /api/support/faq", test_1_faq)
    test("2. POST /api/support/chat (first message)", test_2_chat_first)
    test("3. POST /api/support/chat (follow-up)", test_3_chat_followup)
    test("4. POST /api/support/tickets (create)", test_4_create_ticket)
    test("5. GET /api/support/tickets (list)", test_5_list_tickets)
    test("6. GET /api/support/tickets/{id} (detail)", test_6_get_ticket)
    test("7. POST /api/support/tickets/{id}/message (user reply)", test_7_add_ticket_message)
    
    # Admin tests
    test("8. GET /api/admin/me", test_8_admin_me)
    test("9. GET /api/admin/stats", test_9_admin_stats)
    test("10. GET /api/admin/users", test_10_admin_list_users)
    test("11. GET /api/admin/users?q=user1", test_11_admin_search_users)
    test("12. GET /api/admin/users/{U1_ID}", test_12_admin_user_detail)
    test("13. POST /api/admin/users/{U1_ID}/suspend", test_13_admin_suspend)
    test("14. POST /api/admin/users/{U1_ID}/unsuspend", test_14_admin_unsuspend)
    test("15. POST /api/admin/users/{U2_ID}/promote", test_15_admin_promote)
    test("16. POST /api/admin/users/{U2_ID}/demote", test_16_admin_demote)
    test("17. POST /api/admin/users/{ADMIN_ID}/suspend (self)", test_17_admin_suspend_self)
    test("18. POST /api/admin/users/{ADMIN_ID}/demote (self)", test_18_admin_demote_self)
    test("19. POST /api/admin/users/{U2_ID}/impersonate", test_19_admin_impersonate)
    test("20. POST /api/admin/stop-impersonating", test_20_admin_stop_impersonate)
    test("21. GET /api/admin/tickets", test_21_admin_list_tickets)
    test("22. GET /api/admin/tickets?status=open", test_22_admin_filter_tickets)
    test("23. POST /api/support/tickets/{id}/message (admin reply)", test_23_admin_reply_ticket)
    test("24. POST /api/support/tickets/{id}/close", test_24_admin_close_ticket)
    test("25. DELETE /api/admin/users/{U2_ID}", test_25_admin_delete_user)
    test("26. DELETE /api/admin/users/{ADMIN_ID} (self)", test_26_admin_delete_self)
    test("27. GET /api/admin/me with U1_TOKEN (non-admin)", test_27_non_admin_access)
    
    # Cleanup
    cleanup()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Total: {passed + failed}")
    print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")
    
    if failed > 0:
        print("\n" + "="*60)
        print("FAILED TESTS:")
        print("="*60)
        for result in test_results:
            if result["status"] != "PASSED":
                print(f"❌ {result['name']}")
                print(f"   {result['error']}")
    
    sys.exit(0 if failed == 0 else 1)
