import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  TrendingUp, Loader2, RefreshCw, ExternalLink, MessageSquare,
  ArrowUp, Sparkles, Settings as SettingsIcon, X as XIcon, Plus, Info,
  Wand2, Copy as CopyIcon, Check, ChevronDown,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/trends — live signal feed pulled from Reddit + Google Trends
   and ingested as kind="trend" memories that every agent can recall. */

const Trends = () => {
  const { toast } = useToast();
  const [trends, setTrends] = useState([]);
  const [seeds, setSeeds] = useState({ subreddits: [], keywords: [], user_configured: false });
  const [sourceStatus, setSourceStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [draftSubs, setDraftSubs] = useState([]);
  const [draftKws, setDraftKws] = useState([]);

  const load = async () => {
    const [t, s, st] = await Promise.all([
      axios.get(`${API}/trends/recent?limit=50`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/trends/seeds`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/trends/status`, { withCredentials: true }).catch(() => null),
    ]);
    if (t?.data) setTrends(t.data.trends || []);
    if (s?.data) {
      setSeeds(s.data);
      setDraftSubs(s.data.subreddits || []);
      setDraftKws(s.data.keywords || []);
    }
    if (st?.data) setSourceStatus(st.data);
  };

  useEffect(() => { load().finally(() => setLoading(false)); }, []);

  const ingest = async (subreddits, keywords) => {
    if (ingesting) return;
    setIngesting(true);
    try {
      const body = {};
      if (subreddits !== undefined) body.subreddits = subreddits;
      if (keywords !== undefined) body.keywords = keywords;
      const r = await axios.post(`${API}/trends/ingest`, body, { withCredentials: true });
      const total = (r.data.reddit || 0) + (r.data.gtrends || 0);
      const desc =
        r.data.reddit_configured === false
          ? `Google Trends: ${r.data.gtrends} · Reddit skipped (not configured)`
          : `Reddit: ${r.data.reddit} · Google Trends: ${r.data.gtrends}`;
      toast({ title: `Pulled ${total} signal${total === 1 ? '' : 's'}`, description: desc });
      await load();
    } catch (e) {
      toast({ title: 'Ingest failed', description: e.response?.data?.detail || e.message });
    }
    setIngesting(false);
  };

  const sources = trends.reduce((acc, t) => {
    const src = (t.meta?.source) || 'unknown';
    acc[src] = (acc[src] || 0) + 1;
    return acc;
  }, {});

  return (
    <DashboardLayout
      title="Trends"
      subtitle="Live signals from Reddit + Google Trends. Every signal is added to your AI team's memory."
      headerExtra={
        <div className="flex gap-2">
          <button
            onClick={() => setShowConfig(true)}
            data-testid="trends-config-btn"
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium bg-white/[0.04] hover:bg-white/10 border border-white/10 text-zinc-200 px-3.5 h-9 rounded-lg"
          >
            <SettingsIcon size={12} /> Configure
          </button>
          <button
            onClick={() => ingest()}
            disabled={ingesting}
            data-testid="trends-refresh-btn"
            className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-violet-600 hover:bg-violet-500 text-white px-3.5 h-9 rounded-lg disabled:opacity-40"
          >
            {ingesting ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Pull fresh signals
          </button>
        </div>
      }
    >
      <div className="cv-dash-scope" data-testid="trends-page">

        {/* Reddit-not-configured hint */}
        {sourceStatus?.reddit?.configured === false && (
          <div
            className="cv-glass rounded-2xl p-3.5 mb-4 flex items-start gap-3 border-amber-500/30 bg-amber-500/5"
            data-testid="trends-reddit-unconfigured-banner"
          >
            <Info size={15} className="text-amber-300 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-[12.5px] text-amber-200 font-semibold">Reddit ingestion is offline</p>
              <p className="text-[11.5px] text-zinc-400 leading-relaxed mt-0.5">
                Add a free Reddit "script" app at{' '}
                <a href="https://www.reddit.com/prefs/apps" target="_blank" rel="noopener noreferrer" className="text-amber-300 underline">reddit.com/prefs/apps</a>{' '}
                and paste <code className="text-amber-200">REDDIT_CLIENT_ID</code> + <code className="text-amber-200">REDDIT_CLIENT_SECRET</code> into the backend env. Google Trends keeps working in the meantime.
              </p>
            </div>
          </div>
        )}

        {/* Seeds + counts */}
        <div className="cv-glass rounded-2xl p-4 mb-5 flex items-center flex-wrap gap-3" data-testid="trends-seeds-strip">
          <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold">Watching</span>
          {seeds.subreddits.map((s) => (
            <span key={s} className="text-[11.5px] font-medium text-orange-300 bg-orange-500/10 border border-orange-500/30 rounded-full px-2.5 py-1">
              r/{s}
            </span>
          ))}
          {seeds.keywords.map((k) => (
            <span key={k} className="text-[11.5px] font-medium text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2.5 py-1">
              {k}
            </span>
          ))}
          {!seeds.user_configured && (
            <span className="text-[11px] text-zinc-500 ml-auto">Using niche defaults</span>
          )}
        </div>

        {/* Source breakdown */}
        {trends.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-5" data-testid="trends-counts">
            <span className="inline-flex items-center gap-1.5 text-[12px] text-zinc-300 bg-white/[0.04] border border-white/10 rounded-full px-3 py-1">
              <TrendingUp size={11} /> <strong className="text-white">{trends.length}</strong> signals
            </span>
            {Object.entries(sources).map(([src, n]) => (
              <span key={src} className="inline-flex items-center gap-1.5 text-[11.5px] text-zinc-300 bg-white/[0.04] border border-white/10 rounded-full px-3 py-1">
                {src} · {n}
              </span>
            ))}
          </div>
        )}

        {/* List */}
        {loading ? (
          <div className="text-center py-12 text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
        ) : trends.length === 0 ? (
          <div className="cv-glass rounded-2xl p-10 text-center" data-testid="trends-empty">
            <TrendingUp size={28} className="text-zinc-500 mx-auto mb-3" />
            <p className="text-white font-semibold">No signals yet</p>
            <p className="text-[13px] text-zinc-400 mt-1.5 max-w-md mx-auto leading-relaxed">
              Click <strong className="text-white">Pull fresh signals</strong> to scan Reddit + Google Trends and seed your AI team's memory. New signals auto-refresh every 6 hours.
            </p>
            <button
              onClick={() => ingest()}
              disabled={ingesting}
              data-testid="trends-empty-refresh"
              className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-violet-600 hover:bg-violet-500 text-white px-4 h-10 rounded-lg disabled:opacity-40"
            >
              {ingesting ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              Pull signals now
            </button>
          </div>
        ) : (
          <div className="space-y-2.5" data-testid="trends-list">
            {trends.map((t) => (
              <TrendCard key={t.id} trend={t} />
            ))}
          </div>
        )}
      </div>

      {showConfig && (
        <ConfigModal
          subs={draftSubs}
          kws={draftKws}
          setSubs={setDraftSubs}
          setKws={setDraftKws}
          onClose={() => setShowConfig(false)}
          onSave={async () => {
            await ingest(draftSubs, draftKws);
            setShowConfig(false);
          }}
        />
      )}
    </DashboardLayout>
  );
};

const PLATFORMS = ['linkedin', 'twitter', 'instagram', 'tiktok', 'pinterest', 'facebook'];

const TrendCard = ({ trend }) => {
  const isReddit = (trend.meta?.source) === 'reddit';
  const [open, setOpen] = useState(false);
  const [platform, setPlatform] = useState('linkedin');
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const generate = async () => {
    setDrafting(true);
    setError('');
    setDraft(null);
    try {
      const r = await axios.post(
        `${API}/trends/draft-post`,
        { trend_id: trend.id, platform },
        { withCredentials: true },
      );
      setDraft(r.data);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Draft failed';
      setError(typeof msg === 'string' ? msg : 'Draft failed');
    }
    setDrafting(false);
  };

  const copyDraft = async () => {
    if (!draft?.draft) return;
    const text = draft.draft + (draft.suggested_hashtags?.length
      ? '\n\n' + draft.suggested_hashtags.join(' ') : '');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (_) {}
  };

  const openInCompose = () => {
    if (!draft?.draft) return;
    const params = new URLSearchParams({
      content: draft.draft,
      platform: draft.platform,
      source: 'trend',
    });
    window.location.href = `/dashboard/compose?${params.toString()}`;
  };

  return (
    <div className="cv-glass rounded-xl p-3.5" data-testid={`trend-card-${trend.id}`}>
      <div className="flex items-start gap-3">
        <span className={`shrink-0 text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${
          isReddit
            ? 'bg-orange-500/15 text-orange-300 border-orange-500/30'
            : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
        }`}>
          {isReddit ? 'Reddit' : 'GTrends'}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[13.5px] text-zinc-100 leading-snug">{trend.text}</p>
          <div className="flex items-center gap-3 mt-1.5 text-[11px] text-zinc-500 flex-wrap">
            {isReddit && trend.meta?.score != null && (
              <span className="inline-flex items-center gap-1"><ArrowUp size={10} /> {trend.meta.score.toLocaleString()}</span>
            )}
            {!isReddit && trend.meta?.growth != null && (
              <span className="text-emerald-400 font-semibold">+{trend.meta.growth}%</span>
            )}
            <span>{new Date(trend.created_at).toLocaleString()}</span>
            {trend.meta?.permalink && (
              <a
                href={trend.meta.permalink}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 hover:text-zinc-200 inline-flex items-center gap-1"
              >
                view source <ExternalLink size={10} />
              </a>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          data-testid={`trend-draft-toggle-${trend.id}`}
          className={`shrink-0 inline-flex items-center gap-1.5 text-[11.5px] font-semibold px-2.5 h-7 rounded-md border transition-colors ${
            open
              ? 'bg-violet-500/20 text-violet-200 border-violet-500/40'
              : 'bg-white/[0.04] text-zinc-300 border-white/10 hover:text-white hover:bg-white/[0.08]'
          }`}
        >
          <Wand2 size={11} />
          Draft post
          <ChevronDown size={10} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-white/5 space-y-2.5" data-testid={`trend-draft-panel-${trend.id}`}>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10.5px] uppercase tracking-[0.18em] text-zinc-500 font-semibold pr-1">For</span>
            {PLATFORMS.map((p) => (
              <button
                key={p}
                type="button"
                disabled={drafting}
                onClick={() => setPlatform(p)}
                data-testid={`trend-draft-platform-${trend.id}-${p}`}
                className={`text-[11px] font-semibold rounded-full px-2.5 h-6 inline-flex items-center capitalize transition-colors ${
                  platform === p
                    ? 'bg-violet-500/20 text-violet-200 border border-violet-500/40'
                    : 'bg-white/[0.04] text-zinc-400 border border-white/10 hover:text-zinc-200'
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          {!draft && (
            <button
              type="button"
              onClick={generate}
              disabled={drafting}
              data-testid={`trend-draft-generate-${trend.id}`}
              className="w-full h-10 rounded-lg text-[12.5px] font-semibold inline-flex items-center justify-center gap-1.5 cv-btn-primary disabled:opacity-50"
            >
              {drafting ? <><Loader2 size={13} className="animate-spin" /> Nova is drafting…</> : <><Sparkles size={13} /> Generate {platform} post with Nova</>}
            </button>
          )}

          {draft && (
            <div className="space-y-2" data-testid={`trend-draft-result-${trend.id}`}>
              <div className="rounded-lg border border-violet-500/30 bg-violet-500/[0.04] p-3">
                <pre className="text-[12.5px] text-zinc-100 leading-relaxed whitespace-pre-wrap font-sans">{draft.draft}</pre>
              </div>
              {draft.suggested_hashtags?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {draft.suggested_hashtags.map((h) => (
                    <span key={h} className="text-[11px] text-violet-300 bg-violet-500/10 border border-violet-500/30 rounded-full px-2 py-0.5">{h}</span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={copyDraft}
                  data-testid={`trend-draft-copy-${trend.id}`}
                  className="h-9 px-3 rounded-md text-[12px] font-semibold bg-white/[0.06] hover:bg-white/[0.10] text-zinc-200 border border-white/10 inline-flex items-center gap-1.5"
                >
                  {copied ? <><Check size={12} className="text-emerald-400" /> Copied</> : <><CopyIcon size={12} /> Copy</>}
                </button>
                <button
                  type="button"
                  onClick={openInCompose}
                  data-testid={`trend-draft-compose-${trend.id}`}
                  className="h-9 px-3 rounded-md text-[12px] font-semibold cv-btn-primary inline-flex items-center gap-1.5"
                >
                  <ExternalLink size={12} /> Open in Compose
                </button>
                <button
                  type="button"
                  onClick={() => { setDraft(null); }}
                  className="h-9 px-3 rounded-md text-[12px] font-semibold text-zinc-400 hover:text-zinc-200"
                >
                  Try another platform
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="text-[12px] text-rose-300 bg-rose-500/[0.08] border border-rose-500/30 rounded-lg p-2.5" data-testid={`trend-draft-error-${trend.id}`}>
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ConfigModal = ({ subs, kws, setSubs, setKws, onClose, onSave }) => {
  const [newSub, setNewSub] = useState('');
  const [newKw, setNewKw] = useState('');

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-zinc-950 border border-violet-500/30 rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="trends-config-modal">
        <h3 className="text-lg font-semibold text-white mb-1">Configure your watch-list</h3>
        <p className="text-[12.5px] text-zinc-400 leading-relaxed mb-5">
          Subreddits we'll scan + keywords we'll watch on Google Trends. Up to 10 subs and 5 keywords. Auto-refreshes every 6 hours.
        </p>

        <div className="mb-4">
          <label className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold">Subreddits</label>
          <div className="flex flex-wrap gap-1.5 mt-2 min-h-8">
            {subs.map((s) => (
              <span key={s} className="inline-flex items-center gap-1.5 text-[11.5px] text-orange-300 bg-orange-500/10 border border-orange-500/30 rounded-full px-2.5 py-1">
                r/{s}
                <button onClick={() => setSubs(subs.filter((x) => x !== s))} className="hover:text-rose-300">
                  <XIcon size={9} />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <input
              value={newSub}
              onChange={(e) => setNewSub(e.target.value.replace(/^r\//, ''))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newSub.trim()) {
                  e.preventDefault();
                  if (subs.length < 10 && !subs.includes(newSub.trim())) {
                    setSubs([...subs, newSub.trim()]);
                  }
                  setNewSub('');
                }
              }}
              placeholder="e.g. marketing"
              data-testid="trends-config-sub-input"
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 h-9 text-[13px] text-zinc-100 outline-none focus:border-violet-500/50"
            />
            <button
              onClick={() => {
                if (newSub.trim() && subs.length < 10 && !subs.includes(newSub.trim())) {
                  setSubs([...subs, newSub.trim()]);
                  setNewSub('');
                }
              }}
              className="px-3 h-9 rounded-lg bg-white/[0.04] hover:bg-white/10 text-zinc-300 text-[12px] inline-flex items-center gap-1"
            >
              <Plus size={11} /> Add
            </button>
          </div>
        </div>

        <div className="mb-5">
          <label className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold">Keywords (Google Trends)</label>
          <div className="flex flex-wrap gap-1.5 mt-2 min-h-8">
            {kws.map((k) => (
              <span key={k} className="inline-flex items-center gap-1.5 text-[11.5px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2.5 py-1">
                {k}
                <button onClick={() => setKws(kws.filter((x) => x !== k))} className="hover:text-rose-300">
                  <XIcon size={9} />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <input
              value={newKw}
              onChange={(e) => setNewKw(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newKw.trim()) {
                  e.preventDefault();
                  if (kws.length < 5 && !kws.includes(newKw.trim())) {
                    setKws([...kws, newKw.trim()]);
                  }
                  setNewKw('');
                }
              }}
              placeholder="e.g. AI marketing"
              data-testid="trends-config-kw-input"
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 h-9 text-[13px] text-zinc-100 outline-none focus:border-violet-500/50"
            />
            <button
              onClick={() => {
                if (newKw.trim() && kws.length < 5 && !kws.includes(newKw.trim())) {
                  setKws([...kws, newKw.trim()]);
                  setNewKw('');
                }
              }}
              className="px-3 h-9 rounded-lg bg-white/[0.04] hover:bg-white/10 text-zinc-300 text-[12px] inline-flex items-center gap-1"
            >
              <Plus size={11} /> Add
            </button>
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-[13px] text-zinc-300 px-4 h-10 rounded-xl hover:bg-zinc-800/80">Cancel</button>
          <button onClick={onSave} data-testid="trends-config-save" className="cv-btn-primary text-[13px] font-semibold px-5 h-10 rounded-xl">
            Save & pull
          </button>
        </div>
      </div>
    </div>
  );
};

export default Trends;
