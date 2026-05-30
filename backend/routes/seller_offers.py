"""Phase 4 — AI personalized offer ARTIFACT generation.

Given a lead + offer_type, generate a structured deliverable (SEO Audit /
Marketplace Growth Audit / Product Listing Audit / Onboarding Plan /
Featured Brief) that gets attached to the outreach thread as a real,
downloadable artifact (HTML).

Lead → LLM → structured JSON audit → persisted `seller_offer_artifacts`
→ rendered as HTML on demand by `/seller-offers/{id}/download.html`.
The outreach generator (Phase 2) now also attaches `artifact_id` to the
sent event so the Conversations UI can show a "View audit" link.

Schema for `seller_offer_artifacts`:
    {
      id, user_id, lead_id, mission_id, offer_type, channel,
      title, summary, score (0-100), sections: [{heading, body,
      recommendations: [str]}],
      generated_at, generated_by: 'nova' | 'fallback',
    }

Falls back to a deterministic template when EMERGENT_LLM_KEY is missing
or the LLM errors — keeps the pipeline testable offline.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from core import api, db, EMERGENT_LLM_KEY
from deps import get_current_user
from routes.seller_outreach import OFFER_TYPES, _pick_offer

logger = logging.getLogger(__name__)


# --- Audit recipes ---------------------------------------------------
AUDIT_RECIPES = {
    "free_seo_audit": {
        "title_template":  "Free SEO Audit · {business_name}",
        "sections": [
            "Current organic visibility",
            "Top 5 keyword gaps vs. category leaders",
            "On-page issues to fix this week",
            "Backlink + authority opportunities",
        ],
    },
    "marketplace_growth": {
        "title_template":  "Marketplace Growth Audit · {business_name}",
        "sections": [
            "Storefront positioning vs. top performers",
            "Pricing + bundle opportunities",
            "Conversion-rate fixes",
            "Cross-promotion + collab playbook",
        ],
    },
    "product_optimization": {
        "title_template":  "Product Listing Audit · {business_name}",
        "sections": [
            "Listing title rewrites (top 5 products)",
            "Photo + thumbnail recommendations",
            "Description + benefit framing",
            "Tag / category corrections",
        ],
    },
    "free_onboarding": {
        "title_template":  "10-Minute Onboarding Plan · {business_name}",
        "sections": [
            "What we'll set up in your first 10 minutes",
            "Product import strategy",
            "Storefront brand recommendations",
            "Week 1 promotion plan",
        ],
    },
    "featured_invite": {
        "title_template":  "Featured Seller Brief · {business_name}",
        "sections": [
            "Why your shop fits our featured slot",
            "Co-marketing assets we'll produce",
            "Premium placement + launch plan",
            "Performance benchmarks we'll track",
        ],
    },
}


# --- Pydantic schemas -----------------------------------------------
class OfferGenerate(BaseModel):
    lead_id: str
    offer_type: Optional[str] = None     # auto-pick if blank
    custom_brief: Optional[str] = None


# --- Helpers --------------------------------------------------------
def _slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "audit"


def _score_from_lead(lead: dict, offer_type: str) -> int:
    """Heuristic baseline score (0-100). The LLM may override this in the
    structured JSON it returns — we use this as the fallback floor."""
    base = 55
    sc = lead.get("seller_score") or 0
    base += min(25, sc // 4)
    activity = (lead.get("estimated_activity") or "").lower()
    if activity == "high": base += 8
    if activity == "low": base -= 5
    socials = lead.get("socials") or {}
    base += min(10, 3 * len(socials))
    if offer_type == "free_seo_audit" and lead.get("website"): base += 5
    return max(15, min(95, base))


def _fallback_artifact(lead: dict, offer_type: str) -> dict:
    """Deterministic template — keeps tests deterministic + offline-safe."""
    recipe = AUDIT_RECIPES[offer_type]
    business = lead.get("business_name") or "your shop"
    niche = lead.get("niche") or "your category"
    sections = []
    for heading in recipe["sections"]:
        sections.append({
            "heading": heading,
            "body":   (f"Cortex's read on {business} in the {niche} space "
                       f"suggests the highest-leverage move under '{heading}' is "
                       "to clarify the customer's first-glance promise and tighten "
                       "the call-to-action."),
            "recommendations": [
                f"Audit the top 3 {niche} keywords your listings target.",
                "Tighten the hero photo + first 7 words of the storefront.",
                "Add one social-proof line above the fold (sales / reviews).",
            ],
        })
    return {
        "title":    recipe["title_template"].format(business_name=business),
        "summary":  (f"A short, actionable audit prepared for {business}. "
                     f"Built from public signals + {niche} category benchmarks. "
                     "Each section ends with three concrete moves we recommend "
                     "shipping this week."),
        "score":    _score_from_lead(lead, offer_type),
        "sections": sections,
        "generated_by": "fallback",
    }


async def _llm_generate_artifact(lead: dict, offer_type: str,
                                  custom_brief: Optional[str], user_id: str) -> dict:
    """Ask Nova for a structured audit. Returns the fallback on any error."""
    if not EMERGENT_LLM_KEY:
        return _fallback_artifact(lead, offer_type)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from routes.ai import send_with_usage

        recipe = AUDIT_RECIPES[offer_type]
        system = (
            "You are Nova generating a personalized, useful seller audit for the "
            "CortexViral Seller Acquisition OS. Output STRICT JSON only — no prose "
            "outside the JSON. Schema: "
            '{ "title": str, "summary": str (<=400 chars), "score": int (0-100), '
            '"sections": [{"heading": str, "body": str (<=600 chars), '
            '"recommendations": [str (<=200 chars)] }] }. '
            "Be specific — reference the seller's niche, platform, and signals. "
            "Provide 3-4 sections, each with 3 concrete recommendations."
        )
        chat = (
            LlmChat(api_key=EMERGENT_LLM_KEY,
                    session_id=f"offer-artifact-{lead['id']}",
                    system_message=system)
            .with_model("openai", "gpt-5")
        )
        prompt = (
            f"Seller: {lead.get('business_name')}\n"
            f"Niche: {lead.get('niche')}\n"
            f"Source platform: {lead.get('source')}\n"
            f"Website: {lead.get('website')}\n"
            f"Activity: {lead.get('estimated_activity')}\n"
            f"Seller score: {lead.get('seller_score')}\n"
            f"Audit type: {offer_type}\n"
            f"Required sections (use these exact headings):\n"
            + "\n".join(f"  - {s}" for s in recipe["sections"])
        )
        if custom_brief:
            prompt += f"\n\nOperator's extra context:\n{custom_brief}"

        raw, _ = await send_with_usage(
            chat, UserMessage(text=prompt),
            agent_id="nova", user_id=user_id, model="gpt-5",
        )
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip(), flags=re.MULTILINE)
        data = json.loads(text)

        # Coerce / clamp shape
        sections_out = []
        for s in (data.get("sections") or [])[:6]:
            recs = [str(r)[:200] for r in (s.get("recommendations") or [])[:5]]
            sections_out.append({
                "heading": str(s.get("heading") or "Recommendation"),
                "body":    str(s.get("body") or "")[:800],
                "recommendations": recs,
            })
        return {
            "title":    str(data.get("title") or recipe["title_template"].format(
                business_name=lead.get("business_name") or "Seller"))[:140],
            "summary":  str(data.get("summary") or "")[:500],
            "score":    int(data.get("score") or _score_from_lead(lead, offer_type)),
            "sections": sections_out or _fallback_artifact(lead, offer_type)["sections"],
            "generated_by": "nova",
        }
    except Exception:
        logger.exception("seller-offer: LLM gen failed, using fallback")
        return _fallback_artifact(lead, offer_type)


async def generate_and_persist_artifact(
    user_id: str, lead: dict, *, offer_type: Optional[str] = None,
    custom_brief: Optional[str] = None,
) -> dict:
    """Public helper — used by the Phase 2 outreach generator when an
    operator clicks 'Send offer with artifact'."""
    offer = offer_type or _pick_offer(lead)
    if offer not in AUDIT_RECIPES:
        raise HTTPException(400, f"No audit recipe for offer_type={offer}")
    payload = await _llm_generate_artifact(lead, offer, custom_brief, user_id)
    rec = {
        "id":          uuid.uuid4().hex,
        "user_id":     user_id,
        "lead_id":     lead["id"],
        "mission_id":  lead.get("mission_id"),
        "offer_type":  offer,
        **payload,
        "generated_at": datetime.now(timezone.utc),
    }
    await db.seller_offer_artifacts.insert_one(rec)
    return _serialize(rec)


def _serialize(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    v = out.get("generated_at")
    if isinstance(v, datetime):
        out["generated_at"] = v.isoformat()
    return out


# --- HTML renderer --------------------------------------------------
def _artifact_to_html(art: dict, lead: dict) -> str:
    sections_html = ""
    for s in art.get("sections") or []:
        recs = "".join(f"<li>{_esc(r)}</li>" for r in (s.get("recommendations") or []))
        sections_html += (
            f"<section><h2>{_esc(s.get('heading') or '')}</h2>"
            f"<p>{_esc(s.get('body') or '')}</p>"
            f"<ul>{recs}</ul></section>"
        )
    score = art.get("score") or 0
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{_esc(art.get('title') or 'Audit')}</title>
<style>
  :root {{ --bg:#0b0b12; --fg:#f4f4f5; --muted:#a1a1aa; --accent:#a78bfa; --line:#2a2a35; }}
  * {{ box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--fg); font-family:-apple-system,Inter,system-ui,sans-serif; margin:0; padding:48px 24px; line-height:1.55; }}
  .wrap {{ max-width:740px; margin:0 auto; }}
  .badge {{ display:inline-block; background:linear-gradient(135deg,#7c3aed,#3b82f6); padding:4px 10px; border-radius:99px; font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; }}
  h1 {{ font-size:28px; margin:14px 0 8px; }}
  .summary {{ color:var(--muted); font-size:15px; margin-bottom:28px; padding-bottom:20px; border-bottom:1px solid var(--line); }}
  .score {{ display:flex; align-items:center; gap:10px; margin-bottom:24px; }}
  .score .bar {{ flex:1; height:8px; background:#1a1a24; border-radius:99px; overflow:hidden; }}
  .score .fill {{ height:100%; background:linear-gradient(90deg,#7c3aed,#3b82f6); border-radius:99px; width:{score}%; }}
  .score .n {{ font-weight:600; font-size:18px; }}
  section {{ margin:28px 0; }}
  h2 {{ font-size:17px; color:var(--accent); margin:0 0 8px; letter-spacing:-.005em; }}
  p {{ color:#d4d4d8; margin:0 0 12px; font-size:14.5px; }}
  ul {{ margin:0; padding-left:20px; }}
  li {{ color:#e4e4e7; margin:6px 0; font-size:14px; }}
  footer {{ margin-top:48px; padding-top:18px; border-top:1px solid var(--line); color:#71717a; font-size:12px; }}
</style></head><body>
<div class="wrap">
  <div class="badge">Cortex · Seller Audit</div>
  <h1>{_esc(art.get('title') or '')}</h1>
  <div class="summary">{_esc(art.get('summary') or '')}</div>
  <div class="score">
    <div class="bar"><div class="fill"></div></div>
    <div class="n">{score}<span style="color:var(--muted);font-size:13px;font-weight:400;">/100 fit score</span></div>
  </div>
  {sections_html}
  <footer>Generated for <strong style="color:#e4e4e7">{_esc(lead.get('business_name') or 'Seller')}</strong> · CortexViral &middot; {_esc(art.get('generated_at') or '')}</footer>
</div></body></html>"""


