import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Sparkles, Search, Radar, Share2, Send, Inbox, FileText, LogOut, ChevronRight, Wand2, LifeBuoy, ShieldCheck, Users as UsersIcon, Ticket as TicketIcon, History, Megaphone, Activity, TrendingUp, Calendar } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import ImpersonateBanner from './ImpersonateBanner';
import BroadcastBanner from './BroadcastBanner';

const items = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard, exact: true },
  { to: '/dashboard/main', label: 'Activity', icon: Activity },
  { to: '/dashboard/performance', label: 'Performance', icon: TrendingUp },
  { to: '/dashboard/calendar', label: 'Calendar', icon: Calendar },
  { to: '/dashboard/insights', label: 'AI Insights', icon: Sparkles },
  { to: '/dashboard/studio', label: 'Content Studio', icon: Wand2 },
  { to: '/dashboard/seo', label: 'SEO Review', icon: Search },
  { to: '/dashboard/scan', label: 'Site Scan', icon: Radar },
  { to: '/dashboard/channels', label: 'Integrations', icon: Share2 },
  { to: '/dashboard/compose', label: 'Compose & Publish', icon: Send },
  { to: '/dashboard/posts', label: 'Posts', icon: FileText },
  { to: '/dashboard/leads', label: 'Leads', icon: Inbox },
  { to: '/dashboard/help', label: 'Help & Support', icon: LifeBuoy },
];

const adminItems = [
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, exact: true },
  { to: '/admin/users', label: 'Users', icon: UsersIcon },
  { to: '/admin/tickets', label: 'Support Inbox', icon: TicketIcon },
  { to: '/admin/broadcasts', label: 'Broadcasts', icon: Megaphone },
  { to: '/admin/audit-log', label: 'Audit Log', icon: History },
];

const DashboardLayout = ({ children, title, subtitle }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F6F4ED] text-neutral-900">
      <ImpersonateBanner />
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 shrink-0 border-r border-neutral-200/70 bg-white/60 backdrop-blur-sm min-h-screen sticky top-0 pb-24">
          <div className="p-5 border-b border-neutral-200/70">
            <button onClick={() => navigate('/')} className="flex items-center gap-2 group">
              <img src="/cortex-logo.png" alt="CortexViral" className="w-9 h-9 rounded-lg object-contain" style={{ background: '#0B0B16' }} />
              <span className="font-semibold text-[15px]">CortexViral</span>
              {user?.is_admin && <span className="ml-1 text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">admin</span>}
            </button>
          </div>
          <nav className="p-3 flex flex-col gap-1">
            {items.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.exact}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-medium transition-colors ${
                    isActive
                      ? 'bg-[#1B7BFF] text-white'
                      : 'text-neutral-700 hover:bg-neutral-100'
                  }`
                }
              >
                <it.icon size={17} />
                {it.label}
              </NavLink>
            ))}

            {user?.is_admin && (
              <>
                <div className="mt-4 mb-1 px-3 text-[10.5px] uppercase tracking-wider text-neutral-400 font-semibold">Admin</div>
                {adminItems.map((it) => (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    end={it.exact}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-medium transition-colors ${
                        isActive
                          ? 'bg-violet-600 text-white'
                          : 'text-neutral-700 hover:bg-violet-50 hover:text-violet-700'
                      }`
                    }
                  >
                    <it.icon size={17} />
                    {it.label}
                  </NavLink>
                ))}
              </>
            )}
          </nav>

          {/* User block */}
          <div className="absolute bottom-0 left-0 right-0 w-64 p-4 border-t border-neutral-200/70 bg-white/80">
            <div className="flex items-center gap-3">
              {user?.picture ? (
                <img src={user.picture} alt={user?.name} className="w-9 h-9 rounded-full ring-2 ring-white shadow-sm" />
              ) : (
                <div className="w-9 h-9 rounded-full bg-[#1B7BFF] text-white flex items-center justify-center text-sm font-semibold">
                  {user?.name?.[0] || 'U'}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-semibold truncate">{user?.name || 'Account'}</div>
                <div className="text-[11px] text-neutral-500 truncate">{user?.email}</div>
              </div>
              <button onClick={logout} className="p-1.5 rounded-lg hover:bg-neutral-100 text-neutral-500" title="Sign out">
                <LogOut size={15} />
              </button>
            </div>
          </div>
        </aside>

        {/* Main */}
        <main className="flex-1 min-w-0">
          <div className="max-w-6xl mx-auto px-8 py-10">
            <BroadcastBanner />
            {title && (
              <div className="mb-8 flex items-center gap-2 text-[12px] text-neutral-500">
                <span>Dashboard</span>
                <ChevronRight size={12} />
                <span className="text-neutral-700">{title}</span>
              </div>
            )}
            {title && (
              <div className="mb-8">
                <h1 className="text-3xl font-medium tracking-tight">{title}</h1>
                {subtitle && <p className="text-neutral-600 mt-1">{subtitle}</p>}
              </div>
            )}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
