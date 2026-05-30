import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Activity, AlertTriangle, Search, Globe, Users, FileText, BarChart3,
  RotateCw, Bug, CheckCircle2, X, ChevronRight, Sparkles, Loader2,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* ActiveWorkRail — live status for long-running analysis jobs.

   CRITICAL: this rail is the canonical truth for whether Cortex is
   actually running an analysis. If a job isn't here, Cortex is not
   doing the work — anything else is a lie. The chat layer creates
   real `analysis_jobs` rows BEFORE saying "I'm scanning..." so the
   user can see the proof in this rail.

   Sections (rendered in order):
     1. Running   — animated progress, ETA, current step
     2. Queued    — waiting list
     3. Completed — flash + slide animation on transition; persists 1h
     4. Failed    — Retry + Debug CTAs

   Polls every 1.5s while any non-terminal job exists; backs off to
   8s when idle. */

const JOB_ICONS = {
  seo_scan:         Globe,
  seller_discovery: Users,
  site_scan:        Search,
  competitor_audit: BarChart3,
  content_audit:    FileText,
};

const JOB_TONES = {
  seo_scan:         'text-emerald-300 border-emerald-500/25 bg-emerald-500/[0.04]',
  seller_discovery: 'text-violet-300 border-violet-500/25 bg-violet-500/[0.04]',
  site_scan:        'text-sky-300 border-sky-500/25 bg-sky-500/[0.04]',
  competitor_audit: 'text-amber-300 border-amber-500/25 bg-amber-500/[0.04]',
  content_audit:    'text-fuchsia-300 border-fuchsia-500/25 bg-fuchsia-500/[0.04]',
};

