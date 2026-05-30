"""Image Provider Abstraction — Phase B.

A thin layer that lets the campaign engine generate images without
caring which model produced them. Two providers ship today; the
routing layer picks per concept/platform/objective, and users can
override.

Routing (per Phase B spec):
  • Gemini Nano Banana → product ads, lifestyle imagery, photorealistic
  • OpenAI GPT Image 1  → infographics, illustrations, marketing visuals
  • Default fallback     → Gemini (photoreal is the bigger use case)

Adding a new provider later (e.g., FLUX, Imagen 4) requires only:
  1) Implement `ImageProvider` with `name` + `async generate()`
  2) Register in `_PROVIDERS`
  3) Optionally extend `_select_provider` heuristics
All call sites in campaigns / assets / future workflows are unchanged.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import uuid
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


# Aspect-ratio presets per common platform/use. Both providers honor
# square as default; non-square ratios are injected into the prompt for
# Gemini (no native size param) and passed as `size` for OpenAI when
# supported. We keep this enum small — adding more presets later is a
# one-line change.
SIZE_PRESETS = {
    "square":    {"aspect": "1:1",  "px": (1024, 1024),
                   "hint": "square 1:1 composition, perfectly balanced"},
    "story":     {"aspect": "9:16", "px": (1024, 1792),
                   "hint": "vertical 9:16 composition for mobile stories, content centered in the top two-thirds"},
    "pin":       {"aspect": "2:3",  "px": (1024, 1536),
                   "hint": "vertical 2:3 composition optimized for Pinterest, text/CTA-friendly upper third"},
    "landscape": {"aspect": "16:9", "px": (1792, 1024),
                   "hint": "horizontal 16:9 composition with strong central focal point"},
}


class ImageProvider(Protocol):
    """Contract every image-generation backend must satisfy."""
    name: str
    async def generate(self, prompt: str, *, size: str = "square") -> bytes: ...


# ----------------------------------------------------------- Gemini
class GeminiNanoBananaProvider:
    """Photoreal / product / lifestyle. Uses the Emergent LLM key via
    `emergentintegrations`. Gemini doesn't accept an explicit size param,
    so aspect ratio is injected into the prompt's natural language."""

    name = "gemini"
    model_id = "gemini-3.1-flash-image-preview"

    async def generate(self, prompt: str, *, size: str = "square") -> bytes:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from core import EMERGENT_LLM_KEY
        if not EMERGENT_LLM_KEY:
            raise RuntimeError("EMERGENT_LLM_KEY missing")

        preset = SIZE_PRESETS.get(size, SIZE_PRESETS["square"])
        sized_prompt = f"{prompt}\n\nAspect: {preset['hint']}."

        # New chat per generation so sessions don't bleed prompt context.
        chat = LlmChat(api_key=EMERGENT_LLM_KEY,
                        session_id=f"img-{uuid.uuid4().hex}",
                        system_message=("You are a marketing creative director "
                                          "generating high-quality ad imagery."))
        chat.with_model("gemini", self.model_id) \
             .with_params(modalities=["image", "text"])

        _text, images = await chat.send_message_multimodal_response(
            UserMessage(text=sized_prompt))
        if not images:
            raise RuntimeError("Gemini returned no images")
        return base64.b64decode(images[0]["data"])


# ----------------------------------------------------------- OpenAI
class OpenAIGPTImageProvider:
    """Infographics / illustrations / marketing visuals. Returns raw
    PNG bytes directly — no base64 hop needed."""

    name = "openai"
    model_id = "gpt-image-1"

    async def generate(self, prompt: str, *, size: str = "square") -> bytes:
        from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
        from core import EMERGENT_LLM_KEY
        if not EMERGENT_LLM_KEY:
            raise RuntimeError("EMERGENT_LLM_KEY missing")

        # OpenAI GPT Image 1 supports 1024x1024 (square), 1024x1536
        # (portrait) and 1536x1024 (landscape). Map presets accordingly.
        preset = SIZE_PRESETS.get(size, SIZE_PRESETS["square"])
        # OpenAI param translation — pin is 2:3 portrait too.
        size_param = {
            "square":    "1024x1024",
            "story":     "1024x1536",
            "pin":       "1024x1536",
            "landscape": "1536x1024",
        }.get(size, "1024x1024")

        gen = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
        # The library signature is generate_images(prompt, model, n).
        # `size` is currently unused — kept in our preset table for future.
        _ = size_param  # avoid unused-var warning until lib gains size kwarg
        # Add the natural-language aspect hint for safety in case the
        # library defaults to square only.
        sized_prompt = f"{prompt}\n\nFormat: {preset['hint']}."
        images = await gen.generate_images(
            prompt=sized_prompt,
            model=self.model_id,
            number_of_images=1,
        )
        if not images:
            raise RuntimeError("OpenAI returned no images")
        return images[0]


