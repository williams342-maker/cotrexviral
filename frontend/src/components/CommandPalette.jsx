import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Command as CommandIcon, Compass, Target, FlaskConical, ShieldAlert,
  MessagesSquare, Users2, Ear, Sparkles, Wand2, Search, Radar, Send,
  LayoutDashboard, Activity, LifeBuoy, ShieldCheck, Users as UsersIcon,
  Ticket as TicketIcon, History, Megaphone, Webhook, Settings as SettingsIcon,
  KeyRound, Map as MapIcon, Bot, Calendar, FileText, Inbox,
  Rocket, Brain, TrendingUp, CheckSquare, User as UserIcon, BarChart3,
  ShoppingBag, MessageSquare,
} from 'lucide-react';
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem, CommandSeparator,
} from './ui/command';
import { useAuth } from '../context/AuthContext';

/* Ctrl+K Command Palette.
   Keyboard nav: Ctrl/Cmd+K opens. ESC closes. Arrow keys + Enter to navigate.
   Pages NOT in the new compact sidebar are reachable from here. */

const CommandPalette = () => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  // Global Ctrl+K / Cmd+K listener.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const go = (to) => {
    setOpen(false);
    // Defer so the dialog has time to close before route change paints.
    setTimeout(() => navigate(to), 50);
  };

  const groups = useMemo(() => {
    const dashboard = [
      { to: '/dashboard/missions',         label: 'Mission Dashboard',    icon: LayoutDashboard, hint: 'Home' },
      { to: '/dashboard/command-center',   label: 'Command Center',       icon: CommandIcon },
      { to: '/dashboard/team-performance', label: 'Team Performance',     icon: TrendingUp },
      { to: '/dashboard/overview',         label: 'Overview',             icon: LayoutDashboard },
      { to: '/dashboard/main',             label: 'Activity feed',        icon: Activity },
    ];
    const cortexGroup = [
      { to: '/dashboard/cortex',           label: 'Cortex workspace',     icon: Brain,    hint: 'Master orchestrator' },
      { to: '/dashboard/autonomy-control', label: 'Autonomy Control Center', icon: ShieldAlert, hint: 'L0–L5 per team' },
      { to: '/dashboard/teams/scout',        label: 'Scout team',         icon: Compass },
      { to: '/dashboard/teams/creator',      label: 'Creator team',       icon: Sparkles },
      { to: '/dashboard/teams/operator',     label: 'Operator team',      icon: Send },
      { to: '/dashboard/teams/intelligence', label: 'Intelligence team',  icon: TrendingUp },
    ];
    const sellerOS = [
      { to: '/dashboard/seller-os',               label: 'Seller OS · Mission Control', icon: LayoutDashboard },
      { to: '/dashboard/seller-os/discovery',     label: 'Seller OS · Discovery',       icon: Search },
      { to: '/dashboard/seller-os/qualified',     label: 'Seller OS · Qualified',       icon: Sparkles },
      { to: '/dashboard/seller-os/conversations', label: 'Seller OS · Conversations',   icon: MessageSquare, hint: 'Phase 2' },
      { to: '/dashboard/seller-os/onboarding',    label: 'Seller OS · Onboarding',      icon: TrendingUp,    hint: 'Phase 3' },
      { to: '/dashboard/seller-os/retention',     label: 'Seller OS · Retention',       icon: ShieldCheck,   hint: 'Phase 3' },
      { to: '/dashboard/seller-os/analytics',     label: 'Seller OS · Analytics',       icon: BarChart3,     hint: 'Phase 3' },
    ];
    const campaigns = [
      { to: '/dashboard/campaigns/active', label: 'Active Campaigns',     icon: Rocket },
      { to: '/dashboard/calendar',         label: 'Marketing Calendar',   icon: Calendar },
      { to: '/dashboard/approvals',        label: 'Approvals queue',      icon: CheckSquare },
      { to: '/dashboard/briefs',           label: 'Briefs Inbox',         icon: Compass,    hint: 'Atlas proposals' },
      { to: '/dashboard/standups',         label: 'Monday Standup',       icon: Sparkles },
      { to: '/dashboard/experiments',      label: 'Experiments',          icon: FlaskConical },
      { to: '/dashboard/goals',            label: 'Growth Goals',         icon: Target },
    ];
    const agents = [
      { to: '/dashboard/team',             label: 'AI Team',              icon: Users2 },
      { to: '/dashboard/memory',           label: 'Agent Memory',         icon: Brain },
      { to: '/dashboard/trends',           label: 'Trend Engine',         icon: TrendingUp },
      { to: '/dashboard/growth-team',      label: 'Growth Team roster',   icon: Users2 },
      { to: '/dashboard/chatter',          label: 'Agent Chatter',        icon: MessagesSquare },
      { to: '/dashboard/autonomy',         label: 'Autonomy budgets',     icon: ShieldAlert },
      { to: '/dashboard/listening',        label: 'Social Listening',     icon: Ear },
      { to: '/dashboard/agent',            label: 'Agent Workspace',      icon: Bot },
    ];
    const content = [
      { to: '/dashboard/studio',           label: 'Content Studio',       icon: Wand2 },
      { to: '/dashboard/posts',            label: 'Posts',                icon: FileText },
      { to: '/dashboard/compose',          label: 'Compose & Publish',    icon: Send },
      { to: '/dashboard/insights',         label: 'AI Insights',          icon: Sparkles },
      { to: '/dashboard/seo',              label: 'SEO Review',           icon: Search },
      { to: '/dashboard/scan',             label: 'Site Scan',            icon: Radar },
    ];
    const analytics = [
      { to: '/dashboard/performance',      label: 'Performance',          icon: BarChart3 },
      { to: '/dashboard/leads',            label: 'Leads',                icon: Inbox },
      { to: '/dashboard/team-performance', label: 'Team Performance',     icon: TrendingUp },
    ];
    const settings = [
      { to: '/dashboard/channels',         label: 'Integrations',         icon: KeyRound },
      { to: '/dashboard/settings/account', label: 'Account',              icon: UserIcon },
      { to: '/dashboard/help',             label: 'Help & Support',       icon: LifeBuoy },
    ];
    const admin = user?.is_admin ? [
      { to: '/admin',                      label: 'Admin Overview',       icon: ShieldCheck },
      { to: '/admin/users',                label: 'Users',                icon: UsersIcon },
      { to: '/admin/tickets',              label: 'Support Inbox',        icon: TicketIcon },
      { to: '/admin/broadcasts',           label: 'Broadcasts',           icon: Megaphone },
      { to: '/admin/audit-log',            label: 'Audit Log',            icon: History },
      { to: '/admin/webhook-events',       label: 'Webhook Events',       icon: Webhook },
      { to: '/admin/settings',             label: 'System Settings',      icon: SettingsIcon },
      { to: '/admin/integrations',         label: 'Admin Integrations',   icon: KeyRound },
      { to: '/admin/roadmap',              label: 'Roadmap',              icon: MapIcon },
    ] : [];

    return { dashboard, cortexGroup, sellerOS, campaigns, agents, content, analytics, settings, admin };
  }, [user?.is_admin]);

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Type a command or search…" data-testid="command-palette-input" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

        <CommandGroup heading="Dashboard">
          {groups.dashboard.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Cortex & Teams">
          {groups.cortexGroup.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Seller OS">
          {groups.sellerOS.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Campaigns">
          {groups.campaigns.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Agents">
          {groups.agents.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Content">
          {groups.content.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Analytics">
          {groups.analytics.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>
        <CommandSeparator />

        <CommandGroup heading="Settings">
          {groups.settings.map((it) => (
            <PaletteItem key={it.to} item={it} go={go} />
          ))}
        </CommandGroup>

        {groups.admin.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Admin">
              {groups.admin.map((it) => (
                <PaletteItem key={it.to} item={it} go={go} />
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
};

const PaletteItem = ({ item, go }) => (
  <CommandItem
    value={`${item.label} ${item.hint || ''}`}
    onSelect={() => go(item.to)}
    data-testid={`cmd-${item.to.replace(/\//g, '-')}`}
    className="flex items-center gap-2.5 cursor-pointer"
  >
    <item.icon size={14} className="text-zinc-400" />
    <span className="text-[13px]">{item.label}</span>
    {item.hint && (
      <span className="ml-auto text-[11px] text-zinc-500">{item.hint}</span>
    )}
  </CommandItem>
);

export default CommandPalette;
