"""
Backend test suite for NEW Audit Log + Broadcast endpoints
Tests 19 test cases as specified in the review request
"""
import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://social-sync-ai-1.preview.emergentagent.com/api"

# Test user tokens (will be set after MongoDB setup)
ADMIN_TOKEN = None
U_TOKEN = None
ADMIN_ID = None
U_ID = None

# Test results tracking
passed = 0
failed = 0
test_results = []

# Test data
broadcast_id1 = None
broadcast_id2 = None

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
            resp_json = r.json()
            print(f"Response: {json.dumps(resp_json, indent=2)[:800]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

def post(path, token=None, data=None):
    """Helper for POST requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post(f"{BASE_URL}{path}", headers=headers, json=data)
    print(f"POST {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            resp_json = r.json()
            print(f"Response: {json.dumps(resp_json, indent=2)[:800]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

def patch(path, token=None, data=None):
    """Helper for PATCH requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.patch(f"{BASE_URL}{path}", headers=headers, json=data)
    print(f"PATCH {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            resp_json = r.json()
            print(f"Response: {json.dumps(resp_json, indent=2)[:800]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

def delete(path, token=None):
    """Helper for DELETE requests"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.delete(f"{BASE_URL}{path}", headers=headers)
    print(f"DELETE {path} -> {r.status_code}")
    if r.status_code != 204:
        try:
            resp_json = r.json()
            print(f"Response: {json.dumps(resp_json, indent=2)[:800]}")
        except:
            print(f"Response: {r.text[:500]}")
    return r

# ==================== BROADCAST TESTS ====================

def test_1_create_broadcast_1():
    """POST /api/admin/broadcasts as admin — payload: {"title": "Maintenance tonight", "body": "Brief downtime at 11pm UTC", "severity": "warning", "active": true}"""
    global broadcast_id1
    r = post("/admin/broadcasts", token=ADMIN_TOKEN, data={
        "title": "Maintenance tonight",
        "body": "Brief downtime at 11pm UTC",
        "severity": "warning",
        "active": True
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "id" in data, "Missing id field"
    assert data["title"] == "Maintenance tonight", "Title mismatch"
    assert data["severity"] == "warning", "Severity mismatch"
    assert data["active"] == True, "Active should be true"
    broadcast_id1 = data["id"]
    print(f"Broadcast 1 ID: {broadcast_id1}")

def test_2_create_broadcast_2():
    """POST /api/admin/broadcasts as admin — payload: {"title": "New feature live", "body": "Try Content Studio", "severity": "success"}"""
    global broadcast_id2
    r = post("/admin/broadcasts", token=ADMIN_TOKEN, data={
        "title": "New feature live",
        "body": "Try Content Studio",
        "severity": "success"
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "id" in data, "Missing id field"
    assert data["title"] == "New feature live", "Title mismatch"
    assert data["severity"] == "success", "Severity mismatch"
    # active defaults to true
    assert data.get("active", True) == True, "Active should default to true"
    broadcast_id2 = data["id"]
    print(f"Broadcast 2 ID: {broadcast_id2}")

def test_3_admin_list_broadcasts():
    """GET /api/admin/broadcasts as admin — returns array with both broadcasts"""
    r = get("/admin/broadcasts", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    assert len(data) >= 2, f"Expected at least 2 broadcasts, got {len(data)}"
    ids = [b["id"] for b in data]
    assert broadcast_id1 in ids, "Broadcast 1 not in list"
    assert broadcast_id2 in ids, "Broadcast 2 not in list"

def test_4_user_active_broadcasts():
    """GET /api/broadcasts/active as REGULAR USER — returns only active=true ones (both)"""
    r = get("/broadcasts/active", token=U_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    # Both broadcasts should be active
    assert len(data) >= 2, f"Expected at least 2 active broadcasts, got {len(data)}"
    ids = [b["id"] for b in data]
    assert broadcast_id1 in ids, "Broadcast 1 not in active list"
    assert broadcast_id2 in ids, "Broadcast 2 not in active list"
    # All should have active=true
    for b in data:
        assert b.get("active") == True, f"Broadcast {b['id']} should be active"

def test_5_update_broadcast_deactivate():
    """PATCH /api/admin/broadcasts/{id1} as admin — payload: {"active": false} → 200 ok"""
    r = patch(f"/admin/broadcasts/{broadcast_id1}", token=ADMIN_TOKEN, data={"active": False})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"

def test_6_user_active_broadcasts_after_deactivate():
    """GET /api/broadcasts/active as REGULAR USER — returns only the still-active one (#2)"""
    r = get("/broadcasts/active", token=U_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    ids = [b["id"] for b in data]
    assert broadcast_id1 not in ids, "Broadcast 1 should not be in active list (was deactivated)"
    assert broadcast_id2 in ids, "Broadcast 2 should still be in active list"

def test_7_update_broadcast_title():
    """PATCH /api/admin/broadcasts/{id1} — payload: {"title": "Updated maintenance"} → 200"""
    r = patch(f"/admin/broadcasts/{broadcast_id1}", token=ADMIN_TOKEN, data={"title": "Updated maintenance"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Verify title was updated
    r2 = get("/admin/broadcasts", token=ADMIN_TOKEN)
    broadcasts = r2.json()
    b1 = next((b for b in broadcasts if b["id"] == broadcast_id1), None)
    assert b1 is not None, "Broadcast 1 not found"
    assert b1["title"] == "Updated maintenance", f"Title not updated, got {b1['title']}"

def test_8_delete_broadcast():
    """DELETE /api/admin/broadcasts/{id1} as admin — 200 ok"""
    r = delete(f"/admin/broadcasts/{broadcast_id1}", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"

def test_9_user_active_broadcasts_after_delete():
    """GET /api/broadcasts/active as regular user — only 1 left"""
    r = get("/broadcasts/active", token=U_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    ids = [b["id"] for b in data]
    assert broadcast_id1 not in ids, "Broadcast 1 should not be in list (was deleted)"
    assert broadcast_id2 in ids, "Broadcast 2 should still be in list"

def test_10_broadcast_non_admin():
    """POST /api/admin/broadcasts as REGULAR USER → 403 Admin access required"""
    r = post("/admin/broadcasts", token=U_TOKEN, data={
        "title": "Test",
        "body": "Should fail",
        "severity": "info"
    })
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    data = r.json()
    assert "admin" in data.get("detail", "").lower(), "Expected 'Admin access required' message"

def test_11_broadcast_no_auth():
    """GET /api/broadcasts/active without auth → 401"""
    r = get("/broadcasts/active")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"

# ==================== AUDIT LOG TESTS ====================

def test_12_suspend_writes_audit():
    """POST /api/admin/users/{U_ID}/suspend as admin — should write audit log entry"""
    r = post(f"/admin/users/{U_ID}/suspend", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"

def test_13_unsuspend_writes_audit():
    """POST /api/admin/users/{U_ID}/unsuspend as admin — writes log"""
    r = post(f"/admin/users/{U_ID}/unsuspend", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    
    # Recreate user session (since suspend deleted it)
    import pymongo
    from datetime import timedelta
    mongo_client = pymongo.MongoClient("mongodb://localhost:27017")
    db = mongo_client["test_database"]
    db.user_sessions.insert_one({
        "user_id": U_ID,
        "session_token": U_TOKEN,
        "expires_at": datetime.now() + timedelta(days=7),
        "created_at": datetime.now()
    })
    print(f"Recreated session for user {U_ID}")

def test_14_promote_writes_audit():
    """POST /api/admin/users/{U_ID}/promote — writes log"""
    r = post(f"/admin/users/{U_ID}/promote", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"

def test_15_demote_writes_audit():
    """POST /api/admin/users/{U_ID}/demote — writes log"""
    r = post(f"/admin/users/{U_ID}/demote", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"

def test_16_impersonate_writes_audit():
    """POST /api/admin/users/{U_ID}/impersonate — writes log"""
    r = post(f"/admin/users/{U_ID}/impersonate", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("ok") == True, "Expected ok: true"
    assert "impersonating" in data, "Missing impersonating field"

def test_17_audit_log_list():
    """GET /api/admin/audit-log as admin — returns array sorted by created_at desc"""
    r = get("/admin/audit-log", token=ADMIN_TOKEN)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert isinstance(data, list), "Expected array"
    
    # Should have entries for: create_broadcast (2), update_broadcast (2), delete_broadcast (1),
    # suspend_user, unsuspend_user, promote_admin, demote_admin, impersonate_user
    # Total: at least 9 entries
    assert len(data) >= 9, f"Expected at least 9 audit log entries, got {len(data)}"
    
    # Check required fields
    for entry in data:
        assert "id" in entry, "Missing id field"
        assert "admin_id" in entry, "Missing admin_id field"
        assert "admin_email" in entry, "Missing admin_email field"
        assert "admin_name" in entry, "Missing admin_name field"
        assert "action" in entry, "Missing action field"
        assert "created_at" in entry, "Missing created_at field"
        # target_user_id and target_email are optional (not present for broadcasts)
    
    # Check for specific actions
    actions = [e["action"] for e in data]
    assert "create_broadcast" in actions, "Missing create_broadcast action"
    assert "update_broadcast" in actions, "Missing update_broadcast action"
    assert "delete_broadcast" in actions, "Missing delete_broadcast action"
    assert "suspend_user" in actions, "Missing suspend_user action"
    assert "unsuspend_user" in actions, "Missing unsuspend_user action"
    assert "promote_admin" in actions, "Missing promote_admin action"
    assert "demote_admin" in actions, "Missing demote_admin action"
    assert "impersonate_user" in actions, "Missing impersonate_user action"
    
    # Verify sorted by created_at desc (most recent first)
    if len(data) > 1:
        for i in range(len(data) - 1):
            t1 = datetime.fromisoformat(data[i]["created_at"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(data[i+1]["created_at"].replace("Z", "+00:00"))
            assert t1 >= t2, f"Audit log not sorted by created_at desc: {data[i]['created_at']} < {data[i+1]['created_at']}"
    
    print(f"Found {len(data)} audit log entries")
    print(f"Actions: {set(actions)}")

def test_18_audit_log_non_admin():
    """GET /api/admin/audit-log as REGULAR USER → 403"""
    r = get("/admin/audit-log", token=U_TOKEN)
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    data = r.json()
    assert "admin" in data.get("detail", "").lower(), "Expected 'Admin access required' message"

# ==================== SUSPENDED USER TEST ====================

def test_19_suspended_user_403():
    """Update U_ID's status to 'suspended' in DB. Then call /api/auth/me with U_TOK → expect 403 'Account suspended'"""
    import pymongo
    mongo_client = pymongo.MongoClient("mongodb://localhost:27017")
    db = mongo_client["test_database"]
    
    # Suspend the user
    db.users.update_one({"user_id": U_ID}, {"$set": {"status": "suspended"}})
    print(f"Suspended user {U_ID} in database")
    
    # Try to access /api/auth/me
    r = get("/auth/me", token=U_TOKEN)
    assert r.status_code == 403, f"Expected 403 for suspended user, got {r.status_code}"
    data = r.json()
    assert "suspended" in data.get("detail", "").lower(), f"Expected 'Account suspended' message, got {data.get('detail')}"
    
    # Restore user status for cleanup
    db.users.update_one({"user_id": U_ID}, {"$set": {"status": "active"}})
    print(f"Restored user {U_ID} to active status")

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
    result = db.users.delete_many({"user_id": {"$in": [ADMIN_ID, U_ID]}})
    print(f"Deleted {result.deleted_count} users")
    
    # Delete sessions
    result = db.user_sessions.delete_many({"user_id": {"$in": [ADMIN_ID, U_ID]}})
    print(f"Deleted {result.deleted_count} sessions")
    
    # Delete broadcasts (only the test ones)
    result = db.broadcasts.delete_many({"id": {"$in": [broadcast_id1, broadcast_id2]}})
    print(f"Deleted {result.deleted_count} broadcasts")
    
    # Delete audit log entries for test admin
    result = db.audit_log.delete_many({"admin_id": ADMIN_ID})
    print(f"Deleted {result.deleted_count} audit log entries")
    
    print("✅ Cleanup complete")

# ==================== SETUP ====================

def setup():
    """Create test users via mongosh"""
    global ADMIN_TOKEN, U_TOKEN, ADMIN_ID, U_ID
    
    print("\n" + "="*60)
    print("SETUP: Creating test users via mongosh")
    print("="*60)
    
    import subprocess
    import re
    
    timestamp = int(datetime.now().timestamp() * 1000)
    admin_id = f"audit_admin{timestamp}"
    u_id = f"audit_user{timestamp}"
    admin_tok = f"audit_admin_tok_{timestamp}"
    u_tok = f"audit_user_tok_{timestamp}"
    
    mongo_cmd = f"""
mongosh "mongodb://localhost:27017/test_database" --quiet --eval "
var adminId = '{admin_id}';
var uId = '{u_id}';
var adminTok = '{admin_tok}';
var uTok = '{u_tok}';
db.users.insertOne({{user_id: adminId, email: 'williams342@gmail.com', name: 'Admin', is_admin: true, status: 'active', created_at: new Date()}});
db.users.insertOne({{user_id: uId, email: 'reguser@test.dev', name: 'Reg User', is_admin: false, status: 'active', created_at: new Date()}});
db.user_sessions.insertOne({{user_id: adminId, session_token: adminTok, expires_at: new Date(Date.now()+7*86400000), created_at: new Date()}});
db.user_sessions.insertOne({{user_id: uId, session_token: uTok, expires_at: new Date(Date.now()+7*86400000), created_at: new Date()}});
print('ADMIN_TOK='+adminTok); print('U_TOK='+uTok); print('ADMIN_ID='+adminId); print('U_ID='+uId);
"
"""
    
    result = subprocess.run(mongo_cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    
    # Parse output
    ADMIN_TOKEN = admin_tok
    U_TOKEN = u_tok
    ADMIN_ID = admin_id
    U_ID = u_id
    
    print(f"✅ Created admin user: {ADMIN_ID}")
    print(f"✅ Created regular user: {U_ID}")
    print(f"✅ Admin token: {ADMIN_TOKEN}")
    print(f"✅ User token: {U_TOKEN}")

# ==================== RUN ALL TESTS ====================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("BACKEND TEST SUITE: Audit Log + Broadcast Endpoints")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    
    # Setup
    setup()
    
    # Broadcast tests
    test("1. POST /api/admin/broadcasts (maintenance)", test_1_create_broadcast_1)
    test("2. POST /api/admin/broadcasts (new feature)", test_2_create_broadcast_2)
    test("3. GET /api/admin/broadcasts (admin list)", test_3_admin_list_broadcasts)
    test("4. GET /api/broadcasts/active (user - both active)", test_4_user_active_broadcasts)
    test("5. PATCH /api/admin/broadcasts/{id1} (deactivate)", test_5_update_broadcast_deactivate)
    test("6. GET /api/broadcasts/active (user - one active)", test_6_user_active_broadcasts_after_deactivate)
    test("7. PATCH /api/admin/broadcasts/{id1} (update title)", test_7_update_broadcast_title)
    test("8. DELETE /api/admin/broadcasts/{id1}", test_8_delete_broadcast)
    test("9. GET /api/broadcasts/active (user - one left)", test_9_user_active_broadcasts_after_delete)
    test("10. POST /api/admin/broadcasts as regular user (403)", test_10_broadcast_non_admin)
    test("11. GET /api/broadcasts/active without auth (401)", test_11_broadcast_no_auth)
    
    # Audit log tests
    test("12. POST /api/admin/users/{U_ID}/suspend (writes audit)", test_12_suspend_writes_audit)
    test("13. POST /api/admin/users/{U_ID}/unsuspend (writes audit)", test_13_unsuspend_writes_audit)
    test("14. POST /api/admin/users/{U_ID}/promote (writes audit)", test_14_promote_writes_audit)
    test("15. POST /api/admin/users/{U_ID}/demote (writes audit)", test_15_demote_writes_audit)
    test("16. POST /api/admin/users/{U_ID}/impersonate (writes audit)", test_16_impersonate_writes_audit)
    test("17. GET /api/admin/audit-log (admin - list all)", test_17_audit_log_list)
    test("18. GET /api/admin/audit-log as regular user (403)", test_18_audit_log_non_admin)
    
    # Suspended user test
    test("19. Suspended user gets 403 on /api/auth/me", test_19_suspended_user_403)
    
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
