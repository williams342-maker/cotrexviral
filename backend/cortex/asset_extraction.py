"""Asset text extraction — pluggable per-type dispatcher.

Each kind (pdf/image/url) returns a normalized dict:

  {
    "text":     "<full extracted text, capped at ~12k chars>",
    "meta":     {<kind-specific metadata: dimensions, page_count, etc.>},
    "thumb_b64": "<optional base64 PNG thumbnail for image previews>",
  }

This module deliberately does NO LLM work — that lives in
`cortex.asset_intelligence`. Keeping the extraction step pure makes
the pipeline testable and lets us add PPTX/Video later by registering
a new entry in `_EXTRACTORS`.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum text passed downstream to the LLM — ~12k chars ≈ 3k tokens.
# Anything more would inflate the prompt without adding insight.
TEXT_CAP = 12_000


async def extract(*, kind: str, data: bytes | None = None,
                    url: str | None = None) -> dict:
    """Dispatch to the per-kind extractor. Always returns a dict; on
    failure returns {"text": "", "meta": {"error": <reason>}} so the
    pipeline can still produce a partial brief instead of crashing."""
    fn = _EXTRACTORS.get(kind)
    if not fn:
        return {"text": "", "meta": {"error": f"unknown_kind:{kind}"}}
    try:
        if kind == "url":
            return await fn(url or "")
        return await fn(data or b"")
    except Exception as e:
        logger.exception("asset_extraction: %s extractor crashed", kind)
        return {"text": "", "meta": {"error": f"{type(e).__name__}: {e}"}}


# --------------------------------------------------------------- PDF
async def _extract_pdf(data: bytes) -> dict:
    """Pull text + page count using PyMuPDF (offline, no API calls)."""
    def _run():
        import fitz  # PyMuPDF
        doc = fitz.open(stream=data, filetype="pdf")
        pages: list[str] = []
        for i in range(min(doc.page_count, 30)):  # cap at 30 pages
            try:
                pages.append(doc.load_page(i).get_text("text"))
            except Exception:
                continue
        text = "\n\n".join(p for p in pages if p.strip())
        return {
            "text": text[:TEXT_CAP],
            "meta": {
                "page_count":      doc.page_count,
                "pages_extracted": min(doc.page_count, 30),
                "char_count":      len(text),
            },
        }
    return await asyncio.to_thread(_run)


# -------------------------------------------------------------- Image
async def _extract_image(data: bytes) -> dict:
    """Pull dimensions + a small thumbnail. We deliberately skip OCR
    here — the LLM with vision capability ingests the raw image during
    intelligence extraction, so OCR adds latency without new signal."""
    def _run():
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
        w, h = img.size
        fmt = (img.format or "").lower()
        # Thumb: 320px wide, preserve aspect, PNG for transparency safety.
        thumb = img.copy()
        thumb.thumbnail((320, 320), Image.LANCZOS)
        buf = io.BytesIO()
        thumb.convert("RGB").save(buf, format="JPEG", quality=78,
                                    optimize=True)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            # No text for raw images — the LLM gets the original bytes.
            "text": "",
            "meta": {
                "width":  w, "height": h,
                "format": fmt or "jpeg",
                "thumb_format": "jpeg",
            },
            "thumb_b64": thumb_b64,
        }
    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------- URL
async def _extract_url(url: str) -> dict:
    """Fetch a webpage and return a clean text excerpt + title.
    Re-uses the existing site-fetcher pattern from analysis_runner.
    Returns empty text on fetch failure (caller decides if that's fatal).
    """
    if not url or not re.match(r"^https?://", url):
        return {"text": "", "meta": {"error": "invalid_url"}}
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True,
                                        timeout=15.0,
                                        headers={"User-Agent":
                                                  "Mozilla/5.0 CortexViral/1.0"}) as client:
            r = await client.get(url)
            html = r.text or ""
    except Exception as e:
        return {"text": "", "meta": {"error": f"fetch_failed:{type(e).__name__}"}}

    # Simple HTML → text. We don't need beautifulsoup precision; the
    # LLM is robust to noise. Just strip script/style and collapse tags.
    cleaned = re.sub(r"(?is)<(script|style|svg|noscript)\b[^>]*>.*?</\1>",
                       " ", html)
    cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
    text = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    text = re.sub(r"\s+", " ", text).strip()

    # Pull a title for the asset name fallback.
    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = re.sub(r"\s+", " ", (title_m.group(1) if title_m else "")).strip()

    return {
        "text": text[:TEXT_CAP],
        "meta": {
            "url":         url,
            "title":       title[:200],
            "html_bytes":  len(html),
            "text_chars":  len(text),
        },
    }


_EXTRACTORS = {
    "pdf":   _extract_pdf,
    "image": _extract_image,
    "url":   _extract_url,
    # Future: "pptx", "video" — register here, no other changes needed.
}


def kind_from_mime(mime: str | None) -> Optional[str]:
    """Normalize an HTTP content-type into our asset kind enum."""
    if not mime:
        return None
    m = mime.lower()
    if m == "application/pdf":
        return "pdf"
    if m.startswith("image/"):
        return "image"
    return None
