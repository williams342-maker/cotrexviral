"""PDF rendering for audit artifacts.

Uses playwright + headless Chromium (already installed for testing). Renders
the same HTML produced by `_artifact_to_html` to a real `.pdf` byte stream.

Falls back to the original HTML attachment if playwright errors (e.g. in
environments where Chromium can't launch) — the helper returns `None` and
the calling code keeps the existing HTML attachment behavior.

Cache: a single browser instance is launched lazily and reused across
requests to keep render time under 800ms after first hit.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_browser = None
_browser_lock = asyncio.Lock()


async def _get_browser():
    """Lazily launch a single Chromium instance and reuse it. Tries the
    Playwright-bundled Chromium first, then falls back to system
    `/root/bin/chromium` / `/usr/bin/google-chrome` (preview env). On any
    failure returns `None` so callers know to use the HTML fallback."""
    global _browser
    if _browser is not None and _browser.is_connected():
        return _browser
    async with _browser_lock:
        if _browser is not None and _browser.is_connected():
            return _browser
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            launch_kwargs = {
                "headless": True,
                "args":     ["--no-sandbox", "--disable-dev-shm-usage"],
            }
            # Prefer system chromium when present — preview env doesn't
            # ship Playwright's bundled headless_shell.
            for candidate in (os.environ.get("CHROMIUM_BIN"),
                              "/root/bin/chromium",
                              "/usr/bin/google-chrome",
                              "/usr/bin/chromium"):
                if candidate and os.path.exists(candidate):
                    launch_kwargs["executable_path"] = candidate
                    break
            _browser = await pw.chromium.launch(**launch_kwargs)
            return _browser
        except Exception:
            logger.exception("audit_pdf: failed to launch chromium")
            _browser = None
            return None


async def render_html_to_pdf(html: str) -> Optional[bytes]:
    """Render the provided HTML string to a PDF byte stream. Returns
    `None` on any failure — callers should fall back to HTML attachment.

    Print-friendly settings: A4 portrait, generous side margins, background
    colors enabled (so the dark CortexViral theme renders correctly)."""
    if not html:
        return None
    browser = await _get_browser()
    if browser is None:
        return None
    try:
        context = await browser.new_context()
        page = await context.new_page()
        await page.set_content(html, wait_until="load")
        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "right": "16mm",
                    "bottom": "20mm", "left": "16mm"},
            prefer_css_page_size=False,
        )
        await context.close()
        return pdf_bytes
    except Exception:
        logger.exception("audit_pdf: render failed, returning None")
        return None


async def shutdown_pdf_renderer() -> None:
    """Cleanly close the cached Chromium on app shutdown."""
    global _browser
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
