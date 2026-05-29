/* Attribution panel — campaign-scoped performance dashboard.

   Reads `/api/attribution/overview?campaign_id=<id>` for the headline
   numbers + per-platform breakdown, and `/api/attribution/timeseries`
   for the sparkline. Renders an empty-state when no metrics have
   landed yet (which is the default for a fresh campaign or a fresh
   account before the engagement refresh cron has run).

   Used by `CampaignDetail.jsx`. Could be reused on a global dashboard
   later — `campaignId` is optional. */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { TrendingUp, Eye, Heart, MousePointer, Layers, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

const Window = ({ label, w, testid }) => (
  <div className="flex-1 min-w-[150px] rounded-xl border border-white/10 bg-zinc-950/40 p-3" data-testid={testid}>
    <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">{label}</div>
    <div className="grid grid-cols-2 gap-y-1.5 gap-x-3 text-[11px]">
      <div className="text-zinc-500">Impr.</div>
      <div className="text-zinc-100 tabular-nums text-right font-semibold">{fmt(w.impressions)}</div>
      <div className="text-zinc-500">Reach</div>
      <div className="text-zinc-100 tabular-nums text-right">{fmt(w.reach)}</div>
      <div className="text-zinc-500">Clicks</div>
      <div className="text-zinc-100 tabular-nums text-right">{fmt(w.clicks)}</div>
      <div className="text-zinc-500">Eng.</div>
      <div className="text-zinc-100 tabular-nums text-right">{fmt(w.engagements)}</div>
      <div className="text-zinc-500">CTR</div>
      <div className="text-violet-300 tabular-nums text-right font-semibold">
        {(w.ctr * 100).toFixed(2)}%
      </div>
    </div>
  </div>
);

const PlatformPill = ({ name, data }) => (
  <div className="rounded-lg border border-white/10 bg-zinc-950/40 p-2.5 min-w-[140px]">
    <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-1.5">{name}</div>
    <div className="text-lg font-bold text-white tabular-nums">{fmt(data.engagements)}</div>
    <div className="text-[10px] text-zinc-500 mt-0.5">
      {fmt(data.impressions)} impr · {(data.ctr * 100).toFixed(1)}% CTR
    </div>
  </div>
);

const AttributionPanel = ({ campaignId = null }) => {
  const [overview, setOverview] = useState(null);
  const [series, setSeries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      axios.get(`${API}/attribution/overview${campaignId ? `?campaign_id=${campaignId}` : ''}`,
        { withCredentials: true }).then((r) => r.data),
      axios.get(`${API}/attribution/timeseries?days=30${campaignId ? `&campaign_id=${campaignId}` : ''}`,
        { withCredentials: true }).then((r) => r.data.series || []),
    ]).then(([ov, sr]) => {
      if (cancelled) return;
      setOverview(ov);
      setSeries(sr);
    }).catch((e) => {
      if (!cancelled) setError(e.response?.data?.detail || e.message);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [campaignId]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6 flex items-center justify-center text-zinc-500 text-sm gap-2" data-testid="attribution-loading">
        <Loader2 size={14} className="animate-spin" /> Loading attribution…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-4 text-rose-300 text-sm" data-testid="attribution-error">
        Could not load attribution: {error}
      </div>
    );
  }
  if (!overview || overview.variants_tracked === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6" data-testid="attribution-empty">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center shrink-0">
            <TrendingUp size={18} />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-white mb-1">No attribution data yet</h3>
            <p className="text-xs text-zinc-400 leading-relaxed max-w-prose">
              We'll show per-platform CTR, engagement, and reach here as soon as your posts start
              gathering engagement. The metrics refresh every 6 hours from the connected channel APIs.
              {' '}
              <span className="text-zinc-500">
                Variants tracked: <span className="tabular-nums">{overview.variants_tracked}</span>
              </span>
            </p>
          </div>
        </div>
      </div>
    );
  }

  const w = overview.windows || {};
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5 space-y-5" data-testid="attribution-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} className="text-violet-400" />
          <h3 className="text-sm font-semibold text-white">Attribution</h3>
          <span className="text-[10px] px-1.5 py-0.5 rounded border border-violet-500/30 text-violet-300 bg-violet-500/10">
            {overview.variants_tracked} variant{overview.variants_tracked === 1 ? '' : 's'}
          </span>
        </div>
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {series.length} day{series.length === 1 ? '' : 's'} of data
        </span>
      </div>

      {/* Window tiles */}
      <div className="flex flex-wrap gap-3">
        <Window label="Last 7 days"  w={w.last_7d  || {}} testid="attribution-window-7d" />
        <Window label="Last 30 days" w={w.last_30d || {}} testid="attribution-window-30d" />
        <Window label="All time"     w={w.all_time || {}} testid="attribution-window-all" />
      </div>

      {/* Per-platform */}
      {Object.keys(overview.platforms || {}).length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2 flex items-center gap-1.5">
            <Layers size={11} /> By platform · all-time
          </div>
          <div className="flex flex-wrap gap-2" data-testid="attribution-platforms">
            {Object.entries(overview.platforms).map(([name, data]) => (
              <PlatformPill key={name} name={name} data={data} />
            ))}
          </div>
        </div>
      )}

      {/* Top content_items */}
      {overview.top_items?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2 flex items-center gap-1.5">
            <Heart size={11} /> Top content · last 30d
          </div>
          <div className="space-y-1.5" data-testid="attribution-top-items">
            {overview.top_items.map((t, i) => (
              <div key={t.content_item_id} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-white/5 bg-zinc-950/40">
                <span className="text-[10px] text-zinc-500 tabular-nums w-4">#{i + 1}</span>
                <span className="text-[12px] text-zinc-200 flex-1 truncate">{t.title}</span>
                <span className="text-[11px] text-rose-300 tabular-nums flex items-center gap-1">
                  <Heart size={10} /> {fmt(t.engagements)}
                </span>
                <span className="text-[11px] text-cyan-300 tabular-nums flex items-center gap-1">
                  <Eye size={10} /> {fmt(t.impressions)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AttributionPanel;
