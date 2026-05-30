import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Lightbulb, Sparkles, ChevronRight, Loader2, Rocket, Target,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* ExecutiveInsights — right-rail panel listing Cortex's recent
 * Recommendation Bridges sorted by a confidence × recency score.
 *
 * Source: GET /api/cortex/recommendation-bridges
 *
 * Each tile is a one-click affordance:
 *   • Click body  → opens the source report (View Findings analog)
 *   • Create Mission → fires the same one-click flow as the in-chat card
 *
 * Polls every 30s while mounted so newly-completed analyses surface
 * within the polling cadence without a manual refresh.
 */

const JOB_TYPE_TONE = {
  seo_scan:         'text-emerald-300 border-emerald-500/25',
  seller_discovery: 'text-violet-300 border-violet-500/25',
  site_scan:        'text-sky-300 border-sky-500/25',
  competitor_audit: 'text-amber-300 border-amber-500/25',
  content_audit:    'text-fuchsia-300 border-fuchsia-500/25',
};

const JOB_TYPE_LABEL = {
  seo_scan:         'SEO',
  seller_discovery: 'Sellers',
  site_scan:        'Site',
  competitor_audit: 'Competitor',
  content_audit:    'Content',
};

const ConfidenceColor = (conf) => {
  if (conf >= 80) return 'text-emerald-300 bg-emerald-500/15 border-emerald-500/30';
  if (conf >= 60) return 'text-amber-300 bg-amber-500/15 border-amber-500/30';
  return 'text-rose-300 bg-rose-500/15 border-rose-500/30';
};

// Score by confidence + recency (newer & higher-confidence first).
function score(b) {
  const conf = Number(b.confidence) || 0;
  const created = new Date(b.created_at || 0).getTime();
  const ageMs = Date.now() - created;
  const ageHours = Math.max(0, ageMs / 3_600_000);
  // Decay: full weight in last 24h, 50% by 7d, ~0 by 30d.
  const recency = Math.max(0, 1 - ageHours / (24 * 7));
  return conf * (0.6 + 0.4 * recency);
}


export default function ExecutiveInsights() {
  const [bridges, setBridges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/recommendation-bridges?limit=15`,
                                  { withCredentials: true });
      const rows = (r.data?.bridges || []).slice();
      rows.sort((a, b) => score(b) - score(a));
      setBridges(rows.slice(0, 5));
    } catch (_e) { setBridges([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    const refresh = () => load();
    window.addEventListener('cortex:conversation:refresh', refresh);
    return () => {
      clearInterval(id);
      window.removeEventListener('cortex:conversation:refresh', refresh);
    };
  }, [load]);

  const openReport = () => window.open('/dashboard/reports', '_self');

  const createMission = async (jobId) => {
    setBusyId(jobId);
    try {
      const r = await axios.post(
        `${API}/cortex/analysis-jobs/${jobId}/create-mission`,
        {}, { withCredentials: true });
      window.location.href = `/dashboard/missions?id=${r.data.mission_id}`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('exec-insights create mission failed', e?.response?.data);
      setBusyId(null);
    }
  };

  if (!loading && bridges.length === 0) return null;

  return (
    <div data-testid="executive-insights-panel"
          className="rounded-xl border border-violet-500/15 bg-violet-500/[0.03] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold flex items-center gap-1.5">
          <Lightbulb size={10} /> Executive Insights
        </div>
        <span className="text-[9px] text-zinc-500 uppercase tracking-wider">
          Top {bridges.length} {loading && <Loader2 size={9} className="inline animate-spin ml-1" />}
        </span>
      </div>

      <AnimatePresence mode="popLayout">
        {bridges.map((b) => (
          <motion.div key={b.id || b.job_id}
                        layout
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ duration: 0.3 }}
                        data-testid={`executive-insight-${b.job_id}`}
                        className={`rounded-lg border bg-white/[0.02] p-2.5 mb-2 last:mb-0
                                     ${JOB_TYPE_TONE[b.job_type] || 'border-white/10 text-zinc-300'}`}>
            <div className="flex items-center justify-between gap-1.5 mb-1.5">
              <div className="flex items-center gap-1.5 min-w-0">
                <Sparkles size={9} className="shrink-0" />
                <span className="text-[9.5px] uppercase tracking-wider font-semibold">
                  {JOB_TYPE_LABEL[b.job_type] || b.job_type}
                </span>
                {b.target && (
                  <span className="text-[9px] text-zinc-500 truncate">
                    · {b.target.replace(/^https?:\/\//, '')}
                  </span>
                )}
              </div>
              <span data-testid={`exec-insight-confidence-${b.job_id}`}
                    className={`text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-full border ${ConfidenceColor(Number(b.confidence) || 0)}`}>
                {Number(b.confidence) || 0}%
              </span>
            </div>

            <button onClick={openReport}
                    className="w-full text-left"
                    data-testid={`exec-insight-body-${b.job_id}`}>
              {b.finding && (
                <div className="text-[11.5px] text-zinc-200 leading-snug font-medium mb-1">
                  {b.finding}
                </div>
              )}
              {b.recommendation && (
                <div className="text-[10.5px] text-zinc-400 leading-snug line-clamp-2">
                  <Target size={9} className="inline -mt-0.5 mr-1 text-violet-400" />
                  {b.recommendation}
                </div>
              )}
            </button>

            <div className="flex items-center gap-1 mt-2 pt-1.5 border-t border-white/5">
              <button onClick={openReport}
                      data-testid={`exec-insight-view-${b.job_id}`}
                      className="text-[10px] font-semibold px-1.5 py-0.5 rounded hover:bg-white/10 text-zinc-400 hover:text-zinc-200 transition flex items-center gap-0.5">
                View <ChevronRight size={8} />
              </button>
              <div className="flex-1" />
              <button onClick={() => createMission(b.job_id)}
                      disabled={busyId === b.job_id}
                      data-testid={`exec-insight-mission-${b.job_id}`}
                      className="text-[10px] font-semibold px-2 py-0.5 rounded bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition flex items-center gap-1 disabled:opacity-50">
                <Rocket size={9} /> Mission
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
