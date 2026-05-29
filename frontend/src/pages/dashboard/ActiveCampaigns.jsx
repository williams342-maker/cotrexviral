import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Rocket, Calendar as CalendarIcon, ArrowRight, Target,
  CheckCircle2, Archive, FileEdit, Sparkles,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Active Campaigns — one tile per running campaign.
   - Tabs: Active (default) | Draft | Completed | All
   - Each tile: name + goal + platforms + KPI badges + "Open →" CTA
   - Empty state nudges the operator into Briefs Inbox (where proposals turn into campaigns) */

const TABS = [
  { id: 'active',    label: 'Active',    icon: Rocket,       testid: 'tab-active'    },
  { id: 'draft',     label: 'Draft',     icon: FileEdit,     testid: 'tab-draft'     },
  { id: 'completed', label: 'Completed', icon: CheckCircle2, testid: 'tab-completed' },
  { id: 'all',       label: 'All',       icon: Archive,      testid: 'tab-all'       },
];

const STATUS_TONE = {
  draft:     'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  active:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  completed: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  archived:  'bg-zinc-700/30 text-zinc-500 border-zinc-700/40',
};

const PLATFORM_DOT = {
  instagram: 'bg-pink-500',
  facebook:  'bg-blue-500',
  linkedin:  'bg-sky-500',
  tiktok:    'bg-rose-500',
  x:         'bg-zinc-300',
  youtube:   'bg-red-500',
  pinterest: 'bg-red-600',
  threads:   'bg-purple-500',
};

const ActiveCampaigns = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState('active');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/campaigns`, { withCredentials: true });
      setRows(r.data.campaigns || []);
    } catch (e) {
      toast({
        title: 'Failed to load campaigns',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (tab === 'all') return rows;
    return rows.filter((c) => (c.status || 'draft') === tab);
  }, [tab, rows]);

  const counts = useMemo(() => {
    const c = { active: 0, draft: 0, completed: 0, archived: 0, all: rows.length };
    for (const r of rows) c[r.status || 'draft'] = (c[r.status || 'draft'] || 0) + 1;
    return c;
  }, [rows]);

  return (
    <DashboardLayout
      title="Campaigns"
      subtitle="Every running, drafted, or completed campaign — in one place."
      headerExtra={
        <button
          onClick={() => navigate('/dashboard/briefs')}
          className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 shadow-md"
          data-testid="active-campaigns-new"
        >
          <Sparkles size={13} /> New from brief
        </button>
      }
    >
      <div className="space-y-6" data-testid="active-campaigns-page">
        {/* Tabs */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white/[0.03] border border-white/5 w-fit">
          {TABS.map((t) => {
            const isActive = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                data-testid={t.testid}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-[12.5px] font-semibold transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow'
                    : 'text-zinc-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <t.icon size={13} />
                {t.label}
                <span className={`text-[10px] tabular-nums px-1.5 py-0.5 rounded-full ${
                  isActive ? 'bg-white/20' : 'bg-white/5 text-zinc-500'
                }`}>
                  {counts[t.id] ?? 0}
                </span>
              </button>
            );
          })}
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-zinc-500 text-[13px]">
            <Loader2 className="animate-spin" size={14} /> Loading campaigns…
          </div>
        )}

        {/* Empty state */}
        {!loading && filtered.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-12 text-center" data-testid="active-campaigns-empty">
            <Rocket className="mx-auto mb-3 text-zinc-600" size={28} />
            <div className="text-[15px] font-semibold text-white mb-1">
              {tab === 'active' ? 'No active campaigns yet' : tab === 'all' ? 'No campaigns yet' : `No ${tab} campaigns`}
            </div>
            <div className="text-[13px] text-zinc-500 max-w-md mx-auto mb-5">
              Campaigns are spawned when you approve a brief from Atlas. Head to <strong className="text-zinc-300">Briefs Inbox</strong> to see what's waiting.
            </div>
            <button
              onClick={() => navigate('/dashboard/briefs')}
              className="text-[12px] font-semibold px-4 py-2 rounded-lg bg-white/10 text-white hover:bg-white/15 transition inline-flex items-center gap-1.5"
              data-testid="active-campaigns-go-briefs"
            >
              Open Briefs Inbox <ArrowRight size={13} />
            </button>
          </div>
        )}

        {/* Campaign grid */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((c) => (
              <CampaignTile key={c.id} campaign={c} navigate={navigate} />
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const CampaignTile = ({ campaign, navigate }) => {
  const status = campaign.status || 'draft';
  const platforms = (campaign.platforms || []).slice(0, 6);
  const kpis = Object.entries(campaign.kpi_targets || {}).slice(0, 3);

  return (
    <button
      onClick={() => navigate(`/dashboard/campaigns/${campaign.id}`)}
      data-testid={`campaign-tile-${campaign.id}`}
      className="text-left rounded-2xl border border-white/5 bg-white/[0.03] p-5 hover:bg-white/[0.05] hover:border-white/10 transition-all group"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="text-[14.5px] font-semibold text-white truncate group-hover:text-violet-300 transition">
            {campaign.name}
          </div>
          {campaign.goal && (
            <div className="flex items-center gap-1.5 mt-1 text-[11.5px] text-zinc-500">
              <Target size={11} />
              <span className="capitalize">{campaign.custom_goal || campaign.goal}</span>
            </div>
          )}
        </div>
        <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${STATUS_TONE[status] || STATUS_TONE.draft}`}>
          {status}
        </span>
      </div>

      {/* KPI chips */}
      {kpis.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {kpis.map(([k, v]) => (
            <span key={k} className="text-[10.5px] tabular-nums px-2 py-1 rounded-md bg-white/5 border border-white/5 text-zinc-300">
              {k}: <strong className="text-white">{v || 0}</strong>
            </span>
          ))}
        </div>
      )}

      {/* Platforms + date footer */}
      <div className="flex items-center justify-between pt-3 border-t border-white/5">
        <div className="flex items-center gap-1.5">
          {platforms.length > 0 ? (
            platforms.map((p) => (
              <span
                key={p}
                title={p}
                className={`w-2 h-2 rounded-full ${PLATFORM_DOT[p] || 'bg-zinc-500'}`}
              />
            ))
          ) : (
            <span className="text-[10.5px] text-zinc-600">no platforms</span>
          )}
        </div>
        <div className="flex items-center gap-1 text-[10.5px] text-zinc-500">
          <CalendarIcon size={10} />
          {campaign.created_at ? new Date(campaign.created_at).toLocaleDateString() : '—'}
        </div>
      </div>
    </button>
  );
};

export default ActiveCampaigns;
