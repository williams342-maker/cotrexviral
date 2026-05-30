import React, { useState } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import {
  Compass, Target, Users, Megaphone, Layers, Sparkles, RefreshCw,
  Loader2, Hash, Lightbulb, Wand2, Image as ImageIcon, AlertTriangle,
  Rocket,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* CreativeBriefPanel — Phase A2 surface.
 *
 * Hydrates `asset.brief` (auto-generated when the asset completes
 * analysis). Renders the 8-part executable brief:
 *
 *   • Campaign Goal           (hero — single sentence)
 *   • Target Audience         (primary + secondary chips + psychographics)
 *   • Offer                   (headline hook)
 *   • Messaging Angles        (3-5 angles to test)
 *   • Recommended Platforms   (channel chips)
 *   • Content Plan            (platform × format × frequency × concept)
 *   • Creative Concepts       (3-5 concrete ideas with format)
 *
 * "Regenerate brief" CTA fires POST /cortex/assets/{id}/brief.
 */

const PLATFORM_TONE = {
  facebook:         'text-sky-300 border-sky-500/30 bg-sky-500/10',
  instagram:        'text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10',
  instagram_story:  'text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10',
  pinterest:        'text-rose-300 border-rose-500/30 bg-rose-500/10',
  linkedin:         'text-cyan-300 border-cyan-500/30 bg-cyan-500/10',
  tiktok:           'text-zinc-200 border-white/20 bg-white/[0.06]',
  youtube:          'text-rose-300 border-rose-500/30 bg-rose-500/10',
  youtube_shorts:   'text-rose-300 border-rose-500/30 bg-rose-500/10',
  email:            'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  blog:             'text-amber-300 border-amber-500/30 bg-amber-500/10',
  google_ads:       'text-emerald-300 border-emerald-500/30 bg-emerald-500/10',
  x:                'text-zinc-200 border-white/20 bg-white/[0.06]',
};

const ConfidenceTone = (c) => {
  if (c >= 80) return { text: 'text-emerald-300', bar: 'bg-emerald-400' };
  if (c >= 60) return { text: 'text-amber-300',   bar: 'bg-amber-400' };
  return            { text: 'text-rose-300',    bar: 'bg-rose-400' };
};


export default function CreativeBriefPanel({ asset, onChanged }) {
  const brief = asset?.brief;
  const [busy, setBusy] = useState(false);
  const [creatives, setCreatives] = useState([]);
  const [generatingIdx, setGeneratingIdx] = useState(null);
  const [generatingAll, setGeneratingAll] = useState(false);
  const animate = ['queued', 'extracting', 'analyzing'].includes(asset?.status);

  const loadCreatives = React.useCallback(async () => {
    if (!brief?.id) return;
    try {
      const r = await axios.get(
        `${API}/cortex/creatives?brief_id=${brief.id}`,
        { withCredentials: true });
      setCreatives(r.data?.creatives || []);
    } catch (_e) { setCreatives([]); }
  }, [brief?.id]);

  React.useEffect(() => { loadCreatives(); }, [loadCreatives]);

  // Poll while any creative is mid-generation.
  React.useEffect(() => {
    const busy = creatives.some((c) => c.status === 'generating');
    if (!busy) return undefined;
    const id = setInterval(loadCreatives, 3000);
    return () => clearInterval(id);
  }, [creatives, loadCreatives]);

  const creativeForIdx = (i) =>
    creatives.find((c) => c.concept_index === i && c.status !== 'deleted');

  const generateConcept = async (idx) => {
    setGeneratingIdx(idx);
    try {
      await axios.post(
        `${API}/cortex/briefs/${brief.id}/concepts/${idx}/generate`,
        {}, { withCredentials: true });
      await loadCreatives();
    } catch (_e) {
      // surfaced in the row's `failed` state on next poll
    } finally { setGeneratingIdx(null); }
  };

  const generateAll = async () => {
    setGeneratingAll(true);
    try {
      await axios.post(`${API}/cortex/briefs/${brief.id}/generate-all`,
                          {}, { withCredentials: true });
      await loadCreatives();
    } catch (_e) { /* */ }
    finally { setGeneratingAll(false); }
  };

  const regenerate = async (creativeId) => {
    try {
      await axios.post(`${API}/cortex/creatives/${creativeId}/regenerate`,
                          {}, { withCredentials: true });
      await loadCreatives();
    } catch (_e) { /* */ }
  };

  const regenerateBrief = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/cortex/assets/${asset.id}/brief`,
                          {}, { withCredentials: true });
      onChanged && onChanged();
    } catch (_e) { /* */ }
    finally { setBusy(false); }
  };

  const buildCampaign = async () => {
    if (!brief?.id) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/cortex/campaigns`,
                                    { brief_id: brief.id },
                                    { withCredentials: true });
      // Hop to the campaign detail so the user watches the build trace.
      window.location.href = `/dashboard/campaigns?id=${r.data.id}`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('build campaign failed', e?.response?.data);
      setBusy(false);
    }
  };

  if (!brief && animate) {
    return (
      <div data-testid="brief-pending"
            className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">
        <Loader2 size={14} className="inline mr-2 animate-spin" />
        Synthesizing the campaign brief…
      </div>
    );
  }
  if (!brief) {
    return (
      <div data-testid="brief-empty"
            className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-400 text-center">
        <Compass size={18} className="text-violet-300 mx-auto mb-2" />
        Creative Brief hasn't been generated for this asset yet.
        <button onClick={regenerateBrief} disabled={busy}
                data-testid="brief-generate-btn"
                className="block mx-auto mt-3 text-[12px] font-semibold px-3 py-1.5 rounded-md bg-violet-500/20 hover:bg-violet-500/30 text-violet-200 border border-violet-500/40 transition disabled:opacity-50">
          {busy ? 'Generating…' : 'Generate brief'}
        </button>
      </div>
    );
  }

  const conf = Number(brief.confidence) || 0;
  const tone = ConfidenceTone(conf);
  const ta = brief.target_audience || {};

  return (
    <motion.div
      data-testid="brief-panel"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="rounded-xl border border-fuchsia-500/20 bg-gradient-to-br from-fuchsia-500/[0.06] via-violet-500/[0.02] to-fuchsia-500/[0.03] p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-widest text-fuchsia-300 font-semibold flex items-center gap-1.5">
          <Compass size={11} /> Creative Brief
        </div>
        <div className="flex items-center gap-2">
          <span data-testid="brief-confidence"
                className={`text-[10px] uppercase tracking-wider font-bold ${tone.text}`}>
            {conf}% confidence
          </span>
          <button onClick={buildCampaign} disabled={busy}
                  data-testid="brief-build-campaign-btn"
                  className="text-[11px] font-semibold px-2.5 py-1 rounded-md bg-gradient-to-r from-violet-500 to-fuchsia-500 hover:from-violet-400 hover:to-fuchsia-400 text-white shadow-md shadow-violet-500/20 transition flex items-center gap-1 disabled:opacity-50">
            {busy
              ? <><Loader2 size={10} className="animate-spin" /> Building…</>
              : <><Rocket size={10} /> Build full campaign</>}
          </button>
          <button onClick={regenerateBrief} disabled={busy}
                  data-testid="brief-regenerate-btn"
                  className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1 disabled:opacity-50">
            <RefreshCw size={10} className={busy ? 'animate-spin' : ''} /> Regenerate
          </button>
        </div>
      </div>

      {/* Campaign goal — hero line */}
      <div data-testid="brief-goal"
            className="rounded-lg p-3 mb-3 bg-fuchsia-500/[0.07] border border-fuchsia-500/20">
        <div className="text-[9.5px] uppercase tracking-wider text-fuchsia-300 font-semibold mb-1 flex items-center gap-1">
          <Target size={10} /> Campaign goal
        </div>
        <div className="text-[14px] text-zinc-100 leading-relaxed font-medium">
          {brief.campaign_goal}
        </div>
      </div>

      {/* Two-column: Audience + Offer */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 mb-3">
        {/* Audience */}
        <div data-testid="brief-audience"
              className="rounded-lg p-3 bg-white/[0.02] border border-white/5">
          <div className="text-[9.5px] uppercase tracking-wider text-emerald-300 font-semibold mb-1.5 flex items-center gap-1">
            <Users size={10} /> Target audience
          </div>
          <div className="text-[12.5px] text-zinc-100 font-semibold mb-1.5">
            {ta.primary || '—'}
          </div>
          {ta.secondary?.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {ta.secondary.map((s, i) => (
                <span key={i} className="text-[10.5px] px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-200">
                  {s}
                </span>
              ))}
            </div>
          )}
          {ta.psychographics?.length > 0 && (
            <div className="space-y-0.5 text-[11.5px] text-zinc-400">
              {ta.psychographics.slice(0, 5).map((p, i) => (
                <div key={i} className="flex gap-1.5"><span className="text-zinc-600">·</span>{p}</div>
              ))}
            </div>
          )}
        </div>

        {/* Offer */}
        <div data-testid="brief-offer"
              className="rounded-lg p-3 bg-white/[0.02] border border-white/5">
          <div className="text-[9.5px] uppercase tracking-wider text-violet-300 font-semibold mb-1.5 flex items-center gap-1">
            <Megaphone size={10} /> The offer
          </div>
          <div className="text-[13px] text-zinc-100 leading-relaxed">
            {brief.offer || '—'}
          </div>
        </div>
      </div>

      {/* Messaging angles */}
      {brief.messaging_angles?.length > 0 && (
        <div data-testid="brief-angles"
              className="rounded-lg p-3 mb-3 bg-white/[0.02] border border-white/5">
          <div className="text-[9.5px] uppercase tracking-wider text-cyan-300 font-semibold mb-2 flex items-center gap-1">
            <Lightbulb size={10} /> Messaging angles
          </div>
          <ul className="space-y-1.5">
            {brief.messaging_angles.map((a, i) => (
              <li key={i} className="text-[12.5px] text-zinc-200 leading-snug flex gap-2">
                <span className="text-cyan-400 mt-0.5 shrink-0">{i + 1}.</span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommended platforms */}
      {brief.recommended_platforms?.length > 0 && (
        <div data-testid="brief-platforms" className="mb-3">
          <div className="text-[9.5px] uppercase tracking-wider text-zinc-400 font-semibold mb-1.5 flex items-center gap-1">
            <Hash size={10} /> Recommended platforms
          </div>
          <div className="flex flex-wrap gap-1.5">
            {brief.recommended_platforms.map((p, i) => {
              const key = p.toLowerCase().replace(/\s+/g, '_');
              const ptone = PLATFORM_TONE[key] || 'text-zinc-300 border-white/15 bg-white/[0.04]';
              return (
                <span key={i}
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${ptone}`}>
                  {p}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Content plan */}
      {brief.content_plan?.length > 0 && (
        <div data-testid="brief-content-plan" className="mb-3">
          <div className="text-[9.5px] uppercase tracking-wider text-amber-300 font-semibold mb-1.5 flex items-center gap-1">
            <Layers size={10} /> Content plan
          </div>
          <div className="space-y-1.5">
            {brief.content_plan.map((row, i) => {
              const key = (row.platform || '').toLowerCase().replace(/\s+/g, '_');
              const ptone = PLATFORM_TONE[key] || 'text-zinc-300 border-white/15 bg-white/[0.04]';
              return (
                <div key={i} className="rounded-md bg-white/[0.02] border border-white/5 p-2">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className={`text-[10.5px] font-semibold px-1.5 py-0.5 rounded border ${ptone}`}>
                      {row.platform}
                    </span>
                    {row.format && (
                      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
                        · {row.format}
                      </span>
                    )}
                    {row.frequency && (
                      <span className="text-[10px] text-zinc-500 ml-auto">{row.frequency}</span>
                    )}
                  </div>
                  <div className="text-[12px] text-zinc-300 leading-snug">
                    {row.concept}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Creative concepts — now with one-click image generation */}
      {brief.creative_concepts?.length > 0 && (
        <div data-testid="brief-concepts">
          <div className="flex items-center justify-between mb-1.5">
            <div className="text-[9.5px] uppercase tracking-wider text-violet-300 font-semibold flex items-center gap-1">
              <Sparkles size={10} /> Creative concepts
            </div>
            <button onClick={generateAll} disabled={generatingAll}
                    data-testid="generate-all-btn"
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-gradient-to-r from-violet-500 to-fuchsia-500 hover:from-violet-400 hover:to-fuchsia-400 text-white shadow-md shadow-violet-500/20 transition flex items-center gap-1 disabled:opacity-50">
              {generatingAll
                ? <><Loader2 size={10} className="animate-spin" /> Generating all…</>
                : <><Wand2 size={10} /> Generate all images</>}
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
            {brief.creative_concepts.map((c, i) => {
              const cr = creativeForIdx(i);
              return (
                <ConceptCard key={i}
                              concept={c} idx={i}
                              creative={cr}
                              busy={generatingIdx === i}
                              onGenerate={() => generateConcept(i)}
                              onRegenerate={() => cr && regenerate(cr.id)} />
              );
            })}
          </div>
        </div>
      )}
    </motion.div>
  );
}



function ConceptCard({ concept, idx, creative, busy, onGenerate, onRegenerate }) {
  const status = creative?.status;
  const fileUrl = creative?.file_url;
  const generating = status === 'generating' || busy;
  const failed = status === 'failed';
  const complete = status === 'complete' && fileUrl;
  const provider = creative?.provider;
  const providerTone = provider === 'openai'
    ? 'text-emerald-300 bg-emerald-500/15 border-emerald-500/30'
    : 'text-fuchsia-300 bg-fuchsia-500/15 border-fuchsia-500/30';

  // Stream the image through the auth-scoped /assets/file route. The
  // backend's storage adapter publishes file_url already prefixed with
  // /api/cortex/assets/file/<user_id>/creatives/<id>.png so we just
  // prepend REACT_APP_BACKEND_URL when needed.
  const imgSrc = fileUrl ? (fileUrl.startsWith('http')
    ? fileUrl
    : `${process.env.REACT_APP_BACKEND_URL}${fileUrl}`) : null;

  return (
    <div data-testid={`concept-card-${idx}`}
          className="rounded-md bg-violet-500/[0.05] border border-violet-500/15 p-2.5 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] text-zinc-100 font-semibold truncate">{concept.title}</span>
        {concept.format && (
          <span className="text-[9.5px] uppercase tracking-wider text-violet-300 font-bold px-1.5 py-0.5 rounded bg-violet-500/15 border border-violet-500/30 shrink-0">
            {concept.format}
          </span>
        )}
      </div>
      <div className="text-[11.5px] text-zinc-300 leading-snug">
        {concept.description}
      </div>

      {/* Image surface */}
      {complete && imgSrc && (
        <div className="relative rounded-md overflow-hidden border border-white/10 bg-black/30">
          <img src={imgSrc} alt={concept.title}
                data-testid={`concept-image-${idx}`}
                className="w-full aspect-square object-cover" />
          <span className={`absolute top-1 left-1 text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded border ${providerTone}`}>
            {provider}
          </span>
        </div>
      )}
      {generating && (
        <div data-testid={`concept-generating-${idx}`}
              className="rounded-md border border-violet-500/20 bg-violet-500/[0.05] aspect-square flex flex-col items-center justify-center text-violet-300">
          <Loader2 size={20} className="animate-spin mb-1" />
          <span className="text-[11px]">Generating image…</span>
          <span className="text-[9.5px] text-zinc-500 mt-0.5">~30-60s</span>
        </div>
      )}
      {failed && (
        <div data-testid={`concept-failed-${idx}`}
              className="rounded-md border border-rose-500/30 bg-rose-500/[0.06] p-2 text-[11px] text-rose-200">
          <AlertTriangle size={11} className="inline mr-1" />
          Generation failed. <span className="text-zinc-500 font-mono">{(creative?.error || '').slice(0, 80)}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1 pt-1">
        {!complete && !generating && (
          <button onClick={onGenerate}
                  data-testid={`concept-generate-${idx}`}
                  className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-violet-500/20 hover:bg-violet-500/30 text-violet-200 border border-violet-500/40 transition flex items-center gap-1">
            <Wand2 size={10} /> Generate image
          </button>
        )}
        {complete && (
          <>
            <button onClick={onRegenerate}
                    data-testid={`concept-regenerate-${idx}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1">
              <RefreshCw size={9} /> Regenerate
            </button>
            <a href={imgSrc} target="_blank" rel="noreferrer"
                data-testid={`concept-open-${idx}`}
                className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1">
              <ImageIcon size={9} /> Open full
            </a>
          </>
        )}
        {failed && (
          <button onClick={onGenerate}
                  data-testid={`concept-retry-${idx}`}
                  className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-rose-500/15 hover:bg-rose-500/25 text-rose-200 border border-rose-500/30 transition flex items-center gap-1">
            <RefreshCw size={9} /> Retry
          </button>
        )}
      </div>
    </div>
  );
}
