import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Sparkles, Search, Radar, Share2, Send, Inbox, FileText, LogOut, ChevronRight, Wand2, LifeBuoy, ShieldCheck, Users as UsersIcon, Ticket as TicketIcon, History, Megaphone, Activity, TrendingUp, Calendar, Webhook, Settings as SettingsIcon, User as UserIcon, Map as MapIcon, Bot, Brain, CheckSquare, Users2, Command, KeyRound, Ear } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import ImpersonateBanner from './ImpersonateBanner';
import BroadcastBanner from './BroadcastBanner';
import HitlInboxBell from './HitlInboxBell';

const items = [
  { to: '/dashboard/command-center', label: 'Command Center', icon: Command },
  { to: '/dashboard/standups', label: 'Monday Standup', icon: Sparkles },
  { to: '/dashboard/growth-team', label: 'Growth Team', icon: Users2 },
  { to: '/dashboard/listening', label: 'Listening', icon: Ear },
  { to: '/dashboard/team', label: 'AI Team', icon: Users2 },
  { to: '/dashboard/agent', label: 'Agents', icon: Bot, exact: true },
  { to: '/dashboard/memory', label: 'Memory', icon: Brain },
  { to: '/dashboard/trends', label: 'Trends', icon: TrendingUp },
  { to: '/dashboard/approvals', label: 'Approvals', icon: CheckSquare },
  { to: '/dashboard/overview', label: 'Overview', icon: LayoutDashboard },
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
  { to: '/dashboard/settings/account', label: 'Account', icon: UserIcon },
];

const adminItems = [
  { to: '/admin', label: 'Admin Overview', icon: ShieldCheck, exact: true },
  { to: '/admin/users', label: 'Users', icon: UsersIcon },
  { to: '/admin/tickets', label: 'Support Inbox', icon: TicketIcon },
  { to: '/admin/broadcasts', label: 'Broadcasts', icon: Megaphone },
  { to: '/admin/audit-log', label: 'Audit Log', icon: History },
  { to: '/admin/webhook-events', label: 'Webhook Events', icon: Webhook },
  { to: '/admin/settings', label: 'System Settings', icon: SettingsIcon },
  { to: '/admin/integrations', label: 'Integrations', icon: KeyRound },
  { to: '/admin/roadmap', label: 'Roadmap', icon: MapIcon },
];

const DashboardLayout = ({ children, title, subtitle, headerExtra }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="cv-dash-scope min-h-screen text-zinc-200 relative overflow-x-hidden" style={{ background: '#09090B' }}>
      {/* Ambient backdrop */}
      <div className="fixed inset-0 pointer-events-none z-0" aria-hidden>
        <div className="absolute inset-0 cv-grid-bg opacity-60" />
        <div className="cv-aurora cv-aurora-violet" style={{ top: '-25%', left: '-20%', width: '50rem', height: '50rem' }} />
        <div className="cv-aurora cv-aurora-cyan" style={{ bottom: '-30%', right: '-25%', width: '45rem', height: '45rem' }} />
      </div>

      <div className="relative z-10">
        <ImpersonateBanner />
        <div className="flex">
          {/* Sidebar */}
          <aside className="w-64 shrink-0 min-h-screen sticky top-0 pb-24 border-r border-white/5"
            style={{ background: 'rgba(9, 9, 14, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}>
            <div className="p-5 border-b border-white/5">
              <button onClick={() => navigate('/')} className="flex items-center gap-2.5 group" data-testid="dash-sidebar-logo">
                <span className="relative inline-block w-9 h-9">
                  <span className="absolute inset-0 rounded-lg cv-pulse" style={{
                    background: 'radial-gradient(circle, rgba(124,58,237,.45), rgba(6,182,212,.2) 60%, transparent 75%)',
                    filter: 'blur(8px)',
                  }} />
                  <img src="/cortex-logo.png" alt="CortexViral" className="relative w-9 h-9 object-contain" />
                </span>
                <span className="cv-display font-semibold text-[15px] text-white">
                  Cortex<span className="cv-gradient-text">Viral</span>
                </span>
                {user?.is_admin && (
                  <span className="ml-1 text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 border border-violet-500/30">admin</span>
                )}
              </button>
            </div>

            <nav className="p-3 flex flex-col gap-1">
              {items.map((it) => (
                <NavLink
                  key={it.to}
                  to={it.to}
                  end={it.exact}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-medium transition-all ${
                      isActive
                        ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-lg'
                        : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                    }`
                  }
                >
                  <it.icon size={17} />
                  {it.label}
                </NavLink>
              ))}

              {user?.is_admin && (
                <>
                  <div className="mt-4 mb-1 px-3 text-[10.5px] uppercase tracking-[0.2em] text-zinc-500 font-semibold">Admin</div>
                  {adminItems.map((it) => (
                    <NavLink
                      key={it.to}
                      to={it.to}
                      end={it.exact}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-medium transition-all ${
                          isActive
                            ? 'bg-violet-600 text-white shadow-lg'
                            : 'text-zinc-400 hover:bg-violet-500/10 hover:text-violet-300'
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
            <div className="absolute bottom-0 left-0 right-0 w-64 p-4 border-t border-white/5"
              style={{ background: 'rgba(9, 9, 14, 0.9)' }}>
              <div className="flex items-center gap-3">
                {user?.picture ? (
                  <img src={user.picture} alt={user?.name} className="w-9 h-9 rounded-full ring-2 ring-violet-500/30 shadow-sm" />
                ) : (
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 text-white flex items-center justify-center text-sm font-semibold">
                    {user?.name?.[0] || 'U'}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold truncate text-white">{user?.name || 'Account'}</div>
                  <div className="text-[11px] text-zinc-500 truncate">{user?.email}</div>
                </div>
                <button onClick={logout} className="p-1.5 rounded-lg hover:bg-white/5 text-zinc-400 hover:text-white transition-colors" title="Sign out" data-testid="dash-sidebar-logout">
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
                <div className="mb-8 flex items-center gap-2 text-[12px] text-zinc-500">
                  <span>Dashboard</span>
                  <ChevronRight size={12} />
                  <span className="text-zinc-300">{title}</span>
                </div>
              )}
              {title && (
                <div className="mb-8 flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <h1 className="cv-display text-3xl font-semibold tracking-tight text-white">{title}</h1>
                    {subtitle && <p className="text-zinc-400 mt-1">{subtitle}</p>}
                  </div>
                  {headerExtra && <div className="shrink-0">{headerExtra}</div>}
                </div>
              )}
              {children}
            </div>
          </main>
        </div>
      </div>
      <HitlInboxBell />
    </div>
  );
};

export default DashboardLayout;
