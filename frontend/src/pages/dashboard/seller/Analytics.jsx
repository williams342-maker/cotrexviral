import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, BarChart3, Target, TrendingUp, Users, Sparkles, Send, CheckCircle2,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

const KPI_TONES = {
  cyan:    'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
  violet:  'bg-violet-500/10 border-violet-500/20 text-violet-300',
  blue:    'bg-blue-500/10 border-blue-500/20 text-blue-300',
  emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
};

function KpiTile({ icon: Icon, label, value, tone = 'violet' }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4"
         data-testid={`analytics-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border ${KPI_TONES[tone]} mb-2`}>
        <Icon size={14} />
      </div>
      <div className="text-[10.5px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
      <div className="text-2xl tabular-nums font-semibold text-white mt-0.5">{value}</div>
    </div>
  );
}

const Analytics = () => {
  const { toast } = useToast();
  const [missions, setMissions] = useState([]);
  const [funnels, setFunnels] = useState({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/missions`, { withCredentials: true });
      const sel = (r.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
      setMissions(sel);
      const out = {};
      await Promise.all(sel.map(async (m) => {
        try {
          const f = await axios.get(`${API}/missions/${m.id}/seller-funnel`, { withCredentials: true });
          out[m.id] = f.data;
        } catch (e) { /* keep going */ }
      }));
      setFunnels(out);
    } catch (e) {
      toast({ title: 'Analytics load failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const totals = React.useMemo(() => {
    const acc = { discovered: 0, qualified: 0, outreached: 0, interested: 0,
                  onboarding: 0, active: 0, churned: 0, unresponsive: 0,
                  target: 0, onboarded: 0 };
    Object.values(funnels).forEach((f) => {
      const fn = f.funnel || {};
      Object.keys(acc).forEach((k) => { if (fn[k] != null) acc[k] += fn[k]; });
      acc.target += (f.target || 0);
      acc.onboarded += (f.projected_completion?.current || 0);
    });
    return acc;
  }, [funnels]);

  const pct = (n, d) => (d > 0 ? Math.round((n / d) * 1000) / 10 : 0);
  const convRates = [
    { label: 'Discovery → Qualified', from: 'discovered', to: 'qualified' },
    { label: 'Qualified → Outreached', from: 'qualified', to: 'outreached' },
    { label: 'Outreached → Interested', from: 'outreached', to: 'interested' },
    { label: 'Interested → Onboarding', from: 'interested', to: 'onboarding' },
    { label: 'Onboarding → Active', from: 'onboarding', to: 'active' },
  ];

  return (
    <DashboardLayout
      title="Seller OS · Analytics"
      subtitle="The unified seller funnel across every mission Cortex is running."
    >
      <div className="space-y-5" data-testid="seller-analytics-page">
        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500">
            <Loader2 className="animate-spin" size={14} /> Loading analytics…
          </div>
        ) : missions.length === 0 ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            <BarChart3 size={20} className="mx-auto mb-2 text-zinc-600" />
            No seller missions yet. Brief Cortex with a seller-acquisition goal to start.
          </div>
        ) : (
          <>
            {/* Hero KPI tiles */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KpiTile icon={Users} label="Discovered" value={totals.discovered} tone="cyan" />
              <KpiTile icon={Sparkles} label="Qualified" value={totals.qualified} tone="violet" />
              <KpiTile icon={Send} label="Outreached" value={totals.outreached} tone="blue" />
              <KpiTile icon={CheckCircle2} label="Active sellers" value={totals.active} tone="emerald" />
            </div>

            {/* Conversion funnel */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={14} className="text-violet-300" />
                <div className="text-[13px] font-semibold text-white">Funnel conversion</div>
              </div>
              <div className="space-y-3">
                {convRates.map((c) => {
                  const fromN = totals[c.from] || 0;
                  const toN = totals[c.to] || 0;
                  const r = pct(toN, fromN);
                  return (
                    <div key={c.label} data-testid={`analytics-conv-${c.from}-${c.to}`}>
                      <div className="flex items-center justify-between text-[11.5px] text-zinc-400 mb-1">
                        <span>{c.label}</span>
                        <span className="tabular-nums"><strong className="text-white">{toN}</strong> / {fromN} <span className="text-zinc-500">·</span> <strong className="text-violet-300">{r}%</strong></span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500"
                             style={{ width: `${Math.min(100, r)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Per-mission rollup */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <Target size={14} className="text-blue-300" />
                <div className="text-[13px] font-semibold text-white">Mission velocity</div>
              </div>
              <div className="space-y-2.5">
                {missions.map((m) => {
                  const f = funnels[m.id];
                  const proj = f?.projected_completion || {};
                  const target = m.target || 0;
                  const current = proj.current || 0;
                  const pctDone = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
                  return (
                    <div key={m.id} className="p-3 rounded-lg bg-white/[0.03] border border-white/5"
                         data-testid={`analytics-mission-${m.id}`}>
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <div className="text-[13px] font-semibold text-white truncate flex-1 min-w-0">{m.title}</div>
                        <span className="text-[11px] text-zinc-500 tabular-nums">
                          <strong className="text-white">{current}</strong> / {target}
                          {proj.eta_days != null && <> · <span className="text-violet-300">{proj.eta_days}d ETA</span></>}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-blue-500"
                             style={{ width: `${pctDone}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Stage waterfall */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={14} className="text-emerald-300" />
                <div className="text-[13px] font-semibold text-white">Stage waterfall (all missions)</div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {['discovered', 'qualified', 'outreached', 'interested',
                  'onboarding', 'active', 'churned', 'unresponsive'].map((k) => (
                  <div key={k} className="p-3 rounded-lg bg-white/[0.03] border border-white/5"
                       data-testid={`analytics-stage-${k}`}>
                    <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">{k}</div>
                    <div className="text-xl tabular-nums font-semibold text-white">{totals[k] || 0}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Analytics;
