import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Brain, Loader2, ArrowLeft, Sparkles, Play, Pause, Target, Zap, XCircle,
  Calendar, Hash, Trophy, Compass, Wand2, Send, TrendingUp, Activity,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import MissionProvenanceCard from './cortex/MissionProvenanceCard';

/* Cortex workspace — both an index (no :id) and a mission detail (:id).

   Index view: Cortex hero + "Start a mission" CTA + list of running missions.
   Detail view: a single mission's progress + dispatch log per team + autonomy panel.
*/

const TEAM_ICONS = { scout: Compass, creator: Wand2, operator: Send, intelligence: TrendingUp };
const TEAM_COLOR = { scout: '#22d3ee', creator: '#a78bfa', operator: '#34d399', intelligence: '#f59e0b' };

const AUTONOMY_LABELS = {
  0: 'L0 · Manual',
  1: 'L1 · Auto-create',
  2: 'L2 · Auto-publish',
  3: 'L3 · Auto-optimize',
  4: 'L4 · Goal-seeking',
  5: 'L5 · Full autonomous',
};

const CortexWorkspace = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [mission, setMission]       = useState(null);
  const [dispatches, setDispatches] = useState([]);
  const [loading, setLoading]       = useState(true);

  const load = async () => {
    if (!id) {
      // Index — redirect to missions hub
      navigate('/dashboard/missions');
      return;
    }
    setLoading(true);
    try {
      const m = await axios.get(`${API}/missions/${id}`, { withCredentials: true });
      setMission(m.data);
      // Pull the full dispatch timeline (Phase 2 endpoint).
      const d = await axios.get(`${API}/missions/${id}/dispatches`, { withCredentials: true });
      setDispatches(d.data?.dispatches || []);
    } catch (e) {
      toast({ title: 'Could not load mission',
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [id]);

  // Live polling — refresh every 5s while the mission is running so the
  // operator sees Cortex's dispatch graph evolve in near real-time.
  useEffect(() => {
    if (!mission || mission.status !== 'running') return undefined;
    const h = setInterval(load, 5000);
    return () => clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mission?.status, id]);

  const updateAutonomy = async (newLevel) => {
    try {
      await axios.patch(`${API}/missions/${id}`, { autonomy_level: newLevel }, { withCredentials: true });
      load();
      toast({ title: `Autonomy → ${AUTONOMY_LABELS[newLevel]}` });
    } catch (e) {
      toast({ title: 'Update failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const toggle = async (action) => {
    try {
      await axios.post(`${API}/missions/${id}/${action}`, {}, { withCredentials: true });
      load();
    } catch (e) {
      toast({ title: `Failed to ${action}`, description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const runLoop = async () => {
    try {
      const r = await axios.post(`${API}/missions/loop/run-once`, {}, { withCredentials: true });
      toast({ title: 'Loop drained',
              description: `Processed ${r.data?.processed ?? 0} dispatch${r.data?.processed === 1 ? '' : 'es'}.` });
      load();
    } catch (e) {
      toast({ title: 'Loop failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  if (!id || loading || !mission) {
    return (
      <DashboardLayout title="Cortex" subtitle="The master orchestrator workspace.">
        <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
      </DashboardLayout>
    );
  }

  const p = mission.progress || {};
  const status = mission.status || 'draft';
  const teamGroups = dispatches.reduce((acc, d) => {
    const t = d.team || '_other';
    (acc[t] = acc[t] || []).push(d);
    return acc;
  }, {});

  return (
    <DashboardLayout
      title={mission.title}
      subtitle="Cortex is coordinating four teams to achieve this outcome."
      headerExtra={
        <button
          onClick={() => navigate('/dashboard/missions')}
          className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white transition flex items-center gap-1.5"
        >
          <ArrowLeft size={13} /> All missions
        </button>
      }
    >
      <div className="space-y-6" data-testid={`cortex-mission-${mission.id}`}>
        {/* Provenance — when this mission was auto-launched via the
            Optimize-via-Bridge flow, surface the source Recommendation
            Bridge inline so the operator sees WHY Cortex chose this
            mission (Finding / Root Cause / Recommendation / Confidence).
            Renders nothing for missions created manually. */}
        <MissionProvenanceCard mission={mission} />

        {/* Hero card */}
        <div className="rounded-2xl border border-white/5 bg-gradient-to-br from-violet-500/10 via-blue-500/5 to-zinc-900 p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center">
              <Brain size={20} className="text-violet-300" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-violet-300 font-semibold mb-1">Mission</div>
              <div className="text-xl font-semibold text-white cv-display">{mission.title}</div>
              {mission.description && (
                <div className="text-[13px] text-zinc-400 mt-1.5">{mission.description}</div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {status === 'running' ? (
                <button onClick={() => toggle('pause')}
                        className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 transition flex items-center gap-1.5"
                        data-testid="cortex-mission-pause">
                  <Pause size={12} /> Pause
                </button>
              ) : (
                <button onClick={() => toggle('start')}
                        className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 transition flex items-center gap-1.5"
                        data-testid="cortex-mission-start">
                  <Play size={12} /> {status === 'paused' ? 'Resume' : 'Start'}
                </button>
              )}
              {!['cancelled', 'completed', 'failed'].includes(status) && (
                <button onClick={() => {
                  if (window.confirm(`Cancel mission "${mission.title}"? This stops all further automation and cannot be undone.`)) {
                    toggle('cancel');
                  }
                }}
                        className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 transition flex items-center gap-1.5"
                        data-testid="cortex-mission-cancel">
                  <XCircle size={12} /> Cancel
                </button>
              )}
            </div>
          </div>

          {/* Big progress bar */}
          <div className="mt-5">
            <div className="flex items-baseline justify-between mb-2">
              <div className="flex items-center gap-1.5 text-[12px] text-zinc-400">
                <Target size={11} /> Progress
              </div>
              <div className="text-lg tabular-nums font-semibold text-white">
                {p.current ?? 0} <span className="text-zinc-600 text-sm">/ {p.target ?? mission.target ?? 0}</span>
              </div>
            </div>
            <div className="h-2 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500 transition-all"
                style={{ width: `${Math.min(100, p.progress_pct || 0)}%` }}
              />
            </div>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
            <Stat icon={Zap}      label="Confidence"  value={`${p.confidence ?? 0}%`} />
            <Stat icon={Calendar} label="ETA"         value={p.eta_days == null ? '—' : (p.eta_days === 0 ? 'Hit!' : `${p.eta_days}d`)} />
            <Stat icon={Hash}     label="Campaigns"   value={p.campaigns_active ?? 0} />
            <Stat icon={Send}     label="Top channel" value={p.top_channel || '—'} />
          </div>
        </div>

        {/* Autonomy strip */}
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
          <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Autonomy</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(AUTONOMY_LABELS).map(([k, lbl]) => {
              const lvl = Number(k);
              const isActive = lvl === mission.autonomy_level;
              return (
                <button
                  key={k}
                  onClick={() => updateAutonomy(lvl)}
                  data-testid={`cortex-autonomy-${k}`}
                  className={`text-[11.5px] font-semibold px-3 py-1.5 rounded-md transition ${
                    isActive
                      ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow'
                      : 'bg-white/5 hover:bg-white/10 text-zinc-300'
                  }`}
                >
                  {lbl}
                </button>
              );
            })}
          </div>
        </div>

        {/* Per-team dispatch columns */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {['scout', 'creator', 'operator', 'intelligence'].map((tid) => {
            const Icon = TEAM_ICONS[tid];
            const ds = teamGroups[tid] || [];
            return (
              <div key={tid} className="rounded-xl border border-white/5 bg-white/[0.03] p-4" data-testid={`cortex-team-col-${tid}`}>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                       style={{ background: `${TEAM_COLOR[tid]}22`, color: TEAM_COLOR[tid] }}>
                    <Icon size={14} />
                  </div>
                  <div className="flex-1">
                    <div className="text-[13px] font-semibold text-white capitalize">{tid}</div>
                    <div className="text-[10.5px] text-zinc-500">{ds.length} dispatch{ds.length === 1 ? '' : 'es'}</div>
                  </div>
                </div>
                {ds.length === 0 ? (
                  <div className="text-[12px] text-zinc-600 italic">No tasks yet.</div>
                ) : (
                  <div className="space-y-2">
                    {ds.slice(0, 4).map((d) => (
                      <div key={d.id} className="rounded-md bg-white/5 p-2 text-[12px] text-zinc-300">
                        <div className="line-clamp-2">{d.task || d.body || d.content || '—'}</div>
                        <DispatchStatusBadge status={d.status} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Live dispatch timeline + Run-loop CTA */}
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity size={12} className="text-zinc-400" />
              <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">
                Event relay ({dispatches.length})
              </div>
              {mission.status === 'running' && (
                <span className="text-[10px] uppercase tracking-wider text-emerald-300 font-semibold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> live
                </span>
              )}
            </div>
            <button onClick={runLoop}
                    data-testid="cortex-run-loop"
                    className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 transition flex items-center gap-1">
              Run loop now
            </button>
          </div>
          {dispatches.length === 0 ? (
            <div className="text-[12px] text-zinc-600 italic py-3">Cortex hasn't dispatched anything yet.</div>
          ) : (
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {dispatches.slice().reverse().slice(0, 30).map((d) => (
                <DispatchRow key={d.id} dispatch={d} />
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

const STATUS_TONE = {
  queued:             'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  done:               'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  awaiting_approval:  'bg-amber-500/15 text-amber-300 border-amber-500/30',
  blocked_cap:        'bg-rose-500/15 text-rose-300 border-rose-500/30',
};

const DispatchStatusBadge = ({ status }) => (
  <span className={`mt-1 inline-block text-[9.5px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded border ${STATUS_TONE[status] || STATUS_TONE.queued}`}>
    {(status || 'queued').replace(/_/g, ' ')}
  </span>
);

const DispatchRow = ({ dispatch }) => {
  const Icon = TEAM_ICONS[dispatch.team] || Activity;
  const tone = TEAM_COLOR[dispatch.team] || '#a78bfa';
  return (
    <div className="flex items-center gap-2.5 text-[12px] py-1.5 px-2 rounded hover:bg-white/5">
      <Icon size={11} style={{ color: tone }} />
      <span className="capitalize text-zinc-400 w-20 shrink-0">{dispatch.team}</span>
      <span className="flex-1 text-zinc-300 truncate">{dispatch.task}</span>
      <DispatchStatusBadge status={dispatch.status} />
    </div>
  );
};

const Stat = ({ icon: Icon, label, value }) => (
  <div className="rounded-lg bg-white/5 border border-white/5 p-3">
    <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
      <Icon size={10} /> {label}
    </div>
    <div className="text-[15px] font-semibold text-white capitalize truncate">{value}</div>
  </div>
);

export default CortexWorkspace;
