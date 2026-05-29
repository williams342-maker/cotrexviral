import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Ear, AlertTriangle, ThumbsUp, ThumbsDown, Minus, GitMerge, Sparkles, ExternalLink, MessageCircle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Social Listening — Lyra's domain.
   Top row: 4 stat tiles (total, by sentiment, attention score).
   Body: chronological feed of signals with sentiment + urgency.
   Synthesize button: LLM-generates realistic signals for empty states. */

const SENTIMENT_META = {
  positive: { icon: ThumbsUp,  color: 'text-emerald-700 bg-emerald-50 border-emerald-200', label: 'Positive' },
  negative: { icon: ThumbsDown,color: 'text-rose-700 bg-rose-50 border-rose-200',           label: 'Negative' },
  mixed:    { icon: GitMerge,  color: 'text-amber-700 bg-amber-50 border-amber-200',        label: 'Mixed' },
  neutral:  { icon: Minus,     color: 'text-neutral-600 bg-neutral-100 border-neutral-200', label: 'Neutral' },
};

const SOURCE_LABELS = {
  reddit: 'Reddit', twitter: 'Twitter / X', instagram_comment: 'IG Comment',
  forum: 'Forum', blog: 'Blog', synthetic: 'Synthetic',
};

const Listening = () => {
  const { toast } = useToast();
  const [stats, setStats] = useState(null);
  const [signals, setSignals] = useState([]);
  const [filter, setFilter] = useState({ sentiment: '', signal_type: '' });
  const [loading, setLoading] = useState(true);
  const [synthing, setSynthing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filter.sentiment) params.set('sentiment', filter.sentiment);
      if (filter.signal_type) params.set('signal_type', filter.signal_type);
      const [s, f] = await Promise.all([
        axios.get(`${API}/listening/stats`, { withCredentials: true }),
        axios.get(`${API}/listening/signals?${params.toString()}`, { withCredentials: true }),
      ]);
      setStats(s.data);
      setSignals(f.data.items || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [filter]);

  const synthesize = async () => {
    setSynthing(true);
    try {
      const r = await axios.post(`${API}/listening/synthesize`,
        { brand: 'CortexViral', competitors: ['Hootsuite', 'Buffer', 'Later'], n_signals: 6 },
        { withCredentials: true, timeout: 30000 },
      );
      toast({ title: `Captured ${r.data.created} signals`, description: 'Lyra has logged them to your listening feed.' });
      await load();
    } catch (e) {
      toast({ title: 'Synthesize failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setSynthing(false); }
  };

  const sentByKey = stats?.by_sentiment || {};

  return (
    <DashboardLayout title="Social Listening" subtitle="Lyra's signal feed — mentions, sentiment, trends.">
      <div className="space-y-6" data-testid="listening-page">

        {/* Hero — Lyra intro + alert banner */}
        <div className="rounded-2xl border border-amber-200/60 bg-gradient-to-br from-amber-50 via-white to-orange-50 p-5 flex items-start gap-4">
          <span className="w-12 h-12 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
            <Ear size={22} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-amber-600 font-bold mb-1">Listening Engine — Lyra</div>
            <div className="text-[14px] text-neutral-800 leading-relaxed">
              Always-on. Tracks brand + competitor mentions across Reddit, Twitter, Instagram, blogs, and forums.
              Classifies sentiment, scores urgency, surfaces emerging trends.
            </div>
            {stats?.alert_triggered && (
              <div className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-[12px] font-semibold" data-testid="attention-alert">
                <AlertTriangle size={13} /> Attention score {stats.attention_score} — above threshold ({stats.alert_threshold}). Review negative signals below.
              </div>
            )}
          </div>
          <button
            onClick={synthesize}
            disabled={synthing}
            className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 inline-flex items-center gap-1.5 shrink-0"
            data-testid="synthesize-btn"
          >
            {synthing ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            Capture signals
          </button>
        </div>

        {/* Stat tiles */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatTile label="Signals (7d)" value={stats?.total ?? 0} icon={MessageCircle} />
          <StatTile label="Positive" value={sentByKey.positive || 0} tone="emerald" icon={ThumbsUp} />
          <StatTile label="Negative" value={sentByKey.negative || 0} tone="rose" icon={ThumbsDown} />
          <StatTile label="Mixed" value={sentByKey.mixed || 0} tone="amber" icon={GitMerge} />
          <StatTile label="Attention" value={stats?.attention_score ?? 0} tone={stats?.alert_triggered ? 'rose' : 'neutral'} icon={AlertTriangle} />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-neutral-500 font-bold mr-1">Filter:</span>
          {['', 'positive', 'negative', 'mixed', 'neutral'].map((s) => (
            <button
              key={s || 'all'}
              onClick={() => setFilter({ ...filter, sentiment: s })}
              className={`text-[11.5px] px-2.5 py-1 rounded-full border font-semibold transition-colors ${
                filter.sentiment === s ? 'bg-violet-600 text-white border-violet-600' : 'bg-white text-neutral-600 border-neutral-200 hover:border-neutral-400'
              }`}
              data-testid={`filter-sentiment-${s || 'all'}`}
            >
              {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All'}
            </button>
          ))}
        </div>

        {loading && !signals.length && (
          <div className="flex items-center gap-2 text-neutral-500"><Loader2 size={14} className="animate-spin" /> Loading signals…</div>
        )}

        {/* Empty state */}
        {!loading && !signals.length && (
          <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50 p-10 text-center">
            <Ear className="mx-auto text-amber-400 mb-3" size={26} />
            <h3 className="text-lg font-bold text-neutral-800 mb-1">No signals yet</h3>
            <p className="text-[13px] text-neutral-500 mb-3 max-w-md mx-auto">
              Connect a listening source (Reddit RSS, Twitter search, Mention.com) — or click "Capture signals" above to generate a realistic sample feed for now.
            </p>
          </div>
        )}

        {/* Signal feed */}
        {signals.length > 0 && (
          <div className="space-y-2" data-testid="signal-feed">
            {signals.map((s) => {
              const meta = SENTIMENT_META[s.sentiment] || SENTIMENT_META.neutral;
              const Icon = meta.icon;
              return (
                <div
                  key={s.id}
                  className="bg-white rounded-xl border border-neutral-200/70 p-4 hover:border-neutral-300 transition-colors"
                  data-testid={`signal-${s.id}`}
                >
                  <div className="flex items-start gap-3">
                    <span className={`px-2 py-1 rounded-md border text-[10.5px] font-bold uppercase tracking-wider inline-flex items-center gap-1 shrink-0 ${meta.color}`}>
                      <Icon size={11} /> {meta.label}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-[11.5px] font-semibold text-neutral-700">{SOURCE_LABELS[s.source] || s.source}</span>
                        {s.author && <span className="text-[11px] text-neutral-500">· {s.author}</span>}
                        {s.topic && <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600 font-mono">{s.topic}</span>}
                        {s.urgency >= 4 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 font-bold uppercase tracking-wider">
                            Urgent
                          </span>
                        )}
                      </div>
                      <div className="text-[13.5px] text-neutral-800 leading-relaxed">{s.text}</div>
                      <div className="mt-2 flex items-center gap-3 text-[11px] text-neutral-500">
                        <span className="tabular-nums">{s.engagement || 0} engagements</span>
                        <span className="tabular-nums">urgency {s.urgency}/5</span>
                        {s.source_url && (
                          <a href={s.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-violet-600">
                            Source <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const StatTile = ({ label, value, tone = 'neutral', icon: Icon }) => {
  const tones = {
    neutral: 'bg-white border-neutral-200 text-neutral-900',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    rose:    'bg-rose-50 border-rose-200 text-rose-800',
    amber:   'bg-amber-50 border-amber-200 text-amber-800',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-widest font-bold opacity-70">{label}</div>
        {Icon && <Icon size={13} className="opacity-50" />}
      </div>
      <div className="text-[20px] font-bold tabular-nums">{value}</div>
    </div>
  );
};

export default Listening;
