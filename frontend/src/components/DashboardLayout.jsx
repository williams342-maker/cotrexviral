import React, { useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Rocket, Bot, BarChart3, Settings as SettingsIcon,
  Calendar, CheckSquare, Brain, TrendingUp, Inbox,
  KeyRound, User as UserIcon, LogOut, ChevronRight, ChevronDown,
  Command as CommandIcon, Compass, Sparkles, Send,
  ShoppingBag, Search, MessageSquare, ShieldCheck, FileText,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import ImpersonateBanner from './ImpersonateBanner';
import BroadcastBanner from './BroadcastBanner';
import HitlInboxBell from './HitlInboxBell';
import CommandPalette from './CommandPalette';

/* The mission-driven sidebar — 10 top-level destinations matching the
   Autonomous Marketing OS spec.

     🏠 Command Center      (the home / mission dashboard)
     🚀 Campaigns           → Active / Calendar / Approvals
     🧠 Cortex              (master orchestrator workspace)
     🔭 Scout team
     ✍️ Creator team
     📡 Operator team
     📊 Intelligence team
     🗂️ Memory
     📈 Analytics           → Performance / Leads
     ⚙️ Settings            → Integrations / Account

   Everything else lives in the Ctrl+K palette.
*/
const SECTIONS = [
  { id: 'home',     label: 'Command Center', icon: Brain, to: '/dashboard' },
  { id: 'missions', label: 'Mission Control', icon: LayoutDashboard, to: '/dashboard/missions' },
  {
    id: 'campaigns', label: 'Campaigns', icon: Rocket,
    children: [
      { to: '/dashboard/campaigns/active', label: 'Active',    icon: Rocket    },
      { to: '/dashboard/calendar',         label: 'Calendar',  icon: Calendar  },
      { to: '/dashboard/approvals',        label: 'Approvals', icon: CheckSquare },
    ],
  },
  { id: 'cortex',       label: 'Cortex Brief', icon: Brain,    to: '/dashboard/cortex' },
  { id: 'assets',       label: 'Assets',       icon: FileText, to: '/dashboard/assets' },
  { id: 'scout',        label: 'Scout',        icon: Compass,  to: '/dashboard/teams/scout' },
  { id: 'creator',      label: 'Creator',      icon: Sparkles, to: '/dashboard/teams/creator' },
  { id: 'operator',     label: 'Operator',     icon: Send,     to: '/dashboard/teams/operator' },
  { id: 'intelligence', label: 'Intelligence', icon: TrendingUp, to: '/dashboard/teams/intelligence' },
  {
    id: 'seller_os', label: 'Seller OS', icon: ShoppingBag,
    children: [
      { to: '/dashboard/seller-os',                label: 'Mission Control',   icon: LayoutDashboard },
      { to: '/dashboard/seller-os/discovery',      label: 'Discovery',         icon: Search          },
      { to: '/dashboard/seller-os/qualified',      label: 'Qualified',         icon: Sparkles        },
      { to: '/dashboard/seller-os/conversations',  label: 'Conversations',     icon: MessageSquare   },
      { to: '/dashboard/seller-os/onboarding',     label: 'Onboarding',        icon: TrendingUp      },
      { to: '/dashboard/seller-os/retention',      label: 'Retention',         icon: ShieldCheck     },
      { to: '/dashboard/seller-os/analytics',      label: 'Analytics',         icon: BarChart3       },
    ],
  },
  { id: 'memory',       label: 'Memory',       icon: Bot,      to: '/dashboard/memory' },
  {
    id: 'analytics', label: 'Analytics', icon: BarChart3,
    children: [
      { to: '/dashboard/performance', label: 'Performance', icon: BarChart3 },
      { to: '/dashboard/leads',       label: 'Leads',       icon: Inbox     },
    ],
  },
  {
    id: 'settings', label: 'Settings', icon: SettingsIcon,
    children: [
      { to: '/dashboard/channels',         label: 'Integrations', icon: KeyRound },
      { to: '/dashboard/settings/account', label: 'Account',      icon: UserIcon },
    ],
  },
];

// Detect Mac for the Ctrl+K hint label.
const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform || '');