export default function ActiveWorkRail({ onLaunchScan }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [flashIds, setFlashIds] = useState(new Set());
  const prevStatusRef = React.useRef({});

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/analysis-jobs`,
                                  { withCredentials: true });
      const next = r.data.jobs || [];

      // Detect status transitions queued/running → completed/failed,
      // mark those IDs as "flash" for the slide-in animation.
      const toFlash = new Set();
      next.forEach((j) => {
        const prev = prevStatusRef.current[j.id];
        const justFinished = (prev === 'running' || prev === 'queued')
          && (j.status === 'completed' || j.status === 'failed');
        if (justFinished) toFlash.add(j.id);
      });
      if (toFlash.size > 0) {
        setFlashIds((cur) => {
          const merged = new Set(cur);
          toFlash.forEach((id) => merged.add(id));
          return merged;
        });
        // Auto-clear the flash class after 1.4s.
        setTimeout(() => {
          setFlashIds((cur) => {
            const cp = new Set(cur);
            toFlash.forEach((id) => cp.delete(id));
            return cp;
          });
        }, 1400);
      }

      // Update prev status map for next diff.
      prevStatusRef.current = next.reduce((acc, j) => {
        acc[j.id] = j.status;
        return acc;
      }, {});

      setJobs(next);
    } catch (_e) { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Polling cadence: 1.5s while any non-terminal job exists; 8s when idle.
  useEffect(() => {
    const hasActive = jobs.some(
      (j) => j.status === 'running' || j.status === 'queued');
    const interval = hasActive ? 1500 : 8000;
    const id = setInterval(load, interval);
    return () => clearInterval(id);
  }, [jobs, load]);

  // Group jobs for the rail sections. "reviewed" cards drop off the
  // rail; failed stays until the user retries/cancels.
  const running   = jobs.filter((j) => j.status === 'running');
  const queued    = jobs.filter((j) => j.status === 'queued');
  const completed = jobs.filter((j) => j.status === 'completed');
  const failed    = jobs.filter((j) => j.status === 'failed');

  const isEmpty = !loading && jobs.length === 0;

  return (
    <div data-testid="active-work-rail" className="space-y-2">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-2 flex items-center gap-1.5">
        <Activity size={10} className="text-emerald-400" /> Active Work
        {loading && <Loader2 size={10} className="animate-spin ml-1" />}
        <span className="ml-auto text-zinc-600 normal-case tracking-normal font-normal">
          {running.length} running · {completed.length} done
        </span>
      </div>

      {isEmpty ? (
        <div data-testid="active-work-empty"
              className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-center">
          <div className="text-[11px] text-zinc-500 mb-2">
            No active analyses. Cortex picks scans up when you ask.
          </div>
          <button onClick={() => onLaunchScan?.('seo_scan')}
                  data-testid="launch-seo-scan-btn"
                  className="text-[10px] font-semibold px-2.5 py-1.5 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition inline-flex items-center gap-1.5">
            <Sparkles size={9} /> Run SEO Scan
          </button>
        </div>
      ) : (
        <AnimatePresence mode="popLayout">
          {[...running, ...queued, ...completed, ...failed].map((j) => (
            <motion.div key={j.id}
                          layout
                          initial={{ opacity: 0, y: -8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.95 }}
                          transition={{ duration: 0.35, ease: 'easeOut' }}
                          className={flashIds.has(j.id)
                            ? 'animate-[pulse_1s_ease-in-out_1]'
                            : ''}>
              <JobCard job={j} onChange={load} />
            </motion.div>
          ))}
        </AnimatePresence>
      )}
    </div>
  );
}


// ---------------------------------------------------------- JobCard
function JobCard({ job, onChange }) {
  const Icon = JOB_ICONS[job.job_type] || Search;
  const tone = JOB_TONES[job.job_type] || JOB_TONES.seo_scan;
  const isRunning   = job.status === 'running';
  const isQueued    = job.status === 'queued';
  const isCompleted = job.status === 'completed';
  const isFailed    = job.status === 'failed';

  const retry = async () => {
    try {
      await axios.post(`${API}/cortex/analysis-jobs/${job.id}/retry`, {},
                        { withCredentials: true });
      onChange?.();
    } catch (_e) { /* */ }
  };
  const cancel = async () => {
    try {
      await axios.post(`${API}/cortex/analysis-jobs/${job.id}/cancel`, {},
                        { withCredentials: true });
      onChange?.();
    } catch (_e) { /* */ }
  };
  const markReviewed = async () => {
    try {
      await axios.post(`${API}/cortex/analysis-jobs/${job.id}/mark-reviewed`,
                        {}, { withCredentials: true });
      onChange?.();
    } catch (_e) { /* */ }
  };
  const createMission = async () => {
    try {
      const r = await axios.post(
        `${API}/cortex/analysis-jobs/${job.id}/create-mission`,
        {}, { withCredentials: true });
      // Hop to Mission Control so the user lands on the new mission.
      window.location.href = `/dashboard/missions?id=${r.data.mission_id}`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('create mission failed', e?.response?.data);
    }
  };

  return (
    <div data-testid={`active-work-job-${job.id}`}
          className={`rounded-xl border p-3 transition ${tone}
                       ${isFailed ? 'border-rose-500/30 bg-rose-500/[0.04]' : ''}
                       ${isCompleted ? 'border-emerald-500/30 bg-emerald-500/[0.05]' : ''}`}>
      {/* Header row */}
      <div className="flex items-start gap-2 mb-2">
        <span className="shrink-0 w-7 h-7 rounded-md bg-white/[0.05] border border-white/5 flex items-center justify-center">
          <Icon size={12} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <div className="text-[12.5px] font-semibold text-white truncate">
              {job.job_label}
            </div>
            {isCompleted && <CheckCircle2 size={11} className="text-emerald-400 shrink-0" />}
            {isFailed && <AlertTriangle size={11} className="text-rose-400 shrink-0" />}
            {isRunning && <Activity size={9} className="text-emerald-400 animate-pulse shrink-0" />}
          </div>
          <div className="text-[10px] text-zinc-500 mt-0.5 flex items-center gap-1.5">
            <span className="font-mono">#{job.id.slice(0, 8)}</span>
            {job.target && (
              <>
                <span>·</span>
                <span className="truncate">{job.target}</span>
              </>
            )}
          </div>
        </div>
        {(isRunning || isQueued) && (
          <button onClick={cancel} title="Cancel"
                  data-testid={`active-work-cancel-${job.id}`}
                  className="shrink-0 w-6 h-6 rounded hover:bg-white/10 text-zinc-500 hover:text-zinc-200 transition flex items-center justify-center">
            <X size={10} />
          </button>
        )}
      </div>

      {/* Progress (running) */}
      {(isRunning || isQueued) && (
        <>
          <div className="h-1.5 bg-white/5 rounded-full overflow-hidden mb-2">
            <motion.div
              className="h-full bg-gradient-to-r from-violet-400 via-fuchsia-400 to-violet-400"
              style={{ backgroundSize: '200% 100%' }}
              animate={{
                width: `${job.progress_pct}%`,
                backgroundPosition: ['0% 0%', '100% 0%'],
              }}
              transition={{
                width: { duration: 0.6, ease: 'easeOut' },
                backgroundPosition: { duration: 2.5, repeat: Infinity, ease: 'linear' },
              }}
            />
          </div>
          <div className="grid grid-cols-2 gap-1 text-[10px]">
            <div>
              <div className="text-zinc-500">Current</div>
              <div className="text-zinc-200 truncate">{job.current_step || '—'}</div>
            </div>
            <div>
              <div className="text-zinc-500">Next</div>
              <div className="text-zinc-400 truncate">{job.next_step || '—'}</div>
            </div>
          </div>
          <div className="flex items-center justify-between mt-1.5 text-[10px]">
            <span className="text-zinc-500">
              Status: <span className={isRunning ? 'text-emerald-300' : 'text-amber-300'}>
                {isRunning ? 'Running' : 'Queued'}
              </span>
            </span>
            <span className="text-zinc-500 tabular-nums">
              {job.eta_seconds != null ? `~${job.eta_seconds}s left` : ''}
              <span className="ml-2 text-zinc-300 tabular-nums">{job.progress_pct}%</span>
            </span>
          </div>
        </>
      )}

      {/* Completed summary + CTAs */}
      {isCompleted && (
        <>
          {job.result_summary && (
            <div className="text-[11.5px] text-zinc-300 leading-snug mb-2">
              {job.result_summary}
            </div>
          )}
          {job.metrics && Object.keys(job.metrics).length > 0 && (
            <div className="grid grid-cols-3 gap-1 mb-2">
              {Object.entries(job.metrics).slice(0, 3).map(([k, v]) => (
                <div key={k} className="text-center bg-white/[0.03] rounded-md py-1.5 px-1">
                  <div className="text-[14px] text-emerald-200 font-bold tabular-nums leading-none">
                    {typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v}
                  </div>
                  <div className="text-[8.5px] text-zinc-500 mt-0.5 uppercase tracking-wider truncate">
                    {k.replace(/_/g, ' ')}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => {
                      if (job.result_link) window.open(job.result_link, '_self');
                      markReviewed();
                    }}
                    data-testid={`active-work-view-${job.id}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-500/30 transition flex items-center gap-1">
              {job.view_label} <ChevronRight size={9} />
            </button>
            <button onClick={createMission}
                    data-testid={`active-work-create-${job.id}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition">
              {job.create_label}
            </button>
            <button disabled title="Coming soon"
                    data-testid={`active-work-optimize-${job.id}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-white/5 text-zinc-500 border border-white/10 transition opacity-60 cursor-not-allowed">
              {job.optimize_label} · soon
            </button>
          </div>
        </>
      )}

      {/* Failed CTAs */}
      {isFailed && (
        <>
          <div className="text-[11.5px] text-rose-200 leading-snug mb-2">
            <span className="text-zinc-500">Reason:</span> {job.error_message || 'Unknown failure'}
          </div>
          <div className="flex gap-1.5">
            <button onClick={retry}
                    data-testid={`active-work-retry-${job.id}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-rose-500/15 hover:bg-rose-500/25 text-rose-200 border border-rose-500/30 transition flex items-center gap-1">
              <RotateCw size={9} /> Retry
            </button>
            <button onClick={() => window.open('/dashboard?debug=1&job=' + job.id, '_self')}
                    data-testid={`active-work-debug-${job.id}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/10 transition flex items-center gap-1">
              <Bug size={9} /> Debug
            </button>
          </div>
        </>
      )}
    </div>
  );
}
