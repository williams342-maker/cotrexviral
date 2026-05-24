"""Regenerate /app/frontend/public/sitemap.xml from the live backend's dynamic sitemap.

Run after adding new pages/routes to keep the static sitemap.xml at the site root
in sync with the canonical /api/seo/sitemap.xml endpoint.

Usage:
    python /app/tools/regen_sitemap.py
"""
import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
OUT = Path("/app/frontend/public/sitemap.xml")


def main():
    url = f"{API_URL}/api/seo/sitemap.xml"
    print(f"Fetching {url} …")
    try:
        import httpx
        r = httpx.get(url, timeout=15)
        r.raise_for_status()
        xml = r.text
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    if "<urlset" not in xml:
        print("FAIL: response is not a valid sitemap XML", file=sys.stderr)
        sys.exit(1)
    OUT.write_text(xml)
    n = xml.count("<url>")
    print(f"OK — wrote {n} URLs to {OUT}")


if __name__ == "__main__":
    main()