def _esc(s) -> str:
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# --- Routes ---------------------------------------------------------
@api.post("/seller-offers/generate")
async def generate_offer(payload: OfferGenerate, request: Request):
    """Operator-triggered audit generation. Persists the artifact and
    returns it (without auto-sending outreach — call /seller-outreach/generate
    with `attach_artifact=True` for that)."""
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one(
        {"id": payload.lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    art = await generate_and_persist_artifact(
        user.user_id, lead,
        offer_type=payload.offer_type,
        custom_brief=payload.custom_brief,
    )
    return art


@api.get("/seller-offers/lead/{lead_id}")
async def list_for_lead(lead_id: str, request: Request, limit: int = 20):
    user = await get_current_user(request)
    lead = await db.seller_leads.find_one({"id": lead_id, "user_id": user.user_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    cur = db.seller_offer_artifacts.find(
        {"user_id": user.user_id, "lead_id": lead_id},
        {"_id": 0},
    ).sort("generated_at", -1).limit(min(50, max(1, limit)))
    rows = await cur.to_list(length=limit)
    for r in rows:
        v = r.get("generated_at")
        if isinstance(v, datetime):
            r["generated_at"] = v.isoformat()
    return {"artifacts": rows, "count": len(rows)}


@api.get("/seller-offers/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request):
    user = await get_current_user(request)
    art = await db.seller_offer_artifacts.find_one(
        {"id": artifact_id, "user_id": user.user_id}, {"_id": 0})
    if not art:
        raise HTTPException(404, "Artifact not found")
    v = art.get("generated_at")
    if isinstance(v, datetime):
        art["generated_at"] = v.isoformat()
    return art


@api.get("/seller-offers/{artifact_id}/download.html")
async def download_artifact_html(artifact_id: str, request: Request):
    """Serve the artifact as a styled HTML page. Authenticated via the
    same session cookie/Bearer header as everything else."""
    user = await get_current_user(request)
    art = await db.seller_offer_artifacts.find_one(
        {"id": artifact_id, "user_id": user.user_id})
    if not art:
        raise HTTPException(404, "Artifact not found")
    lead = await db.seller_leads.find_one(
        {"id": art["lead_id"], "user_id": user.user_id}) or {}
    v = art.get("generated_at")
    if isinstance(v, datetime):
        art["generated_at"] = v.isoformat()
    html = _artifact_to_html(art, lead)
    slug = _slugify((art.get("title") or "audit"))
    headers = {
        "Content-Disposition": f'inline; filename="{slug}.html"',
        "Cache-Control": "private, max-age=300",
    }
    return Response(content=html, media_type="text/html; charset=utf-8", headers=headers)


@api.get("/seller-offers/{artifact_id}/download.pdf")
async def download_artifact_pdf(artifact_id: str, request: Request):
    """Same audit, rendered as a real PDF via playwright + headless
    Chromium. Falls back to 502 if the PDF pipeline failed (caller can
    retry with the `.html` route)."""
    from routes.audit_pdf import render_html_to_pdf
    user = await get_current_user(request)
    art = await db.seller_offer_artifacts.find_one(
        {"id": artifact_id, "user_id": user.user_id})
    if not art:
        raise HTTPException(404, "Artifact not found")
    lead = await db.seller_leads.find_one(
        {"id": art["lead_id"], "user_id": user.user_id}) or {}
    v = art.get("generated_at")
    if isinstance(v, datetime):
        art["generated_at"] = v.isoformat()
    html = _artifact_to_html(art, lead)
    pdf_bytes = await render_html_to_pdf(html)
    if not pdf_bytes:
        raise HTTPException(502, "PDF render failed — try the .html route instead")
    slug = _slugify((art.get("title") or "audit"))
    headers = {
        "Content-Disposition": f'inline; filename="{slug}.pdf"',
        "Cache-Control": "private, max-age=300",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
