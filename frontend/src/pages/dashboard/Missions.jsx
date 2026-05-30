import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Sparkles, Target, Rocket, Activity, Pause, Play, XCircle,
  TrendingUp, Send, Brain, ArrowRight, X, Trophy, Compass,
  Zap, Calendar, Hash,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* The Mission Dashboard — the new home of CortexViral.
   - Shows running, paused, succeeded missions as cards
   - "+ New mission" opens a brief modal — user types goal in natural language,
      Cortex parses + dispatches 4 teams in one call.
   - Each card matches the spec: Title / Status / Progress / Confidence / ETA / Channels / Best Asset
*/

const STATUS_TONE = {
  running:   'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  paused:    'bg-amber-500/15 text-amber-300 border-amber-500/30',
  draft:     'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  succeeded: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  abandoned: 'bg-zinc-700/30 text-zinc-500 border-zinc-700/40',
};

const AUTONOMY_LABELS = {
  0: 'L0 · Manual',
  1: 'L1 · Auto-create',
  2: 'L2 · Auto-publish',
  3: 'L3 · Auto-optimize',
  4: 'L4 · Goal-seeking',
  5: 'L5 · Full autonomous',
};

const Missions = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [missions, setMissions] = useState([]);
  const [summary, setSummary]   = useState({});
  const [loading, setLoading]   = useState(true);
  const [showNew, setShowNew]   = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [m, s] = await Promise.all([
        axios.get(`${API}/missions`, { withCredentials: true }),
        axios.get(`${API}/cortex/summary`, { withCredentials: true }),
      ]);
      setMissions(m.data.missions || []);
      setSummary(s.data || {});
    } catch (e) {
      toast({ title: 'Failed to load missions',
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  return (
    <DashboardLayout
      title="Missions"
      subtitle="Tell Cortex what you want. It assembles the team and runs the playbook."
      headerExtra={
        <button
          onClick={() => setShowNew(true)}
          className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 shadow-md"
          data-testid="mission-new-btn"
        >
          <Sparkles size={13} /> Start a mission
        </button>
      }
    >
      <div className="space-y-8" data-testid="missions-page">
        {/* Top summary strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryStat label="Running"        value={summary.running_missions ?? 0} icon={Rocket}     tone="emerald" />
          <SummaryStat label="On track"       value={summary.on_track ?? 0}         icon={TrendingUp} tone="violet"  />
          <SummaryStat label="Dispatches 24h" value={summary.dispatches_24h ?? 0}   icon={Activity}   tone="cyan"    />
          <SummaryStat label="Succeeded"      value={summary.succeeded_missions ?? 0} icon={Trophy}   tone="amber"   />
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-zinc-500 text-[13px]">
            <Loader2 className="animate-spin" size={14} /> Loading missions…
          </div>
        )}

        {!loading && missions.length === 0 && (
          <EmptyState onStart={() => setShowNew(true)} />
        )}

        {!loading && missions.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {missions.map((m) => (
              <MissionCard key={m.id} mission={m} navigate={navigate} reload={load} />
            ))}
          </div>
        )}
      </div>

      {showNew && (
        <NewMissionModal onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); load(); }} />
      )}
    </DashboardLayout>
  );
};

const TONES = {
  emerald: 'from-emerald-500/15 to-emerald-500/0 text-emerald-300',
  violet:  'from-violet-500/15 to-violet-500/0 text-violet-300',
  cyan:    'from-cyan-500/15 to-cyan-500/0 text-cyan-300',
  amber:   'from-amber-500/15 to-amber-500/0 text-amber-300',
};

const SummaryStat = ({ label, value, icon: Icon, tone }) => (
  <div
    className={`relative rounded-xl border border-white/5 bg-gradient-to-br ${TONES[tone] || TONES.violet} p-4`}
    data-testid={`mission-summary-${label.toLowerCase().replace(/\s+/g, '-')}`}
  >
    <div className="flex items-center justify-between mb-2">
      <span className="text-[11px] uppercase tracking-wider font-semibold text-zinc-400">{label}</span>
      <Icon size={14} />
    </div>
    <div className="text-3xl font-semibold tabular-nums text-white">{value}</div>
  </div>
);

const EmptyState = ({ onStart }) => (
  <div
    className="relative overflow-hidden rounded-3xl border border-white/5 bg-gradient-to-br from-violet-500/10 via-blue-500/5 to-zinc-900 p-12 text-center"
    data-testid="missions-empty"
  >
    <div className="absolute inset-0 cv-grid-bg opacity-40 pointer-events-none" />
    <Brain className="relative mx-auto mb-4 text-violet-300" size={36} />
    <div className="relative text-2xl font-semibold text-white mb-2 cv-display">Cortex is waiting for orders.</div>
    <div className="relative text-[13.5px] text-zinc-400 max-w-lg mx-auto mb-6">
      Tell Cortex a business outcome in plain English — "Get 50 maker signups in 14 days".
      It parses the goal, assembles the right team, and runs the playbook automatically.
    </div>
    <button
      onClick={onStart}
      data-testid="missions-empty-start"
      className="relative text-[13px] font-semibold px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition inline-flex items-center gap-2 shadow-lg shadow-violet-900/40"
    >
      <Sparkles size={14} /> Start your first mission
    </button>
  </div>
);

const MissionCard = ({ mission, navigate, reload }) => {
  const p = mission.progress || {};
  const status = mission.status || 'draft';
  const pct = p.progress_pct ?? 0;
  const conf = p.confidence ?? 0;
  const eta = p.eta_days;

  return (
    <div
      className="relative rounded-2xl border border-white/5 bg-white/[0.03] hover:bg-white/[0.05] hover:border-white/10 transition-all p-5 flex flex-col gap-4"
      data-testid={`mission-card-${mission.id}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[15.5px] font-semibold text-white">{mission.title}</div>
          {mission.description && (
            <div className="text-[12px] text-zinc-500 mt-1 line-clamp-2">{mission.description}</div>
          )}
        </div>
        <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${STATUS_TONE[status] || STATUS_TONE.draft}`}>
          {status}
        </span>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <div className="flex items-center gap-1.5 text-[11.5px] text-zinc-400">
            <Target size={11} /> Progress
          </div>
          <div className="text-[13px] tabular-nums font-semibold text-white">
            {p.current ?? 0} <span className="text-zinc-600">/ {p.target ?? mission.target ?? 0}</span>
          </div>
        </div>
        <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500 transition-all"
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 text-[12px]">
        <Stat icon={Zap}      label="Confidence" value={`${conf}%`} />
        <Stat icon={Calendar} label="ETA"        value={eta == null ? '—' : (eta === 0 ? 'Hit!' : `${eta}d`)} />
        <Stat icon={Hash}     label="Campaigns"  value={p.campaigns_active ?? 0} />
        <Stat icon={Send}     label="Top channel" value={p.top_channel || '—'} />
      </div>

      {/* Best asset */}
      {p.best_asset && (
        <div className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5 flex items-center gap-2">
          <Trophy size={12} className="text-amber-300" />
          <div className="flex-1 min-w-0">
            <div className="text-[10.5px] uppercase tracking-wider text-zinc-500">Best asset</div>
            <div className="text-[12px] text-white truncate">{p.best_asset.title || p.best_asset.id}</div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-white/5">
        <span className="text-[10.5px] uppercase tracking-wider text-zinc-500">
          {AUTONOMY_LABELS[mission.autonomy_level] || `L${mission.autonomy_level}`}
        </span>
        <div className="flex items-center gap-1.5">
          <MissionAction mission={mission} reload={reload} />
          <button
            onClick={() => navigate(`/dashboard/cortex/${mission.id}`)}
            className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white transition flex items-center gap-1"
            data-testid={`mission-open-${mission.id}`}
          >
            Open <ArrowRight size={11} />
          </button>
        </div>
      </div>
    </div>
  );
};

const Stat = ({ icon: Icon, label, value }) => (
  <div className="flex items-center gap-2">
    <Icon size={11} className="text-zinc-500" />
    <span className="text-zinc-500">{label}</span>
    <span className="ml-auto text-white font-semibold capitalize truncate">{value}</span>
  </div>
);

const MissionAction = ({ mission, reload }) => {
  const { toast } = useToast();
  const [pending, setPending] = useState(false);
  const fire = async (path) => {
    setPending(true);
    try {
      await axios.post(`${API}/missions/${mission.id}/${path}`, {}, { withCredentials: true });
      reload();
    } catch (e) {
      toast({ title: `Failed to ${path}`, description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setPending(false); }
  };
  if (mission.status === 'running') {
    return (
      <div className="flex items-center gap-1.5">
        <button onClick={() => fire('pause')} disabled={pending}
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 transition flex items-center gap-1 disabled:opacity-50"
                data-testid={`mission-pause-${mission.id}`}>
          <Pause size={11} /> Pause
        </button>
        <button onClick={() => {
          if (window.confirm(`Cancel "${mission.title}"? This stops further automation.`)) fire('cancel');
        }} disabled={pending} title="Cancel mission"
                className="text-[11.5px] font-semibold w-7 h-7 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 transition flex items-center justify-center disabled:opacity-50"
                data-testid={`mission-cancel-${mission.id}`}>
          <XCircle size={11} />
        </button>
      </div>
    );
  }
  if (mission.status === 'paused' || mission.status === 'draft') {
    return (
      <div className="flex items-center gap-1.5">
        <button onClick={() => fire('start')} disabled={pending}
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 transition flex items-center gap-1 disabled:opacity-50"
                data-testid={`mission-start-${mission.id}`}>
          <Play size={11} /> {mission.status === 'paused' ? 'Resume' : 'Start'}
        </button>
        <button onClick={() => {
          if (window.confirm(`Cancel "${mission.title}"? This stops further automation.`)) fire('cancel');
        }} disabled={pending} title="Cancel mission"
                className="text-[11.5px] font-semibold w-7 h-7 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 transition flex items-center justify-center disabled:opacity-50"
                data-testid={`mission-cancel-${mission.id}`}>
          <XCircle size={11} />
        </button>
      </div>
    );
  }
  return null;
};

const NewMissionModal = ({ onClose, onCreated }) => {
  const { toast } = useToast();
  const [goal, setGoal] = useState('');
  const [autonomy, setAutonomy] = useState(2);
  const [deadlineDays, setDeadlineDays] = useState(14);
  const [budget, setBudget] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!goal.trim() || goal.trim().length < 4) {
      toast({ title: 'Tell Cortex more', description: 'Give the goal at least a few words.', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/cortex/missions`, {
        goal: goal.trim(),
        autonomy_level: autonomy,
        deadline_days: deadlineDays || null,
        budget_usd_cap: budget ? Number(budget) : null,
      }, { withCredentials: true });
      toast({ title: 'Mission launched', description: 'Cortex has dispatched all four teams.' });
      onCreated();
    } catch (e) {
      toast({ title: 'Could not launch mission',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="relative w-full max-w-xl rounded-2xl border border-white/10 bg-zinc-950 p-6 shadow-2xl"
           onClick={(e) => e.stopPropagation()} data-testid="mission-new-modal">
        <button onClick={onClose} className="absolute top-3 right-3 p-1.5 rounded-md text-zinc-500 hover:text-white hover:bg-white/5">
          <X size={16} />
        </button>
        <div className="flex items-center gap-2 mb-1">
          <Brain size={16} className="text-violet-300" />
          <div className="text-[11px] uppercase tracking-wider text-violet-300 font-semibold">Brief Cortex</div>
        </div>
        <div className="text-xl font-semibold text-white mb-4 cv-display">What's the outcome you want?</div>

        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Generate 50 new maker signups for CraftersMarket in 14 days"
          rows={3}
          autoFocus
          data-testid="mission-new-goal"
          className="w-full px-3.5 py-3 rounded-lg bg-white/5 border border-white/10 text-white placeholder-zinc-600 text-[14px] focus:outline-none focus:border-violet-500/50 resize-none"
        />

        <div className="grid grid-cols-2 gap-3 mt-4">
          <label className="text-[11.5px] text-zinc-400">
            <span className="block mb-1.5 font-semibold uppercase tracking-wider">Autonomy</span>
            <select
              value={autonomy} onChange={(e) => setAutonomy(Number(e.target.value))}
              data-testid="mission-new-autonomy"
              className="w-full px-2.5 py-2 rounded-md bg-white/5 border border-white/10 text-white text-[13px]"
            >
              {Object.entries(AUTONOMY_LABELS).map(([k, lbl]) => (
                <option key={k} value={k}>{lbl}</option>
              ))}
            </select>
          </label>
          <label className="text-[11.5px] text-zinc-400">
            <span className="block mb-1.5 font-semibold uppercase tracking-wider">Deadline (days)</span>
            <input
              type="number" min="1" max="365" value={deadlineDays}
              onChange={(e) => setDeadlineDays(Number(e.target.value) || null)}
              data-testid="mission-new-deadline"
              className="w-full px-2.5 py-2 rounded-md bg-white/5 border border-white/10 text-white text-[13px]"
            />
          </label>
        </div>
        <label className="block text-[11.5px] text-zinc-400 mt-3">
          <span className="block mb-1.5 font-semibold uppercase tracking-wider">Weekly budget cap (USD, optional)</span>
          <input
            type="number" min="0" step="0.01" value={budget}
            onChange={(e) => setBudget(e.target.value)}
            placeholder="e.g. 50"
            data-testid="mission-new-budget"
            className="w-full px-2.5 py-2 rounded-md bg-white/5 border border-white/10 text-white text-[13px]"
          />
        </label>

        <div className="flex items-center justify-between mt-5">
          <div className="text-[11px] text-zinc-500 flex items-center gap-1.5">
            <Compass size={11} /> Cortex routes to Scout → Creator → Operator → Intelligence
          </div>
          <button
            onClick={submit} disabled={submitting}
            data-testid="mission-new-submit"
            className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 shadow-lg shadow-violet-900/30 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="animate-spin" size={13} /> : <Sparkles size={13} />}
            {submitting ? 'Launching…' : 'Launch mission'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Missions;
