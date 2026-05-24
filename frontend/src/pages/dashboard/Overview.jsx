import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Send, Search, Radar, Share2, Sparkles, ArrowRight, FileText, Inbox, BarChart3 } from 'lucide-react';

const Overview = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState({ posts: 0, reports: 0, channels: 0, leads: 0 });

  useEffect(() => {
    axios.get(`${API}/dashboard/stats`, { withCredentials: true })
      .then((r) => setStats(r.data))
      .catch(() => {});
  }, []);

  const tiles = [
    { label: 'Posts published', value: stats.posts, icon: FileText, color: 'bg-emerald-50 text-emerald-700' },
    { label: 'AI reports', value: stats.reports, icon: BarChart3, color: 'bg-violet-50 text-violet-700' },
    { label: 'Channels connected', value: stats.channels, icon: Share2, color: 'bg-amber-50 text-amber-700' },
    { label: 'Leads collected', value: stats.leads, icon: Inbox, color: 'bg-rose-50 text-rose-700' },
  ];

  const quickActions = [
    { to: '/dashboard/seo', icon: Search, title: 'Run an SEO review', desc: 'Audit any URL with AI — score, issues, fixes.', color: 'from-blue-100 to-blue-50' },
    { to: '/dashboard/scan', icon: Radar, title: 'Scan your website', desc: 'Detect new listings & generate post ideas.', color: 'from-emerald-100 to-emerald-50' },
    { to: '/dashboard/compose', icon: Send, title: 'Compose & publish', desc: 'Push new posts across all your channels.', color: 'from-violet-100 to-violet-50' },
    { to: '/dashboard/insights', icon: Sparkles, title: 'Get AI insights', desc: 'Tailored marketing advice for your business.', color: 'from-amber-100 to-amber-50' },
  ];

  return (
    <DashboardLayout>
      <div className="mb-9">
        <div className="text-[13px] text-neutral-500 mb-1">Welcome back</div>
        <h1 className="text-3xl md:text-4xl font-medium tracking-tight">
          Hi {user?.name?.split(' ')[0] || 'there'} 👋
        </h1>
        <p className="text-neutral-600 mt-1">Here's what's running across your marketing today.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        {tiles.map((t) => (
          <div key={t.label} className="bg-white rounded-2xl p-5 border border-neutral-200/70">
            <div className={`w-9 h-9 rounded-lg ${t.color} flex items-center justify-center mb-3`}>
              <t.icon size={17} />
            </div>
            <div className="text-3xl font-medium tracking-tight">{t.value}</div>
            <div className="text-[13px] text-neutral-600 mt-1">{t.label}</div>
          </div>
        ))}
      </div>

      <h2 className="text-xl font-semibold tracking-tight mb-4">Quick actions</h2>
      <div className="grid md:grid-cols-2 gap-4">
        {quickActions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className={`group relative overflow-hidden rounded-3xl bg-gradient-to-br ${a.color} p-7 border border-neutral-200/50 hover:shadow-lg transition-all hover:-translate-y-0.5`}
          >
            <div className="w-12 h-12 rounded-xl bg-white flex items-center justify-center mb-4 shadow-sm">
              <a.icon size={20} className="text-neutral-800" />
            </div>
            <div className="text-lg font-semibold tracking-tight mb-1">{a.title}</div>
            <div className="text-[14px] text-neutral-700">{a.desc}</div>
            <div className="mt-5 inline-flex items-center gap-1.5 text-[13px] font-medium text-[#1B7BFF] group-hover:gap-2 transition-all">
              Open <ArrowRight size={14} />
            </div>
          </Link>
        ))}
      </div>
    </DashboardLayout>
  );
};

export default Overview;
