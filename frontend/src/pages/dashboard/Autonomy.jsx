import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, ShieldAlert, Coins, Zap, ShieldCheck, AlertTriangle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Autonomy — per-agent weekly budget caps owned by Jules.
   Top: Jules hero card with at-risk + exhausted KPIs.
   Body: table of 8 agents with progress bars for tokens / $ / irreversible. */

const Autonomy = () => {
  const { toast } = useToast();
  const [budgets, setBudgets] = useState([]);
  const [stats, setStats] = useState({ at_risk: 0, exhausted: 0, iso_week: '—' });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/agents/budgets`, { withCredentials: true });
      setBudgets(r.data.items || []);
      setStats({ at_risk: r.data.at_risk, exhausted: r.data.exhausted, iso_week: r.data.iso_week });
    } catch (e) {
      toast({ title: 'Failed to load budgets', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  return (
    <DashboardLayout title="Autonomy Budgets" subtitle="Per-agent weekly caps owned by Jules.">
      <div className="space-y-8" data-testid="autonomy-page">

        {/* Jules hero */}
        <div className="rounded-2xl border border-rose-200/60 bg-gradient-to-br from-rose-50 via-white to-rose-50 p-6 flex items-start gap-5">
          <span className="w-12 h-12 rounded-xl bg-rose-100 text-rose-700 flex items-center justify-center shrink-0">
            <ShieldAlert size={22} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-rose-600 font-bold mb-1">Jules · Ops Manager</div>
            <h2 className="text-lg font-semibold text-neutral-900 mb-1">Fast. Transactional. Pauses the team if anything's weird.</h2>
            <p className="text-[13px] text-neutral-600 leading-relaxed">
              Each agent has a weekly cap on tokens, USD, and irreversible actions. When an agent hits its cap, Jules blocks further autonomous side effects — they fall back to HITL until the next ISO week. Showing week <strong>{stats.iso_week}</strong>.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className={`text-[11px] uppercase tracking-widest font-bold px-2.5 py-1 rounded-full border ${stats.at_risk > 0 ? 'bg-amber-50 border-amber-300 text-amber-700' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`} data-testid="kpi-at-risk">
              {stats.at_risk} at risk
            </span>
            <span className={`text-[11px] uppercase tracking-widest font-bold px-2.5 py-1 rounded-full border ${stats.exhausted > 0 ? 'bg-rose-50 border-rose-300 text-rose-700' : 'bg-neutral-50 border-neutral-200 text-neutral-500'}`} data-testid="kpi-exhausted">
              {stats.exhausted} exhausted
            </span>
          </div>
        </div>

        {loading && <div className="flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading budgets…</div>}

        {/* Agent budget table */}
        {!loading && (
          <div className="bg-white rounded-2xl border border-neutral-200/70 overflow-hidden">
            <div className="grid grid-cols-12 px-5 py-3 bg-neutral-50 border-b border-neutral-200 text-[10px] uppercase tracking-widest text-neutral-500 font-bold">
              <div className="col-span-3">Agent</div>
              <div className="col-span-3 flex items-center gap-1"><Zap size={11} /> Tokens / wk</div>
              <div className="col-span-3 flex items-center gap-1"><Coins size={11} /> USD / wk</div>
              <div className="col-span-3 flex items-center gap-1"><ShieldCheck size={11} /> Irreversible / wk</div>
            </div>
            {budgets.map((b) => (
              <div key={b.agent_id} className="grid grid-cols-12 px-5 py-4 border-b border-neutral-100 items-center" data-testid={`budget-row-${b.agent_id}`}>
                <div className="col-span-3">
                  <div className="font-semibold text-[13px] text-neutral-900">{b.agent_name}</div>
                  <div className="text-[11px] text-neutral-500">{b.agent_role}</div>
                  {!b.can_act && (
                    <span className="inline-flex items-center gap-1 mt-1 text-[10px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded bg-rose-100 text-rose-700">
                      <AlertTriangle size={10} /> Paused
                    </span>
                  )}
                </div>
                <BudgetBar used={b.tokens_used} cap={b.tokens_cap} pct={b.tokens_pct} unit="tok" testid={`tokens-${b.agent_id}`} />
                <BudgetBar used={`$${b.usd_used.toFixed(2)}`} capLabel={`$${b.usd_cap.toFixed(2)}`} pct={b.usd_pct} testid={`usd-${b.agent_id}`} />
                <BudgetBar used={b.irreversible_used} cap={b.irreversible_cap} pct={b.irreversible_pct} unit="" testid={`irr-${b.agent_id}`} />
              </div>
            ))}
          </div>
        )}

        <div className="text-[11.5px] text-neutral-500 leading-relaxed">
          Auto-approval gating: when an agent is at <strong>100%</strong> of any cap, autonomous side-effects from that agent (e.g., Atlas auto-approving briefs) are blocked until the next ISO week. Manual operator actions are never blocked.
        </div>
      </div>
    </DashboardLayout>
  );
};

const BudgetBar = ({ used, cap, capLabel, pct, unit = '', testid }) => {
  const tone = pct >= 100 ? 'bg-rose-500' : pct >= 80 ? 'bg-amber-500' : 'bg-emerald-500';
  const safePct = Math.min(100, Math.max(0, pct || 0));
  return (
    <div className="col-span-3 pr-4" data-testid={testid}>
      <div className="flex items-center justify-between text-[11.5px] tabular-nums mb-1">
        <span className="text-neutral-700 font-semibold">{used}{unit ? ` ${unit}` : ''}</span>
        <span className="text-neutral-400">/ {capLabel || `${cap}${unit ? ` ${unit}` : ''}`}</span>
      </div>
      <div className="h-1.5 rounded-full bg-neutral-100 overflow-hidden">
        <div className={`h-full ${tone} rounded-full transition-all`} style={{ width: `${safePct}%` }} />
      </div>
      <div className="text-[10px] tabular-nums text-neutral-400 mt-0.5">{pct.toFixed(1)}%</div>
    </div>
  );
};

export default Autonomy;
