import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Plus, Target, Trash2, X, CheckCircle2, Archive, AlertTriangle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Goals — durable OKRs owned by Vera.
   Top: 4 KPI tiles (active / completed / avg progress / overdue).
   Body: card grid, each with a progress bar + metric + deadline.
   New-goal modal with metric dropdown sourced from /goals/metrics. */
const STATUS_META = {
  active:    { label: 'Active',    color: 'bg-violet-100 text-violet-700 border-violet-200' },
  completed: { label: 'Completed', color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  abandoned: { label: 'Abandoned', color: 'bg-neutral-100 text-neutral-500 border-neutral-200' },
};

const Goals = () => {
  const { toast } = useToast();
  const [goals, setGoals] = useState([]);
  const [stats, setStats] = useState({ active_count: 0, completed_count: 0, avg_progress_pct: 0, overdue_count: 0 });
  const [metrics, setMetrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', metric: 'posts_published', target: 50, deadline: '' });

  const load = async () => {
    setLoading(true);
    try {
      const [g, m] = await Promise.all([
        axios.get(`${API}/goals`, { withCredentials: true }),
        axios.get(`${API}/goals/metrics`, { withCredentials: true }),
      ]);
      setGoals(g.data.items || []);
      setStats({
        active_count:     g.data.active_count,
        completed_count:  g.data.completed_count,
        avg_progress_pct: g.data.avg_progress_pct,
        overdue_count:    g.data.overdue_count,
      });
      setMetrics(m.data.metrics || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.title.trim() || !form.target) return;
    setCreating(true);
    try {
      const payload = {
        title:       form.title.trim(),
        description: form.description.trim() || null,
        metric:      form.metric,
        target:      parseInt(form.target, 10),
      };
      if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
      await axios.post(`${API}/goals`, payload, { withCredentials: true });
      toast({ title: 'Goal created', description: 'Vera will track this in next Monday\'s standup.' });
      setShowForm(false);
      setForm({ title: '', description: '', metric: 'posts_published', target: 50, deadline: '' });
      await load();
    } catch (e) {
      toast({ title: 'Failed to create goal', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setCreating(false); }
  };

  const setStatus = async (goal, status) => {
    try {
      await axios.patch(`${API}/goals/${goal.id}`, { status }, { withCredentials: true });
      toast({ title: `Goal ${status}` });
      await load();
    } catch (e) {
      toast({ title: 'Update failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const remove = async (goal) => {
    if (!window.confirm(`Delete "${goal.title}"? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API}/goals/${goal.id}`, { withCredentials: true });
      toast({ title: 'Goal deleted' });
      await load();
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  return (
    <DashboardLayout title="Growth Goals" subtitle="Durable OKRs. Vera tracks them in every standup.">
      <div className="space-y-6" data-testid="goals-page">

        {/* Hero — Vera intro + new-goal CTA */}
        <div className="flex items-start justify-between gap-4 rounded-2xl border border-violet-200/60 bg-gradient-to-br from-violet-50 via-white to-fuchsia-50 p-5">
          <div className="flex items-start gap-4">
            <span className="w-12 h-12 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center shrink-0">
              <Target size={22} />
            </span>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-violet-600 font-bold mb-1">Goals — Vera</div>
              <div className="text-[14px] text-neutral-800 leading-relaxed max-w-2xl">
                Set the metrics that matter, give them a target + deadline. Progress is computed live from your published posts,
                listening signals, and performance rollups — Vera will surface these in every Monday standup.
              </div>
            </div>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 inline-flex items-center gap-1.5 shrink-0"
            data-testid="new-goal-btn"
          >
            <Plus size={14} /> New goal
          </button>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiTile label="Active" value={stats.active_count} icon={Target} />
          <KpiTile label="Avg progress" value={`${stats.avg_progress_pct}%`} icon={CheckCircle2} tone="violet" />
          <KpiTile label="Completed" value={stats.completed_count} icon={CheckCircle2} tone="emerald" />
          <KpiTile label="Overdue" value={stats.overdue_count} icon={AlertTriangle} tone={stats.overdue_count > 0 ? 'rose' : 'neutral'} />
        </div>

        {/* Goal cards */}
        {loading && (
          <div className="flex items-center gap-2 text-neutral-500"><Loader2 size={14} className="animate-spin" /> Loading goals…</div>
        )}

        {!loading && goals.length === 0 && (
          <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50 p-12 text-center">
            <Target className="mx-auto text-violet-400 mb-3" size={28} />
            <h3 className="text-lg font-bold text-neutral-800 mb-1">No goals yet</h3>
            <p className="text-[13px] text-neutral-500 mb-4 max-w-md mx-auto">
              Set your first OKR — Vera will start tracking it immediately.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 inline-flex items-center gap-1.5"
              data-testid="empty-state-new-goal-btn"
            >
              <Plus size={14} /> Create your first goal
            </button>
          </div>
        )}

        {!loading && goals.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {goals.map((g) => (
              <GoalCard key={g.id} goal={g} onSetStatus={setStatus} onDelete={remove} />
            ))}
          </div>
        )}

        {/* New-goal modal */}
        {showForm && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)}>
            <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl p-6" onClick={(e) => e.stopPropagation()} data-testid="new-goal-modal">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-neutral-900 flex items-center gap-2"><Target size={18} className="text-violet-600" /> New goal</h3>
                <button onClick={() => setShowForm(false)} className="text-neutral-400 hover:text-neutral-700"><X size={18} /></button>
              </div>

              <div className="space-y-3">
                <Field label="Title (the headline outcome)">
                  <input
                    value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                    placeholder="Reach 5K Instagram followers by March"
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none"
                    data-testid="form-title"
                  />
                </Field>
                <Field label="Description (optional)">
                  <textarea
                    value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                    placeholder="Why this matters, what success looks like…"
                    rows={2}
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none resize-none"
                    data-testid="form-description"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Metric">
                    <select
                      value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value })}
                      className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none"
                      data-testid="form-metric"
                    >
                      {metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                    </select>
                  </Field>
                  <Field label="Target">
                    <input
                      type="number" min={1}
                      value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}
                      className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none"
                      data-testid="form-target"
                    />
                  </Field>
                </div>
                <Field label="Deadline (optional)">
                  <input
                    type="date" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-violet-500 focus:ring-1 focus:ring-violet-500 outline-none"
                    data-testid="form-deadline"
                  />
                </Field>
              </div>

              <div className="mt-5 flex items-center justify-end gap-2">
                <button onClick={() => setShowForm(false)} className="text-[13px] font-semibold px-4 py-2 rounded-lg border border-neutral-300 text-neutral-700 hover:bg-neutral-50">
                  Cancel
                </button>
                <button
                  onClick={submit} disabled={!form.title.trim() || !form.target || creating}
                  className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 inline-flex items-center gap-1.5"
                  data-testid="form-submit"
                >
                  {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Create goal
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const GoalCard = ({ goal, onSetStatus, onDelete }) => {
  const status = STATUS_META[goal.status] || STATUS_META.active;
  const barColor = goal.is_overdue ? 'bg-rose-500' : goal.progress_pct >= 100 ? 'bg-emerald-500' : 'bg-violet-500';
  const deadline = goal.deadline ? new Date(goal.deadline).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : null;
  return (
    <div className="bg-white rounded-2xl border border-neutral-200/70 p-5 hover:border-neutral-300 transition-colors" data-testid={`goal-card-${goal.id}`}>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded border ${status.color}`}>{status.label}</span>
            {goal.is_overdue && (
              <span className="text-[10px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded border bg-rose-100 text-rose-700 border-rose-200 inline-flex items-center gap-1">
                <AlertTriangle size={10} /> Overdue
              </span>
            )}
          </div>
          <div className="text-[15px] font-bold text-neutral-900 mb-1 leading-tight">{goal.title}</div>
          {goal.description && <div className="text-[12px] text-neutral-600 mb-2 leading-relaxed">{goal.description}</div>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {goal.status === 'active' && (
            <button onClick={() => onSetStatus(goal, 'abandoned')} className="p-1.5 text-neutral-400 hover:text-neutral-700" title="Abandon">
              <Archive size={14} />
            </button>
          )}
          <button onClick={() => onDelete(goal)} className="p-1.5 text-neutral-400 hover:text-rose-600" title="Delete" data-testid={`delete-goal-${goal.id}`}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-2">
        <div className="flex items-baseline justify-between mb-1">
          <div className="text-[11px] font-mono text-neutral-500">{goal.metric}</div>
          <div className="text-[11px] tabular-nums text-neutral-500">
            <span className="font-bold text-neutral-900 text-[14px]">{goal.current?.toLocaleString?.()}</span>
            <span className="mx-1">/</span>
            <span>{goal.target?.toLocaleString?.()}</span>
            <span className="ml-2 text-violet-600 font-semibold">{goal.progress_pct}%</span>
          </div>
        </div>
        <div className="h-2 rounded-full bg-neutral-100 overflow-hidden">
          <div className={`h-full ${barColor} transition-all`} style={{ width: `${Math.min(100, goal.progress_pct)}%` }} />
        </div>
      </div>

      {deadline && <div className="mt-3 text-[11px] text-neutral-500">Deadline: <span className="text-neutral-700 font-semibold">{deadline}</span></div>}
    </div>
  );
};

const Field = ({ label, children }) => (
  <div>
    <label className="block text-[11px] uppercase tracking-widest text-neutral-500 font-bold mb-1">{label}</label>
    {children}
  </div>
);

const KpiTile = ({ label, value, icon: Icon, tone = 'neutral' }) => {
  const tones = {
    neutral: 'bg-white border-neutral-200 text-neutral-900',
    violet:  'bg-violet-50 border-violet-200 text-violet-800',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    rose:    'bg-rose-50 border-rose-200 text-rose-800',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-widest font-bold opacity-70">{label}</div>
        {Icon && <Icon size={13} className="opacity-50" />}
      </div>
      <div className="text-[22px] font-bold tabular-nums">{value}</div>
    </div>
  );
};

export default Goals;
