import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Compass, Wand2, Send, TrendingUp, ArrowLeft,
  Sparkles, Activity, Target, Brain,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* TeamDetail — one page that adapts to Scout / Creator / Operator / Intelligence.
   URL: /dashboard/teams/:teamId  */

const TEAM_ICONS = {
  scout: Compass, creator: Wand2, operator: Send, intelligence: TrendingUp,
};

const TeamDetail = () => {
  const { teamId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/teams/${teamId}`, { withCredentials: true });
      setTeam(r.data);
    } catch (e) {
      toast({ title: 'Could not load team',
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [teamId]);

  if (loading || !team) {
    return (
      <DashboardLayout title="Team" subtitle="Loading team detail…">
        <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
      </DashboardLayout>
    );
  }

  const Icon = TEAM_ICONS[team.id] || Sparkles;
  const tone = team.color || '#a78bfa';

  return (
    <DashboardLayout
      title={team.name}
      subtitle={team.tagline}
      headerExtra={
        <button
          onClick={() => navigate('/dashboard/missions')}
          className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-300 hover:text-white transition flex items-center gap-1.5"
        >
          <ArrowLeft size={13} /> Missions
        </button>
      }
    >
      <div className="space-y-6" data-testid={`team-detail-${team.id}`}>
        {/* Hero */}
        <div className="rounded-2xl border border-white/5 p-5 flex items-center gap-4"
             style={{ background: `linear-gradient(135deg, ${tone}22, transparent 60%)` }}>
          <div className="w-12 h-12 rounded-xl flex items-center justify-center"
               style={{ background: `${tone}33`, color: tone, border: `1px solid ${tone}55` }}>
            <Icon size={20} />
          </div>
          <div className="flex-1">
            <div className="text-[11px] uppercase tracking-wider font-semibold mb-1" style={{ color: tone }}>
              Team · {team.personas?.length || 0} {team.personas?.length === 1 ? 'persona' : 'personas'}
            </div>
            <div className="text-xl font-semibold text-white cv-display">{team.name}</div>
            <div className="text-[13px] text-zinc-400 mt-1">{team.tagline}</div>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(team.kpis || {}).map(([k, v]) => (
            <div key={k} className="rounded-xl border border-white/5 bg-white/[0.03] p-4" data-testid={`team-kpi-${k}`}>
              <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                {k.replace(/_/g, ' ')}
              </div>
              <div className="text-2xl font-semibold tabular-nums text-white">{v}</div>
            </div>
          ))}
        </div>

        {/* Personas */}
        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Members</div>
          <div className="flex flex-wrap gap-2">
            {(team.personas || []).map((p) => (
              <div key={p.id} className="rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2 flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-md flex items-center justify-center text-white font-semibold text-[11px]"
                     style={{ background: p.color || '#7c3aed' }}>
                  {p.name?.[0]}
                </div>
                <div>
                  <div className="text-[12.5px] font-semibold text-white">{p.name}</div>
                  <div className="text-[10.5px] text-zinc-500">{p.role}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Responsibilities + Outputs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2 flex items-center gap-1.5">
              <Target size={11} /> Responsibilities
            </div>
            <ul className="space-y-1 text-[13px] text-zinc-300">
              {(team.responsibilities || []).map((r) => (
                <li key={r} className="flex items-start gap-2">
                  <span className="text-zinc-600">·</span>{r}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2 flex items-center gap-1.5">
              <Brain size={11} /> Outputs
            </div>
            <ul className="space-y-1 text-[13px] text-zinc-300">
              {(team.outputs || []).map((o) => (
                <li key={o} className="flex items-start gap-2">
                  <span className="text-zinc-600">·</span>
                  <span className="capitalize">{o.replace(/_/g, ' ')}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Recent activity */}
        <div>
          <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2 flex items-center gap-1.5">
            <Activity size={11} /> Recent activity
          </div>
          {(team.recent_activity || []).length === 0 ? (
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-6 text-center text-[13px] text-zinc-600">
              No activity yet — once Cortex dispatches work to this team, it will show up here.
            </div>
          ) : (
            <div className="rounded-xl border border-white/5 bg-white/[0.02] divide-y divide-white/5">
              {(team.recent_activity || []).slice(0, 12).map((a, i) => (
                <div key={i} className="p-3 flex items-center gap-3 text-[12.5px]">
                  <span className="text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded bg-white/5 text-zinc-400">
                    {a.__type}
                  </span>
                  <span className="flex-1 text-zinc-300 truncate">
                    {a.title || a.task || a.text || a.platform || a.id || '—'}
                  </span>
                  <span className="text-[10.5px] text-zinc-600">
                    {a.__when ? new Date(a.__when).toLocaleString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default TeamDetail;
