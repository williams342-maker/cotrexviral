import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Users, Shield, ShieldCheck, FileText, Send, Inbox, BarChart3, Ticket as TicketIcon, Loader2, Sparkles, Crown, Zap, TrendingUp, Eye, UserPlus, Wand2, CreditCard, Mail, AlertCircle, DollarSign, Database, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';

const AdminOverview = () => {
  const [stats, setStats] = useState(null);
  const [aiUsage, setAiUsage] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [funnelDays, setFunnelDays] = useState(30);
  const [emailHealth, setEmailHealth] = useState(null);
  const [llmSpend, setLlmSpend] = useState(null);
  const [spendDays, setSpendDays] = useState(30);
  const [memoryPerf, setMemoryPerf] = useState(null);
  const [contentLayer, setContentLayer] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/admin/stats`, { withCredentials: true }).then((r) => setStats(r.data)).catch(() => {}),
      axios.get(`${API}/admin/ai-usage?months=6`, { withCredentials: true }).then((r) => setAiUsage(r.data)).catch(() => {}),
      axios.get(`${API}/admin/funnel?days=30`, { withCredentials: true }).then((r) => setFunnel(r.data)).catch(() => {}),
      axios.get(`${API}/admin/email/health?hours=24`, { withCredentials: true }).then((r) => setEmailHealth(r.data)).catch(() => {}),
      axios.get(`${API}/admin/llm-spend?days=30`, { withCredentials: true }).then((r) => setLlmSpend(r.data)).catch(() => {}),
      axios.get(`${API}/admin/memory-perf`, { withCredentials: true }).then((r) => setMemoryPerf(r.data)).catch(() => {}),
      axios.get(`${API}/admin/content-layer/health`, { withCredentials: true }).then((r) => setContentLayer(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const reloadSpend = (days) => {
    setSpendDays(days);
    axios.get(`${API}/admin/llm-spend?days=${days}`, { withCredentials: true })
      .then((r) => setLlmSpend(r.data))
      .catch(() => {});
  };

  const reloadFunnel = (days) => {
    setFunnelDays(days);
    axios.get(`${API}/admin/funnel?days=${days}`, { withCredentials: true })
      .then((r) => setFunnel(r.data))
      .catch(() => {});
  };

  if (loading) return <DashboardLayout><div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div></DashboardLayout>;

  const userTiles = [
    { label: 'Total users', value: stats?.total_users, icon: Users, color: 'bg-emerald-50 text-emerald-700' },
    { label: 'Active', value: stats?.active_users, icon: ShieldCheck, color: 'bg-sky-50 text-sky-700' },
    { label: 'Suspended', value: stats?.suspended_users, icon: Shield, color: 'bg-rose-50 text-rose-700' },
    { label: 'Admins', value: stats?.admins, icon: Shield, color: 'bg-violet-50 text-violet-700' },
  ];
  const activityTiles = [
    { label: 'Total leads', value: stats?.total_leads, icon: Inbox, color: 'bg-amber-50 text-amber-700' },
    { label: 'Total posts', value: stats?.total_posts, icon: Send, color: 'bg-emerald-50 text-emerald-700' },
    { label: 'AI reports', value: stats?.total_reports, icon: BarChart3, color: 'bg-violet-50 text-violet-700' },
    { label: 'Channels', value: stats?.total_channels, icon: FileText, color: 'bg-sky-50 text-sky-700' },
  ];
  const ticketTiles = [
    { label: 'Open tickets', value: stats?.open_tickets, color: 'bg-amber-50 text-amber-700' },
    { label: 'Answered', value: stats?.answered_tickets, color: 'bg-sky-50 text-sky-700' },
    { label: 'Closed', value: stats?.closed_tickets, color: 'bg-emerald-50 text-emerald-700' },
  ];
  const subTiles = [
    { label: 'Free', value: stats?.users_free, icon: Users, color: 'bg-neutral-100 text-neutral-700' },
    { label: 'Starter', value: stats?.users_starter, icon: Zap, color: 'bg-sky-50 text-sky-700' },
    { label: 'Growth', value: stats?.users_growth, icon: Sparkles, color: 'bg-violet-50 text-violet-700' },
    { label: 'Agency', value: stats?.users_agency, icon: Crown, color: 'bg-amber-50 text-amber-700' },
  ];
  const subSecondary = [
    { label: 'Trialing', value: stats?.trialing_subs, color: 'bg-emerald-50 text-emerald-700' },
    { label: 'Past due', value: stats?.past_due_subs, color: 'bg-rose-50 text-rose-700' },
    { label: 'Legacy (Pro/Scale)', value: stats?.users_legacy, color: 'bg-neutral-100 text-neutral-600' },
  ];

  // Seller Acquisition OS — cross-user totals
  const sellerOsTiles = [
    { label: 'Total seller leads', value: stats?.seller_leads_total,     icon: Users,    color: 'bg-amber-50 text-amber-700' },
    { label: 'Qualified',          value: stats?.seller_leads_qualified, icon: Sparkles, color: 'bg-violet-50 text-violet-700' },
    { label: 'Outreached',         value: stats?.seller_leads_outreached,icon: Send,     color: 'bg-sky-50 text-sky-700' },
    { label: 'Active sellers',     value: stats?.seller_leads_active,    icon: ShieldCheck, color: 'bg-emerald-50 text-emerald-700' },
  ];
  const sellerOsSecondary = [
    { label: 'Churn workflows running',  value: stats?.seller_workflows_running,  color: 'bg-rose-50 text-rose-700' },
    { label: 'Workflows complete',       value: stats?.seller_workflows_complete, color: 'bg-neutral-100 text-neutral-600' },
    { label: 'Audit artifacts generated',value: stats?.seller_artifacts_total,    color: 'bg-violet-50 text-violet-700' },
    { label: 'Active seller missions',   value: stats?.seller_missions_active,    color: 'bg-sky-50 text-sky-700' },
  ];

  // AI-usage sparkline scaling
  const maxMonth = Math.max(1, ...(aiUsage?.global_by_month || []).map((m) => m.ai_generations));

  return (
    <DashboardLayout title="Admin Overview" subtitle="Platform-wide stats and controls.">
      <Section title="Users">
        <Grid items={userTiles} />
      </Section>
      <Section title="Activity">
        <Grid items={activityTiles} />
      </Section>
      <Section title="Support tickets">
        <div className="grid grid-cols-3 gap-4">
          {ticketTiles.map((t) => (
            <div key={t.label} className="bg-white rounded-2xl p-5 border border-neutral-200/70">
              <div className={`w-9 h-9 rounded-lg ${t.color} flex items-center justify-center mb-3`}>
                <TicketIcon size={16} />
              </div>
              <div className="text-3xl font-medium tracking-tight">{t.value || 0}</div>
              <div className="text-[13px] text-neutral-600 mt-1">{t.label}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Seller Acquisition OS"
        action={
          <Link to="/admin/seller-os" data-testid="admin-overview-seller-os-link"
                className="text-[12.5px] font-semibold text-violet-700 hover:text-violet-900 inline-flex items-center gap-1">
            Inspect <ArrowUpRight size={12} />
          </Link>
        }
      >
        <Grid items={sellerOsTiles} />
        <div className="grid grid-cols-4 gap-4 mt-4">
          {sellerOsSecondary.map((t) => (
            <div key={t.label} className="bg-white rounded-2xl p-4 border border-neutral-200/70"
                 data-testid={`admin-overview-seller-${t.label.toLowerCase().replace(/\s+/g, '-')}`}>
              <div className={`inline-block text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full ${t.color} mb-2`}>
                {t.label}
              </div>
              <div className="text-2xl font-medium tracking-tight">{t.value || 0}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Subscription distribution">
        <Grid items={subTiles} />
        <div className="grid grid-cols-3 gap-4 mt-4">
          {subSecondary.map((t) => (
            <div key={t.label} className="bg-white rounded-2xl p-5 border border-neutral-200/70" data-testid={`admin-sub-${t.label.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
              <div className={`w-9 h-9 rounded-lg ${t.color} flex items-center justify-center mb-3`}>
                <BarChart3 size={16} />
              </div>
              <div className="text-3xl font-medium tracking-tight">{t.value || 0}</div>
              <div className="text-[13px] text-neutral-600 mt-1">{t.label}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Conversion funnel">
        <div className="bg-white rounded-2xl p-6 border border-neutral-200/70" data-testid="admin-funnel">
          <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
            <div>
              <div className="text-[13px] text-neutral-500 font-medium">Last {funnelDays} days</div>
              <div className="text-[15px] font-semibold text-neutral-900 mt-0.5">Visitor → Paid conversion</div>
            </div>
            <div className="inline-flex rounded-full bg-neutral-100 p-1" data-testid="admin-funnel-tabs">
              {[7, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => reloadFunnel(d)}
                  data-testid={`admin-funnel-tab-${d}`}
                  className={`px-3 h-7 rounded-full text-[12px] font-semibold transition-colors ${funnelDays === d ? 'bg-white text-neutral-900 shadow-sm' : 'text-neutral-500 hover:text-neutral-700'}`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>
          <FunnelStages funnel={funnel} />
        </div>
      </Section>

      <Section title="Email health (last 24h)">
        <EmailHealthCard health={emailHealth} />
      </Section>

      <MemoryPerfCallout perf={memoryPerf} />

      <ContentLayerCallout health={contentLayer} />

      <Section title="LLM model spend (estimated)">
        <LlmSpendCard
          spend={llmSpend}
          days={spendDays}
          onChangeDays={reloadSpend}
        />
      </Section>

      <Section title="AI generation analytics">
        <div className="grid lg:grid-cols-3 gap-4" data-testid="admin-ai-usage">
          {/* Sparkline: last 6 months */}
          <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-neutral-200/70">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-[13px] text-neutral-500 font-medium">Total AI generations (last 6 months)</div>
                <div className="text-3xl font-medium tracking-tight mt-1">{aiUsage?.totals?.last_n_months ?? 0}</div>
              </div>
              <div className="text-right">
                <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">This month</div>
                <div className="text-2xl font-semibold text-[#1B7BFF]">{aiUsage?.totals?.this_month ?? 0}</div>
              </div>
            </div>
            <div className="flex items-end gap-2 h-24">
              {(aiUsage?.global_by_month || []).map((m) => {
                const h = Math.max(4, Math.round((m.ai_generations / maxMonth) * 100));
                return (
                  <div key={m.month} className="flex-1 flex flex-col items-center justify-end gap-1.5">
                    <div className="text-[10px] text-neutral-500 tabular-nums">{m.ai_generations}</div>
                    <div
                      className="w-full bg-gradient-to-t from-violet-500 to-blue-400 rounded-md transition-all"
                      style={{ height: `${h}%`, minHeight: '4px' }}
                      title={`${m.month}: ${m.ai_generations}`}
                    />
                    <div className="text-[10px] text-neutral-500">{m.month.slice(-2)}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Breakdown by kind */}
          <div className="bg-white rounded-2xl p-5 border border-neutral-200/70">
            <div className="text-[13px] text-neutral-500 font-medium mb-3">By content type</div>
            {(aiUsage?.breakdown_by_kind || []).length === 0 ? (
              <div className="text-[12.5px] text-neutral-500 italic py-4 text-center">No generations yet.</div>
            ) : (
              <div className="space-y-2.5">
                {aiUsage.breakdown_by_kind.slice(0, 8).map((k) => (
                  <div key={k.kind} className="flex items-center justify-between text-[13px]">
                    <span className="text-neutral-700 capitalize">{k.kind.replace(/_/g, ' ')}</span>
                    <span className="font-semibold text-neutral-900 tabular-nums">{k.count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Top users table */}
        <div className="mt-4 bg-white rounded-2xl border border-neutral-200/70 overflow-hidden" data-testid="admin-ai-top-users">
          <div className="px-5 py-4 border-b border-neutral-200/70">
            <div className="text-[13px] text-neutral-500 font-medium">Top users this month</div>
          </div>
          {(aiUsage?.top_users || []).length === 0 ? (
            <div className="text-[12.5px] text-neutral-500 italic py-6 text-center">No usage to show yet.</div>
          ) : (
            <table className="w-full text-[13.5px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500 font-semibold border-b border-neutral-200/70">
                  <th className="px-5 py-3">User</th>
                  <th className="px-5 py-3">Plan</th>
                  <th className="px-5 py-3 text-right">Generations</th>
                </tr>
              </thead>
              <tbody>
                {aiUsage.top_users.map((u) => (
                  <tr key={u.user_id} className="border-b border-neutral-200/40 last:border-0">
                    <td className="px-5 py-3">
                      <div className="font-medium text-neutral-900">{u.name || u.email}</div>
                      <div className="text-[11.5px] text-neutral-500">{u.email}</div>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`inline-block text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-full font-semibold ${
                        u.plan === 'agency' ? 'bg-amber-50 text-amber-700'
                        : u.plan === 'growth' ? 'bg-violet-50 text-violet-700'
                        : u.plan === 'starter' ? 'bg-sky-50 text-sky-700'
                        : 'bg-neutral-100 text-neutral-700'
                      }`}>
                        {u.plan || 'free'}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums font-semibold">{u.ai_generations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Section>
      <div className="grid md:grid-cols-2 gap-4">
        <Link to="/admin/users" className="group bg-gradient-to-br from-blue-100 to-blue-50 rounded-3xl p-7 border border-blue-200/50 hover:-translate-y-0.5 hover:shadow-lg transition-all">
          <div className="w-12 h-12 rounded-xl bg-white shadow-sm flex items-center justify-center mb-4"><Users size={20} /></div>
          <div className="text-lg font-semibold tracking-tight mb-1">Manage users →</div>
          <p className="text-[14px] text-neutral-700">Search, suspend, promote, delete, or impersonate any user.</p>
        </Link>
        <Link to="/admin/tickets" className="group bg-gradient-to-br from-amber-100 to-amber-50 rounded-3xl p-7 border border-amber-200/50 hover:-translate-y-0.5 hover:shadow-lg transition-all">
          <div className="w-12 h-12 rounded-xl bg-white shadow-sm flex items-center justify-center mb-4"><TicketIcon size={20} /></div>
          <div className="text-lg font-semibold tracking-tight mb-1">Support inbox →</div>
          <p className="text-[14px] text-neutral-700">Reply to escalated support tickets.</p>
        </Link>
      </div>
    </DashboardLayout>
  );
};

const Section = ({ title, action, children }) => (
  <div className="mb-9">
    <div className="flex items-center justify-between mb-3">
      <h2 className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold">{title}</h2>
      {action}
    </div>
    {children}
  </div>
);

const Grid = ({ items }) => (
  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
    {items.map((t) => (
      <div key={t.label} className="bg-white rounded-2xl p-5 border border-neutral-200/70">
        <div className={`w-9 h-9 rounded-lg ${t.color} flex items-center justify-center mb-3`}>
          <t.icon size={16} />
        </div>
        <div className="text-3xl font-medium tracking-tight">{t.value || 0}</div>
        <div className="text-[13px] text-neutral-600 mt-1">{t.label}</div>
      </div>
    ))}
  </div>
);

const FunnelStages = ({ funnel }) => {
  if (!funnel) {
    return <div className="text-[12.5px] text-neutral-500 italic py-4 text-center">Loading funnel…</div>;
  }
  const b = funnel.buckets || {};
  const r = funnel.rates || {};
  const stages = [
    {
      key: 'visitors', icon: Eye, label: 'Visitors', value: b.visitors || 0,
      sub: `${b.raw_views || 0} raw views`, color: 'bg-sky-50 text-sky-700 border-sky-100',
    },
    {
      key: 'signups', icon: UserPlus, label: 'Signups', value: b.signups || 0,
      sub: `${pct(r.visit_to_signup)} of visitors`, color: 'bg-violet-50 text-violet-700 border-violet-100',
    },
    {
      key: 'activated', icon: Wand2, label: 'Activated', value: b.activated || 0,
      sub: `${pct(r.signup_to_activated)} of signups`, color: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-100',
    },
    {
      key: 'paid', icon: CreditCard, label: 'Paid', value: b.paid || 0,
      sub: `${pct(r.activated_to_paid)} of activated`, color: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    },
  ];
  const peak = Math.max(1, ...stages.map((s) => s.value));

  return (
    <div className="space-y-2.5">
      {stages.map((s, i) => {
        const width = Math.max(8, Math.round((s.value / peak) * 100));
        return (
          <div
            key={s.key}
            className="flex items-center gap-4"
            data-testid={`admin-funnel-stage-${s.key}`}
          >
            <div className="w-32 shrink-0 flex items-center gap-2">
              <div className={`w-7 h-7 rounded-lg border ${s.color} flex items-center justify-center`}>
                <s.icon size={13} />
              </div>
              <div className="text-[13.5px] font-semibold text-neutral-900">{s.label}</div>
            </div>
            <div className="flex-1">
              <div
                className={`h-9 rounded-lg border ${s.color} flex items-center px-3 transition-all duration-500`}
                style={{ width: `${width}%`, minWidth: '40px' }}
              >
                <span className="text-[14px] font-semibold tabular-nums">{s.value.toLocaleString()}</span>
              </div>
            </div>
            <div className="w-44 shrink-0 text-right text-[11.5px] text-neutral-500 tabular-nums">{s.sub}</div>
          </div>
        );
      })}
      <div className="mt-5 pt-4 border-t border-neutral-200/70 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} className="text-emerald-600" />
          <span className="text-[13px] text-neutral-700">
            Overall <strong className="text-neutral-900">{pct(r.visit_to_paid)}</strong> of visitors become paid customers
          </span>
        </div>
        {b.comped > 0 && (
          <span className="text-[11.5px] text-neutral-500" data-testid="admin-funnel-comped">
            + {b.comped} comped (not counted)
          </span>
        )}
      </div>
    </div>
  );
};

const pct = (n) => {
  if (typeof n !== 'number' || !isFinite(n)) return '0%';
  return `${(n * 100).toFixed(n < 0.001 && n > 0 ? 3 : 1)}%`;
};

const EmailHealthCard = ({ health }) => {
  if (!health) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-neutral-200/70 text-[12.5px] text-neutral-500 italic">
        Loading email health…
      </div>
    );
  }
  const { total, sent, rejected, errored, skipped, delivery_rate, last_problem } = health;
  // Health state — gives the headline pill its color/copy.
  let state = { color: 'bg-neutral-50 text-neutral-600 border-neutral-200', label: 'No sends in the last 24h', icon: Mail };
  if (total > 0) {
    if (delivery_rate >= 0.95) state = { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', label: 'Healthy', icon: ShieldCheck };
    else if (delivery_rate >= 0.7) state = { color: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Degraded', icon: AlertCircle };
    else state = { color: 'bg-rose-50 text-rose-700 border-rose-200', label: 'Failing', icon: AlertCircle };
  }
  const tiles = [
    { label: 'Sent', value: sent, tone: 'text-emerald-700' },
    { label: 'Rejected', value: rejected, tone: rejected > 0 ? 'text-rose-700' : 'text-neutral-700' },
    { label: 'Errored', value: errored, tone: errored > 0 ? 'text-rose-700' : 'text-neutral-700' },
    { label: 'Skipped', value: skipped, tone: 'text-neutral-500' },
  ];

  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-200/70" data-testid="admin-email-health">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-5">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg border ${state.color} flex items-center justify-center`}>
            <state.icon size={16} />
          </div>
          <div>
            <div className="text-[13px] text-neutral-500 font-medium">Transactional email</div>
            <div className="text-[15px] font-semibold text-neutral-900 mt-0.5">
              {state.label}
              {total > 0 && (
                <span className="ml-2 text-[12.5px] font-normal text-neutral-500 tabular-nums">
                  {pct(delivery_rate)} delivered · {total.toLocaleString()} sends
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-neutral-200/70 p-3" data-testid={`email-tile-${t.label.toLowerCase()}`}>
            <div className={`text-2xl font-medium tabular-nums ${t.tone}`}>{t.value || 0}</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">{t.label}</div>
          </div>
        ))}
      </div>

      {last_problem && (
        <div className="rounded-lg border border-amber-200/70 bg-amber-50/40 px-3 py-2.5 text-[12.5px]" data-testid="email-last-problem">
          <div className="flex items-center gap-2 text-amber-800 font-semibold mb-1">
            <AlertCircle size={12} /> Most recent issue
          </div>
          <div className="text-neutral-700 leading-snug">
            <span className="font-semibold capitalize">{last_problem.status}</span>
            {last_problem.mg_status && <span className="text-neutral-500"> · HTTP {last_problem.mg_status}</span>}
            <span className="text-neutral-500"> · </span>
            <span className="text-neutral-500">{last_problem.subject}</span>
          </div>
          {last_problem.reason && (
            <div className="text-neutral-500 mt-1 line-clamp-2 italic">{String(last_problem.reason).slice(0, 220)}</div>
          )}
        </div>
      )}
    </div>
  );
};


/* ----------------------- Memory perf migration callout -------------------------- */
const MemoryPerfCallout = ({ perf }) => {
  // Render NOTHING while loading or if the endpoint failed — this is
  // purely a "you have a new problem" callout, no need to take up
  // dashboard real estate otherwise.
  if (!perf) return null;
  const triggered = perf.migration_triggered || perf.capacity_triggered;
  if (!triggered) {
    // Still expose the metric in a compact slate card so an admin can
    // see the headroom without digging — but with zero visual urgency.
    return (
      <div
        className="bg-white rounded-2xl p-4 border border-neutral-200/70 flex items-center gap-3 text-[12.5px] text-neutral-500"
        data-testid="memory-perf-card-healthy"
      >
        <span className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
          <Database size={14} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-neutral-700 font-medium">Memory retrieval healthy</div>
          <div className="text-neutral-500 tabular-nums">
            p95 {perf.p95_ms?.toFixed?.(1) ?? '0.0'} ms · p50 {perf.p50_ms?.toFixed?.(1) ?? '0.0'} ms · {perf.samples} samples ·
            {' '}{perf.total_memories} memories across {perf.distinct_users} users
          </div>
        </div>
        <a
          href={`${API}/admin/memory-perf/samples.csv`}
          className="text-[11px] px-2 py-1 rounded border border-neutral-300 text-neutral-600 hover:bg-neutral-100"
          data-testid="memory-perf-csv-export-healthy"
          title="Download the rolling latency window as CSV (for histogramming / pre-migration tuning)"
        >
          Export CSV
        </a>
        <span className="text-[10px] uppercase tracking-widest text-emerald-600 font-bold">OK</span>
      </div>
    );
  }
  // Triggered — render the violet "migration recommended" callout.
  const reason = perf.migration_triggered
    ? `Retrieval p95 has crossed ${perf.p95_threshold_ms} ms (currently ${perf.p95_ms?.toFixed?.(1)} ms over ${perf.samples} samples)`
    : `Top user now holds ${perf.top_user_memory_count?.toLocaleString?.()} memories — the documented capacity trigger`;
  return (
    <div
      className="rounded-2xl border border-violet-300/60 bg-gradient-to-br from-violet-50 via-white to-violet-50 p-5"
      data-testid="memory-perf-migration-callout"
    >
      <div className="flex items-start gap-4">
        <span className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center shrink-0">
          <Database size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-widest text-violet-600 font-bold">Vector DB migration recommended</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-violet-400/50 bg-violet-100 text-violet-700 font-semibold">
              {perf.migration_triggered ? 'P95 TRIGGER' : 'CAPACITY TRIGGER'}
            </span>
          </div>
          <div className="text-[13.5px] text-neutral-800 leading-relaxed">
            {reason}. The 2-hour <span className="font-semibold">Mongo Atlas <code className="text-violet-700 bg-violet-100 px-1 rounded text-[12px]">$vectorSearch</code></span> migration is the recommended next step — no second datastore, drop-in replacement, fully reversible by feature flag.
          </div>
          <div className="mt-2 text-[12px] text-neutral-600 tabular-nums">
            p95 <span className="font-semibold text-violet-700">{perf.p95_ms?.toFixed?.(1) ?? '0.0'} ms</span> (threshold {perf.p95_threshold_ms} ms) · p99 {perf.p99_ms?.toFixed?.(1) ?? '0.0'} ms ·
            {' '}{perf.total_memories?.toLocaleString?.()} memories · top user {perf.top_user_memory_count?.toLocaleString?.()} rows · {perf.samples} samples
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <a
              href="https://github.com/your-org/cortexviral/blob/main/memory/VECTOR_DB_EVALUATION.md"
              target="_blank"
              rel="noreferrer"
              onClick={(e) => {
                // Fallback: copy the path to clipboard if no external repo URL is set.
                e.preventDefault();
                try {
                  navigator.clipboard.writeText('/app/memory/VECTOR_DB_EVALUATION.md');
                } catch { /* ignore */ }
                window.alert(
                  'Migration plan: /app/memory/VECTOR_DB_EVALUATION.md\n\n'
                  + '§7 has the 4-step migration plan (strategy interface → MongoVectorSearchBackend → search index → feature flag rollout). '
                  + 'Total effort: ~half a day.',
                );
              }}
              className="px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-[12px] font-medium flex items-center gap-1.5"
              data-testid="memory-perf-open-eval-doc"
            >
              Open migration plan <ArrowUpRight size={12} />
            </a>
            <a
              href={`${API}/admin/memory-perf/samples.csv`}
              className="px-3 py-1.5 rounded-lg border border-violet-400/60 text-violet-700 hover:bg-violet-50 text-[12px] font-medium"
              data-testid="memory-perf-csv-export-triggered"
              title="Download the rolling latency window as CSV for histogramming / pre-migration tuning"
            >
              Export latency CSV
            </a>
            <span className="text-[11px] text-neutral-500 italic">{perf.migration_doc}</span>
          </div>
        </div>
      </div>
    </div>
  );
};


/* -------------- Content-layer drift / mirror-coverage callout ----------------- */
/* Phase 3 read cutover relies on every legacy `posts` row carrying a
   `content_item_id` cross-ref. This callout surfaces the un-mirrored
   count + percentage so admins can see drift trend toward zero
   before we cut over to strict-normalized reads (Phase 4). */
const ContentLayerCallout = ({ health }) => {
  if (!health) return null;
  const triggered = health.drift_triggered;
  if (!triggered) {
    return (
      <div
        className="bg-white rounded-2xl p-4 border border-neutral-200/70 flex items-center gap-3 text-[12.5px] text-neutral-500"
        data-testid="content-layer-card-healthy"
      >
        <span className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
          <Database size={14} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-neutral-700 font-medium flex items-center gap-2">
            Content layer healthy
            {health.strict_mode && (
              <span className="text-[9.5px] uppercase tracking-widest px-1.5 py-0.5 rounded border border-violet-300 bg-violet-50 text-violet-700 font-bold" data-testid="content-layer-strict-pill">
                STRICT
              </span>
            )}
          </div>
          <div className="text-neutral-500 tabular-nums">
            {health.mirror_coverage_pct?.toFixed?.(1) ?? '0.0'}% mirror coverage ·
            {' '}{health.mirrored_posts?.toLocaleString?.()} / {health.total_posts?.toLocaleString?.()} posts mirrored ·
            {' '}{health.total_content_items?.toLocaleString?.()} items ·
            {' '}{health.total_content_variants?.toLocaleString?.()} variants
          </div>
        </div>
        <span className="text-[10px] uppercase tracking-widest text-emerald-600 font-bold">OK</span>
      </div>
    );
  }
  return (
    <div
      className="rounded-2xl border border-amber-300/60 bg-gradient-to-br from-amber-50 via-white to-amber-50 p-5"
      data-testid="content-layer-drift-callout"
    >
      <div className="flex items-start gap-4">
        <span className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
          <Database size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-widest text-amber-600 font-bold">Content layer drift</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-400/60 bg-amber-100 text-amber-700 font-semibold">
              {health.unmirrored_posts} UN-MIRRORED
            </span>
          </div>
          <div className="text-[13.5px] text-neutral-800 leading-relaxed">
            <span className="font-semibold text-amber-700">{health.unmirrored_posts}</span> posts lack a normalized mirror
            (threshold {health.drift_threshold}). Reads still surface them via the lenient fallback, but Phase 4
            (strict-normalized reads) is blocked until this hits zero.
          </div>
          <div className="mt-2 text-[12px] text-neutral-600 tabular-nums">
            Coverage <span className="font-semibold text-amber-700">{health.mirror_coverage_pct?.toFixed?.(2)}%</span> ·
            {' '}{health.mirrored_posts?.toLocaleString?.()} / {health.total_posts?.toLocaleString?.()} mirrored ·
            {' '}{health.total_content_items?.toLocaleString?.()} items ·
            {' '}{health.total_content_variants?.toLocaleString?.()} variants
          </div>
          {Object.keys(health.unmirrored_by_status || {}).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5" data-testid="content-layer-unmirrored-status">
              {Object.entries(health.unmirrored_by_status).map(([status, n]) => (
                <span
                  key={status}
                  className="text-[11px] px-2 py-0.5 rounded-full border border-amber-300/60 bg-amber-50 text-amber-700 font-medium tabular-nums"
                >
                  {status}: {n}
                </span>
              ))}
            </div>
          )}
          <div className="mt-3 text-[11px] text-neutral-500 italic">
            Fix: re-run <code className="text-amber-700 bg-amber-100 px-1 rounded">POST /api/admin/migrations/normalize/run</code>
            {' '}to backfill any stragglers.
          </div>
        </div>
      </div>
    </div>
  );
};






/* ----------------------------------- LLM spend ---------------------------------- */
const LlmSpendCard = ({ spend, days, onChangeDays }) => {
  if (!spend) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-neutral-200/70 text-center text-[12.5px] text-neutral-500 italic" data-testid="admin-llm-spend-loading">
        Loading LLM spend…
      </div>
    );
  }
  const totalCost = spend.total_estimated_cost || 0;
  const totalCalls = spend.total_calls || 0;
  const driver = spend.biggest_driver;
  const fmtUSD = (v) => `$${(v || 0).toFixed(2)}`;
  const fmtTokens = (n) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };
  const maxCost = Math.max(0.01, ...(spend.by_mode || []).map((r) => r.cost));

  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-200/70" data-testid="admin-llm-spend">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
        <div>
          <div className="text-[13px] text-neutral-500 font-medium flex items-center gap-1.5">
            <DollarSign size={12} /> Estimated LLM spend · last {days} days
          </div>
          <div className="flex items-baseline gap-2 mt-1.5">
            <span className="text-3xl font-medium tracking-tight text-neutral-900" data-testid="admin-llm-spend-total">{fmtUSD(totalCost)}</span>
            <span className="text-[13px] text-neutral-500">· {totalCalls.toLocaleString()} call{totalCalls === 1 ? '' : 's'}</span>
            {spend.total_tokens?.total > 0 && (
              <span className="text-[13px] text-neutral-500" data-testid="admin-llm-spend-tokens">
                · {fmtTokens(spend.total_tokens.total)} tokens
              </span>
            )}
          </div>
          <div className="text-[11px] text-neutral-400 mt-1">
            Token-accurate when available, falls back to per-call averages — accuracy ±5%.
          </div>
        </div>
        <div className="inline-flex rounded-full bg-neutral-100 p-1" data-testid="admin-llm-spend-tabs">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => onChangeDays(d)}
              data-testid={`admin-llm-spend-tab-${d}`}
              className={`px-3 h-7 rounded-full text-[12px] font-semibold transition-colors ${days === d ? 'bg-white text-neutral-900 shadow-sm' : 'text-neutral-500 hover:text-neutral-700'}`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {totalCalls === 0 ? (
        <div className="text-[12.5px] text-neutral-500 italic py-4 text-center" data-testid="admin-llm-spend-empty">
          No agent_chat calls in this window yet.
        </div>
      ) : (
        <>
          {/* Biggest cost driver callout */}
          {driver && driver.percentage >= 20 && (
            <div className="rounded-lg border border-violet-200/70 bg-violet-50/50 px-3 py-2.5 mb-5 text-[12.5px] flex items-start gap-2" data-testid="admin-llm-spend-driver">
              <Sparkles size={13} className="text-violet-600 mt-0.5 shrink-0" />
              <span className="text-neutral-700 leading-snug">
                <strong className="text-violet-700">{driver.percentage}%</strong> of spend is
                {' '}<span className="font-mono text-[12px] bg-white px-1.5 py-0.5 rounded border border-violet-200/60">{driver.model}</span>{' '}
                from <strong className="capitalize">{driver.agent}</strong>.
                {driver.percentage >= 60 && (
                  <span className="text-neutral-500"> Nudge users toward Auto/Fast mode to lower bills.</span>
                )}
              </span>
            </div>
          )}

          <div className="grid lg:grid-cols-3 gap-5">
            {/* By mode */}
            <div data-testid="admin-llm-by-mode">
              <div className="text-[11.5px] uppercase tracking-wider text-neutral-500 font-semibold mb-2.5">By mode</div>
              <div className="space-y-2.5">
                {(spend.by_mode || []).map((r) => {
                  const pct = totalCost > 0 ? Math.round((r.cost / totalCost) * 100) : 0;
                  return (
                    <div key={r.mode}>
                      <div className="flex items-center justify-between text-[12.5px]">
                        <span className="capitalize text-neutral-700 font-medium">{r.mode}</span>
                        <span className="tabular-nums text-neutral-900 font-semibold">{fmtUSD(r.cost)} <span className="text-neutral-400 font-normal">· {pct}%</span></span>
                      </div>
                      <div className="h-1.5 bg-neutral-100 rounded-full mt-1 overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-violet-500 to-blue-400" style={{ width: `${Math.max(2, (r.cost / maxCost) * 100)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* By agent */}
            <div data-testid="admin-llm-by-agent">
              <div className="text-[11.5px] uppercase tracking-wider text-neutral-500 font-semibold mb-2.5">By agent</div>
              <div className="space-y-1.5">
                {(spend.by_agent || []).slice(0, 6).map((r) => (
                  <div key={r.agent_id} className="flex items-center justify-between text-[12.5px]">
                    <span className="capitalize text-neutral-700">{r.agent_id}</span>
                    <span className="tabular-nums">
                      <span className="text-neutral-400 mr-2">{r.calls}</span>
                      <span className="text-neutral-900 font-semibold">{fmtUSD(r.cost)}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Top users */}
            <div data-testid="admin-llm-top-users">
              <div className="text-[11.5px] uppercase tracking-wider text-neutral-500 font-semibold mb-2.5">Top spenders</div>
              {(spend.top_users || []).length === 0 ? (
                <div className="text-[12px] text-neutral-500 italic">No data.</div>
              ) : (
                <div className="space-y-1.5">
                  {spend.top_users.slice(0, 5).map((u) => (
                    <div key={u.user_id} className="flex items-center justify-between text-[12.5px]" title={u.user_id}>
                      <span className="text-neutral-700 truncate max-w-[180px]">{u.email || u.name || u.user_id.slice(0, 12)}</span>
                      <span className="tabular-nums text-neutral-900 font-semibold">{fmtUSD(u.cost)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AdminOverview;
