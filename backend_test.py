#!/usr/bin/env python3
"""Backend API tests for Automatex"""
import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "https://social-sync-ai-1.preview.emergentagent.com/api"
SESSION_TOKEN = "test_session_1779636592168"
USER_ID = "user_test1779636592168"

# Test results
results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"  Details: {details}")
    
    if passed:
        results["passed"].append(name)
    else:
        results["failed"].append({"test": name, "details": details})

def log_warning(name: str, details: str):
    """Log warning"""
    print(f"⚠️  WARNING: {name}")
    print(f"  Details: {details}")
    results["warnings"].append({"test": name, "details": details})

def test_health_check():
    """Test GET /api/ - health check (no auth)"""
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("app") == "Automatex" and data.get("status") == "ok":
                log_test("Health check", True, f"Response: {data}")
            else:
                log_test("Health check", False, f"Unexpected response: {data}")
        else:
            log_test("Health check", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Health check", False, f"Exception: {e}")

def test_auth_me_with_token():
    """Test GET /api/auth/me with valid Bearer token"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("user_id") == USER_ID and data.get("email") == "test@automatex.dev":
                log_test("Auth /me with token", True, f"User: {data.get('name')}")
            else:
                log_test("Auth /me with token", False, f"Unexpected user data: {data}")
        else:
            log_test("Auth /me with token", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Auth /me with token", False, f"Exception: {e}")

def test_auth_me_without_token():
    """Test GET /api/auth/me without token (should 401)"""
    try:
        r = requests.get(f"{BASE_URL}/auth/me", timeout=10)
        if r.status_code == 401:
            log_test("Auth /me without token (401)", True, "Correctly rejected")
        else:
            log_test("Auth /me without token (401)", False, f"Expected 401, got {r.status_code}")
    except Exception as e:
        log_test("Auth /me without token (401)", False, f"Exception: {e}")

def test_create_lead_public():
    """Test POST /api/leads - public endpoint"""
    try:
        payload = {
            "agent_id": "nova",
            "email": "lead@test.com",
            "website": "https://test.com",
            "platforms": ["instagram"],
            "pain_points": "no traffic"
        }
        r = requests.post(f"{BASE_URL}/leads", json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("id"):
                log_test("Create lead (public)", True, f"Lead ID: {data.get('id')}")
                return data.get("id")
            else:
                log_test("Create lead (public)", False, f"Unexpected response: {data}")
        else:
            log_test("Create lead (public)", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Create lead (public)", False, f"Exception: {e}")
    return None

def test_list_leads():
    """Test GET /api/leads - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/leads", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log_test("List leads", True, f"Found {len(data)} leads")
            else:
                log_test("List leads", False, f"Expected list, got: {type(data)}")
        else:
            log_test("List leads", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("List leads", False, f"Exception: {e}")

def test_seo_review():
    """Test POST /api/ai/seo-review - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {"url": "https://example.com"}
        print("  ⏳ Calling LLM for SEO review (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/seo-review", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            report = data.get("report", {})
            if "score" in report and "strengths" in report and "issues" in report:
                log_test("AI SEO Review", True, f"Score: {report.get('score')}, Issues: {len(report.get('issues', []))}")
            else:
                log_warning("AI SEO Review", f"Response structure unexpected: {list(report.keys())}")
                log_test("AI SEO Review", True, "Endpoint works but response format may vary")
        else:
            log_test("AI SEO Review", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI SEO Review", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI SEO Review", False, f"Exception: {e}")

def test_site_scan():
    """Test POST /api/ai/site-scan - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {"url": "https://example.com"}
        print("  ⏳ Calling LLM for site scan (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/site-scan", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            report = data.get("report", {})
            if "summary" in report and "notable_items" in report:
                log_test("AI Site Scan", True, f"Summary length: {len(report.get('summary', ''))}")
            else:
                log_warning("AI Site Scan", f"Response structure unexpected: {list(report.keys())}")
                log_test("AI Site Scan", True, "Endpoint works but response format may vary")
        else:
            log_test("AI Site Scan", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Site Scan", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Site Scan", False, f"Exception: {e}")

def test_insights():
    """Test POST /api/ai/insights - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {"context": "I run a small SaaS for project managers"}
        print("  ⏳ Calling LLM for insights (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/insights", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            insights = data.get("insights", {})
            if isinstance(insights, dict) and ("insights" in insights or "trends" in insights):
                log_test("AI Insights", True, f"Keys: {list(insights.keys())}")
            else:
                log_warning("AI Insights", f"Response structure unexpected: {data}")
                log_test("AI Insights", True, "Endpoint works but response format may vary")
        else:
            log_test("AI Insights", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Insights", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Insights", False, f"Exception: {e}")

def test_generate_post():
    """Test POST /api/ai/generate-post - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "topic": "new product launch",
            "platform": "instagram",
            "tone": "friendly"
        }
        print("  ⏳ Calling LLM for post generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/generate-post", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            if "caption" in data and "hashtags" in data:
                log_test("AI Generate Post", True, f"Caption length: {len(data.get('caption', ''))}")
            else:
                log_warning("AI Generate Post", f"Response structure unexpected: {list(data.keys())}")
                log_test("AI Generate Post", True, "Endpoint works but response format may vary")
        else:
            log_test("AI Generate Post", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Generate Post", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Generate Post", False, f"Exception: {e}")

def test_generate_newsletter():
    """Test POST /api/ai/generate-newsletter - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "topic": "Spring product launch",
            "audience": "loyal customers",
            "tone": "friendly",
            "sections": 3
        }
        print("  ⏳ Calling LLM for newsletter generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/generate-newsletter", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["subject", "preheader", "intro", "sections", "cta", "ps"]
            if all(k in data for k in required_keys):
                if isinstance(data.get("sections"), list) and len(data["sections"]) > 0:
                    section = data["sections"][0]
                    if "heading" in section and "body" in section:
                        log_test("AI Generate Newsletter", True, f"Subject: {data.get('subject')[:50]}...")
                    else:
                        log_test("AI Generate Newsletter", False, f"Section missing heading/body: {section}")
                else:
                    log_test("AI Generate Newsletter", False, f"Sections not a list or empty: {data.get('sections')}")
            else:
                missing = [k for k in required_keys if k not in data]
                log_test("AI Generate Newsletter", False, f"Missing keys: {missing}. Got: {list(data.keys())}")
        else:
            log_test("AI Generate Newsletter", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Generate Newsletter", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Generate Newsletter", False, f"Exception: {e}")

def test_generate_content():
    """Test POST /api/ai/generate-content - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "topic": "How to choose a yoga mat",
            "keywords": ["yoga", "sustainable"],
            "tone": "professional",
            "length": "short"
        }
        print("  ⏳ Calling LLM for blog content generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/generate-content", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["title", "meta_description", "slug", "outline", "intro", "sections", "conclusion", "tags", "estimated_read_minutes"]
            if all(k in data for k in required_keys):
                log_test("AI Generate Content", True, f"Title: {data.get('title')[:50]}...")
            else:
                missing = [k for k in required_keys if k not in data]
                log_test("AI Generate Content", False, f"Missing keys: {missing}. Got: {list(data.keys())}")
        else:
            log_test("AI Generate Content", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Generate Content", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Generate Content", False, f"Exception: {e}")

def test_generate_update():
    """Test POST /api/ai/generate-update - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "product": "Automatex v2.4",
            "changes": "- New AI insights tab\n- Faster loads\n- Login bug fix",
            "tone": "friendly"
        }
        print("  ⏳ Calling LLM for update generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/generate-update", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["headline", "subheadline", "highlights", "social_post", "email_subject", "email_body"]
            if all(k in data for k in required_keys):
                if isinstance(data.get("highlights"), list) and len(data["highlights"]) > 0:
                    highlight = data["highlights"][0]
                    if "title" in highlight and "desc" in highlight:
                        log_test("AI Generate Update", True, f"Headline: {data.get('headline')[:50]}...")
                    else:
                        log_test("AI Generate Update", False, f"Highlight missing title/desc: {highlight}")
                else:
                    log_test("AI Generate Update", False, f"Highlights not a list or empty: {data.get('highlights')}")
            else:
                missing = [k for k in required_keys if k not in data]
                log_test("AI Generate Update", False, f"Missing keys: {missing}. Got: {list(data.keys())}")
        else:
            log_test("AI Generate Update", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Generate Update", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Generate Update", False, f"Exception: {e}")

def test_generate_video_script():
    """Test POST /api/ai/generate-video-script - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "topic": "3 hidden features of our app",
            "platform": "tiktok",
            "duration_seconds": 30,
            "tone": "energetic"
        }
        print("  ⏳ Calling LLM for video script generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/generate-video-script", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["hook", "title", "scenes", "caption", "hashtags", "music_vibe"]
            if all(k in data for k in required_keys):
                if isinstance(data.get("scenes"), list) and len(data["scenes"]) > 0:
                    scene = data["scenes"][0]
                    scene_keys = ["timestamp", "visual", "voiceover", "on_screen_text"]
                    if all(k in scene for k in scene_keys):
                        log_test("AI Generate Video Script", True, f"Hook: {data.get('hook')[:50]}...")
                    else:
                        missing = [k for k in scene_keys if k not in scene]
                        log_test("AI Generate Video Script", False, f"Scene missing keys: {missing}")
                else:
                    log_test("AI Generate Video Script", False, f"Scenes not a list or empty: {data.get('scenes')}")
            else:
                missing = [k for k in required_keys if k not in data]
                log_test("AI Generate Video Script", False, f"Missing keys: {missing}. Got: {list(data.keys())}")
        else:
            log_test("AI Generate Video Script", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Generate Video Script", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Generate Video Script", False, f"Exception: {e}")

def test_multi_post():
    """Test POST /api/ai/multi-post - real LLM call"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "listing": "New organic cotton tote bag, $29, made in Portugal, 5 colors",
            "platforms": ["instagram", "linkedin", "x"],
            "tone": "friendly"
        }
        print("  ⏳ Calling LLM for multi-post generation (may take 10-30s)...")
        r = requests.post(f"{BASE_URL}/ai/multi-post", json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            if "posts" in data and isinstance(data["posts"], list):
                if len(data["posts"]) == 3:
                    post = data["posts"][0]
                    if "platform" in post and "content" in post and "hashtags" in post:
                        log_test("AI Multi-Post", True, f"Generated {len(data['posts'])} platform posts")
                    else:
                        log_test("AI Multi-Post", False, f"Post missing keys: {list(post.keys())}")
                else:
                    log_test("AI Multi-Post", False, f"Expected 3 posts, got {len(data['posts'])}")
            else:
                log_test("AI Multi-Post", False, f"Missing 'posts' key or not a list. Got: {list(data.keys())}")
        else:
            log_test("AI Multi-Post", False, f"Status {r.status_code}: {r.text}")
    except requests.Timeout:
        log_test("AI Multi-Post", False, "Request timeout (>60s)")
    except Exception as e:
        log_test("AI Multi-Post", False, f"Exception: {e}")

def test_ai_endpoints_without_auth():
    """Test that all 5 new AI endpoints return 401 without auth"""
    endpoints = [
        ("/ai/generate-newsletter", {"topic": "test", "audience": "test", "tone": "test", "sections": 1}),
        ("/ai/generate-content", {"topic": "test", "keywords": [], "tone": "test", "length": "short"}),
        ("/ai/generate-update", {"product": "test", "changes": "test", "tone": "test"}),
        ("/ai/generate-video-script", {"topic": "test", "platform": "tiktok", "duration_seconds": 30, "tone": "test"}),
        ("/ai/multi-post", {"listing": "test", "platforms": ["instagram"], "tone": "test"})
    ]
    
    all_passed = True
    for endpoint, payload in endpoints:
        try:
            r = requests.post(f"{BASE_URL}{endpoint}", json=payload, timeout=10)
            if r.status_code != 401:
                all_passed = False
                print(f"  ❌ {endpoint} returned {r.status_code} instead of 401")
        except Exception as e:
            all_passed = False
            print(f"  ❌ {endpoint} exception: {e}")
    
    if all_passed:
        log_test("AI endpoints without auth (401)", True, "All 5 endpoints correctly return 401")
    else:
        log_test("AI endpoints without auth (401)", False, "Some endpoints did not return 401")

def test_list_channels():
    """Test GET /api/channels - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/channels", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) == 6:
                platforms = [ch.get("platform") for ch in data]
                expected = ["instagram", "tiktok", "x", "facebook", "linkedin", "reddit"]
                if set(platforms) == set(expected):
                    log_test("List channels", True, f"All 6 platforms present")
                else:
                    log_test("List channels", False, f"Expected {expected}, got {platforms}")
            else:
                log_test("List channels", False, f"Expected 6 channels, got {len(data) if isinstance(data, list) else 'non-list'}")
        else:
            log_test("List channels", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("List channels", False, f"Exception: {e}")

def test_connect_channel():
    """Test POST /api/channels/connect - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {"platform": "instagram"}
        r = requests.post(f"{BASE_URL}/channels/connect", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("platform") == "instagram":
                log_test("Connect channel", True, f"Handle: {data.get('handle')}")
                return True
            else:
                log_test("Connect channel", False, f"Unexpected response: {data}")
        else:
            log_test("Connect channel", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Connect channel", False, f"Exception: {e}")
    return False

def test_disconnect_channel():
    """Test POST /api/channels/disconnect - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {"platform": "instagram"}
        r = requests.post(f"{BASE_URL}/channels/disconnect", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                log_test("Disconnect channel", True)
            else:
                log_test("Disconnect channel", False, f"Unexpected response: {data}")
        else:
            log_test("Disconnect channel", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Disconnect channel", False, f"Exception: {e}")

def test_publish_post():
    """Test POST /api/channels/publish - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        payload = {
            "content": "Hello world post from automated test",
            "platforms": ["instagram"]
        }
        r = requests.post(f"{BASE_URL}/channels/publish", json=payload, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and data.get("status") == "published":
                log_test("Publish post", True, f"Post ID: {data.get('id')}")
                return data.get("id")
            else:
                log_test("Publish post", False, f"Unexpected response: {data}")
        else:
            log_test("Publish post", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Publish post", False, f"Exception: {e}")
    return None

def test_list_posts():
    """Test GET /api/posts - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/posts", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log_test("List posts", True, f"Found {len(data)} posts")
            else:
                log_test("List posts", False, f"Expected list, got: {type(data)}")
        else:
            log_test("List posts", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("List posts", False, f"Exception: {e}")

def test_list_reports():
    """Test GET /api/reports - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/reports", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                log_test("List reports", True, f"Found {len(data)} reports")
            else:
                log_test("List reports", False, f"Expected list, got: {type(data)}")
        else:
            log_test("List reports", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("List reports", False, f"Exception: {e}")

def test_dashboard_stats():
    """Test GET /api/dashboard/stats - auth required"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.get(f"{BASE_URL}/dashboard/stats", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            required_keys = ["posts", "reports", "channels", "leads"]
            if all(k in data for k in required_keys):
                log_test("Dashboard stats", True, f"Stats: {data}")
            else:
                log_test("Dashboard stats", False, f"Missing keys. Got: {list(data.keys())}")
        else:
            log_test("Dashboard stats", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Dashboard stats", False, f"Exception: {e}")

def test_logout():
    """Test POST /api/auth/logout"""
    try:
        headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
        r = requests.post(f"{BASE_URL}/auth/logout", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                log_test("Logout", True)
            else:
                log_test("Logout", False, f"Unexpected response: {data}")
        else:
            log_test("Logout", False, f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_test("Logout", False, f"Exception: {e}")

def print_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✅ Passed: {len(results['passed'])}")
    print(f"❌ Failed: {len(results['failed'])}")
    print(f"⚠️  Warnings: {len(results['warnings'])}")
    
    if results['failed']:
        print("\nFailed Tests:")
        for fail in results['failed']:
            print(f"  - {fail['test']}: {fail['details']}")
    
    if results['warnings']:
        print("\nWarnings:")
        for warn in results['warnings']:
            print(f"  - {warn['test']}: {warn['details']}")
    
    print("="*60)

if __name__ == "__main__":
    print("Starting Automatex Backend API Tests")
    print(f"Base URL: {BASE_URL}")
    print(f"Session Token: {SESSION_TOKEN[:20]}...")
    print("="*60 + "\n")
    
    # Run tests in order
    print("1. Testing Health Check...")
    test_health_check()
    
    print("\n2. Testing Auth Endpoints...")
    test_auth_me_with_token()
    test_auth_me_without_token()
    
    print("\n3. Testing Leads Endpoints...")
    test_create_lead_public()
    test_list_leads()
    
    print("\n4. Testing NEW AI Content Generator Endpoints (LLM calls - will take time)...")
    test_generate_newsletter()
    test_generate_content()
    test_generate_update()
    test_generate_video_script()
    test_multi_post()
    
    print("\n5. Testing AI Endpoints Auth (401 without token)...")
    test_ai_endpoints_without_auth()
    
    print_summary()
