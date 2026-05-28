import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import {
  Loader2, MessageSquare, Brain, TrendingUp, ShieldCheck, ArrowUpRight,
  Sparkles, AlertCircle, Clock, Users2, X, Check, Hourglass,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';

/* /dashboard/team — Unified "AI Growth Team" command center.
   Four panel cards laid out 2×2, each surfacing the most recent activity
   from the matching subsystem with a clear CTA to the full view:
     • Active Conversations  → /dashboard/agent/{id}
     • Pending Approvals     → /dashboard/approvals
     • Recent Memories       → /dashboard/memory
     • Recent Trend Signals  → /dashboard/trends
   A "Quick prompt" hero at top routes the user into Atlas chat with
   their prompt pre-seeded via query param. */

const AGENT_TONES = {
  strategy: 'bg-blue-500/10 border-blue-500/30 text-blue-300',
  research: 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300',
  nova:     'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
  sam:      'bg-amber-500/10 border-amber-500/30 text-amber-300',
  kai:      'bg-rose-500/10 border-rose-500/30 text-rose-300',
  angela:   'bg-violet-500/10 border-violet-500/30 text-violet-300',
};

const AITeam = () => {
  const [data, setData] = useState({
    convos: [], approvals: [], memories: [], trends: [],
    counts: { approvals: 0, memories: 0, trends: 0 },
  });
  const [loading, setLoading] = useState(true);
  const [quickPrompt, setQuickPrompt] = useState('');
  const [conveneOpen, setConveneOpen] = useState(false);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/ai/agent/conversations/recent?limit=5`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/approvals`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/memory/list?limit=8`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/trends/recent?limit=5`, { withCredentials: true }).catch(() => null),
    ]).then(([c, a, m, t]) => {
      setData({
        convos:    c?.data?.conversations || [],
        approvals: a?.data?.posts || [],
        memories:  m?.data?.memories || [],
        trends:    t?.data?.trends || [],
        counts: {
          approvals: (a?.data?.posts || []).length,
          memories:  m?.data?.total || (m?.data?.memories || []).length,
          trends:    t?.data?.count || (t?.data?.trends || []).length,
        },
      });
    }).finally(() => setLoading(false));
  }, []);

  return (
    <DashboardLayout
      title="AI Growth Team"
      subtitle="One pane of glass: what your specialists are doing, what's waiting for your sign-off, and what they're learning."
    >
      <div className="cv-dash-scope" data-testid="ai-team-page">

        {/* Quick prompt hero */}
        <div className="grid lg:grid-cols-[1fr_auto] gap-4 mb-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const p = quickPrompt.trim();
              if (!p) return;
              window.location.href = `/dashboard/agent/strategy?q=${encodeURIComponent(p)}`;
            }}
            className="cv-glass rounded-2xl p-5 border-violet-500/20"
            data-testid="ai-team-quick-prompt"
          >
            <div className="flex items-center gap-2 mb-2">
              <Sparkles size={14} className="text-violet-400" />
              <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-400 font-semibold">Ask Atlas</span>
            </div>
            <div className="flex gap-2">
              <input
                value={quickPrompt}
                onChange={(e) => setQuickPrompt(e.target.value)}
                placeholder="What should the team focus on this week?"
                data-testid="ai-team-quick-prompt-input"
                className="flex-1 bg-zinc-900 border border-zinc-800 focus:border-violet-500/50 rounded-xl px-4 h-11 text-[14px] text-zinc-100 placeholder-zinc-500 outline-none"
              />
              <button
                type="submit"
                data-testid="ai-team-quick-prompt-submit"
                className="cv-btn-primary px-4 h-11 rounded-xl text-[13px] font-semibold inline-flex items-center gap-1.5"
              >
                Ask <ArrowUpRight size={14} />
              </button>
            </div>
          </form>

          {/* Convene CTA */}
          <button
            type="button"
            onClick={() => setConveneOpen(true)}
            data-testid="ai-team-convene-open"
            className="cv-glass rounded-2xl p-5 border-violet-500/20 text-left hover:border-violet-500/40 transition-colors group flex items-center gap-3"
          >
            <span className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-blue-500/10 border border-violet-500/30 inline-flex items-center justify-center shrink-0">
              <Users2 size={18} className="text-violet-300" />
            </span>
            <span>
              <span className="block text-[11px] uppercase tracking-[0.18em] text-zinc-400 font-semibold">Convene the team</span>
              <span className="block text-[13px] text-zinc-200 mt-0.5 group-hover:text-white">Get every specialist's take in one go →</span>
            </span>
          </button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-zinc-400" data-testid="ai-team-loading">
            <Loader2 className="animate-spin mx-auto" />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ActiveConvosPanel convos={data.convos} />
            <ApprovalsPanel posts={data.approvals} />
            <MemoryPanel memories={data.memories} count={data.counts.memories} />
            <TrendsPanel trends={data.trends} count={data.counts.trends} />
          </div>
        )}

        {conveneOpen && <ConveneModal onClose={() => setConveneOpen(false)} />}
      </div>
    </DashboardLayout>
  );
};