const DashboardLayout = ({ children, title, subtitle, headerExtra }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Section open state — section auto-opens when its child is active so
  // a deep-link refresh doesn't hide the user's current location.
  const initial = {};
  for (const s of SECTIONS) {
    if (!s.children) continue;
    initial[s.id] = s.children.some((c) => location.pathname.startsWith(c.to));
  }
  const [openSections, setOpenSections] = useState(initial);

  const toggle = (id) => setOpenSections((s) => ({ ...s, [id]: !s[id] }));

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
          <aside
            className="w-64 shrink-0 min-h-screen sticky top-0 pb-24 border-r border-white/5 flex flex-col"
            style={{ background: 'rgba(9, 9, 14, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}
            data-testid="dash-sidebar"
          >
            {/* Logo */}
            <div className="p-5 border-b border-white/5">
              <button
                onClick={() => navigate('/')}
                className="flex items-center gap-2.5 group"
                data-testid="dash-sidebar-logo"
              >
                <span className="relative inline-block w-9 h-9">
                  <span
                    className="absolute inset-0 rounded-lg cv-pulse"
                    style={{
                      background: 'radial-gradient(circle, rgba(124,58,237,.45), rgba(6,182,212,.2) 60%, transparent 75%)',
                      filter: 'blur(8px)',
                    }}
                  />
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

            {/* Ctrl+K hint button */}
            <button
              onClick={() => {
                // Synthesize a real Ctrl+K keydown so the global listener catches it.
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: !isMac, metaKey: isMac }));
              }}
              data-testid="dash-sidebar-cmdk-trigger"
              className="mx-3 mt-3 flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-white/5 bg-white/[0.03] hover:bg-white/[0.06] text-zinc-400 hover:text-white transition group"
            >
              <span className="flex items-center gap-2 text-[12.5px]">
                <CommandIcon size={13} />
                <span className="font-medium">Quick find</span>
              </span>
              <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-zinc-400 group-hover:text-zinc-200">
                {isMac ? '⌘K' : 'Ctrl K'}
              </kbd>
            </button>

            {/* Sections */}
            <nav className="flex-1 p-3 pt-4 flex flex-col gap-0.5 overflow-y-auto">
              {SECTIONS.map((section) => {
                // Top-level no-child entry (Dashboard).
                if (!section.children) {
                  return (
                    <NavLink
                      key={section.id}
                      to={section.to}
                      end
                      data-testid={`nav-${section.id}`}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[14px] font-semibold transition-all ${
                          isActive
                            ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-lg'
                            : 'text-zinc-300 hover:bg-white/5 hover:text-white'
                        }`
                      }
                    >
                      <section.icon size={17} />
                      {section.label}
                    </NavLink>
                  );
                }

                const isOpen = !!openSections[section.id];
                const hasActiveChild = section.children.some((c) => location.pathname.startsWith(c.to));

                return (
                  <div key={section.id} className="flex flex-col">
                    <button
                      onClick={() => toggle(section.id)}
                      data-testid={`nav-section-${section.id}`}
                      className={`w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl text-[14px] font-semibold transition-all ${
                        hasActiveChild
                          ? 'text-white bg-white/[0.04]'
                          : 'text-zinc-300 hover:bg-white/5 hover:text-white'
                      }`}
                    >
                      <span className="flex items-center gap-3">
                        <section.icon size={17} />
                        {section.label}
                      </span>
                      {isOpen ? (
                        <ChevronDown size={14} className="text-zinc-500" />
                      ) : (
                        <ChevronRight size={14} className="text-zinc-500" />
                      )}
                    </button>

                    {/* Children */}
                    {isOpen && (
                      <div className="ml-3 pl-3 mt-0.5 flex flex-col gap-0.5 border-l border-white/5">
                        {section.children.map((child) => (
                          <NavLink
                            key={child.to}
                            to={child.to}
                            end
                            data-testid={`nav-${section.id}-${child.label.toLowerCase()}`}
                            className={({ isActive }) =>
                              `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition-all ${
                                isActive
                                  ? 'bg-gradient-to-r from-violet-600/80 to-blue-600/80 text-white shadow'
                                  : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                              }`
                            }
                          >
                            <child.icon size={13} />
                            {child.label}
                          </NavLink>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </nav>

            {/* User block */}
            <div
              className="w-64 p-4 border-t border-white/5"
              style={{ background: 'rgba(9, 9, 14, 0.9)' }}
            >
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
                <button
                  onClick={logout}
                  className="p-1.5 rounded-lg hover:bg-white/5 text-zinc-400 hover:text-white transition-colors"
                  title="Sign out"
                  data-testid="dash-sidebar-logout"
                >
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
      <CommandPalette />
    </div>
  );
};

export default DashboardLayout;
