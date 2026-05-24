import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Users, Shield, ShieldCheck, FileText, Send, Inbox, BarChart3, Ticket as TicketIcon, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';

const AdminOverview = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/admin/stats`, { withCredentials: true })
      .then((r) => setStats(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
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