/* -------------------------------- Panels -------------------------------- */

const PanelHeader = ({ icon: Icon, title, count, href, ctaLabel = 'Open' }) => (
  <div className="flex items-center justify-between mb-3">
    <div className="flex items-center gap-2">
      <Icon size={14} className="text-zinc-400" />
      <span className="text-[13px] font-semibold text-white">{title}</span>
      {count != null && (
        <span className="text-[10.5px] font-bold text-zinc-400 bg-white/[0.04] border border-white/10 rounded-full px-2 py-0.5">
          {count}
        </span>
      )}
    </div>
    <Link to={href} className="text-[11.5px] text-violet-300 hover:text-violet-200 inline-flex items-center gap-0.5">
      {ctaLabel} <ArrowUpRight size={11} />
    </Link>
  </div>
);

const ActiveConvosPanel = ({ convos }) => (
  <div className="cv-glass rounded-2xl p-5" data-testid="ai-team-convos">
    <PanelHeader icon={MessageSquare} title="Active conversations" href="/dashboard/agent/strategy" ctaLabel="Open chat" />
    {convos.length === 0 ? (
      <EmptyState label="Start chatting with an agent — recent threads will appear here." />
    ) : (
      <div className="space-y-2">
        {convos.slice(0, 5).map((c) => (
          <Link
            key={`${c.agent_id}-${c.last_at}`}
            to={`/dashboard/agent/${c.agent_id}`}
            className="block p-2.5 rounded-lg hover:bg-white/[0.03] transition-colors"
            data-testid={`ai-team-convo-${c.agent_id}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${AGENT_TONES[c.agent_id] || 'bg-white/[0.04] border-white/10 text-zinc-300'}`}>
                {c.agent_name}
              </span>
              <span className="text-[10.5px] text-zinc-500"><Clock size={9} className="inline mr-1" />{relTime(c.last_at)}</span>
            </div>
            <div className="text-[13px] text-zinc-200 truncate" title={c.preview}>{c.preview}</div>
          </Link>
        ))}
      </div>
    )}
  </div>
);

const ApprovalsPanel = ({ posts }) => (
  <div className="cv-glass rounded-2xl p-5" data-testid="ai-team-approvals">
    <PanelHeader icon={ShieldCheck} title="Pending approvals" count={posts.length} href="/dashboard/approvals" ctaLabel="Review" />
    {posts.length === 0 ? (
      <EmptyState label="No posts waiting for your sign-off." />
    ) : (
      <div className="space-y-2">
        {posts.slice(0, 4).map((p) => (
          <Link
            key={p.id}
            to="/dashboard/approvals"
            className="block p-2.5 rounded-lg hover:bg-white/[0.03] transition-colors"
            data-testid={`ai-team-approval-${p.id}`}
          >
            <div className="flex items-center gap-1.5 mb-1 flex-wrap">
              {(p.platforms || []).slice(0, 3).map((pl) => (
                <span key={pl} className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 bg-white/[0.04] border border-white/10 rounded px-1.5 py-0.5">{pl}</span>
              ))}
              {p.scheduled_at && (
                <span className="text-[10.5px] text-zinc-500"><Clock size={9} className="inline mr-1" />{new Date(p.scheduled_at).toLocaleDateString()}</span>
              )}
            </div>
            <div className="text-[13px] text-zinc-200 line-clamp-2">{(p.content || '').slice(0, 180)}</div>
          </Link>
        ))}
      </div>
    )}
  </div>
);

