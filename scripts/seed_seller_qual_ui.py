"""Seed a fresh seller_acquisition mission with 5 leads spanning bands,
then run qualification — used to set up state for UI testing."""
import asyncio, os, uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import requests

load_dotenv("/app/backend/.env")
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
TOKEN = "test_session_1779636592168"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

uid = requests.get(f"{API}/api/auth/me", headers=HEADERS).json()["user_id"]
print("uid=", uid)

async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    mid = "ui_test_mission_" + uuid.uuid4().hex[:8]
    await db.missions.insert_one({
        "id": mid, "user_id": uid, "title": "UI_TEST_SELLER_MISSION",
        "mission_type": "seller_acquisition",
        "seller_target_niche": "woodworking",
        "qualification_threshold": 60.0,
        "created_at": datetime.now(timezone.utc),
    })
    # 2 high
    for _ in range(2):
        await db.seller_leads.insert_one({
            "id": uuid.uuid4().hex, "user_id": uid, "mission_id": mid,
            "business_name": f"HighSeller_{uuid.uuid4().hex[:5]}",
            "niche": "woodworking", "source": "etsy", "stage": "discovered",
            "socials": {"instagram": "a", "pinterest": "b", "tiktok": "c"},
            "website": "https://hi.example.com",
            "estimated_activity": "high",
            "product_categories": ["c1","c2","c3","c4"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    # 2 medium
    for _ in range(2):
        await db.seller_leads.insert_one({
            "id": uuid.uuid4().hex, "user_id": uid, "mission_id": mid,
            "business_name": f"MidSeller_{uuid.uuid4().hex[:5]}",
            "niche": "unrelated", "source": "etsy", "stage": "discovered",
            "socials": {"instagram": "x"}, "website": "",
            "estimated_activity": "medium",
            "product_categories": ["c1"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    # 1 low
    await db.seller_leads.insert_one({
        "id": uuid.uuid4().hex, "user_id": uid, "mission_id": mid,
        "business_name": "test demo brand",
        "niche": "off-topic", "source": "other", "stage": "discovered",
        "socials": {}, "website": "",
        "estimated_activity": "low", "product_categories": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    print("mission_id=", mid)

    r = requests.post(f"{API}/api/seller-qualification/run",
                      json={"mission_id": mid}, headers=HEADERS)
    print("run:", r.status_code, r.json())

asyncio.run(main())
