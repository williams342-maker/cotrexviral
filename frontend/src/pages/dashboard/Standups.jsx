import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, RefreshCw, Sparkles, Target, Compass, Pencil, Microscope, Ear, Send, LineChart, ShieldAlert, Clock, History } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const ICONS = { Target, Compass, Pencil, Microscope, Ear, Send, LineChart, ShieldAlert };

const Standups = () => {
  const { toast } = useToast();
  const [latest, setLatest] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [l, h] = await Promise.all([
        axios.get(`${API}/standups/latest`, { withCredentials: true }),
        axios.get(`${API}/standups?limit=6`, { withCredentials: true }),
      ]);
      setLatest(l.data?.empty ? null : l.data);
      setHistory((h.data?.items || []).slice(1));   // drop the latest from history rail
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const generate = async () => {
    setGenerating(true);
    try {
      const r = await axios.post(`${API}/standups/generate`, {},
        { withCredentials: true, timeout: 60000 });
      setLatest(r.data);
      toast({ title: 'Standup ready', description: 'All 8 agents have contributed.' });
      await load();
    } catch (e) {
      toast({ title: 'Generation failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setGenerating(false); }
  };

  const fmtDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  };

  return (
    <DashboardLayout title="Monday Standup" subtitle="Your weekly briefing from the autonomous growth team.">
      <div className="space-y-6" data-testid="standups-page">

        {/* Header — date + regenerate */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-violet-600 font-bold mb-1 flex items-center gap-1.5">
              <Sparkles size={11} /> Latest standup
            </div>
            <h2 className="text-xl font-bold text-neutral-900">
              {latest ? fmtDate(latest.generated_at) : 'No standup yet'}
            </h2>
          </div>
          <button
            onClick={generate}
            disabled={generating}
            className="text-[13px] font-semibold px-4 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 inline-flex items-center gap-1.5"
            data-testid="regenerate-standup-btn"
          >
            {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {generating ? 'Gathering input…' : 'Regenerate now'}
          </button>
        </div>

        {loading && !latest && (
          <div className="flex items-center gap-2 text-neutral-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>
        )}

        {/* Empty state */}
        {!loading && !latest && (
          <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50 p-12 text-center">
            <Sparkles className="mx-auto text-violet-400 mb-3" size={28} />
            <h3 className="text-lg font-bold text-neutral-800 mb-1">Your team hasn't checked in yet</h3>
            <p className="text-[13px] text-neutral-500 mb-4 max-w-lg mx-auto">
              Click "Regenerate now" above to have your 8 specialists summarize the past 7 days.
              Once a week (Monday 9am) this will happen automatically.
            </p>
          </div>
        )}

        {/* The thread */}
        {latest && (
          <div className="space-y-3" data-testid="standup-thread">
            {/* Facts strip */}
            <div className="bg-neutral-900 text-white rounded-2xl p-4 flex flex-wrap gap-6 text-[12px]">
              <Fact label="Posts published" value={latest.facts?.posts_published} />
              <Fact label="Drafts" value={latest.facts?.posts_drafted} />
              <Fact label="Failed" value={latest.facts?.posts_failed} tone={latest.facts?.posts_failed > 0 ? 'warn' : 'ok'} />
              <Fact label="Top platform" value={latest.facts?.top_platform?.platform || '—'} />
              <Fact label="Impressions" value={(latest.facts?.perf_total?.impressions || 0).toLocaleString()} />
              <Fact label="Engagements" value={(latest.facts?.perf_total?.engagements || 0).toLocaleString()} />
            </div>

            {/* Contributions */}
            {(latest.contributions || []).map((c) => {
              const Icon = ICONS[c.icon] || Sparkles;
              return (
                <div
                  key={c.agent_id}
                  className="bg-white rounded-2xl border border-neutral-200/70 p-5 hover:border-neutral-300 transition-colors flex gap-4"
                  data-testid={`contribution-${c.agent_id}`}
                >
                  <span
                    className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0"
                    style={{ backgroundColor: `${c.color}1A`, color: c.color }}
                  >
                    <Icon size={20} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 mb-1.5">
                      <span className="text-[14px] font-bold text-neutral-900">{c.agent_name}</span>
                      <span className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">{c.role}</span>
                    </div>
                    <div className="text-[13.5px] text-neutral-800 leading-relaxed">{c.text}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* History rail */}
        {history.length > 0 && (
          <div className="mt-8">
            <div className="text-[11px] uppercase tracking-widest text-neutral-500 font-bold mb-3 flex items-center gap-1.5">
              <History size={11} /> Past standups
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {history.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setLatest(s)}
                  className="text-left bg-white rounded-xl border border-neutral-200/70 p-3 hover:border-violet-400 transition-colors"
                  data-testid={`history-${s.id}`}
                >
                  <div className="flex items-center gap-1.5 text-[11px] text-neutral-500 mb-1">
                    <Clock size={11} /> {fmtDate(s.generated_at)}
                  </div>
                  <div className="text-[12px] text-neutral-700 tabular-nums">
                    {s.facts?.posts_published || 0} published · {(s.facts?.perf_total?.impressions || 0).toLocaleString()} impressions
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

const Fact = ({ label, value, tone }) => (
  <div>
    <div className="text-[9.5px] uppercase tracking-widest text-neutral-400 font-bold mb-1">{label}</div>
    <div className={`text-[14px] font-bold tabular-nums ${tone === 'warn' ? 'text-amber-400' : 'text-white'}`}>{value ?? '—'}</div>
  </div>
);

export default Standups;