const MemoryPanel = ({ memories, count }) => (
  <div className="cv-glass rounded-2xl p-5" data-testid="ai-team-memory">
    <PanelHeader icon={Brain} title="Recent memories" count={count} href="/dashboard/memory" ctaLabel="Manage" />
    {memories.length === 0 ? (
      <EmptyState label="No memories yet. Ingest your past posts to make agents niche-aware." />
    ) : (
      <div className="space-y-2">
        {memories.slice(0, 5).map((m) => (
          <div key={m.id} className="flex items-start gap-2 p-2.5 rounded-lg" data-testid={`ai-team-memory-${m.id}`}>
            <span className="shrink-0 text-[9.5px] uppercase tracking-wider font-bold text-violet-300 bg-violet-500/10 border border-violet-500/30 rounded px-1.5 py-0.5 mt-0.5">
              {m.kind}
            </span>
            <span className="flex-1 min-w-0 text-[12.5px] text-zinc-300 leading-snug line-clamp-2">{m.text}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);

const TrendsPanel = ({ trends, count }) => (
  <div className="cv-glass rounded-2xl p-5" data-testid="ai-team-trends">
    <PanelHeader icon={TrendingUp} title="Trend signals" count={count} href="/dashboard/trends" ctaLabel="See all" />
    {trends.length === 0 ? (
      <EmptyState label="No trends pulled yet. Visit Trends to seed the engine." />
    ) : (
      <div className="space-y-2">
        {trends.slice(0, 5).map((t) => {
          const isReddit = (t.meta?.source) === 'reddit';
          return (
            <a
              key={t.id}
              href={t.meta?.permalink || '#'}
              target={t.meta?.permalink ? '_blank' : undefined}
              rel="noopener noreferrer"
              className="flex items-start gap-2 p-2.5 rounded-lg hover:bg-white/[0.03] transition-colors"
              data-testid={`ai-team-trend-${t.id}`}
            >
              <span className={`shrink-0 text-[9.5px] uppercase tracking-wider font-bold rounded px-1.5 py-0.5 mt-0.5 border ${
                isReddit ? 'bg-orange-500/15 text-orange-300 border-orange-500/30' : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
              }`}>
                {isReddit ? 'Reddit' : 'GTrends'}
              </span>
              <span className="flex-1 min-w-0 text-[12.5px] text-zinc-300 leading-snug line-clamp-2">{t.text}</span>
            </a>
          );
        })}
      </div>
    )}
  </div>
);

const EmptyState = ({ label }) => (
  <div className="text-center py-4 text-[12px] text-zinc-500 leading-relaxed">
    <AlertCircle size={14} className="text-zinc-600 mx-auto mb-1.5" />
    {label}
  </div>
);

const relTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
};

/* --------------------------------- Convene modal -------------------------------- */
const CONVENE_AGENT_OPTIONS = [
  { id: 'research', name: 'Iris',   role: 'Research' },
  { id: 'sam',      name: 'Sam',    role: 'SEO' },
  { id: 'nova',     name: 'Nova',   role: 'Copy' },
  { id: 'kai',      name: 'Kai',    role: 'Analytics' },
  { id: 'angela',   name: 'Angela', role: 'Email' },
];

const ConveneModal = ({ onClose }) => {
  const [brief, setBrief] = useState('');
  const [picked, setPicked] = useState(['research', 'sam', 'nova']);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState([]); // [{agent_id, agent_name, status, answer}]
  const [summary, setSummary] = useState('');
  const [summarizer, setSummarizer] = useState(null);
  const [error, setError] = useState('');

  const togglePick = (id) => {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  };

  const run = async () => {
    const b = brief.trim();
    if (!b || picked.length === 0 || busy) return;
    setBusy(true);
    setProgress([]);
    setSummary('');
    setError('');
    try {
      const resp = await fetch(`${API}/ai/agent/convene/stream`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ message: b, agents: picked, mode: 'fast' }),
      });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const j = await resp.json(); msg = j?.detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const rec = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          if (!rec.trim() || rec.startsWith(':')) continue;
          let ev = null, data = null;
          for (const line of rec.split('\n')) {
            if (line.startsWith('event: ')) ev = line.slice(7).trim();
            else if (line.startsWith('data: ')) {
              try { data = JSON.parse(line.slice(6)); } catch { data = null; }
            }
          }
          if (ev === 'started') {
            setProgress((data?.chain || []).map((a) => ({ ...a, status: 'pending' })));
            setSummarizer({ agent_id: data?.summarizer_id, agent_name: data?.summarizer_name });
          } else if (ev === 'agent_started') {
            setProgress((p) => p.map((row) =>
              row.agent_id === data.agent_id ? { ...row, status: 'running' } : row,
            ));
          } else if (ev === 'agent_done') {
            setProgress((p) => p.map((row) =>
              row.agent_id === data.agent_id ? { ...row, status: 'done', answer: data.answer } : row,
            ));
          } else if (ev === 'summarizing') {
            setSummarizer({ agent_id: data.agent_id, agent_name: data.agent_name, busy: true });
          } else if (ev === 'complete') {
            setSummary(data.summary || '');
            setSummarizer((s) => ({ ...(s || {}), busy: false }));
          } else if (ev === 'error') {
            throw new Error(data?.message || 'Stream error');
          }
        }
      }
    } catch (e) {
      setError(e.message || String(e));
    }
    setBusy(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
      data-testid="ai-team-convene-modal"
    >
      <div
        className="bg-zinc-950 border border-zinc-800 rounded-2xl max-w-3xl w-full my-8 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Users2 size={16} className="text-violet-400" />
            <span className="text-[14px] font-semibold text-white">Convene the team</span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200" data-testid="ai-team-convene-close">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Brief input */}
          <div>
            <label className="text-[11px] uppercase tracking-[0.18em] text-zinc-400 font-semibold">Your brief</label>
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              rows={3}
              disabled={busy}
              placeholder="e.g., Launch plan for a new AI marketing SaaS targeting indie creators."
              data-testid="ai-team-convene-brief"
              className="mt-1.5 w-full bg-zinc-900 border border-zinc-800 focus:border-violet-500/50 rounded-xl p-3 text-[14px] text-zinc-100 placeholder-zinc-500 outline-none resize-none"
            />
          </div>

          {/* Agent picker */}
          <div>
            <label className="text-[11px] uppercase tracking-[0.18em] text-zinc-400 font-semibold">Specialists to consult <span className="text-zinc-600 normal-case tracking-normal">· {picked.length} selected</span></label>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {CONVENE_AGENT_OPTIONS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  disabled={busy}
                  onClick={() => togglePick(a.id)}
                  data-testid={`ai-team-convene-pick-${a.id}`}
                  className={`text-[12px] font-semibold rounded-full px-3 h-7 border transition-colors ${
                    picked.includes(a.id)
                      ? 'bg-violet-500/20 text-violet-200 border-violet-500/40'
                      : 'bg-white/[0.04] text-zinc-400 border-white/10 hover:text-zinc-200'
                  }`}
                >
                  {a.name} <span className="opacity-50">· {a.role}</span>
                </button>
              ))}
            </div>
            <p className="text-[11px] text-zinc-500 mt-1.5">Atlas will synthesize a single executive summary at the end.</p>
          </div>

          {/* Run button */}
          {!busy && progress.length === 0 && (
            <button
              type="button"
              disabled={!brief.trim() || picked.length === 0}
              onClick={run}
              data-testid="ai-team-convene-run"
              className={`w-full h-11 rounded-xl text-[13px] font-semibold ${
                brief.trim() && picked.length > 0 ? 'cv-btn-primary' : 'bg-white/[0.04] text-zinc-500 cursor-not-allowed'
              }`}
            >
              Convene {picked.length} specialist{picked.length === 1 ? '' : 's'}
            </button>
          )}

          {/* Live progress */}
          {progress.length > 0 && (
            <div className="space-y-2.5" data-testid="ai-team-convene-progress">
              {progress.map((row) => (
                <ProgressRow key={row.agent_id} row={row} />
              ))}
              {summarizer && (
                <div className="flex items-center gap-2 text-[12.5px] mt-3 pt-3 border-t border-zinc-800">
                  {summarizer.busy ? <Loader2 size={13} className="animate-spin text-violet-400" /> : summary ? <Check size={13} className="text-emerald-400" /> : <Hourglass size={13} className="text-zinc-500" />}
                  <span className="text-zinc-400">
                    <strong className="text-zinc-200">{summarizer.agent_name}</strong>
                    {summarizer.busy ? ' is synthesizing the executive summary…' : summary ? ' delivered the executive summary' : ' waiting…'}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Summary panel */}
          {summary && (
            <div className="rounded-xl border border-violet-500/30 bg-violet-500/[0.04] p-4" data-testid="ai-team-convene-summary">
              <div className="flex items-center gap-1.5 mb-2">
                <Sparkles size={13} className="text-violet-400" />
                <span className="text-[11px] uppercase tracking-[0.18em] text-violet-300 font-semibold">Executive summary</span>
              </div>
              <pre className="text-[13px] text-zinc-200 leading-relaxed whitespace-pre-wrap font-sans">{summary}</pre>
            </div>
          )}

          {error && (
            <div className="text-[12.5px] text-rose-300 bg-rose-500/[0.08] border border-rose-500/30 rounded-lg p-3" data-testid="ai-team-convene-error">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const ProgressRow = ({ row }) => {
  const Icon = row.status === 'done' ? Check : row.status === 'running' ? Loader2 : Hourglass;
  const iconCls =
    row.status === 'done' ? 'text-emerald-400'
    : row.status === 'running' ? 'text-violet-400 animate-spin'
    : 'text-zinc-500';
  return (
    <div
      className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3"
      data-testid={`ai-team-convene-row-${row.agent_id}`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={13} className={iconCls} />
        <span className={`text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${AGENT_TONES[row.agent_id] || 'bg-white/[0.04] border-white/10 text-zinc-300'}`}>
          {row.agent_name}
        </span>
        <span className="text-[11px] text-zinc-500 capitalize">{row.status}</span>
      </div>
      {row.answer && (
        <pre className="text-[12.5px] text-zinc-300 leading-relaxed whitespace-pre-wrap font-sans line-clamp-6">{row.answer}</pre>
      )}
    </div>
  );
};

export default AITeam;
