import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import {
  Sparkles, Lightbulb, AlertCircle, Target, TrendingUp, ChevronDown, ChevronUp,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* MissionProvenanceCard — rendered on the Mission Detail page when the
 * mission was spawned via Optimize-via-Bridge. Every such mission has
 * `auto_optimize_meta.bridge_id` stamped pointing at the source
 * Recommendation Bridge — this card hydrates that bridge and shows the
 * provenance inline:
 *
 *     "This mission exists because Cortex saw X and recommended Y at Z%
 *      confidence."
 *
 * Collapsible — closed by default to keep the mission hero clean; one
 * click expands the 4-part executive insight (Finding / Root Cause /
 * Recommendation / Expected Impact) + confidence meter.
 */

const ConfidenceTone = (conf) => {
  if (conf >= 80) return { bar: 'from-emerald-500 to-emerald-400', text: 'text-emerald-300' };
  if (conf >= 60) return { bar: 'from-amber-400 to-amber-300',     text: 'text-amber-300' };
  return                  { bar: 'from-rose-400 to-rose-300',       text: 'text-rose-300' };
};


export default function MissionProvenanceCard({ mission }) {
  const meta = mission?.auto_optimize_meta;
  const bridgeId = meta?.bridge_id;
  const [bridge, setBridge] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!bridgeId) { setBridge(null); return; }
    (async () => {
      try {
        const r = await axios.get(
          `${API}/cortex/recommendation-bridges/by-id/${bridgeId}`,
          { withCredentials: true });
        setBridge(r.data || null);
      } catch (_e) { setBridge(null); }
    })();
  }, [bridgeId]);

  if (!bridgeId) return null;

  const conf = Number(bridge?.confidence ?? meta?.confidence ?? 0) || 0;
  const tone = ConfidenceTone(conf);
  const finding = bridge?.finding;
  const rec = bridge?.recommendation || meta?.recommendation;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      data-testid="mission-provenance-card"
      className="rounded-xl border border-violet-500/20 bg-gradient-to-br from-violet-500/[0.05] via-fuchsia-500/[0.02] to-violet-500/[0.03] p-4"
    >
      <button onClick={() => setExpanded((v) => !v)}
              data-testid="mission-provenance-toggle"
              className="w-full text-left flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center shrink-0">
          <Sparkles size={12} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[9.5px] uppercase tracking-widest text-violet-300 font-semibold mb-0.5">
            Why this mission exists · Cortex's Recommendation
          </div>
          <div className="text-[13px] text-zinc-200 leading-snug line-clamp-1">
            {rec || 'Source recommendation from a completed analysis.'}
          </div>
        </div>
        <span data-testid="mission-provenance-confidence"
              className={`text-[10px] font-bold tabular-nums shrink-0 ${tone.text}`}>
          {conf}%
        </span>
        {expanded
          ? <ChevronUp size={14} className="text-zinc-500 shrink-0" />
          : <ChevronDown size={14} className="text-zinc-500 shrink-0" />}
      </button>

      {expanded && bridge && (
        <motion.div initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-3 pt-3 border-t border-white/5 space-y-2.5">
          {finding && (
            <Row icon={Lightbulb} label="Finding" tone="text-cyan-300"
                  body={finding} testid="provenance-finding" />
          )}
          {bridge.root_cause && (
            <Row icon={AlertCircle} label="Root Cause" tone="text-amber-300"
                  body={bridge.root_cause} testid="provenance-root-cause" />
          )}
          {bridge.recommendation && (
            <Row icon={Target} label="Recommended Action" tone="text-violet-300"
                  body={bridge.recommendation} emphasize
                  testid="provenance-recommendation" />
          )}
          {bridge.expected_impact && (
            <Row icon={TrendingUp} label="Expected Impact" tone="text-emerald-300"
                  body={bridge.expected_impact} testid="provenance-impact" />
          )}

          <div className="pt-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9.5px] uppercase tracking-wider text-zinc-500 font-semibold">
                Confidence
              </span>
              <span className={`text-[10px] tabular-nums font-bold ${tone.text}`}>
                {conf}%
              </span>
            </div>
            <div className="h-1 bg-white/5 rounded-full overflow-hidden">
              <div className={`h-full bg-gradient-to-r ${tone.bar}`}
                    style={{ width: `${Math.max(2, conf)}%` }} />
            </div>
          </div>

          {(bridge.source || meta?.job_type) && (
            <div className="flex items-center gap-2 pt-2 text-[10px] text-zinc-500">
              {meta?.job_type && (
                <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/5">
                  from <span className="text-zinc-400">{meta.job_type}</span>
                </span>
              )}
              {bridge.source && (
                <span className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/5">
                  source: <span className="text-zinc-400">{bridge.source}</span>
                </span>
              )}
              {bridge.pushback && (
                <span className="px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
                  refined with user pushback
                </span>
              )}
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}


function Row({ icon: Icon, label, tone, body, emphasize, testid }) {
  return (
    <div data-testid={testid}
          className={`rounded-lg p-2 ${
            emphasize ? 'bg-violet-500/[0.06] border border-violet-500/15'
                       : 'bg-white/[0.02] border border-white/5'}`}>
      <div className={`flex items-center gap-1 text-[9px] uppercase tracking-wider font-semibold mb-0.5 ${tone}`}>
        <Icon size={9} /> {label}
      </div>
      <div className={`text-[12px] leading-relaxed ${
        emphasize ? 'text-zinc-100 font-medium' : 'text-zinc-300'}`}>
        {body}
      </div>
    </div>
  );
}
