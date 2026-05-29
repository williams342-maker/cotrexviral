import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Shield, Sliders, Play, Pause, ArrowRight, Zap,
  Compass, Wand2, Send, TrendingUp,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Autonomy Control Center — global view + per-mission slider.

   Each row: mission title + status + current autonomy + per-team override hints.
   User can bump the level inline. Changes call PATCH /missions/:id.
*/

const LEVELS = [
  { v: 0, label: 'Manual',           desc: 'Approval required for every step.' },
  { v: 1, label: 'Auto-create',      desc: 'Creator drafts automatically. Operator stays manual.' },
  { v: 2, label: 'Auto-publish',     desc: 'Pre-approved channels publish automatically.' },
  { v: 3, label: 'Auto-optimize',    desc: 'Intelligence swaps creative & budget within caps.' },
  { v: 4, label: 'Goal-seeking',     desc: 'Cortex can extend timelines & shift budget.' },
  { v: 5, label: 'Full autonomous',  desc: 'All teams unlocked within mission budget caps.' },
];

const TEAM_ICONS = { scout: Compass, creator: Wand2, operator: Send, intelligence: TrendingUp };
const TEAM_MIN = { scout: 1, creator: 1, operator: 2, intelligence: 3 };

const Autonomy = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [missions, setMissions] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/missions`, { withCredentials: true });
      setMissions((r.data.missions || []).filter((m) => m.status !== 'abandoned'));
    } catch (e) {
      toast({ title: 'Failed to load missions',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const updateLevel = async (mid, lvl) => {
    try {
      await axios.patch(`${API}/missions/${mid}`, { autonomy_level: lvl }, { withCredentials: true });
      load();
      toast({ title: `Autonomy → L${lvl}` });
    } catch (e) {
      toast({ title: 'Update failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  return (
    <DashboardLayout
      title="Autonomy Control Center"
      subtitle="Decide how much rope Cortex gives each team — per mission, in real time."
    >
      <div className="space-y-6" data-testid="autonomy-control-page">
        {/* Legend */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
          <div className="flex items-center gap-2 mb-3">
            <Shield size={14} className="text-violet-300" />
            <div className="text-[12px] uppercase tracking-wider font-semibold text-violet-300">Autonomy ladder</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {LEVELS.map((l) => (
              <div key={l.v} className="rounded-lg border border-white/5 bg-white/[0.03] p-3"
                   data-testid={`autonomy-legend-${l.v}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 border border-violet-500/30 tabular-nums">L{l.v}</span>
                  <div className="text-[13px] font-semibold text-white">{l.label}</div>
                </div>
                <div className="text-[11.5px] text-zinc-400">{l.desc}</div>
              </div>
            ))}
          </div>

          {/* Team thresholds reference */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Auto-process thresholds</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(TEAM_MIN).map(([t, min]) => {
                const Icon = TEAM_ICONS[t];
                return (
                  <div key={t} className="rounded-md bg-white/5 px-2.5 py-1.5 flex items-center gap-1.5 text-[11.5px]">
                    <Icon size={11} className="text-zinc-400" />
                    <span className="capitalize text-zinc-300">{t}</span>
                    <span className="text-zinc-500">requires ≥ <strong className="text-white">L{min}</strong></span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Missions */}
        {loading && (
          <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
        )}

        {!loading && missions.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-12 text-center" data-testid="autonomy-empty">
            <Sliders className="mx-auto text-zinc-600 mb-3" size={26} />
            <div className="text-[14px] font-semibold text-white mb-1">No missions to govern yet.</div>
            <div className="text-[12.5px] text-zinc-500 mb-4">Start a mission to set its autonomy level.</div>
            <button onClick={() => navigate('/dashboard/missions')}
                    data-testid="autonomy-empty-cta"
                    className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 transition inline-flex items-center gap-1.5">
              Go to Mission Dashboard <ArrowRight size={12} />
            </button>
          </div>
        )}

        {!loading && missions.length > 0 && (
          <div className="space-y-3">
            {missions.map((m) => (
              <MissionAutonomyRow key={m.id} mission={m} onChange={updateLevel} onOpen={(mid) => navigate(`/dashboard/cortex/${mid}`)} />
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const MissionAutonomyRow = ({ mission, onChange, onOpen }) => {
  const lvl = mission.autonomy_level ?? 1;
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.03] hover:bg-white/[0.05] transition p-5"
         data-testid={`autonomy-row-${mission.id}`}>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex-1 min-w-0">
          <div className="text-[14.5px] font-semibold text-white truncate">{mission.title}</div>
          <div className="text-[11.5px] text-zinc-500 mt-1 flex items-center gap-1.5">
            {mission.status === 'running' ? (
              <><Play size={10} className="text-emerald-300" /> running</>
            ) : (
              <><Pause size={10} className="text-amber-300" /> {mission.status}</>
            )}
            {mission.target && (
              <span className="ml-2"><Zap size={9} className="inline mb-0.5" /> {mission.progress?.confidence ?? 0}% confidence · {mission.progress?.current ?? 0}/{mission.target}</span>
            )}
          </div>
        </div>
        <button onClick={() => onOpen(mission.id)}
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-white flex items-center gap-1">
          Open <ArrowRight size={11} />
        </button>
      </div>

      {/* Level segmented control */}
      <div className="flex items-center gap-1 p-1 rounded-xl bg-white/[0.03] border border-white/5">
        {LEVELS.map((l) => {
          const isActive = lvl === l.v;
          return (
            <button
              key={l.v}
              onClick={() => onChange(mission.id, l.v)}
              data-testid={`autonomy-set-${mission.id}-${l.v}`}
              className={`flex-1 text-center px-2 py-1.5 rounded-lg text-[11.5px] font-semibold transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow'
                  : 'text-zinc-400 hover:text-white hover:bg-white/5'
              }`}
              title={l.desc}
            >
              L{l.v}
              <span className="block text-[9.5px] font-medium opacity-80 -mt-0.5">{l.label}</span>
            </button>
          );
        })}
      </div>

      {/* Per-team status hints */}
      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
        {Object.entries(TEAM_MIN).map(([t, min]) => {
          const Icon = TEAM_ICONS[t];
          const ok = lvl >= min;
          return (
            <div key={t} className={`rounded-md px-2.5 py-2 flex items-center gap-1.5 text-[11px] border ${
              ok ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                 : 'bg-zinc-500/5 border-white/5 text-zinc-500'
            }`}
            data-testid={`autonomy-team-${mission.id}-${t}`}>
              <Icon size={10} />
              <span className="capitalize">{t}</span>
              <span className="ml-auto font-semibold">{ok ? 'auto' : 'manual'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Autonomy;
