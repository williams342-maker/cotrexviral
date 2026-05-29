import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, Sparkles, ExternalLink, ArrowRight, ChevronDown, ChevronUp,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

/* QualifiedSellers — list of all leads at stage ≥ qualified, ordered by
   seller_score desc. Each row expandable to show score breakdown. */

const QualifiedSellers = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [missions, setMissions] = useState([]);
  const [missionId, setMissionId] = useState('all');
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const ms = await axios.get(`${API}/missions`, { withCredentials: true });
      const seller = (ms.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
      setMissions(seller);

      const qs = missionId !== 'all' ? `?mission_id=${missionId}&stage=qualified&limit=200`
                                     : `?stage=qualified&limit=300`;
      const r = await axios.get(`${API}/seller-leads${qs}`, { withCredentials: true });
      setLeads(r.data?.leads || []);
    } catch (e) {
      toast({ title: 'Failed to load qualified sellers',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [missionId]);

  return (
    <DashboardLayout
      title="Seller OS · Qualified Sellers"
      subtitle="Leads that cleared the qualification engine — ranked by seller score."
    >
      <div className="space-y-5" data-testid="qualified-sellers-page">
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4 flex items-center gap-3">
          <label className="text-[11.5px] text-zinc-400 font-semibold uppercase tracking-wider">Mission</label>
          <select value={missionId} onChange={(e) => setMissionId(e.target.value)}
                  data-testid="qualified-mission-filter"
                  className="flex-1 px-3 py-2 rounded-md bg-white/5 border border-white/10 text-white text-[13px]">
            <option value="all">All seller missions</option>
            {missions.map((m) => (
              <option key={m.id} value={m.id}>{m.title}</option>
            ))}
          </select>
          <span className="text-[11.5px] text-zinc-500"><strong className="text-white">{leads.length}</strong> qualified</span>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
        ) : leads.length === 0 ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            <Sparkles size={20} className="mx-auto mb-2 text-zinc-600" />
            No qualified sellers yet. Head to <button onClick={() => navigate('/dashboard/seller-os/discovery')} className="text-violet-300 hover:underline" data-testid="qualified-empty-discover">Discovery</button> to surface candidates and qualify them.
          </div>
        ) : (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] divide-y divide-white/5">
            {leads.map((l) => {
              const isOpen = !!expanded[l.id];
              const breakdown = l.score_breakdown || {};
              return (
                <div key={l.id} className="p-4" data-testid={`qualified-row-${l.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-[14px] font-semibold text-white truncate">{l.business_name}</div>
                      <div className="text-[11.5px] text-zinc-500 flex items-center gap-2 mt-0.5">
                        <span className="capitalize">{l.source.replace('_', ' ')}</span>
                        {l.niche && <><span>·</span><span>{l.niche}</span></>}
                        {l.estimated_activity && <><span>·</span><span className="capitalize">{l.estimated_activity} activity</span></>}
                      </div>
                    </div>
                    {l.seller_score != null && (
                      <div className="text-right">
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Score</div>
                        <div className="text-xl tabular-nums font-semibold text-white">{l.seller_score}</div>
                      </div>
                    )}
                    <button onClick={() => setExpanded((s) => ({ ...s, [l.id]: !s[l.id] }))}
                            className="p-2 rounded-md hover:bg-white/5 text-zinc-400 hover:text-white"
                            data-testid={`qualified-toggle-${l.id}`}>
                      {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </div>

                  {isOpen && (
                    <div className="mt-3 pt-3 border-t border-white/5 grid grid-cols-2 md:grid-cols-4 gap-3">
                      {['quality', 'growth', 'marketplace_fit', 'engagement'].map((k) => {
                        const v = breakdown[k] ?? 0;
                        return (
                          <div key={k} data-testid={`qualified-breakdown-${l.id}-${k}`}>
                            <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">{k.replace('_', ' ')}</div>
                            <div className="flex items-center gap-2">
                              <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                                <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500" style={{ width: `${v}%` }} />
                              </div>
                              <span className="text-[12px] tabular-nums font-semibold text-white w-8 text-right">{v}</span>
                            </div>
                          </div>
                        );
                      })}
                      {l.website && (
                        <a href={l.website} target="_blank" rel="noopener noreferrer"
                           className="col-span-2 md:col-span-4 text-[11.5px] text-violet-300 hover:text-violet-200 flex items-center gap-1 truncate">
                          <ExternalLink size={10} /> {l.website}
                        </a>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default QualifiedSellers;
