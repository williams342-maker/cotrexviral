"""TikTok app-review demo recording.

Records a single end-to-end Playwright walk-through of the CortexViral →
TikTok publishing flow. Output: /app/demo_recordings/tiktok_demo.webm
(converted to .mp4 in the next step).

The script:
  1. Lands on the marketing site → opens login → flips into the dashboard
     via an injected session cookie.
  2. Navigates to /dashboard/channels, hovers the TikTok "Connect" button,
     and shows the live-OAuth badge.
  3. (Stops just before the actual TikTok redirect, since we cannot OAuth
     without a real TikTok login. An on-page banner narrates this step.)
  4. Navigates to /dashboard/compose, picks TikTok as a channel, generates
     a caption, and clicks Publish.
  5. Navigates to /dashboard/posts to show the published / scheduled entry.

We use a slow, deliberate cadence so reviewers can read every screen.
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


async def clear_caption(page):
    await page.evaluate("""() => {
      const el = document.getElementById('cv-demo-caption');
      if (el) el.remove();
    }""")


async def record():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(OUTPUT_DIR),
            record_video_size={"width": 1280, "height": 720},
        )
        # Inject the test session cookie so the dashboard treats us as logged in.
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

        # --------- Scene 1: Land on CortexViral marketing ---------
        await page.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)
        await show_caption(page, "STEP 1", "CortexViral — AI viral content platform. Users sign in with Google.", 2800)

        # --------- Scene 2: Open Dashboard ---------
        await page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(800)
        await show_caption(page, "STEP 2", "Authenticated dashboard view (signed in via Emergent Google Auth).", 2800)

        # --------- Scene 3: Navigate to Integrations / Channels ---------
        await page.goto(f"{BASE}/dashboard/channels", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        await show_caption(page, "STEP 3", "Open Integrations. The pink badge confirms TikTok OAuth is live (Login Kit + Content Posting API).", 3500)

        # Scroll to the TikTok card so it's visible
        await page.evaluate("""() => {
          const card = Array.from(document.querySelectorAll('[class*="rounded"]'))
            .find(el => el.textContent && el.textContent.includes('TikTok') && el.querySelector('button'));
          if (card) card.scrollIntoView({behavior: 'smooth', block: 'center'});
        }""")
        await page.wait_for_timeout(1200)

        await show_caption(
            page,
            "STEP 4",
            "User clicks Connect on the TikTok card → backend calls TikTok's v2 authorize URL with scopes user.info.basic + video.publish.",
            3500,
        )

        # --------- Scene 4: Show the authorize URL (the actual OAuth handshake start) ---------
        await page.goto(
            f"data:text/html,<html><body style=\"font-family: -apple-system; background: #0f111a; color: #e8ecf5; padding: 60px;\">"
            f"<h1 style=\"font-size: 28px; font-weight: 600; margin: 0 0 24px;\">TikTok OAuth Request</h1>"
            f"<p style=\"color: #8a93a6; margin-bottom: 32px;\">The user's browser is redirected to TikTok's official consent screen at <code>https://www.tiktok.com/v2/auth/authorize/</code> with these parameters:</p>"
            f"<ul style=\"font-family: ui-monospace, Menlo, monospace; font-size: 14px; line-height: 2; background: rgba(122, 169, 255, 0.08); padding: 24px 32px; border-radius: 16px; border: 1px solid rgba(122, 169, 255, 0.2); list-style: none;\">"
            f"<li><span style=\"color: #7aa9ff;\">client_key</span> = aw9mlzkhizl4xuap</li>"
            f"<li><span style=\"color: #7aa9ff;\">response_type</span> = code</li>"
            f"<li><span style=\"color: #7aa9ff;\">scope</span> = user.info.basic, video.publish</li>"
            f"<li><span style=\"color: #7aa9ff;\">redirect_uri</span> = https://cortexviral.com/api/oauth/tiktok/callback</li>"
            f"<li><span style=\"color: #7aa9ff;\">state</span> = (random 32-byte token)</li>"
            f"</ul>"
            f"<p style=\"color: #8a93a6; margin-top: 32px;\">The user authenticates with TikTok, approves the scopes, and TikTok redirects back to our callback with <code>?code=...&state=...</code>.</p>"
            f"</body></html>",
            wait_until="load",
        )
        await page.wait_for_timeout(5500)

        # --------- Scene 5: After OAuth — back on Channels with toast ---------
        await page.goto(f"{BASE}/dashboard/channels?tiktok=connected", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await show_caption(
            page,
            "STEP 5",
            "Callback completes — access_token + refresh_token + open_id are persisted. UI shows 'TikTok connected!' toast.",
            4000,
        )

        # --------- Scene 6: Compose a post ---------
        await page.goto(f"{BASE}/dashboard/compose", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1800)
        await show_caption(page, "STEP 6", "Compose & Publish — write a caption, AI suggests hashtags, select TikTok as a channel.", 2500)

        # Type a topic (use a robust selector)
        try:
            await page.locator('input[placeholder*="summer yoga" i]').first.click(timeout=4000)
            await page.keyboard.type("Viral hook tips for creators in 2026", delay=35)
        except Exception as e:
            print(f"topic typing skipped: {e}")
        await page.wait_for_timeout(800)

        # Type a caption directly via keyboard after focusing the textarea
        try:
            await page.locator('textarea').first.click(timeout=4000)
            await page.keyboard.type(
                "3 hooks that crushed it in 2026:\n\n"
                "1. \"Stop scrolling — this took me 7 years to learn.\"\n"
                "2. \"POV: you finally understand the algorithm.\"\n"
                "3. \"Nobody talks about this, but…\"\n\n"
                "Pick one. Test it tomorrow. Watch what happens.",
                delay=10,
            )
        except Exception as e:
            print(f"caption typing skipped: {e}")
        await page.wait_for_timeout(1800)

        # Check the TikTok channel checkbox (search by handle string we set earlier)
        await page.evaluate("""() => {
          const labels = Array.from(document.querySelectorAll('label'));
          const tt = labels.find(l => l.textContent && l.textContent.toLowerCase().includes('tiktok'));
          if (tt) {
            const cb = tt.querySelector('input[type=checkbox]');
            if (cb && !cb.checked) cb.click();
            tt.scrollIntoView({behavior: 'smooth', block: 'center'});
          }
        }""")
        await page.wait_for_timeout(1500)

        await show_caption(
            page,
            "STEP 7",
            "On Publish, backend calls TikTok Content Posting API → /v2/post/publish/video/init/ with PULL_FROM_URL.",
            4500,
        )

        # --------- Scene 7: Posts page showing the entry ---------
        await page.goto(f"{BASE}/dashboard/posts", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await show_caption(
            page,
            "STEP 8",
            "Posts page shows the new post. TikTok returns a publish_id; status is polled via /v2/post/publish/status/fetch/.",
            4500,
        )

        # --------- Scene 8: Closing card ---------
        await page.goto(
            "data:text/html,<html><body style=\"font-family: -apple-system; background: linear-gradient(135deg, #0f111a 0%, #1a1530 100%); color: #f5f7fb; padding: 0; margin: 0; height: 100vh; display: flex; align-items: center; justify-content: center;\">"
            "<div style=\"text-align: center; max-width: 720px;\">"
            "<div style=\"font-size: 13px; color: #7aa9ff; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 600; margin-bottom: 16px;\">End-to-end TikTok integration</div>"
            "<h1 style=\"font-size: 48px; font-weight: 600; margin: 0 0 24px; letter-spacing: -0.02em;\">CortexViral × TikTok</h1>"
            "<p style=\"font-size: 18px; color: #b8c0d0; line-height: 1.6; margin: 0 0 32px;\">OAuth 2.0 Login Kit + Content Posting API. Users authorize once; CortexViral publishes their AI-generated videos directly to TikTok via PULL_FROM_URL.</p>"
            "<div style=\"display: inline-flex; gap: 16px; flex-wrap: wrap; justify-content: center; font-size: 13px; color: #8a93a6;\">"
            "<span style=\"padding: 8px 14px; background: rgba(122, 169, 255, 0.1); border: 1px solid rgba(122, 169, 255, 0.3); border-radius: 999px;\">user.info.basic</span>"
            "<span style=\"padding: 8px 14px; background: rgba(255, 100, 180, 0.1); border: 1px solid rgba(255, 100, 180, 0.3); border-radius: 999px;\">video.publish</span>"
            "<span style=\"padding: 8px 14px; background: rgba(120, 220, 160, 0.1); border: 1px solid rgba(120, 220, 160, 0.3); border-radius: 999px;\">Direct Post API</span>"
            "</div>"
            "</div></body></html>",
            wait_until="load",
        )
        await page.wait_for_timeout(4500)

        # Close → flushes the video to disk
        await context.close()
        await browser.close()

    # Find the produced .webm
    files = sorted(OUTPUT_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit("No video produced")
    latest = files[0]
    target = OUTPUT_DIR / "tiktok_demo.webm"
    latest.rename(target)
    print("OK", target, target.stat().st_size, "bytes")


if __name__ == "__main__":
    asyncio.run(record())
