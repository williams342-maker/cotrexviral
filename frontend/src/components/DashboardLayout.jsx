import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Sparkles, Search, Radar, Share2, Send, Inbox, FileText, LogOut, ChevronRight, Wand2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const items = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard, exact: true },
  { to: '/dashboard/insights', label: 'AI Insights', icon: Sparkles },
  { to: '/dashboard/studio', label: 'Content Studio', icon: Wand2 },
  { to: '/dashboard/seo', label: 'SEO Review', icon: Search },
  { to: '/dashboard/scan', label: 'Site Scan', icon: Radar },
  { to: '/dashboard/channels', label: 'Channels', icon: Share2 },
  { to: '/dashboard/compose', label: 'Compose & Publish', icon: Send },
  { to: '/dashboard/posts', label: 'Posts', icon: FileText },
  { to: '/dashboard/leads', label: 'Leads', icon: Inbox },
];

const DashboardLayout = ({ children, title, subtitle }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F6F4ED] text-neutral-900">
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 shrink-0 border-r border-neutral-200/70 bg-white/60 backdrop-blur-sm min-h-screen sticky top-0">
          <div className="p-5 border-b border-neutral-200/70">
            <button onClick={() => navigate('/')} className="flex items-center gap-2 group">
              <div className="w-9 h-9 rounded-lg bg-[#0B2F66] text-white flex items-center justify-center font-bold text-sm">ax</div>
              <span className="font-semibold text-[15px]">Automatex</span>
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
