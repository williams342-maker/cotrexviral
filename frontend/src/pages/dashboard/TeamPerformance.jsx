import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, BarChart3, Activity, AlertTriangle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Team Performance — bird's-eye view of every agent's week.
   Top: 3 KPI tiles (briefs proposed / experiments active / signals captured).
   Body: one row per agent with headline + verb chips + budget headroom bar. */

const AGENT_COLORS = {
  vera:  '#8B5CF6', atlas: '#0EA5E9', nova: '#EC4899',
  rae:   '#22C55E', lyra:  '#F59E0B', echo: '#3B82F6',
  ori:   '#06B6D4', jules: '#EF4444',
};

const TeamPerformance = () => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ iso_week: '—', briefs_week: 0, experiments_active: 0, signals_week: 0 });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/agents/team-performance`, { withCredentials: true });
      setRows(r.data.rows || []);
      setMeta({
        iso_week:            r.data.iso_week,
        briefs_week:         r.data.briefs_week,
        experiments_active:  r.data.experiments_active,
        signals_week:        r.data.signals_week,
      });
    } catch (e) {
      toast({ title: 'Failed to load team performance', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  return (
    <DashboardLayout title="Team Performance" subtitle={`What each agent contributed this week (${meta.iso_week}).`}>
      <div className="space-y-8" data-testid="team-perf-page">

        {/* KPI row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiTile label="Briefs proposed (wk)"   value={meta.briefs_week}         icon={<BarChart3 size={14} />}    tone="sky"     testid="kpi-briefs" />
          <KpiTile label="Experiments active"     value={meta.experiments_active}  icon={<Activity size={14} />}     tone="cyan"    testid="kpi-experiments" />
          <KpiTile label="Listening signals (wk)" value={meta.signals_week}        icon={<AlertTriangle size={14} />} tone="amber"   testid="kpi-signals" />
        </div>

        {loading && <div className="flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>}

        {/* Agent rows */}
        {!loading && (
          <div className="space-y-3">
            {rows.map((r) => {
              const color = AGENT_COLORS[r.agent_id] || '#737373';
              const tone = r.headroom_pct >= 100 ? 'bg-rose-500'
                : r.headroom_pct >= 80 ? 'bg-amber-500'
                : 'bg-emerald-500';
              const pct = Math.min(100, Math.max(0, r.headroom_pct || 0));
              return (
                <div key={r.agent_id} className="rounded-2xl border border-neutral-200/70 bg-white p-5 flex items-start gap-5" data-testid={`row-${r.agent_id}`}>
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-[13px] font-bold uppercase shrink-0"
                    style={{ backgroundColor: `${color}15`, color }}
                  >
                    {r.agent_id.slice(0, 2)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-neutral-900">{r.name}</span>
                      <span className="text-[10.5px] uppercase tracking-widest text-neutral-500">{r.role}</span>
                      {!r.can_act && (
                        <span className="text-[9px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded bg-rose-100 text-rose-700">Paused</span>
                      )}
                    </div>
                    <div className="text-[12.5px] text-neutral-700 mt-0.5 mb-2">{r.headline}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {(r.verbs || []).map((v, i) => (
                        <span
                          key={i}
                          className="text-[10.5px] tabular-nums px-2 py-1 rounded-md border"
                          style={{ borderColor: `${color}30`, backgroundColor: `${color}08`, color }}
                          data-testid={`verb-${r.agent_id}-${i}`}
                        >
                          <span className="opacity-70 mr-1">{v.label}:</span>
                          <span className="font-semibold">{v.value}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="w-40 shrink-0">
                    <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-bold mb-1">Budget headroom</div>
                    <div className="h-1.5 rounded-full bg-neutral-100 overflow-hidden mb-1">
                      <div className={`h-full ${tone} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                    <div className="text-[10.5px] tabular-nums text-neutral-500 text-right">{r.headroom_pct.toFixed(1)}% used</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="text-[11.5px] text-neutral-500 leading-relaxed">
          Each row shows what the agent did this ISO week. Verb chips are individual counters; the headroom bar is the agent's worst-case usage across all 3 budget dimensions (tokens / USD / irreversible).
        </div>
      </div>
    </DashboardLayout>
  );
};

const KpiTile = ({ label, value, icon, tone, testid }) => {
  const toneMap = {
    sky:    'text-sky-700 bg-sky-50 border-sky-200',
    cyan:   'text-cyan-700 bg-cyan-50 border-cyan-200',
    amber:  'text-amber-700 bg-amber-50 border-amber-200',
  };
  return (
    <div className={`rounded-xl border p-4 ${toneMap[tone]}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold mb-1.5 opacity-80">{icon} {label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
};

export default TeamPerformance;
