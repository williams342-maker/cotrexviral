import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Sparkles, Loader2, Layers, Eye, Heart, MousePointer,
  Inbox, Calendar as CalendarIcon, FileText, Play, Edit3, Save, X,
  Send, TrendingUp, Activity, ChevronDown, ChevronUp, GitCompare,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import RunOSModal from '../../components/RunOSModal';
import { wordDiff } from '../../utils/diff';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/campaigns/:id — single campaign detail page.

   Source of truth: GET /api/campaigns/{id} returns
   {...campaignFields, plan_text, posts:[...], metrics:{...}}.

   Layout:
     header        name + status pill + goal + back nav + run-OS CTA
     metrics row   5 KPI tiles (posts, impressions, engagement, clicks, leads)
     pillars       audience + content pillars + platforms (read-only chips)
     plan section  Atlas-generated markdown plan + "Generate" / "Regenerate" CTA
     posts list    every post linked to the campaign, sorted by scheduled_at */


const STATUS_PILL = {
  draft:     'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  active:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  completed: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  archived:  'bg-zinc-700/30 text-zinc-500 border-zinc-700/40',
};

const STATUS_OPTIONS = ['draft', 'active', 'completed', 'archived'];


// Minimal markdown renderer for the Atlas plan output. Handles `##`
// headings and `-` bullets so the result is scannable without pulling
// in a full markdown lib for one screen.
const PlanMarkdown = ({ text }) => {
  if (!text) return null;
  const lines = text.split('\n');
  const blocks = [];
  let current = [];
  const flush = () => {
    if (current.length === 0) return;
    blocks.push({ type: 'para', lines: current });
    current = [];
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith('## ')) {
      flush();
      blocks.push({ type: 'h2', text: line.slice(3).trim() });
    } else if (/^\s*[-*]\s+/.test(line)) {
      flush();
      // Coalesce consecutive bullets into a list block.
      const text = line.replace(/^\s*[-*]\s+/, '');
      const prev = blocks[blocks.length - 1];
      if (prev && prev.type === 'list') prev.items.push(text);
      else blocks.push({ type: 'list', items: [text] });
    } else if (line === '') {
      flush();
    } else {
      current.push(line);
    }
  }
  flush();

  return (
    <div className="space-y-3 text-sm text-zinc-200 leading-relaxed">
      {blocks.map((b, i) => {
        if (b.type === 'h2') {
          return (
            <h3 key={i} className="text-[13px] uppercase tracking-widest text-violet-300 font-bold mt-4 first:mt-0">
              {b.text}
            </h3>
          );
        }
        if (b.type === 'list') {
          return (
            <ul key={i} className="space-y-1 list-disc list-inside marker:text-violet-400">
              {b.items.map((it, j) => <li key={j} className="leading-snug">{it}</li>)}
            </ul>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">{b.lines.join('\n')}</p>
        );
      })}
    </div>
  );
};


// Compact KPI tile for the metrics row.
const KpiTile = ({ icon: Icon, label, value, accent = 'violet', testid }) => {
  const ring = {
    violet:  'border-violet-500/30 bg-violet-500/10 text-violet-300',
    cyan:    'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
    emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
    rose:    'border-rose-500/30 bg-rose-500/10 text-rose-300',
    amber:   'border-amber-500/30 bg-amber-500/10 text-amber-300',
  }[accent];
  return (
    <div data-testid={testid} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-semibold">{label}</div>
          <div className="text-xl font-bold tabular-nums text-white mt-1">{value}</div>
        </div>
        <span className={`shrink-0 w-7 h-7 rounded-md border flex items-center justify-center ${ring}`}>
          <Icon size={13} />
        </span>
      </div>
    </div>
  );
};


const CampaignDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editFields, setEditFields] = useState({ audience: '', content_pillars: '', notes: '' });
  const [runOpen, setRunOpen] = useState(false);
  // Run history for this campaign — lazy-loaded the first time the
  // user expands the accordion to save a roundtrip on initial paint.
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState(null);  // null = not loaded
  const [historyLoading, setHistoryLoading] = useState(false);
  // Set of run-ids currently expanded inside the accordion.
  const [expandedRuns, setExpandedRuns] = useState(new Set());
  // Set of run-ids currently in "diff vs. latest" mode (only valid
  // when there IS a latest_run_summary to diff against).
  const [diffRuns, setDiffRuns] = useState(new Set());
  // Holds the brief to pre-seed into the Run modal when the user hits
  // "Re-run with this" on a historical row. Falls back to the default
  // 30-day brief when null.
  const [runOverrideBrief, setRunOverrideBrief] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/campaigns/${id}`, { withCredentials: true });
      setData(r.data);
      setEditFields({
        audience: r.data.audience || '',
        content_pillars: (r.data.content_pillars || []).join(', '),
        notes: r.data.notes || '',
      });
    } catch (e) {
      if (e.response?.status === 404) {
        toast({ title: 'Campaign not found' });
        navigate('/dashboard/command-center');
      } else {
        toast({ title: 'Could not load campaign', description: e.message });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-line */ }, [id]);

  // Lazy-load run history when the accordion is first opened.
  const toggleHistory = async () => {
    const next = !historyOpen;
    setHistoryOpen(next);
    if (next && history === null && !historyLoading) {
      setHistoryLoading(true);
      try {
        const r = await axios.get(`${API}/marketing-os/runs?campaign_id=${id}&limit=10`, { withCredentials: true });
        setHistory(r.data.runs || []);
      } catch (e) {
        setHistory([]);
        toast({ title: 'Could not load history', description: e.response?.data?.detail || e.message });
      } finally {
        setHistoryLoading(false);
      }
    }
  };

  const toggleRunExpand = (rid) => {
    setExpandedRuns((prev) => {
      const next = new Set(prev);
      if (next.has(rid)) next.delete(rid); else next.add(rid);
      return next;
    });
  };

  const toggleDiff = (rid) => {
    setDiffRuns((prev) => {
      const next = new Set(prev);
      if (next.has(rid)) next.delete(rid); else next.add(rid);
      return next;
    });
    // Auto-expand the row when switching to diff mode.
    setExpandedRuns((prev) => {
      const next = new Set(prev);
      next.add(rid);
      return next;
    });
  };

  const reRunHistorical = (row) => {
    setRunOverrideBrief(row.brief || '');
    setRunOpen(true);
  };

  const fmt = (n) => {
    if (n == null) return '0';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };

  const generatePlan = async () => {
    setGenerating(true);
    try {
      await axios.post(`${API}/campaigns/${id}/plan`, {}, { withCredentials: true });
      toast({ title: 'Plan generated', description: 'Atlas has written the campaign brief.' });
      load();
    } catch (e) {
      toast({
        title: 'Could not generate plan',
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setGenerating(false);
    }
  };

  const updateStatus = async (next) => {
    try {
      await axios.patch(`${API}/campaigns/${id}`, { status: next }, { withCredentials: true });
      toast({ title: 'Status updated', description: `Campaign → ${next}` });
      load();
    } catch (e) {
      toast({ title: 'Could not update status', description: e.response?.data?.detail || e.message });
    }
  };

  const saveEdits = async () => {
    const payload = {};
    if (editFields.audience !== (data.audience || '')) payload.audience = editFields.audience;
    if (editFields.notes !== (data.notes || '')) payload.notes = editFields.notes;
    const pillars = editFields.content_pillars
      .split(',').map((s) => s.trim()).filter(Boolean).slice(0, 6);
    const currentPillars = (data.content_pillars || []).join(',');
    if (pillars.join(',') !== currentPillars) payload.content_pillars = pillars;
    if (Object.keys(payload).length === 0) {
      setEditMode(false);
      return;
    }
    try {
      await axios.patch(`${API}/campaigns/${id}`, payload, { withCredentials: true });
      toast({ title: 'Campaign updated' });
      setEditMode(false);
      load();
    } catch (e) {
      toast({ title: 'Could not save', description: e.response?.data?.detail || e.message });
    }
  };

  const sortedPosts = useMemo(() => {
    return [...(data?.posts || [])].sort((a, b) => {
      const ax = a.scheduled_at ? new Date(a.scheduled_at).getTime() : 0;
      const bx = b.scheduled_at ? new Date(b.scheduled_at).getTime() : 0;
      return ax - bx;
    });
  }, [data?.posts]);

  if (loading) {
    return (
      <DashboardLayout title="Campaign" subtitle="Loading…">
        <div className="flex items-center justify-center py-20 text-zinc-500">
          <Loader2 size={20} className="animate-spin mr-2" /> Loading campaign…
        </div>
      </DashboardLayout>
    );
  }
  if (!data) return null;

  const m = data.metrics || {};

  return (
    <DashboardLayout title={data.name} subtitle={`Campaign · ${data.goal}`}>
      <div className="space-y-6" data-testid="campaign-detail-page">
        {/* Header bar */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard/command-center')}
              className="w-9 h-9 rounded-lg border border-white/10 bg-white/[0.02] hover:bg-white/5 flex items-center justify-center text-zinc-400 hover:text-white"
              data-testid="campaign-back-btn"
              aria-label="Back to Command Center"
            >
              <ArrowLeft size={16} />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-white" data-testid="campaign-name">{data.name}</h1>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold uppercase tracking-wider ${STATUS_PILL[data.status] || STATUS_PILL.draft}`} data-testid="campaign-status">
                  {data.status}
                </span>
                <span className="text-xs text-zinc-500">Goal: {data.custom_goal || data.goal}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={data.status}
              onChange={(e) => updateStatus(e.target.value)}
              className="bg-zinc-900 border border-white/10 rounded-lg px-3 h-9 text-xs text-zinc-200 focus:outline-none focus:border-violet-500/40"
              data-testid="campaign-status-select"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button
              onClick={() => navigate(`/dashboard/trends?campaign_id=${id}`)}
              className="h-9 px-3 rounded-lg border border-white/10 bg-white/[0.02] hover:bg-white/5 text-zinc-200 text-xs font-medium flex items-center gap-1.5"
              data-testid="campaign-trends-btn"
            >
              <TrendingUp size={12} /> Hunt signals
            </button>
            <button
              onClick={() => setRunOpen(true)}
              className="h-9 px-3 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium flex items-center gap-1.5 shadow-[0_4px_20px_rgb(124_58_237_/_0.35)]"
              data-testid="campaign-run-os-btn"
            >
              <Play size={12} /> Run the OS
            </button>
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <KpiTile icon={FileText}      label="Posts"       value={fmt(m.total_posts)}  accent="violet" testid="kpi-posts" />
          <KpiTile icon={Eye}           label="Impressions" value={fmt(m.impressions)}  accent="cyan"   testid="kpi-impressions" />
          <KpiTile icon={Heart}         label="Engagement"  value={fmt(m.engagement)}   accent="rose"   testid="kpi-engagement" />
          <KpiTile icon={MousePointer}  label="Clicks"      value={fmt(m.clicks)}       accent="amber"  testid="kpi-clicks" />
          <KpiTile icon={Inbox}         label="Leads"       value={fmt(m.leads)}        accent="emerald" testid="kpi-leads" />
        </div>

        {/* Audience / Pillars / Platforms */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">Brief</h3>
            {!editMode ? (
              <button
                onClick={() => setEditMode(true)}
                className="text-xs text-zinc-400 hover:text-white flex items-center gap-1"
                data-testid="campaign-edit-btn"
              >
                <Edit3 size={12} /> Edit
              </button>
            ) : (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => { setEditMode(false); setEditFields({ audience: data.audience || '', content_pillars: (data.content_pillars || []).join(', '), notes: data.notes || '' }); }}
                  className="text-xs text-zinc-400 hover:text-white flex items-center gap-1 px-2 py-1 rounded border border-white/10"
                >
                  <X size={12} /> Cancel
                </button>
                <button
                  onClick={saveEdits}
                  className="text-xs text-white flex items-center gap-1 px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500"
                  data-testid="campaign-save-btn"
                >
                  <Save size={12} /> Save
                </button>
              </div>
            )}
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5">Audience</div>
              {editMode ? (
                <textarea
                  value={editFields.audience}
                  onChange={(e) => setEditFields((f) => ({ ...f, audience: e.target.value }))}
                  rows={3}
                  className="w-full bg-zinc-900 border border-white/10 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500/40"
                  placeholder="Who's this for?"
                />
              ) : (
                <div className="text-xs text-zinc-300 leading-snug" data-testid="campaign-audience">
                  {data.audience || <span className="text-zinc-600 italic">Not set</span>}
                </div>
              )}
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5">Content pillars</div>
              {editMode ? (
                <input
                  value={editFields.content_pillars}
                  onChange={(e) => setEditFields((f) => ({ ...f, content_pillars: e.target.value }))}
                  className="w-full bg-zinc-900 border border-white/10 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500/40"
                  placeholder="comma, separated, themes"
                />
              ) : (data.content_pillars || []).length > 0 ? (
                <div className="flex flex-wrap gap-1" data-testid="campaign-pillars">
                  {data.content_pillars.map((p) => (
                    <span key={p} className="text-[10px] px-1.5 py-0.5 rounded border border-violet-500/30 bg-violet-500/10 text-violet-300">{p}</span>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-zinc-600 italic">Not set</div>
              )}
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5">Platforms</div>
              {(data.platforms || []).length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {data.platforms.map((p) => (
                    <span key={p} className="text-[10px] px-1.5 py-0.5 rounded border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 uppercase tracking-wider">{p}</span>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-zinc-600 italic">Any</div>
              )}
            </div>
          </div>

          {(editMode || data.notes) && (
            <div className="mt-3 pt-3 border-t border-white/5">
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5">Notes</div>
              {editMode ? (
                <textarea
                  value={editFields.notes}
                  onChange={(e) => setEditFields((f) => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  className="w-full bg-zinc-900 border border-white/10 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-cyan-500/40"
                />
              ) : (
                <div className="text-xs text-zinc-400 italic leading-snug">{data.notes}</div>
              )}
            </div>
          )}
        </div>

        {/* Latest OS run pin — set by `marketing_os.run_marketing_os`
            whenever a run completes against this campaign. Gives the
            user a one-glance "what did the team last decide" surface
            without digging through the runs history. */}
        {data.latest_run_summary && (
          <div
            className="rounded-2xl border border-violet-500/20 bg-violet-500/[0.04] p-5"
            data-testid="campaign-latest-run"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
                  <Activity size={13} />
                </span>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-violet-300 font-bold">Latest OS run</div>
                  <div className="text-[11px] text-zinc-500">
                    {data.latest_run_at ? new Date(data.latest_run_at).toLocaleString() : ''}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setRunOpen(true)}
                className="text-xs px-2.5 py-1 rounded-md border border-violet-500/30 text-violet-300 hover:bg-violet-500/15 flex items-center gap-1"
                data-testid="campaign-latest-run-rerun"
              >
                <Play size={11} /> Re-run
              </button>
            </div>
            <div className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap line-clamp-[10]" data-testid="campaign-latest-run-summary">
              {data.latest_run_summary}
            </div>

            {/* Run history accordion — lazy-loaded, lists previous 10
                runs for this campaign so the team can compare what they
                said yesterday vs. last week. */}
            <div className="mt-4 pt-3 border-t border-violet-500/10">
              <button
                type="button"
                onClick={toggleHistory}
                className="w-full flex items-center gap-2 text-left text-xs text-zinc-400 hover:text-white"
                data-testid="campaign-history-toggle"
              >
                {historyOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                <span className="font-semibold uppercase tracking-widest text-[10px]">
                  Previous OS runs
                </span>
                {history && history.length > 0 && (
                  <span className="text-[10px] text-zinc-500">· {history.length}</span>
                )}
              </button>

              {historyOpen && (
                <div className="mt-3 space-y-1.5" data-testid="campaign-history-list">
                  {historyLoading && (
                    <div className="text-[11px] text-zinc-500 italic flex items-center gap-1.5 py-1">
                      <Loader2 size={11} className="animate-spin" /> Loading…
                    </div>
                  )}
                  {history && history.length === 0 && (
                    <div className="text-[11px] text-zinc-500 italic py-1">
                      No earlier runs. Hit <span className="text-violet-300">Re-run</span> above to add one.
                    </div>
                  )}
                  {history && history
                    // Hide the run that's currently pinned as the "latest"
                    // — it's already shown at the top of the card.
                    .filter((r) => r.id !== data.latest_run_id)
                    .slice(0, 5)
                    .map((r) => {
                      const open = expandedRuns.has(r.id);
                      const diffOn = diffRuns.has(r.id) && !!data.latest_run_summary;
                      const diffTokens = diffOn
                        ? wordDiff(r.summary || '', data.latest_run_summary || '')
                        : null;
                      return (
                        <div
                          key={r.id}
                          className="rounded-md border border-white/5 bg-zinc-950/40"
                          data-testid={`campaign-history-row-${r.id}`}
                        >
                          <button
                            type="button"
                            onClick={() => toggleRunExpand(r.id)}
                            className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-white/[0.02]"
                          >
                            {open ? <ChevronUp size={11} className="text-zinc-500" /> : <ChevronDown size={11} className="text-zinc-500" />}
                            <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold uppercase tracking-wider ${
                              r.status === 'completed'
                                ? 'border-emerald-500/30 text-emerald-300 bg-emerald-500/10'
                                : 'border-rose-500/30 text-rose-300 bg-rose-500/10'
                            }`}>{r.status}</span>
                            <span className="text-[11px] text-zinc-300 truncate flex-1">
                              {(r.summary || r.brief || '(no summary)').replace(/\n/g, ' ').slice(0, 90)}
                            </span>
                            <span className="text-[10px] text-zinc-500 shrink-0">
                              {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                            </span>
                          </button>
                          {open && (
                            <div className="px-3 pb-3 -mt-1 space-y-2.5">
                              {/* Action row: diff toggle + re-run */}
                              <div className="flex items-center gap-1.5 pt-1">
                                {data.latest_run_summary && r.summary && (
                                  <button
                                    type="button"
                                    onClick={() => toggleDiff(r.id)}
                                    className={`text-[10px] px-2 py-0.5 rounded border flex items-center gap-1 ${
                                      diffOn
                                        ? 'border-violet-500/50 bg-violet-500/15 text-violet-200'
                                        : 'border-white/10 text-zinc-400 hover:bg-white/5'
                                    }`}
                                    data-testid={`history-diff-toggle-${r.id}`}
                                    title="Compare this run's summary against the latest pinned summary"
                                  >
                                    <GitCompare size={10} /> {diffOn ? 'Diff on' : 'Diff vs. latest'}
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => reRunHistorical(r)}
                                  className="text-[10px] px-2 py-0.5 rounded border border-violet-500/40 bg-violet-500/10 text-violet-300 hover:bg-violet-500/20 flex items-center gap-1 ml-auto"
                                  data-testid={`history-rerun-${r.id}`}
                                  title="Re-open the Run modal pre-seeded with this brief"
                                >
                                  <Play size={10} /> Re-run with this
                                </button>
                              </div>

                              {/* Body — either the plain brief+summary or the diff view */}
                              {diffOn ? (
                                <div>
                                  <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1 flex items-center gap-2">
                                    <span>Diff</span>
                                    <span className="text-emerald-400">+ added in latest</span>
                                    <span className="text-rose-400">– removed since this run</span>
                                  </div>
                                  <div
                                    className="text-xs leading-relaxed whitespace-pre-wrap font-mono rounded-md border border-white/5 bg-black/30 p-2.5"
                                    data-testid={`history-diff-body-${r.id}`}
                                  >
                                    {diffTokens.map((tk, i) => {
                                      if (tk.type === 'eq')
                                        return <span key={i} className="text-zinc-400">{tk.text}</span>;
                                      if (tk.type === 'add')
                                        return <span key={i} className="text-emerald-300 bg-emerald-500/10 rounded-sm">{tk.text}</span>;
                                      return <span key={i} className="text-rose-300 bg-rose-500/10 line-through rounded-sm">{tk.text}</span>;
                                    })}
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <div>
                                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">
                                      Brief
                                    </div>
                                    <div className="text-[11px] text-zinc-400 italic leading-relaxed whitespace-pre-wrap">
                                      {r.brief || '(no brief)'}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-1">
                                      Summary
                                    </div>
                                    <div className="text-xs text-zinc-200 leading-relaxed whitespace-pre-wrap">
                                      {r.summary || '(no summary — chain may have failed)'}
                                    </div>
                                  </div>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Atlas's plan */}
        <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-600/5 via-zinc-950/30 to-zinc-950/30 p-5" data-testid="campaign-plan-section">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Sparkles size={14} className="text-violet-300" /> Atlas's campaign plan
            </h3>
            <button
              onClick={generatePlan}
              disabled={generating}
              className="text-xs px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-60 flex items-center gap-1.5"
              data-testid="campaign-generate-plan-btn"
            >
              {generating ? (
                <><Loader2 size={12} className="animate-spin" /> Atlas is writing…</>
              ) : data.plan_text ? (
                <><Sparkles size={12} /> Regenerate</>
              ) : (
                <><Play size={12} /> Generate plan</>
              )}
            </button>
          </div>

          {data.plan_text ? (
            <div data-testid="campaign-plan-text" className="prose-zinc">
              <PlanMarkdown text={data.plan_text} />
            </div>
          ) : (
            <div className="text-xs text-zinc-500 italic py-2" data-testid="campaign-plan-empty">
              No plan yet. Click "Generate plan" — Atlas will produce a 30/60/90-day brief with audience cuts, hook angles, cadence, and success thresholds.
            </div>
          )}
        </div>

        {/* Linked posts */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <Layers size={14} className="text-cyan-300" /> Linked posts
              <span className="text-xs text-zinc-500 font-normal">({sortedPosts.length})</span>
            </h3>
            <button
              onClick={() => navigate(`/dashboard/compose?campaign_id=${id}`)}
              className="text-xs px-2.5 py-1 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/25 flex items-center gap-1"
              data-testid="campaign-compose-btn"
            >
              <Send size={11} /> New post
            </button>
          </div>

          {sortedPosts.length === 0 ? (
            <div className="text-xs text-zinc-500 italic py-3" data-testid="campaign-posts-empty">
              No posts linked yet. Click "New post" to draft one against this campaign brief.
            </div>
          ) : (
            <div className="space-y-2" data-testid="campaign-posts-list">
              {sortedPosts.map((p) => (
                <div key={p.id} className="rounded-lg border border-white/5 bg-zinc-950/40 p-3" data-testid={`campaign-post-${p.id}`}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                      p.status === 'published' ? 'border-emerald-500/30 text-emerald-300 bg-emerald-500/10' :
                      p.status === 'scheduled' ? 'border-cyan-500/30 text-cyan-300 bg-cyan-500/10' :
                      p.status === 'pending_approval' ? 'border-amber-500/30 text-amber-300 bg-amber-500/10' :
                      'border-zinc-500/30 text-zinc-400 bg-zinc-500/10'
                    } uppercase tracking-wider font-semibold`}>
                      {p.status || 'draft'}
                    </span>
                    {(p.platforms || []).map((pf) => (
                      <span key={pf} className="text-[9px] text-zinc-500 uppercase tracking-wider">{pf}</span>
                    ))}
                    <span className="ml-auto text-[10px] text-zinc-500 flex items-center gap-1">
                      <CalendarIcon size={9} />
                      {p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : 'No date'}
                    </span>
                  </div>
                  <div className="text-xs text-zinc-300 leading-snug line-clamp-3">
                    {p.content || '(no content)'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <RunOSModal
        open={runOpen}
        onClose={() => { setRunOpen(false); setRunOverrideBrief(null); }}
        onComplete={load}
        campaignId={data.id}
        campaignName={data.name}
        initialBrief={
          runOverrideBrief != null
            ? runOverrideBrief
            : `Plan the next 30 days of marketing for the "${data.name}" campaign. Goal: ${data.custom_goal || data.goal}.${data.audience ? ` Audience: ${data.audience}.` : ''}`
        }
      />
    </DashboardLayout>
  );
};

export default CampaignDetail;
