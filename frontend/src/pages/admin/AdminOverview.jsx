import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Users, Shield, ShieldCheck, FileText, Send, Inbox, BarChart3, Ticket as TicketIcon, Loader2, Sparkles, Crown, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';

const AdminOverview = () => {
  const [stats, setStats] = useState(null);
  const [aiUsage, setAiUsage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/admin/stats`, { withCredentials: true }).then((r) => setStats(r.data)).catch(() => {}),
      axios.get(`${API}/admin/ai-usage?months=6`, { withCredentials: true }).then((r) => setAiUsage(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

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

const Section = ({ title, children }) => (
  <div className="mb-9">
    <h2 className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">{title}</h2>
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

export default AdminOverview;