# Singleton instances — providers are stateless so one is enough.
_PROVIDERS: dict[str, ImageProvider] = {
    "gemini":  GeminiNanoBananaProvider(),
    "openai":  OpenAIGPTImageProvider(),
}


# ------------------------------------------------------------ routing
_OPENAI_KW = re.compile(
    r"\b(infographic|illustration|graphic|chart|diagram|icon|"
    r"educational|guide|tutorial|stat|comparison|table)\b", re.I)


def select_provider(concept: dict, brief: Optional[dict] = None,
                       platform: Optional[str] = None,
                       override: Optional[str] = None) -> ImageProvider:
    """Pick the right provider for a creative concept.

    Priority:
      1. Explicit user override (`override="gemini"` or `"openai"`)
      2. Format-based hint on the concept itself
      3. Keyword scan over title+description (infographic-ish → OpenAI)
      4. Default: Gemini (photoreal handles the most common case)
    """
    if override and override in _PROVIDERS:
        return _PROVIDERS[override]

    fmt = (concept.get("format") or "").strip().lower()
    if fmt in ("infographic", "illustration", "graphic", "diagram", "chart"):
        return _PROVIDERS["openai"]
    if fmt in ("image", "photo", "lifestyle", "product",
                "carousel", "reel", "short", "video"):
        return _PROVIDERS["gemini"]

    haystack = " ".join([
        concept.get("title") or "",
        concept.get("description") or "",
    ])
    if _OPENAI_KW.search(haystack):
        return _PROVIDERS["openai"]

    return _PROVIDERS["gemini"]


def get_provider(name: str) -> Optional[ImageProvider]:
    return _PROVIDERS.get(name)


# ------------------------------------------------------ prompt builder
def build_prompt(concept: dict, brief: Optional[dict] = None,
                   asset: Optional[dict] = None) -> str:
    """Compose a rich, concept-specific prompt from the structured
    brief context. The prompt deliberately weaves in brand tone +
    audience + value-prop so the output looks like the brand's own
    creative, not generic stock."""
    parts: list[str] = []
    title = (concept.get("title") or "").strip()
    desc  = (concept.get("description") or "").strip()
    fmt   = (concept.get("format") or "").strip()

    if title:
        parts.append(f"Title: {title}")
    if desc:
        parts.append(f"Concept: {desc}")
    if fmt:
        parts.append(f"Format: {fmt}")

    if brief:
        brand = (asset or {}).get("brand") or {}
        ta = brief.get("target_audience") or {}
        if brief.get("offer"):
            parts.append(f"Headline offer: {brief['offer']}")
        if ta.get("primary"):
            parts.append(f"Audience: {ta['primary']}")
        if brand.get("tone"):
            parts.append(f"Brand tone: {brand['tone']}")
        if brand.get("name"):
            parts.append(f"Brand name (no logos unless on-brand): {brand['name']}")

    parts.append("Style: high-end commercial photography quality, clean composition, "
                  "strong focal point, no watermarks, no logos unless explicitly part of the concept.")
    return "\n".join(parts)


async def generate_for_concept(*, concept: dict, brief: Optional[dict],
                                  asset: Optional[dict] = None,
                                  size: str = "square",
                                  platform: Optional[str] = None,
                                  override: Optional[str] = None) -> dict:
    """Top-level orchestrator. Returns:
        { "provider": <name>, "size": <preset>, "prompt": <str>,
          "bytes": <PNG bytes>, "width": int, "height": int }
    Raises on hard failure so callers can mark the row failed."""
    provider = select_provider(concept, brief, platform, override)
    prompt = build_prompt(concept, brief, asset)
    img_bytes = await provider.generate(prompt, size=size)

    # Dimensions for the DB row (Pillow probe — bounded < 5MB so trivial).
    w, h = 0, 0
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))
        w, h = img.size
    except Exception:
        logger.exception("image_provider: PIL probe failed")

    return {
        "provider": provider.name,
        "size":     size,
        "prompt":   prompt,
        "bytes":    img_bytes,
        "width":    w,
        "height":   h,
    }
