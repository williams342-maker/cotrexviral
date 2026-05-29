import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Plus, FlaskConical, Trash2, X, Trophy, AlertTriangle, ArrowRight, LineChart as LineChartIcon, Sparkles } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Experiments — head-to-head content variant testing, owned by Ori.
   Top: Ori hero card + 4 KPI tiles (running / completed / inconclusive / avg margin).
   Body: card grid, each with side-by-side variant comparison + conclude button.
   New-experiment modal: variant pickers + metric dropdown. */

const STATUS_META = {
  running:      { label: 'Running',      color: 'bg-cyan-100 text-cyan-700 border-cyan-200' },
  completed:    { label: 'Completed',    color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  inconclusive: { label: 'Inconclusive', color: 'bg-amber-100 text-amber-700 border-amber-200' },
};

const Experiments = () => {
  const { toast } = useToast();
  const [exps, setExps] = useState([]);
  const [stats, setStats] = useState({ running_count: 0, completed_count: 0, inconclusive_count: 0, avg_winner_margin_pct: 0 });
  const [metrics, setMetrics] = useState([]);
  const [minMargin, setMinMargin] = useState(10);
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [concluding, setConcluding] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', hypothesis: '', variant_a_id: '', variant_b_id: '', metric: 'engagements' });

  const load = async () => {
    setLoading(true);
    try {
      const [e, m, v] = await Promise.all([
        axios.get(`${API}/experiments`, { withCredentials: true }),
        axios.get(`${API}/experiments/metrics`, { withCredentials: true }),
        axios.get(`${API}/variants/recent?limit=50`, { withCredentials: true })
          .catch(() => ({ data: { items: [] } })),
      ]);
      setExps(e.data.items || []);
      setStats({
        running_count:         e.data.running_count,
        completed_count:       e.data.completed_count,
        inconclusive_count:    e.data.inconclusive_count,
        avg_winner_margin_pct: e.data.avg_winner_margin_pct,
      });
      setMetrics(m.data.metrics || []);
      setMinMargin(m.data.min_margin_pct || 10);
      setVariants(v.data.items || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!form.name.trim() || !form.variant_a_id || !form.variant_b_id) return;
    if (form.variant_a_id === form.variant_b_id) {
      toast({ title: 'Pick two different variants', variant: 'destructive' });
      return;
    }
    setCreating(true);
    try {
      await axios.post(`${API}/experiments`, {
        name:         form.name.trim(),
        hypothesis:   form.hypothesis.trim() || null,
        variant_a_id: form.variant_a_id,
        variant_b_id: form.variant_b_id,
        metric:       form.metric,
      }, { withCredentials: true });
      toast({ title: 'Experiment running', description: 'Ori will declare a winner when the margin is decisive.' });
      setShowForm(false);
      setForm({ name: '', hypothesis: '', variant_a_id: '', variant_b_id: '', metric: 'engagements' });
      await load();
    } catch (e) {
      toast({ title: 'Failed to create experiment', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setCreating(false); }
  };

  const conclude = async (exp) => {
    setConcluding(exp.id);
    try {
      const r = await axios.post(`${API}/experiments/${exp.id}/conclude`, {}, { withCredentials: true });
      if (r.data.status === 'completed') {
        toast({ title: `Winner declared (+${r.data.winner_margin_pct.toFixed(1)}%)`, description: 'Learning saved to memory.' });
      } else {
        toast({ title: 'Inconclusive', description: r.data.conclusion_text || 'Margin below threshold.', variant: 'default' });
      }
      await load();
    } catch (e) {
      toast({ title: 'Conclude failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setConcluding(null); }
  };

  const remove = async (exp) => {
    if (!window.confirm(`Delete experiment "${exp.name}"? Memory rows from past winners stay.`)) return;
    try {
      await axios.delete(`${API}/experiments/${exp.id}`, { withCredentials: true });
      toast({ title: 'Experiment deleted' });
      await load();
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  return (
    <DashboardLayout title="Experiments" subtitle="Head-to-head variant testing — owned by Ori, the Analyst.">
      <div className="space-y-8" data-testid="experiments-page">

        {/* Ori hero card */}
        <div className="rounded-2xl border border-cyan-200/60 bg-gradient-to-br from-cyan-50 via-white to-cyan-50 p-6 flex items-start gap-5">
          <span className="w-12 h-12 rounded-xl bg-cyan-100 text-cyan-700 flex items-center justify-center shrink-0">
            <FlaskConical size={22} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-cyan-600 font-bold mb-1">Ori · Analyst</div>
            <h2 className="text-lg font-semibold text-neutral-900 mb-1">Pattern-spotter. Writes the learning to memory.</h2>
            <p className="text-[13px] text-neutral-600 leading-relaxed">
              Pit two variants head-to-head on a single metric. When the margin clears <strong>{minMargin.toFixed(0)}%</strong>, Ori writes the winning pattern to memory — future briefs retrieve it automatically.
            </p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="text-[12.5px] font-semibold px-4 py-2 rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 flex items-center gap-1.5 shrink-0"
            data-testid="new-experiment-btn"
          >
            <Plus size={14} /> New experiment
          </button>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiTile label="Running"      value={stats.running_count}      icon={<FlaskConical size={14} />} tone="cyan"    testid="kpi-running" />
          <KpiTile label="Completed"    value={stats.completed_count}    icon={<Trophy size={14} />}       tone="emerald" testid="kpi-completed" />
          <KpiTile label="Inconclusive" value={stats.inconclusive_count} icon={<AlertTriangle size={14} />} tone="amber"   testid="kpi-inconclusive" />
          <KpiTile label="Avg margin %" value={`${stats.avg_winner_margin_pct.toFixed(1)}%`} icon={<LineChartIcon size={14} />} tone="violet"  testid="kpi-margin" />
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-neutral-500" data-testid="loading">
            <Loader2 className="animate-spin" size={14} /> Loading experiments…
          </div>
        )}

        {!loading && exps.length === 0 && (
          <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-300" data-testid="empty">
            <FlaskConical size={28} className="mx-auto text-neutral-400 mb-3" />
            <p className="text-neutral-600 font-medium">No experiments yet.</p>
            <p className="text-[12.5px] text-neutral-500 mt-1 mb-5">Pit two variants against each other and let Ori call the winner.</p>
            <button onClick={() => setShowForm(true)} className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-cyan-600 text-white hover:bg-cyan-700">
              Create your first experiment
            </button>
          </div>
        )}

        {/* Experiment grid */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          {exps.map((e) => {
            const aLead = e.live_leader === 'a';
            const bLead = e.live_leader === 'b';
            const meta = STATUS_META[e.status] || STATUS_META.running;
            return (
              <div key={e.id} className="rounded-2xl border border-neutral-200/70 bg-white p-5" data-testid={`exp-card-${e.id}`}>
                {/* Header */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-bold mb-1">
                      {e.metric} · margin {e.winner_margin_pct != null ? `${e.winner_margin_pct.toFixed(1)}%` : `${e.live_margin_pct.toFixed(1)}% live`}
                    </div>
                    <h3 className="text-[15px] font-semibold text-neutral-900 leading-snug">{e.name}</h3>
                    {e.hypothesis && (
                      <div className="text-[12px] text-neutral-500 italic mt-1 line-clamp-2">{e.hypothesis}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border font-bold ${meta.color}`}>
                      {meta.label}
                    </span>
                    <button onClick={() => remove(e)} className="text-neutral-400 hover:text-rose-600 p-1" title="Delete">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Variant comparison */}
                <div className="grid grid-cols-2 gap-3">
                  <VariantPanel
                    label="A" data={e.variant_a} metric={e.metric}
                    leading={aLead}
                    winner={e.winner_variant_id === e.variant_a_id}
                  />
                  <VariantPanel
                    label="B" data={e.variant_b} metric={e.metric}
                    leading={bLead}
                    winner={e.winner_variant_id === e.variant_b_id}
                  />
                </div>

                {/* Conclusion or conclude button */}
                {e.status === 'running' ? (
                  <button
                    onClick={() => conclude(e)}
                    disabled={concluding === e.id}
                    className={`mt-4 w-full text-[12.5px] font-semibold px-3 py-2.5 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 ${
                      e.can_conclude
                        ? 'bg-cyan-600 text-white hover:bg-cyan-700'
                        : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
                    }`}
                    data-testid={`conclude-${e.id}`}
                  >
                    {concluding === e.id ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={13} />}
                    {e.can_conclude ? 'Conclude — Ori writes the winner' : 'Conclude (margin not decisive yet)'}
                  </button>
                ) : (
                  <div className="mt-4 rounded-lg bg-neutral-50 border border-neutral-200 p-3 text-[12px] text-neutral-700 leading-relaxed flex items-start gap-2" data-testid={`conclusion-${e.id}`}>
                    {e.status === 'completed' ? <Sparkles size={14} className="text-emerald-600 shrink-0 mt-0.5" /> : <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />}
                    <div>{e.conclusion_text}</div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* New-experiment modal */}
        {showForm && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setShowForm(false)} data-testid="experiment-modal">
            <div onClick={(e) => e.stopPropagation()} className="bg-white rounded-2xl w-full max-w-lg p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-cyan-600 font-bold mb-1">Ori · new experiment</div>
                  <h3 className="text-lg font-semibold text-neutral-900">Pit two variants head-to-head</h3>
                </div>
                <button onClick={() => setShowForm(false)} className="text-neutral-400 hover:text-neutral-700"><X size={18} /></button>
              </div>
              <div className="space-y-4">
                <Field label="Name">
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder='e.g. "Question hook vs Statement hook — IG"'
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                    data-testid="exp-name"
                  />
                </Field>
                <Field label="Hypothesis (optional)">
                  <textarea
                    value={form.hypothesis}
                    onChange={(e) => setForm({ ...form, hypothesis: e.target.value })}
                    placeholder="What do you expect to win and why?"
                    rows={2}
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                    data-testid="exp-hypothesis"
                  />
                </Field>
                <Field label="Variant A">
                  <VariantSelect
                    variants={variants}
                    value={form.variant_a_id}
                    onChange={(v) => setForm({ ...form, variant_a_id: v })}
                    testid="exp-variant-a"
                    exclude={form.variant_b_id}
                  />
                </Field>
                <Field label="Variant B">
                  <VariantSelect
                    variants={variants}
                    value={form.variant_b_id}
                    onChange={(v) => setForm({ ...form, variant_b_id: v })}
                    testid="exp-variant-b"
                    exclude={form.variant_a_id}
                  />
                </Field>
                <Field label="Compare on">
                  <select
                    value={form.metric}
                    onChange={(e) => setForm({ ...form, metric: e.target.value })}
                    className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                    data-testid="exp-metric"
                  >
                    {metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                  </select>
                </Field>
              </div>
              <div className="mt-6 flex items-center justify-end gap-2">
                <button onClick={() => setShowForm(false)} className="text-[12.5px] px-3 py-2 rounded-lg text-neutral-600 hover:bg-neutral-100">Cancel</button>
                <button
                  onClick={submit}
                  disabled={creating || !form.name.trim() || !form.variant_a_id || !form.variant_b_id}
                  className="text-[12.5px] font-semibold px-4 py-2 rounded-lg bg-cyan-600 text-white hover:bg-cyan-700 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                  data-testid="exp-submit"
                >
                  {creating ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />}
                  Start experiment
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const KpiTile = ({ label, value, icon, tone, testid }) => {
  const toneMap = {
    cyan:    'text-cyan-700 bg-cyan-50 border-cyan-200',
    emerald: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    amber:   'text-amber-700 bg-amber-50 border-amber-200',
    violet:  'text-violet-700 bg-violet-50 border-violet-200',
  };
  return (
    <div className={`rounded-xl border p-4 ${toneMap[tone]}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold mb-1.5 opacity-80">{icon} {label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
};

const VariantPanel = ({ label, data, metric, leading, winner }) => {
  const ring = winner ? 'ring-2 ring-emerald-500 border-emerald-300' : leading ? 'ring-1 ring-cyan-400 border-cyan-200' : 'border-neutral-200';
  const value = data?.[metric] ?? data?.value ?? 0;
  return (
    <div className={`rounded-xl border ${ring} bg-neutral-50/50 p-3`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-widest font-bold text-neutral-500">Variant {label}</span>
        {winner && <span className="text-[10px] uppercase tracking-widest font-bold text-emerald-700 flex items-center gap-1"><Trophy size={10} /> Winner</span>}
        {!winner && leading && <span className="text-[10px] uppercase tracking-widest font-bold text-cyan-700">Leading</span>}
      </div>
      <div className="text-2xl font-semibold text-neutral-900 tabular-nums mb-1">
        {typeof value === 'number' && metric === 'ctr' ? `${(value * 100).toFixed(2)}%` : Number(value).toLocaleString()}
      </div>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2">{data?.platform || '—'} · {data?.samples || 0} samples</div>
      <div className="text-[11.5px] text-neutral-700 leading-snug line-clamp-3 font-mono bg-white rounded-md border border-neutral-200 p-2">
        {data?.body_preview || (data?.missing ? '(deleted variant)' : '(no body)')}
      </div>
    </div>
  );
};

const VariantSelect = ({ variants, value, onChange, testid, exclude }) => {
  if (!variants.length) {
    return (
      <div className="text-[12px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
        No variants yet — publish a few posts first, then come back to set up an experiment.
      </div>
    );
  }
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full text-[13px] px-3 py-2 rounded-lg border border-neutral-300 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
      data-testid={testid}
    >
      <option value="">Choose a variant…</option>
      {variants.filter((v) => v.id !== exclude).map((v) => (
        <option key={v.id} value={v.id}>
          [{v.platform}] {(v.body || '').slice(0, 80)}{(v.body || '').length > 80 ? '…' : ''}
        </option>
      ))}
    </select>
  );
};

const Field = ({ label, children }) => (
  <div>
    <label className="block text-[11px] uppercase tracking-widest text-neutral-500 font-bold mb-1.5">{label}</label>
    {children}
  </div>
);

export default Experiments;
