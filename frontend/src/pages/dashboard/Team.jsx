import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Target, Compass, Pencil, Microscope, Ear, Send, LineChart, ShieldAlert, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/* Team — the roster page. "Meet your autonomous growth team."
   Each card features the persona's name, role, voice, and the
   capability domains they own. Lazy-loads from /api/agents/personas. */
const ICONS = { Target, Compass, Pencil, Microscope, Ear, Send, LineChart, ShieldAlert };

const Team = () => {
  const [personas, setPersonas] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/agents/personas`, { withCredentials: true });
        setPersonas(r.data.personas || []);
      } finally { setLoading(false); }
    })();
  }, []);

  return (
    <DashboardLayout title="Your Growth Team" subtitle="Eight autonomous agents — each with a role, a voice, and an autonomy budget.">
      <div className="space-y-6" data-testid="team-page">
        {/* Manifesto block */}
        <div className="rounded-2xl border border-violet-200/60 bg-gradient-to-br from-violet-50 via-white to-fuchsia-50 p-6">
          <div className="text-[10px] uppercase tracking-widest text-violet-600 font-bold mb-2">Autonomous Growth Team</div>
          <h2 className="text-2xl font-bold text-neutral-900 mb-2">Eight specialists. One outcome.</h2>
          <p className="text-[14px] text-neutral-700 leading-relaxed max-w-3xl">
            Your team runs the loop: <span className="font-semibold text-violet-700">Listen → Plan → Draft → Publish → Measure → Learn.</span>
            {' '}Every Monday at 9am they write a standup so you can read what they did and approve next week's bets in 5 minutes.
          </p>
          <button
            onClick={() => navigate('/dashboard/standups')}
            className="mt-4 text-[13px] font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 inline-flex items-center gap-1.5"
            data-testid="cta-view-standup"
          >
            View this week's standup <ArrowRight size={14} />
          </button>
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-neutral-500"><Loader2 size={14} className="animate-spin" /> Loading team…</div>
        )}

        {/* Roster grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {personas.map((p) => {
            const Icon = ICONS[p.icon] || Target;
            return (
              <div
                key={p.id}
                className="group bg-white rounded-2xl border border-neutral-200/70 p-5 hover:shadow-lg transition-shadow"
                data-testid={`persona-card-${p.id}`}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span
                    className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                    style={{ backgroundColor: `${p.color}1A`, color: p.color }}
                  >
                    <Icon size={22} />
                  </span>
                  <div className="min-w-0">
                    <div className="text-[16px] font-bold text-neutral-900 leading-tight">{p.name}</div>
                    <div className="text-[11.5px] uppercase tracking-wider text-neutral-500 font-semibold">{p.role}</div>
                  </div>
                </div>
                <div className="text-[12.5px] text-neutral-700 leading-relaxed italic mb-3 min-h-[2.5em]">{p.tagline}</div>
                <div className="text-[11px] text-neutral-500 leading-relaxed">
                  <span className="font-semibold text-neutral-600">Voice:</span> {p.voice}
                </div>
                {p.owns?.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-neutral-100">
                    <div className="text-[10px] uppercase tracking-widest text-neutral-400 font-bold mb-1.5">Owns</div>
                    <div className="flex flex-wrap gap-1">
                      {p.owns.map((o) => (
                        <span key={o} className="text-[10.5px] px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 font-mono">
                          {o.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Team;
