import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Send, Inbox, BarChart3, Loader2, ArrowRight,
  TrendingUp, FileText, Activity, Sparkles,
} from 'lucide-react';

const Main = () => {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/activity`, { withCredentials: true }),
      axios.get(`${API}/dashboard/stats`, { withCredentials: true }),
    ]).then(([a, s]) => { setItems(a.data); setStats(s.data); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const META = {
    post: { icon: Send, color: 'bg-emerald-50 text-emerald-700' },
    lead: { icon: Inbox, color: 'bg-rose-50 text-rose-700' },
    report: { icon: BarChart3, color: 'bg-violet-50 text-violet-700' },
  };

  return (
    <DashboardLayout title="Activity Feed" subtitle="Everything happening across your CortexViral workspace.">
      {/* Quick stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-7">
        <StatPill label="Posts" value={stats?.posts || 0} icon={Send} color="text-emerald-600 bg-emerald-50" />
        <StatPill label="Reports" value={stats?.reports || 0} icon={BarChart3} color="text-violet-600 bg-violet-50" />
        <StatPill label="Channels" value={stats?.channels || 0} icon={Activity} color="text-sky-600 bg-sky-50" />
        <StatPill label="Leads" value={stats?.leads || 0} icon={Inbox} color="text-rose-600 bg-rose-50" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Activity feed */}
        <div className="lg:col-span-2 bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          <div className="px-5 py-4 border-b border-neutral-200/70 flex items-center justify-between">
            <h3 className="text-[15px] font-semibold">Recent activity</h3>
            <span className="text-[12px] text-neutral-500">{items.length} events</span>
          </div>
          {loading ? (
            <div className="py-12 text-center"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
          ) : items.length === 0 ? (
            <div className="py-12 text-center text-[14px] text-neutral-500">No activity yet — create a post or run an AI report to see things here.</div>
          ) : (
            <div>
              {items.map((it, i) => {
                const m = META[it.type] || META.post;
                const Icon = m.icon;
                return (
                  <div key={`${it.type}-${it.id}-${i}`} className={`flex items-start gap-3 px-5 py-3.5 ${i < items.length - 1 ? 'border-b border-neutral-100' : ''}`}>
                    <div className={`w-9 h-9 rounded-lg ${m.color} flex items-center justify-center shrink-0`}>
                      <Icon size={15} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] text-neutral-800 truncate">{it.title || '(no content)'}</p>
                      <div className="flex items-center gap-2 mt-1 text-[12px] text-neutral-500">
                        <span>{new Date(it.at).toLocaleString()}</span>
                        {it.platforms?.length > 0 && (
                          <>
                            <span>·</span>
                            <span className="truncate">{it.platforms.join(', ')}</span>
                          </>
                        )}
                        {it.subtitle && <><span>·</span><span className="truncate">{it.subtitle}</span></>}
                        {it.status && (
                          <span className={`text-[10.5px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded ${
                            it.status === 'scheduled' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                          }`}>{it.status}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right rail */}
        <div className="space-y-4">
          <Link to="/dashboard/performance" className="block bg-gradient-to-br from-blue-100 to-blue-50 rounded-3xl p-6 border border-blue-200/40 hover:shadow-lg transition-all">
            <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center mb-3"><TrendingUp size={18} className="text-blue-700" /></div>
            <div className="text-[15px] font-semibold mb-1">Performance</div>
            <p className="text-[13px] text-neutral-700 leading-relaxed">Track sessions, revenue & channels.</p>
            <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-blue-700">Open <ArrowRight size={12} /></span>
          </Link>
          <Link to="/dashboard/calendar" className="block bg-gradient-to-br from-emerald-100 to-emerald-50 rounded-3xl p-6 border border-emerald-200/40 hover:shadow-lg transition-all">
            <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center mb-3"><FileText size={18} className="text-emerald-700" /></div>
            <div className="text-[15px] font-semibold mb-1">Marketing Calendar</div>
            <p className="text-[13px] text-neutral-700 leading-relaxed">Schedule & visualize posts across all channels.</p>
            <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-emerald-700">Open <ArrowRight size={12} /></span>
          </Link>
          <Link to="/dashboard/studio" className="block bg-gradient-to-br from-rose-100 to-rose-50 rounded-3xl p-6 border border-rose-200/40 hover:shadow-lg transition-all">
            <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center mb-3"><Sparkles size={18} className="text-rose-700" /></div>
            <div className="text-[15px] font-semibold mb-1">Content Studio</div>
            <p className="text-[13px] text-neutral-700 leading-relaxed">Generate newsletters, blog posts, video scripts.</p>
            <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-rose-700">Open <ArrowRight size={12} /></span>
          </Link>
        </div>
      </div>
    </DashboardLayout>
  );
};

const StatPill = ({ label, value, icon: Icon, color }) => (
  <div className="bg-white rounded-2xl p-4 border border-neutral-200/70 flex items-center gap-3">
    <div className={`w-9 h-9 rounded-lg ${color} flex items-center justify-center`}><Icon size={15} /></div>
    <div>
      <div className="text-xl font-medium tracking-tight">{value}</div>
      <div className="text-[12px] text-neutral-500">{label}</div>
    </div>
  </div>
);

export default Main;
