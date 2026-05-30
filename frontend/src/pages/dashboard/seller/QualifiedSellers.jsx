import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, Sparkles, ExternalLink, ChevronDown, ChevronUp,
  ListChecks, ThumbsUp, ThumbsDown, Target, AlertTriangle,
  CheckCircle2, MessageCircle, TrendingUp, Megaphone,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

const BAND_TONE = {
  high:   'text-emerald-300 border-emerald-500/30 bg-emerald-500/[0.06]',
  medium: 'text-amber-300 border-amber-500/30 bg-amber-500/[0.06]',
  low:    'text-zinc-400 border-white/10 bg-white/[0.04]',
};

const QualifiedSellers = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [missions, setMissions] = useState([]);
  const [missionId, setMissionId] = useState('all');
  const [leads, setLeads] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [recommendation, setRecommendation] = useState(null);
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

      // Review queue + recommended action (mission-scoped only)
      if (missionId !== 'all') {
        const [rq, ra] = await Promise.all([
          axios.get(`${API}/seller-qualification/review-queue?mission_id=${missionId}`, { withCredentials: true }),
          axios.get(`${API}/seller-qualification/recommended-action?mission_id=${missionId}`, { withCredentials: true }),
        ]);
        setReviewQueue(rq.data?.queue || []);
        setRecommendation(ra.data || null);
      } else {
        setReviewQueue([]);
        setRecommendation(null);
      }
    } catch (e) {
      toast({ title: 'Failed to load qualified sellers',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [missionId]);

  const decide = async (leadId, decision) => {
    try {
      await axios.post(`${API}/seller-qualification/review/${leadId}`,
                          { decision }, { withCredentials: true });
      toast({ title: decision === 'promote' ? 'Promoted to qualified' : 'Rejected',
              description: 'Decision saved.' });
      load();
    } catch (e) {
      toast({ title: 'Decision failed',
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    }
  };

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

        {recommendation && (
          <RecommendedActionCard rec={recommendation} />
        )}

        {reviewQueue.length > 0 && (
          <ReviewQueuePanel queue={reviewQueue} onDecide={decide} />
        )}

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
              const card = l.prospect_card || {};
              const band = l.confidence_band || 'high';
              return (
                <div key={l.id} className="p-4" data-testid={`qualified-row-${l.id}`}>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="text-[14px] font-semibold text-white truncate">{l.business_name}</div>
                        <span data-testid={`qualified-band-${l.id}`}
                              className={`text-[9.5px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded border ${BAND_TONE[band]}`}>
                          {band}
                        </span>
                      </div>
                      <div className="text-[11.5px] text-zinc-500 flex items-center gap-2 mt-0.5">
                        <span className="capitalize">{(l.source || '').replace('_', ' ')}</span>
                        {l.niche && <><span>·</span><span>{l.niche}</span></>}
                        {l.estimated_activity && <><span>·</span><span className="capitalize">{l.estimated_activity} activity</span></>}
                      </div>
                    </div>
                    {l.seller_score != null && (
                      <div className="text-right">
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Confidence</div>
                        <div className="text-xl tabular-nums font-semibold text-white">{Math.round(l.seller_score)}%</div>
                      </div>
                    )}
                    <button onClick={() => setExpanded((s) => ({ ...s, [l.id]: !s[l.id] }))}
                            className="p-2 rounded-md hover:bg-white/5 text-zinc-400 hover:text-white"
                            data-testid={`qualified-toggle-${l.id}`}>
                      {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </div>

                  {isOpen && (
                    <div className="mt-3 pt-3 border-t border-white/5 space-y-4">
                      <BreakdownGrid leadId={l.id} breakdown={breakdown} />
                      <ProspectIntelCard card={card} signals={l.signals || []} />
                      {l.website && (
                        <a href={l.website} target="_blank" rel="noopener noreferrer"
                           className="text-[11.5px] text-violet-300 hover:text-violet-200 flex items-center gap-1 truncate">
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


function RecommendedActionCard({ rec }) {
  const tone = rec.action === 'contact_high_confidence' ? 'border-emerald-500/40 from-emerald-500/[0.08] to-emerald-500/[0.02] text-emerald-200'
            : rec.action === 'review_medium_queue' ? 'border-amber-500/40 from-amber-500/[0.08] to-amber-500/[0.02] text-amber-200'
            : 'border-violet-500/40 from-violet-500/[0.08] to-violet-500/[0.02] text-violet-200';
  return (
    <div data-testid="recommended-action-card"
         className={`rounded-2xl border bg-gradient-to-br p-4 ${tone}`}>
      <div className="flex items-start gap-3">
        <span className="w-8 h-8 rounded-md bg-white/10 border border-white/20 flex items-center justify-center mt-0.5">
          <Megaphone size={14} />
        </span>
        <div className="flex-1">
          <div className="text-[10px] uppercase tracking-widest font-bold opacity-70">Recommended action</div>
          <div className="text-[16px] font-semibold mt-1">{rec.summary}</div>
          <div className="text-[12px] opacity-85 mt-1.5 leading-relaxed">{rec.reason}</div>
          <div className="text-[10.5px] opacity-60 mt-2 flex items-center gap-3">
            <span>High-confidence: <strong>{rec.counts?.high || 0}</strong></span>
            <span>·</span>
            <span>Review queue: <strong>{rec.counts?.medium || 0}</strong></span>
          </div>
        </div>
      </div>
    </div>
  );
}


function ReviewQueuePanel({ queue, onDecide }) {
  return (
    <div data-testid="review-queue-panel"
         className="rounded-2xl border border-amber-500/25 bg-amber-500/[0.03] p-4">
      <div className="flex items-center gap-2 mb-3">
        <ListChecks size={14} className="text-amber-300" />
        <h3 className="text-[13px] font-semibold text-white">
          Review queue
        </h3>
        <span className="text-[10.5px] uppercase tracking-wider font-bold text-amber-300 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded">
          {queue.length} pending
        </span>
        <div className="flex-1" />
        <span className="text-[10.5px] text-zinc-500">Medium-confidence — promote to qualified or reject</span>
      </div>
      <div className="space-y-2">
        {queue.map((l) => {
          const card = l.prospect_card || {};
          return (
            <div key={l.id}
                  data-testid={`review-row-${l.id}`}
                  className="rounded-lg bg-white/[0.03] border border-white/5 p-3">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-white truncate">{l.business_name}</div>
                  <div className="text-[11px] text-zinc-500 mt-0.5 flex items-center gap-2 flex-wrap">
                    <span className="capitalize">{(l.source || '').replace('_', ' ')}</span>
                    {l.niche && <><span>·</span><span>{l.niche}</span></>}
                    <span>·</span>
                    <span className="text-amber-300 font-semibold">{Math.round(l.seller_score)}% confidence</span>
                  </div>
                  {card.outreach_angle && (
                    <div className="text-[11px] text-zinc-300 mt-1.5 italic">
                      “{card.outreach_angle}”
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <button onClick={() => onDecide(l.id, 'promote')}
                          data-testid={`review-promote-${l.id}`}
                          className="text-[11px] font-bold px-2 py-1 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-500/30 transition flex items-center gap-1">
                    <ThumbsUp size={9} /> Promote
                  </button>
                  <button onClick={() => onDecide(l.id, 'reject')}
                          data-testid={`review-reject-${l.id}`}
                          className="text-[11px] font-bold px-2 py-1 rounded-md bg-rose-500/15 hover:bg-rose-500/25 text-rose-200 border border-rose-500/30 transition flex items-center gap-1">
                    <ThumbsDown size={9} /> Reject
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


function BreakdownGrid({ leadId, breakdown }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {['quality', 'growth', 'marketplace_fit', 'engagement'].map((k) => {
        const v = breakdown[k] ?? 0;
        return (
          <div key={k} data-testid={`qualified-breakdown-${leadId}-${k}`}>
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
    </div>
  );
}


function ProspectIntelCard({ card, signals }) {
  if (!card || (!card.why_match && !card.pain_points && !card.outreach_angle)) return null;
  return (
    <div data-testid="prospect-intel-card"
         className="rounded-lg border border-violet-500/20 bg-violet-500/[0.04] p-3 space-y-3">
      <div className="text-[10px] uppercase tracking-widest font-bold text-violet-300">Prospect intelligence</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {card.why_match?.length > 0 && (
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-emerald-300 font-bold mb-1.5 flex items-center gap-1">
              <Target size={9} /> Why they match
            </div>
            <ul className="space-y-1">
              {card.why_match.map((m, i) => (
                <li key={i} className="text-[12px] text-zinc-200 flex items-start gap-1.5">
                  <CheckCircle2 size={9} className="text-emerald-400 mt-1 flex-shrink-0" />
                  <span>{m}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {card.pain_points?.length > 0 && (
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-rose-300 font-bold mb-1.5 flex items-center gap-1">
              <AlertTriangle size={9} /> Pain points detected
            </div>
            <ul className="space-y-1">
              {card.pain_points.map((p, i) => (
                <li key={i} className="text-[12px] text-zinc-200 flex items-start gap-1.5">
                  <span className="text-rose-400 mt-1">•</span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {card.outreach_angle && (
        <div className="pt-2 border-t border-violet-500/15">
          <div className="text-[10.5px] uppercase tracking-wider text-violet-300 font-bold mb-1.5 flex items-center gap-1">
            <MessageCircle size={9} /> Recommended outreach angle
          </div>
          <div className="text-[12px] text-zinc-200 italic leading-relaxed">
            “{card.outreach_angle}”
          </div>
        </div>
      )}
      {typeof card.likelihood_to_convert === 'number' && (
        <div className="pt-2 border-t border-violet-500/15 flex items-center gap-2">
          <TrendingUp size={11} className="text-violet-300" />
          <span className="text-[11px] uppercase tracking-wider text-zinc-400 font-semibold">Likelihood to convert</span>
          <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-emerald-500"
                  style={{ width: `${card.likelihood_to_convert * 100}%` }} />
          </div>
          <span className="text-[12px] tabular-nums font-bold text-white">
            {Math.round(card.likelihood_to_convert * 100)}%
          </span>
        </div>
      )}
      {signals?.length > 0 && (
        <details className="pt-2 border-t border-violet-500/15">
          <summary className="text-[10.5px] uppercase tracking-wider text-zinc-400 font-semibold cursor-pointer hover:text-white">
            Signal breakdown ({signals.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {signals.map((s, i) => (
              <li key={i} className="text-[11px] flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full ${
                  s.verdict === 'positive' ? 'bg-emerald-400'
                  : s.verdict === 'neutral' ? 'bg-amber-400' : 'bg-zinc-600'}`} />
                <span className="text-zinc-400 font-semibold">{s.label}</span>
                <span className="text-zinc-500">·</span>
                <span className="text-zinc-300">{s.value}</span>
                <span className="text-zinc-600 ml-auto">w={s.weight}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}


export default QualifiedSellers;
