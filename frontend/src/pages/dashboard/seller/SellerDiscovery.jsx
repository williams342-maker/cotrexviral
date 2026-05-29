import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, Search, Play, Globe, ShoppingBag, Instagram, Facebook,
  ArrowRight, ExternalLink, Hash,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

/* SellerDiscovery — run discovery passes + inspect what each source surfaced.
   URL param mission_id selects which mission to discover for. */

const SOURCE_ICONS = {
  etsy:         ShoppingBag,
  shopify:      ShoppingBag,
  instagram:    Instagram,
  pinterest:    Search,
  facebook:     Facebook,
  tiktok:       Hash,
  reddit:       Search,
  google_search: Globe,
  google_maps:  Globe,
};

const DEFAULT_SOURCES = ['etsy', 'shopify', 'instagram', 'pinterest',
                          'facebook', 'tiktok', 'reddit', 'google_search', 'google_maps'];

const SellerDiscovery = () => {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();

  const initialMid = sp.get('mission_id') || '';
  const [missions, setMissions] = useState([]);
  const [missionId, setMissionId] = useState(initialMid);
  const [activeSources, setActiveSources] = useState(new Set(DEFAULT_SOURCES));
  const [maxPerSource, setMaxPerSource] = useState(25);
  const [runs, setRuns] = useState([]);
  const [leads, setLeads] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadMissions = async () => {
    const r = await axios.get(`${API}/missions`, { withCredentials: true });
    const s = (r.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
    setMissions(s);
    if (!missionId && s.length) setMissionId(s[0].id);
  };

  const loadFor = async (mid) => {
    if (!mid) { setLoading(false); return; }
    setLoading(true);
    try {
      const [r, l] = await Promise.all([
        axios.get(`${API}/seller-discovery/runs/${mid}`, { withCredentials: true }),
        axios.get(`${API}/seller-leads?mission_id=${mid}&limit=200`, { withCredentials: true }),
      ]);
      setRuns(r.data?.runs || []);
      setLeads(l.data?.leads || []);
    } catch (e) {
      toast({ title: 'Failed to load discovery data',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadMissions(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadFor(missionId); }, [missionId]);

  const mission = useMemo(() => missions.find((m) => m.id === missionId), [missions, missionId]);

  const runDiscovery = async () => {
    if (!mission) return;
    setBusy(true);
    try {
      const niche = mission.seller_target_niche || mission.metric || 'general';
      const r = await axios.post(`${API}/seller-discovery/run`, {
        mission_id: missionId,
        niche,
        location: mission.seller_target_location || null,
        sources: Array.from(activeSources),
        max_per_source: maxPerSource,
      }, { withCredentials: true });
      toast({ title: `Discovered ${r.data.inserted} new leads`,
              description: `(${r.data.skipped_existing} duplicates skipped across ${(r.data.sources || []).length} sources)` });
      loadFor(missionId);
    } catch (e) {
      toast({ title: 'Discovery failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };

  const qualifyAll = async () => {
    if (!mission) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/seller-qualification/run`, {
        mission_id: missionId, requalify: false,
      }, { withCredentials: true });
      toast({ title: `Qualified ${r.data.accepted} of ${r.data.scored} leads`,
              description: `${r.data.rejected} rejected at threshold ${r.data.threshold}` });
      loadFor(missionId);
    } catch (e) {
      toast({ title: 'Qualification failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy(false); }
  };

  const toggleSource = (s) => {
    setActiveSources((cur) => {
      const next = new Set(cur);
      if (next.has(s)) next.delete(s); else next.add(s);
      return next;
    });
  };

  return (
    <DashboardLayout
      title="Seller OS · Discovery"
      subtitle="Surface candidate sellers across 9 platforms and feed them into the qualification engine."
    >
      <div className="space-y-6" data-testid="seller-discovery-page">
        {/* Mission picker */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4 flex items-center gap-3 flex-wrap">
          <label className="text-[11.5px] text-zinc-400 font-semibold uppercase tracking-wider">Mission</label>
          <select value={missionId} onChange={(e) => setMissionId(e.target.value)}
                  data-testid="discovery-mission-select"
                  className="flex-1 min-w-0 px-3 py-2 rounded-md bg-white/5 border border-white/10 text-white text-[13px]">
            <option value="">— pick a seller-acquisition mission —</option>
            {missions.map((m) => (
              <option key={m.id} value={m.id}>{m.title}</option>
            ))}
          </select>
          {mission && (
            <>
              <span className="text-[11.5px] text-zinc-500">
                Target niche: <strong className="text-zinc-300">{mission.seller_target_niche || mission.metric || '—'}</strong>
              </span>
              <button onClick={runDiscovery} disabled={busy || !missionId || activeSources.size === 0}
                      data-testid="discovery-run-btn"
                      className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 shadow disabled:opacity-50">
                {busy ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} />} Run discovery
              </button>
              <button onClick={qualifyAll} disabled={busy || !missionId}
                      data-testid="discovery-qualify-btn"
                      className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 transition flex items-center gap-1.5 disabled:opacity-50">
                Qualify all <ArrowRight size={11} />
              </button>
            </>
          )}
        </div>

        {/* Source toggles */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Sources</div>
            <label className="text-[11.5px] text-zinc-400 flex items-center gap-2">
              Max per source:
              <input type="number" min="1" max="100" value={maxPerSource}
                     onChange={(e) => setMaxPerSource(Math.max(1, Math.min(100, Number(e.target.value) || 25)))}
                     data-testid="discovery-max-input"
                     className="w-16 px-2 py-1 rounded bg-white/5 border border-white/10 text-white text-[12px]" />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            {DEFAULT_SOURCES.map((s) => {
              const Icon = SOURCE_ICONS[s] || Search;
              const active = activeSources.has(s);
              return (
                <button key={s} onClick={() => toggleSource(s)}
                        data-testid={`discovery-source-${s}`}
                        className={`text-[11.5px] font-semibold px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
                          active
                            ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow'
                            : 'bg-white/5 hover:bg-white/10 text-zinc-400'
                        }`}>
                  <Icon size={11} /> {s.replace('_', ' ')}
                </button>
              );
            })}
          </div>
        </div>

        {/* Lead grid */}
        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>
        ) : leads.length === 0 ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            No leads discovered yet for this mission. Pick a mission + sources and hit "Run discovery".
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {leads.slice(0, 60).map((l) => <LeadTile key={l.id} lead={l} />)}
          </div>
        )}

        {/* Recent runs */}
        {runs.length > 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">Recent discovery runs</div>
            <div className="space-y-1.5">
              {runs.slice(0, 6).map((r) => (
                <div key={r.id} className="flex items-center gap-3 text-[12px]">
                  <span className="text-zinc-500 tabular-nums">{new Date(r.created_at).toLocaleString()}</span>
                  <span className="text-zinc-400">→</span>
                  <span className="text-white"><strong>{r.inserted}</strong> new <span className="text-zinc-500">/ {r.candidates} candidates</span></span>
                  <span className="text-zinc-500">· {r.sources.length} sources</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const STAGE_TONE = {
  discovered:   'bg-zinc-500/15 text-zinc-300',
  qualified:    'bg-violet-500/15 text-violet-300',
  outreached:   'bg-blue-500/15 text-blue-300',
  interested:   'bg-amber-500/15 text-amber-300',
  onboarding:   'bg-emerald-500/15 text-emerald-300',
  active:       'bg-green-500/20 text-green-300',
  rejected:     'bg-rose-500/10 text-rose-300',
  unresponsive: 'bg-zinc-700/30 text-zinc-500',
  churned:      'bg-zinc-700/30 text-zinc-500',
};

const LeadTile = ({ lead }) => {
  const Icon = SOURCE_ICONS[lead.source] || Search;
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.03] hover:bg-white/[0.05] transition p-4"
         data-testid={`lead-tile-${lead.id}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <div className="text-[13.5px] font-semibold text-white truncate">{lead.business_name}</div>
          <div className="text-[10.5px] text-zinc-500 flex items-center gap-1 mt-0.5">
            <Icon size={10} /> <span className="capitalize">{lead.source.replace('_', ' ')}</span>
            {lead.niche && <><span>·</span><span>{lead.niche}</span></>}
          </div>
        </div>
        <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${STAGE_TONE[lead.stage] || STAGE_TONE.discovered}`}>
          {lead.stage}
        </span>
      </div>
      {lead.seller_score != null && (
        <div className="flex items-center gap-2 mb-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">Seller score</div>
          <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500"
                 style={{ width: `${lead.seller_score}%` }} />
          </div>
          <div className="text-[12px] tabular-nums font-semibold text-white">{lead.seller_score}</div>
        </div>
      )}
      {lead.website && (
        <a href={lead.website} target="_blank" rel="noopener noreferrer"
           className="text-[11px] text-violet-300 hover:text-violet-200 flex items-center gap-1 truncate">
          <ExternalLink size={10} /> {lead.website.replace(/^https?:\/\//, '')}
        </a>
      )}
    </div>
  );
};

export default SellerDiscovery;
