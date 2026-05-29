import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, ShoppingBag, Search, Sparkles, MessageSquare, Inbox,
  CheckCircle2, TrendingUp, Target, ArrowRight,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

/* Seller OS Mission Control — top-level view of every Seller-Acquisition
   mission with its 8 funnel KPIs. Click into a mission → drilldown. */

const STAGES = [
  { id: 'discovered', label: 'Discovered',   icon: Search,        tone: 'cyan'    },
  { id: 'qualified',  label: 'Qualified',    icon: Sparkles,      tone: 'violet'  },
  { id: 'outreached', label: 'Outreach Sent',icon: MessageSquare, tone: 'blue'    },
  { id: 'interested', label: 'Interested',   icon: Inbox,         tone: 'amber'   },
  { id: 'onboarding', label: 'Onboarding',   icon: TrendingUp,    tone: 'emerald' },
  { id: 'active',     label: 'Active',       icon: CheckCircle2,  tone: 'green'   },
];
const TONES = {
  cyan:    'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
  violet:  'bg-violet-500/10 text-violet-300 border-violet-500/20',
  blue:    'bg-blue-500/10 text-blue-300 border-blue-500/20',
  amber:   'bg-amber-500/10 text-amber-300 border-amber-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
  green:   'bg-green-500/15 text-green-300 border-green-500/30',
};

const SellerMissionControl = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [missions, setMissions] = useState([]);
  const [funnels, setFunnels]   = useState({});
  const [loading, setLoading]   = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/missions`, { withCredentials: true });
      const seller = (r.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
      setMissions(seller);
      const out = {};
      await Promise.all(seller.map(async (m) => {
        try {
          const f = await axios.get(`${API}/missions/${m.id}/seller-funnel`, { withCredentials: true });
          out[m.id] = f.data;
        } catch (e) { /* keep going */ }
      }));
      setFunnels(out);
    } catch (e) {
      toast({ title: 'Failed to load seller missions',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  return (
    <DashboardLayout
      title="Seller OS · Mission Control"
      subtitle="Every seller-acquisition mission's funnel — in one glance."
      headerExtra={
        <button
          onClick={() => navigate('/dashboard/missions')}
          className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 shadow-md"
          data-testid="seller-mc-new-mission"
        >
          <Sparkles size={13} /> New seller mission
        </button>
      }
    >
      <div className="space-y-6" data-testid="seller-mission-control">
        {loading && (
          <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
        )}

        {!loading && missions.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-12 text-center" data-testid="seller-mc-empty">
            <ShoppingBag className="mx-auto text-zinc-600 mb-3" size={28} />
            <div className="text-[15px] font-semibold text-white mb-1">No seller-acquisition missions yet.</div>
            <div className="text-[13px] text-zinc-500 max-w-md mx-auto mb-5">
              Tell Cortex what kind of sellers you want to recruit — e.g.
              "Recruit 100 woodworking makers" — and it will discover, qualify,
              and onboard them automatically.
            </div>
            <button
              onClick={() => navigate('/dashboard/missions')}
              data-testid="seller-mc-empty-cta"
              className="text-[13px] font-semibold px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition inline-flex items-center gap-2 shadow-lg shadow-violet-900/40"
            >
              <Sparkles size={14} /> Start your first seller mission <ArrowRight size={13} />
            </button>
          </div>
        )}

        {!loading && missions.length > 0 && (
          <div className="space-y-4">
            {missions.map((m) => (
              <MissionRow key={m.id} mission={m} funnel={funnels[m.id]} navigate={navigate} />
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const MissionRow = ({ mission, funnel, navigate }) => {
  const f = funnel || {};
  const counts = f.funnel || {};
  const total = counts.total || 0;
  const projected = f.projected_completion || {};

  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.03] hover:bg-white/[0.05] transition-all p-5"
         data-testid={`seller-mission-row-${mission.id}`}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex-1 min-w-0">
          <div className="text-[14.5px] font-semibold text-white">{mission.title}</div>
          <div className="text-[11.5px] text-zinc-500 mt-1 flex items-center gap-3">
            <span><Target size={10} className="inline mb-0.5" /> {mission.seller_target_niche || mission.metric || 'no niche'}</span>
            {mission.seller_target_location && <span>📍 {mission.seller_target_location}</span>}
            <span>{total} leads · avg score {f.score_summary?.average ?? '—'}</span>
          </div>
        </div>
        <button onClick={() => navigate(`/dashboard/seller-os/discovery?mission_id=${mission.id}`)}
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white flex items-center gap-1"
                data-testid={`seller-mission-discover-${mission.id}`}>
          Discover <ArrowRight size={11} />
        </button>
      </div>

      {/* 6 funnel KPI tiles */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        {STAGES.map((s) => {
          const v = counts[s.id] ?? 0;
          return (
            <div key={s.id} className={`rounded-lg border p-2.5 ${TONES[s.tone]}`}
                 data-testid={`seller-funnel-${mission.id}-${s.id}`}>
              <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider font-semibold opacity-80 mb-1">
                <s.icon size={9} /> {s.label}
              </div>
              <div className="text-xl font-semibold tabular-nums text-white">{v}</div>
            </div>
          );
        })}
      </div>

      {/* Projected completion + confidence */}
      <div className="mt-4 pt-4 border-t border-white/5 flex items-center gap-4 text-[11.5px]">
        <div>
          <span className="text-zinc-500">Projected:</span>{' '}
          <strong className="text-white tabular-nums">{projected.current ?? 0} / {projected.target ?? mission.target ?? 0}</strong>
        </div>
        {projected.progress_pct != null && (
          <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500"
                 style={{ width: `${projected.progress_pct}%` }} />
          </div>
        )}
        <div>
          <span className="text-zinc-500">Confidence:</span>{' '}
          <strong className="text-white tabular-nums">{mission.progress?.confidence ?? 0}%</strong>
        </div>
      </div>
    </div>
  );
};

export default SellerMissionControl;
