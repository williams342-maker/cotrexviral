import React, { useState } from 'react';
import axios from 'axios';
import {
  Rocket, Compass, Filter, Send, MessageCircle, GraduationCap,
  ShieldCheck, Activity, ChevronRight, Loader2, ExternalLink, X,
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/* ActiveMissionRail — live status panel for missions Cortex is running.
   Updates every 5s via polling, shown above the AI Opportunities list. */

const PHASE_ICON = {
  discovery:     Compass,
  qualification: Filter,
  outreach:      Send,
  conversations: MessageCircle,
  onboarding:    GraduationCap,
  retention:     ShieldCheck,
};

const PHASE_TONE = {
  discovery:     'text-cyan-300',
  qualification: 'text-amber-300',
  outreach:      'text-violet-300',
  conversations: 'text-emerald-300',
  onboarding:    'text-fuchsia-300',
  retention:     'text-rose-300',
};

const fmtAge = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso); const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60)    return 'just now';
    if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    return `${Math.floor(diff/86400)}d ago`;
  } catch { return ''; }
};

const MissionTile = ({ m, onClick, onCancelled }) => {
  const [cancelling, setCancelling] = useState(false);
  const phaseKey = m.phase?.key || 'discovery';
  const Icon = PHASE_ICON[phaseKey] || Compass;
  const tone = PHASE_TONE[phaseKey] || 'text-zinc-300';
  const pct = Math.max(0, Math.min(100, m.progress?.pct ?? 0));
  const eta = m.progress?.eta_days != null
    ? (m.progress.eta_days === 0 ? 'today' : `${m.progress.eta_days}d`)
    : '—';
  const current = m.progress?.current ?? 0;
  const target = m.progress?.target ?? 0;

  const handleCancel = async (e) => {
    e.stopPropagation();
    if (cancelling) return;
    const label = m.title || 'this mission';
    if (!window.confirm(`Cancel "${label}"?\n\nCortex will stop all work on this mission. This cannot be undone.`)) return;
    setCancelling(true);
    try {
      await axios.post(`${API}/missions/${m.id}/cancel`, {}, { withCredentials: true });
      toast.success('Mission cancelled');
      onCancelled?.(m.id);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Failed to cancel mission';
      toast.error(detail);
      setCancelling(false);
    }
  };

  return (
    <div className={`group relative w-full rounded-xl border transition ${
              m.demo
                ? 'border-amber-400/30 hover:border-amber-400/50 bg-gradient-to-br from-amber-500/[0.06] to-amber-500/[0.02]'
                : 'border-violet-500/15 hover:border-violet-500/35 bg-gradient-to-br from-violet-500/[0.04] to-fuchsia-500/[0.02]'
            }`}>
      <button onClick={onClick} data-testid={`active-mission-${m.id}`}
              className="w-full text-left p-3">
      {/* Title row */}
      <div className="flex items-start gap-2 mb-2">
        <span className={`shrink-0 w-7 h-7 rounded-md bg-white/[0.04] border border-white/5 flex items-center justify-center ${tone}`}>
          <Icon size={12} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] font-semibold text-white leading-tight truncate pr-12">
            {m.title}
          </div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5 flex items-center gap-1.5">
            {m.demo && (
              <span data-testid="demo-mission-badge"
                    className="px-1 py-px rounded-sm text-[9px] font-bold bg-amber-500/20 text-amber-200 border border-amber-400/40">
                DEMO
              </span>
            )}
            <span>{(m.mission_type || 'mission').replace('_', ' ')}</span>
            {m.autonomy_level != null && (
              <span className="px-1 py-px rounded-sm text-[9px] font-bold bg-violet-500/15 text-violet-300 border border-violet-500/25">
                AUTONOMY L{m.autonomy_level}
              </span>
            )}
          </div>
        </div>
        <Activity size={10} className="text-emerald-400 animate-pulse mt-1.5" />
      </div>

      {/* Progress bar */}
      <div className="mb-2">
        <div className="flex items-center justify-between text-[10px] mb-1">
          <span className="text-zinc-500">
            {current} / {target} <span className="text-zinc-700">·</span>
          </span>
          <span className="tabular-nums font-semibold text-zinc-300">{pct}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-violet-400 to-fuchsia-400 transition-all duration-700"
                style={{ width: `${Math.max(2, pct)}%` }} />
        </div>
      </div>

      {/* Phase + ETA + next-action */}
      <div className="space-y-1">
        <div className="flex items-center gap-1.5 text-[11px]">
          <span className="text-zinc-500">Current:</span>
          <span className={`font-semibold ${tone}`}>{m.phase?.label || 'Discovery'}</span>
          <span className="ml-auto text-zinc-500">ETA <strong className="text-zinc-300">{eta}</strong></span>
        </div>
        {m.next_action?.label && (
          <div className="flex items-start gap-1 text-[10.5px] text-zinc-500 leading-tight">
            <ChevronRight size={9} className="mt-0.5 shrink-0 text-zinc-600" />
            <span><strong className="text-zinc-400">Next:</strong> {m.next_action.description || m.next_action.label}</span>
          </div>
        )}
        {m.last_action?.label && (
          <div className="text-[10px] text-zinc-600">
            Last action: <span className="text-zinc-500">{m.last_action.label}</span>
            <span className="ml-1 text-zinc-700">· {fmtAge(m.last_action.created_at)}</span>
          </div>
        )}
      </div>
      </button>

      {/* Cancel button — floats top-right, surfaces on hover */}
      <button
        type="button"
        onClick={handleCancel}
        disabled={cancelling}
        data-testid={`cancel-mission-${m.id}`}
        title="Cancel mission"
        aria-label={`Cancel mission ${m.title || ''}`}
        className="absolute top-2 right-2 w-6 h-6 rounded-md flex items-center justify-center
                   text-zinc-500 hover:text-rose-300 hover:bg-rose-500/15 border border-transparent
                   hover:border-rose-500/30 opacity-0 group-hover:opacity-100 focus:opacity-100
                   transition disabled:opacity-50 disabled:cursor-not-allowed">
        {cancelling ? <Loader2 size={11} className="animate-spin" /> : <X size={12} />}
      </button>
    </div>
  );
};

export const ActiveMissionRail = ({ missions = [], loading, onOpenDetails, onCancelled }) => {
  if (!loading && missions.length === 0) return null;
  return (
    <section data-testid="active-mission-rail" className="mb-3">
      <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold mb-2 flex items-center gap-1.5">
        <Rocket size={10} /> Active Missions
        {loading && <Loader2 size={10} className="animate-spin ml-1" />}
        <span className="ml-auto text-zinc-500 normal-case tracking-normal font-normal">
          {missions.length} running
        </span>
      </div>
      <div className="space-y-2">
        {missions.map((m) => (
          <MissionTile key={m.id} m={m}
                       onClick={() => onOpenDetails?.(m)}
                       onCancelled={onCancelled} />
        ))}
      </div>
    </section>
  );
};

export default ActiveMissionRail;
