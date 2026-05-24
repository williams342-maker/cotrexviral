"""TikTok app-review demo — 30-second OAuth-focused cut.

Strips compose/posts scenes and keeps only the OAuth handshake:
  1. Land on Integrations page (TikTok live OAuth badge visible)
  2. Click Connect on TikTok card → backend builds authorize URL
  3. Detail card showing the exact OAuth request parameters
  4. Callback returns with ?tiktok=connected — toast + persisted token
  5. Closing brand card

Output: /app/demo_recordings/tiktok_demo_short.webm → mp4
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("/app/demo_recordings")
OUTPUT_DIR.mkdir(exist_ok=True)

BASE = os.environ.get("DEMO_BASE_URL", "https://social-sync-ai-1.preview.emergentagent.com")
SESSION = "test_session_1779636592168"
HOST = BASE.replace("https://", "").replace("http://", "")

CAPTION_CSS = """
#cv-demo-caption {
  position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
  z-index: 99999; background: rgba(15, 18, 26, 0.92);
  color: #f5f7fb; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  padding: 14px 22px; border-radius: 16px; font-size: 16px;
  border: 1px solid rgba(120, 140, 200, 0.4); box-shadow: 0 10px 30px rgba(0,0,0,0.4);
  letter-spacing: -0.01em; max-width: 1100px; text-align: center;
  backdrop-filter: blur(12px);
}
#cv-demo-caption .cv-demo-step { color: #7aa9ff; font-weight: 600; margin-right: 8px; }
"""


async def show_caption(page, step: str, text: str, hold_ms: int = 0):
    await page.evaluate(
        """([step, text]) => {
          let el = document.getElementById('cv-demo-caption');
          if (!el) {
            el = document.createElement('div');
            el.id = 'cv-demo-caption';
            const style = document.createElement('style');
            style.textContent = arguments_css;
            document.head.appendChild(style);
            document.body.appendChild(el);
          }
          el.innerHTML = `<span class="cv-demo-step">${step}</span>${text}`;
        }""".replace("arguments_css", repr(CAPTION_CSS)),
        [step, text],
    )
    if hold_ms:
        await page.wait_for_timeout(hold_ms)


async def record():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(OUTPUT_DIR),
            record_video_size={"width": 1280, "height": 720},
        )
        await context.add_cookies([{
            "name": "session_token",
            "value": SESSION,
            "domain": HOST,
            "path": "/",
            "secure": True,
            "sameSite": "None",
            "httpOnly": False,
        }])
        page = await context.new_page()

        # --------- Scene 1: Integrations page with TikTok badge (6s) ---------
        await page.goto(f"{BASE}/dashboard/channels", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await show_caption(
            page,
            "STEP 1",
            "CortexViral Integrations — pink badge confirms TikTok OAuth is live (Login Kit + Content Posting API).",
            4500,
        )
        # Scroll to the TikTok card
        await page.evaluate("""() => {
          const cards = Array.from(document.querySelectorAll('div'));
          const card = cards.find(el => el.textContent && el.textContent.startsWith('TikTok') && el.querySelector('button'));
          if (card) card.scrollIntoView({behavior: 'smooth', block: 'center'});
        }""")
        await page.wait_for_timeout(1200)

        # --------- Scene 2: OAuth request detail (7s) ---------
        await page.goto(
            "data:text/html,<html><body style=\"font-family: -apple-system; background: #0f111a; color: #e8ecf5; padding: 60px;\">"
            "<h1 style=\"font-size: 28px; font-weight: 600; margin: 0 0 24px;\">TikTok OAuth Request</h1>"
            "<p style=\"color: #8a93a6; margin-bottom: 32px;\">User is redirected to TikTok's consent screen at <code>https://www.tiktok.com/v2/auth/authorize/</code> with:</p>"
            "<ul style=\"font-family: ui-monospace, Menlo, monospace; font-size: 14px; line-height: 2; background: rgba(122, 169, 255, 0.08); padding: 24px 32px; border-radius: 16px; border: 1px solid rgba(122, 169, 255, 0.2); list-style: none;\">"
            "<li><span style=\"color: #7aa9ff;\">client_key</span> = aw9mlzkhizl4xuap</li>"
            "<li><span style=\"color: #7aa9ff;\">response_type</span> = code</li>"
            "<li><span style=\"color: #7aa9ff;\">scope</span> = user.info.basic, video.publish</li>"
            "<li><span style=\"color: #7aa9ff;\">redirect_uri</span> = https://cortexviral.com/api/oauth/tiktok/callback</li>"
            "<li><span style=\"color: #7aa9ff;\">state</span> = (random 32-byte token)</li>"
            "</ul>"
            "<p style=\"color: #8a93a6; margin-top: 32px;\">After consent, TikTok redirects back to our callback with <code>?code=...&state=...</code>.</p>"
            "</body></html>",
            wait_until="load",
        )
        await page.wait_for_timeout(7000)

        # --------- Scene 3: Callback returns with ?tiktok=connected (6s) ---------
        await page.goto(f"{BASE}/dashboard/channels?tiktok=connected", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await show_caption(
            page,
            "STEP 2",
            "Callback persists access_token + refresh_token + open_id. Toast confirms 'TikTok connected!'",
            4000,
        )

        # --------- Scene 4: Closing card (5s) ---------
        await page.goto(
            "data:text/html,<html><body style=\"font-family: -apple-system; background: linear-gradient(135deg, #0f111a 0%, #1a1530 100%); color: #f5f7fb; padding: 0; margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;\">"
            "<div style=\"text-align: center; max-width: 720px;\">"
            "<div style=\"font-size: 13px; color: #7aa9ff; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 600; margin-bottom: 16px;\">CortexViral × TikTok OAuth</div>"
            "<h1 style=\"font-size: 44px; font-weight: 600; margin: 0 0 24px; letter-spacing: -0.02em;\">End-to-end in 30 seconds.</h1>"
            "<div style=\"display: inline-flex; gap: 16px; flex-wrap: wrap; justify-content: center; font-size: 13px; color: #8a93a6; margin-bottom: 16px;\">"
            "<span style=\"padding: 8px 14px; background: rgba(122, 169, 255, 0.1); border: 1px solid rgba(122, 169, 255, 0.3); border-radius: 999px;\">user.info.basic</span>"
            "<span style=\"padding: 8px 14px; background: rgba(255, 100, 180, 0.1); border: 1px solid rgba(255, 100, 180, 0.3); border-radius: 999px;\">video.publish</span>"
            "<span style=\"padding: 8px 14px; background: rgba(120, 220, 160, 0.1); border: 1px solid rgba(120, 220, 160, 0.3); border-radius: 999px;\">Direct Post API</span>"
            "</div>"
            "</div></body></html>",
            wait_until="load",
        )
        await page.wait_for_timeout(5000)

        await context.close()
        await browser.close()

    files = sorted(OUTPUT_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    latest = files[0]
    target = OUTPUT_DIR / "tiktok_demo_short.webm"
    latest.rename(target)
    print("OK", target, target.stat().st_size, "bytes")


if __name__ == "__main__":
    asyncio.run(record())
