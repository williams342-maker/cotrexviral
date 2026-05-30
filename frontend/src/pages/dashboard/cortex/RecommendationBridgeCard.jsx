import React, { useState } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import {
  Sparkles, FileText, Rocket, MessageSquare, ChevronRight,
  Lightbulb, AlertCircle, Target, TrendingUp, Loader2,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* RecommendationBridgeCard — the "what should I do next?" card.
 *
 * Rendered inside Cortex's chat bubble when a turn has
 * `kind: 'recommendation_bridge'` + an embedded `bridge` payload. The
 * card is structured as a 4-part executive insight (Finding, Root
 * Cause, Recommendation, Expected Impact) + a confidence meter +
 * three primary CTAs:
 *
 *   View Findings           → opens the source report
 *   Discuss Recommendation  → drops a deeper-reasoning Cortex turn
 *   Create Mission          → fires the one-click mission creation
 *
 * Per the spec, the recommendation should feel like a CONCLUSION —
 * Cortex's reasoning prose lands BEFORE this card renders, posted as
 * the message body of the same turn.
 */

const ConfidenceTone = (conf) => {
  if (conf >= 80) return {
    bar: 'from-emerald-500 to-emerald-400',
    label: 'text-emerald-300',
    badge: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-200',
    word: 'High confidence',
  };
  if (conf >= 60) return {
    bar: 'from-amber-400 to-amber-300',
    label: 'text-amber-300',
    badge: 'bg-amber-500/15 border-amber-500/30 text-amber-200',
    word: 'Moderate confidence',
  };
  return {
    bar: 'from-rose-400 to-rose-300',
    label: 'text-rose-300',
    badge: 'bg-rose-500/15 border-rose-500/30 text-rose-200',
    word: 'Low confidence',
  };
};


export default function RecommendationBridgeCard({ turn }) {
  const bridge = turn?.bridge || {};
  const [busy, setBusy] = useState(null);
  const [pushbackOpen, setPushbackOpen] = useState(false);
  const [pushbackText, setPushbackText] = useState('');

  if (!bridge.finding && !bridge.recommendation) return null;

  const conf = Number(bridge.confidence ?? 0) || 0;
  const tone = ConfidenceTone(conf);

  const viewFindings = () => {
    setBusy('view');
    window.open('/dashboard/reports', '_self');
  };

  const discuss = async () => {
    setBusy('discuss');
    try {
      await axios.post(
        `${API}/cortex/recommendation-bridges/${turn.job_id}/discuss`,
        {}, { withCredentials: true });
      window.dispatchEvent(new CustomEvent('cortex:conversation:refresh'));
      // Auto-open the pushback affordance so the user can immediately
      // tell Cortex why they disagree.
      setPushbackOpen(true);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('discuss failed', e?.response?.data);
    } finally {
      setBusy(null);
    }
  };

  const regenerateWithPushback = async () => {
    const text = pushbackText.trim();
    if (!text) return;
    setBusy('regenerate');
    try {
      await axios.post(
        `${API}/cortex/recommendation-bridges/${turn.job_id}/regenerate`,
        { pushback: text }, { withCredentials: true });
      setPushbackText('');
      setPushbackOpen(false);
      window.dispatchEvent(new CustomEvent('cortex:conversation:refresh'));
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('regenerate with pushback failed', e?.response?.data);
    } finally {
      setBusy(null);
    }
  };

  const createMission = async () => {
    setBusy('mission');
    try {
      const r = await axios.post(
        `${API}/cortex/analysis-jobs/${turn.job_id}/create-mission`,
        {}, { withCredentials: true });
      window.location.href = `/dashboard/cortex/${r.data.mission_id}`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('create mission failed', e?.response?.data);
      setBusy(null);
    }
  };

  return (
    <motion.div
      data-testid={`recommendation-bridge-${turn.job_id}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="rounded-2xl border border-violet-500/25 bg-gradient-to-br from-violet-500/[0.06] via-fuchsia-500/[0.02] to-violet-500/[0.04] p-4 mt-1 backdrop-blur-md"
    >
      {/* Header: Cortex Recommendation + confidence badge */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-1.5">
          <span className="w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
            <Sparkles size={12} />
          </span>
          <span className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold">
            Cortex's Recommendation
          </span>
        </div>
        <span data-testid="recommendation-bridge-confidence-badge"
              className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${tone.badge}`}>
          {conf}% · {tone.word}
        </span>
      </div>

      {/* Four-part executive insight */}
      <div className="space-y-2.5 mb-3">
        <InsightRow icon={Lightbulb}
                     label="Finding"
                     toneCls="text-cyan-300"
                     body={bridge.finding}
                     testid="recommendation-bridge-finding" />
        <InsightRow icon={AlertCircle}
                     label="Root Cause"
                     toneCls="text-amber-300"
                     body={bridge.root_cause}
                     testid="recommendation-bridge-root-cause" />
        <InsightRow icon={Target}
                     label="Recommended Action"
                     toneCls="text-violet-300"
                     body={bridge.recommendation}
                     emphasize
                     testid="recommendation-bridge-recommendation" />
        <InsightRow icon={TrendingUp}
                     label="Expected Impact"
                     toneCls="text-emerald-300"
                     body={bridge.expected_impact}
                     testid="recommendation-bridge-impact" />
      </div>

      {/* Confidence meter */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[9.5px] uppercase tracking-wider text-zinc-500 font-semibold">
            Confidence
          </span>
          <span className={`text-[10px] tabular-nums font-bold ${tone.label}`}>
            {conf}%
          </span>
        </div>
        <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
          <motion.div
            data-testid="recommendation-bridge-confidence-bar"
            className={`h-full bg-gradient-to-r ${tone.bar}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(2, conf)}%` }}
            transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
          />
        </div>
      </div>

      {/* CTA row — explain → recommend → offer mission */}
      <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-white/5">
        <button onClick={viewFindings}
                disabled={busy === 'view'}
                data-testid="recommendation-bridge-view-btn"
                className="text-[11px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/10 transition flex items-center gap-1 disabled:opacity-50">
          <FileText size={11} /> View Findings
        </button>
        <button onClick={discuss}
                disabled={busy === 'discuss'}
                data-testid="recommendation-bridge-discuss-btn"
                className="text-[11px] font-semibold px-2.5 py-1.5 rounded-md bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-200 border border-cyan-500/30 transition flex items-center gap-1 disabled:opacity-50">
          <MessageSquare size={11} /> Discuss Recommendation
        </button>
        <div className="flex-1 hidden sm:block" />
        <button onClick={createMission}
                disabled={busy === 'mission'}
                data-testid="recommendation-bridge-mission-btn"
                className="text-[11px] font-semibold px-3 py-1.5 rounded-md bg-gradient-to-r from-violet-500 to-fuchsia-500 hover:from-violet-400 hover:to-fuchsia-400 text-white shadow-lg shadow-violet-500/20 transition flex items-center gap-1 disabled:opacity-50">
          <Rocket size={11} /> Create Mission
          <ChevronRight size={10} />
        </button>
      </div>
      {/* Pushback affordance — opens after the user clicks Discuss.
          Submitting routes through POST /regenerate {pushback}, which
          re-synthesizes the bridge factoring in the user's feedback. */}
      {pushbackOpen && (
        <motion.div data-testid="recommendation-bridge-pushback"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 pt-3 border-t border-cyan-500/20">
          <div className="text-[10px] uppercase tracking-wider text-cyan-300 font-semibold mb-1.5 flex items-center gap-1">
            <MessageSquare size={10} /> Tell Cortex what you'd change
          </div>
          <textarea value={pushbackText}
                    onChange={(e) => setPushbackText(e.target.value)}
                    placeholder="e.g. We tried this last quarter and conversion didn't move — focus on retention instead."
                    data-testid="recommendation-bridge-pushback-input"
                    rows={2}
                    className="w-full text-[12px] text-zinc-100 bg-white/[0.03] border border-white/10 rounded-md px-2.5 py-2 mb-2 focus:outline-none focus:border-cyan-500/40 resize-none" />
          <div className="flex items-center gap-2">
            <button onClick={() => { setPushbackOpen(false); setPushbackText(''); }}
                    data-testid="recommendation-bridge-pushback-cancel"
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md hover:bg-white/5 text-zinc-400 hover:text-zinc-200 transition">
              Never mind
            </button>
            <div className="flex-1" />
            <button onClick={regenerateWithPushback}
                    disabled={busy === 'regenerate' || !pushbackText.trim()}
                    data-testid="recommendation-bridge-pushback-submit"
                    className="text-[10.5px] font-semibold px-2.5 py-1 rounded-md bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-100 border border-cyan-500/40 transition flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed">
              {busy === 'regenerate'
                ? <><Loader2 size={10} className="animate-spin" /> Rethinking…</>
                : <>Regenerate with my feedback <ChevronRight size={9} /></>}
            </button>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}


function InsightRow({ icon: Icon, label, toneCls, body, emphasize, testid }) {
  if (!body) return null;
  return (
    <div data-testid={testid}
          className={`rounded-lg p-2.5 ${
            emphasize
              ? 'bg-violet-500/[0.06] border border-violet-500/15'
              : 'bg-white/[0.02] border border-white/5'
          }`}>
      <div className={`flex items-center gap-1 text-[9.5px] uppercase tracking-wider font-semibold mb-1 ${toneCls}`}>
        <Icon size={10} /> {label}
      </div>
      <div className={`text-[12.5px] leading-relaxed ${
        emphasize ? 'text-zinc-100 font-medium' : 'text-zinc-300'
      }`}>
        {body}
      </div>
    </div>
  );
}
