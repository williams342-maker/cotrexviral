import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Command, Sparkles, Zap, TrendingUp, CheckSquare, Trophy,
  ChevronRight, Play, Activity, Loader2, Flame, ArrowRight, Bot,
  Layers, Users, BarChart3, Megaphone, Brain, Plus,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/command-center — Marketing OS Command Center.

   The autonomous-marketing-os surface: it shows the user what their
   software is *running* right now (active campaigns), what *signals* it
   detected, what's *waiting on approval*, what just *won*, and lets them
   *kick off the 5-role chain* on a brand-new brief. */


// Compact stat tile used in the top row.
const StatTile = ({ icon: Icon, label, value, accent = 'violet', testid }) => {
  const ring = {
    violet: 'border-violet-500/30 bg-violet-500/10 text-violet-300',
    cyan:   'border-cyan-500/30 bg-cyan-500/10 text-cyan-300',
    amber:  'border-amber-500/30 bg-amber-500/10 text-amber-300',
    emerald:'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  }[accent];
  return (
    <div data-testid={testid}
      className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-md">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-400 font-semibold">{label}</div>
          <div className="text-3xl font-bold tabular-nums text-white mt-2">{value}</div>
        </div>
        <span className={`shrink-0 w-9 h-9 rounded-lg border flex items-center justify-center ${ring}`}>
          <Icon size={18} />
        </span>
      </div>
    </div>
  );
};


// Pill rendering for signal recommended-agent.
const AGENT_PILL = {
  nova:   { label: 'Nova',   cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  sam:    { label: 'Sam',    cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  kai:    { label: 'Kai',    cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  angela: { label: 'Angela', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
};

const URGENCY_STYLE = {
  now:        { label: 'ACT NOW',     cls: 'bg-rose-500/20 text-rose-300 border-rose-500/40' },
  this_week:  { label: 'THIS WEEK',   cls: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
  monitor:    { label: 'MONITOR',     cls: 'bg-zinc-500/20 text-zinc-300 border-zinc-500/30' },
};


// Status badge for campaigns.
const STATUS_PILL = {
  draft:     'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
  active:    'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  completed: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  archived:  'bg-zinc-700/30 text-zinc-500 border-zinc-700/40',
};


// ----------------------------------------------------------------------
// Run Modal — kicks off the 5-role chain via SSE
// ----------------------------------------------------------------------
const RunModal = ({ open, onClose, onComplete }) => {
  const [brief, setBrief] = useState('');
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]); // [{role, agent_id, agent_name, status, answer}]
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const { toast } = useToast();

  if (!open) return null;

  const reset = () => {
    setProgress([]); setSummary(''); setError(''); setRunning(false);
  };

  const start = async () => {
    if (!brief.trim()) { toast({ title: 'Brief required', description: 'Tell the OS what to ship.' }); return; }
    reset();
    setRunning(true);
    setProgress([{ role: 'Boot',  status: 'starting', label: 'Booting Marketing OS' }]);
    try {
      const res = await fetch(`${API}/marketing-os/run/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ brief: brief.trim() }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`HTTP ${res.status}: ${t.slice(0, 200)}`);
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        // Parse SSE event blocks (split on blank line)
        const blocks = buf.split('\n\n');
        buf = blocks.pop(); // keep trailing partial
        for (const block of blocks) {
          const lines = block.split('\n');
          let event = 'message';
          let dataStr = '';
          for (const l of lines) {
            if (l.startsWith('event:')) event = l.slice(6).trim();
            else if (l.startsWith('data:')) dataStr += l.slice(5).trim();
          }
          if (!dataStr || event === 'keepalive') continue;
          let data;
          try { data = JSON.parse(dataStr); } catch { continue; }
          if (event === 'os_started') {
            setProgress([
              { role: 'chain', label: `Chain: ${data.chain.join(' → ')} → ${data.summarizer}`, status: 'info' },
            ]);
          } else if (event === 'agent_started') {
            setProgress((p) => [...p, {
              agent_id: data.agent_id, agent_name: data.agent_name,
              status: 'running', step: data.step, total: data.total,
            }]);
          } else if (event === 'agent_done') {
            setProgress((p) => p.map((r) =>
              (r.agent_id === data.agent_id && r.status === 'running')
                ? { ...r, status: 'done', answer: data.answer }
                : r,
            ));
          } else if (event === 'summarizing') {
            setProgress((p) => [...p, {
              agent_id: data.agent_id, agent_name: data.agent_name,
              status: 'summarizing',
            }]);
          } else if (event === 'complete') {
            setSummary(data.summary || '');
            setProgress((p) => p.map((r) =>
              r.status === 'summarizing' ? { ...r, status: 'done', answer: data.summary } : r,
            ));
          } else if (event === 'error') {
            setError(data.message || 'Run failed');
          }
        }
      }
      setRunning(false);
      onComplete && onComplete();
    } catch (e) {
      setError(e.message);
      setRunning(false);
    }
  };

  const close = () => { if (running) return; reset(); setBrief(''); onClose(); };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={close} data-testid="os-run-modal">
      <div className="w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl border border-violet-500/30 bg-zinc-950 p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-violet-400 font-bold mb-1">5-Role Chain</div>
            <h2 className="text-2xl font-bold text-white">Run Marketing OS</h2>
            <p className="text-xs text-zinc-400 mt-1">Strategy → Intelligence → Content → Distribution → Analytics</p>
          </div>
          <button onClick={close} className="text-zinc-500 hover:text-white text-2xl leading-none" data-testid="os-run-close">×</button>
        </div>

        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Brief for the team — e.g. &#10;&#10;'We're launching our analytics product to indie SaaS founders next month. Plan the launch.'"
          rows={5}
          disabled={running}
          className="w-full bg-zinc-900 border border-white/10 rounded-lg p-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-violet-500/50"
          data-testid="os-run-brief"
        />

        {progress.length === 0 ? (
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={close} className="px-4 py-2 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 text-sm">Cancel</button>
            <button onClick={start} className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium flex items-center gap-2" data-testid="os-run-start">
              <Play size={14} /> Run
            </button>
          </div>
        ) : (
          <div className="mt-5 space-y-2" data-testid="os-run-progress">
            {progress.map((p, i) => (
              <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
                <div className="flex items-center gap-2 text-xs">
                  {p.status === 'running' && <Loader2 size={14} className="animate-spin text-violet-400" />}
                  {p.status === 'summarizing' && <Loader2 size={14} className="animate-spin text-violet-400" />}
                  {p.status === 'done' && <CheckSquare size={14} className="text-emerald-400" />}
                  {(p.status === 'info' || p.status === 'starting') && <Activity size={14} className="text-cyan-400" />}
                  <span className="font-semibold text-white">{p.agent_name || p.label || p.role}</span>
                  {p.step && <span className="text-zinc-500">step {p.step}/{p.total}</span>}
                  <span className="ml-auto text-zinc-500 uppercase tracking-wider text-[10px]">{p.status}</span>
                </div>
                {p.answer && (
                  <div className="mt-2 text-xs text-zinc-300 whitespace-pre-wrap line-clamp-6 leading-relaxed">{p.answer}</div>
                )}
              </div>
            ))}
            {summary && (
              <div className="mt-4 rounded-xl border border-violet-500/40 bg-violet-500/5 p-4">
                <div className="flex items-center gap-2 text-violet-300 mb-2">
                  <Sparkles size={14} /><span className="text-xs uppercase tracking-widest font-bold">Executive summary</span>
                </div>
                <div className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed">{summary}</div>
              </div>
            )}
            {error && (
              <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">{error}</div>
            )}
            {!running && (
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => { reset(); setBrief(''); }} className="px-3 py-1.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 text-xs" data-testid="os-run-reset">New run</button>
                <button onClick={close} className="px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs">Done</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};


// ----------------------------------------------------------------------
// New Campaign Modal — minimal create form (name + goal)
// ----------------------------------------------------------------------
const GOAL_OPTIONS = [
  { id: 'awareness',  label: 'Awareness'  },
  { id: 'leads',      label: 'Leads'      },
  { id: 'sales',      label: 'Sales'      },
  { id: 'retention',  label: 'Retention'  },
  { id: 'custom',     label: 'Custom'     },
];

const NewCampaignModal = ({ open, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('awareness');
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  if (!open) return null;

  const submit = async () => {
    if (!name.trim()) {
      toast({ title: 'Name required', description: 'Give your campaign a short name.' });
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/campaigns`,
        { name: name.trim(), goal },
        { withCredentials: true },
      );
      toast({ title: 'Campaign created', description: `"${r.data.name}" is in Draft.` });
      setName(''); setGoal('awareness');
      onCreated && onCreated(r.data);
      onClose();
    } catch (e) {
      toast({
        title: 'Could not create campaign',
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setSaving(false);
    }
  };

  const close = () => { if (saving) return; setName(''); setGoal('awareness'); onClose(); };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={close} data-testid="new-campaign-modal">
      <div className="w-full max-w-md rounded-2xl border border-cyan-500/30 bg-zinc-950 p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-cyan-400 font-bold mb-1">Campaign Board</div>
            <h2 className="text-xl font-bold text-white">New campaign</h2>
            <p className="text-xs text-zinc-400 mt-1">Name + goal to start — you can flesh out audience and pillars later.</p>
          </div>
          <button onClick={close} className="text-zinc-500 hover:text-white text-2xl leading-none" data-testid="new-campaign-close">×</button>
        </div>

        <label className="block text-[10px] uppercase tracking-widest text-zinc-400 font-semibold mb-1.5">Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Q3 product launch"
          autoFocus
          disabled={saving}
          maxLength={120}
          className="w-full bg-zinc-900 border border-white/10 rounded-lg p-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500/50 mb-4"
          data-testid="new-campaign-name"
        />

        <label className="block text-[10px] uppercase tracking-widest text-zinc-400 font-semibold mb-1.5">Goal</label>
        <div className="grid grid-cols-3 gap-1.5 mb-5" data-testid="new-campaign-goal-options">
          {GOAL_OPTIONS.map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setGoal(g.id)}
              disabled={saving}
              data-testid={`new-campaign-goal-${g.id}`}
              className={`px-2.5 py-1.5 rounded-md text-xs border transition-colors ${
                goal === g.id
                  ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
                  : 'border-white/10 text-zinc-400 hover:bg-white/5'
              }`}
            >
              {g.label}
            </button>
          ))}
        </div>

        <div className="flex justify-end gap-2">
          <button
            onClick={close}
            disabled={saving}
            className="px-4 py-2 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 text-sm"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-50"
            data-testid="new-campaign-submit"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Create campaign
          </button>
        </div>
      </div>
    </div>
  );
};


// ----------------------------------------------------------------------
// Main page
// ----------------------------------------------------------------------
const CommandCenter = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runOpen, setRunOpen] = useState(false);
  const [newCampOpen, setNewCampOpen] = useState(false);
  // The campaign currently being dragged — id only.
  const [draggingId, setDraggingId] = useState(null);
  // Target column being hovered (for visual highlight).
  const [hoverStatus, setHoverStatus] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/marketing-os/dashboard`, { withCredentials: true });
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const campaignsByStatus = useMemo(() => {
    const groups = { draft: [], active: [], completed: [] };
    (data?.campaigns || []).forEach((c) => {
      const k = (c.status || 'draft').toLowerCase();
      if (groups[k]) groups[k].push(c);
    });
    return groups;
  }, [data?.campaigns]);

  // Optimistic move: update local state immediately, PATCH the server,
  // roll back + toast on failure. Free movement between all 3 columns.
  const moveCampaign = async (campaignId, nextStatus) => {
    const current = (data?.campaigns || []).find((c) => c.id === campaignId);
    if (!current || current.status === nextStatus) return;

    setData((prev) => prev ? ({
      ...prev,
      campaigns: prev.campaigns.map((c) =>
        c.id === campaignId ? { ...c, status: nextStatus } : c,
      ),
    }) : prev);

    try {
      await axios.patch(
        `${API}/campaigns/${campaignId}`,
        { status: nextStatus },
        { withCredentials: true },
      );
      toast({
        title: 'Campaign moved',
        description: `"${current.name}" → ${nextStatus}`,
      });
    } catch (e) {
      // Roll back the optimistic update.
      setData((prev) => prev ? ({
        ...prev,
        campaigns: prev.campaigns.map((c) =>
          c.id === campaignId ? { ...c, status: current.status } : c,
        ),
      }) : prev);
      toast({
        title: 'Could not move campaign',
        description: e.response?.data?.detail || e.message,
      });
    }
  };

  const onCardDragStart = (e, campaignId) => {
    setDraggingId(campaignId);
    try { e.dataTransfer.effectAllowed = 'move'; } catch (_) { /* noop */ }
  };
  const onCardDragEnd = () => { setDraggingId(null); setHoverStatus(null); };
  const onColumnDragOver = (e, status) => {
    if (!draggingId) return;
    e.preventDefault();
    try { e.dataTransfer.dropEffect = 'move'; } catch (_) { /* noop */ }
    if (hoverStatus !== status) setHoverStatus(status);
  };
  const onColumnDragLeave = (status) => {
    if (hoverStatus === status) setHoverStatus(null);
  };
  const onColumnDrop = (e, status) => {
    e.preventDefault();
    const id = draggingId;
    setDraggingId(null);
    setHoverStatus(null);
    if (id) moveCampaign(id, status);
  };

  return (
    <DashboardLayout
      title="Command Center"
      subtitle="Your autonomous marketing OS — campaigns, signals, approvals, agents."
    >
      <div className="space-y-6" data-testid="command-center-page">
        {/* Hero / CTA row */}
        <div className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-600/15 via-zinc-950/30 to-cyan-600/10 p-6 flex items-center gap-4 flex-wrap">
          <span className="w-12 h-12 rounded-xl bg-violet-500/20 border border-violet-500/40 flex items-center justify-center text-violet-300">
            <Command size={22} />
          </span>
          <div className="flex-1 min-w-[240px]">
            <div className="text-[10px] uppercase tracking-widest text-violet-400 font-bold mb-1">Marketing OS</div>
            <h1 className="text-2xl font-bold text-white">Run a campaign through the 5-role chain</h1>
            <p className="text-xs text-zinc-400 mt-1">Strategy · Intelligence · Content · Distribution · Analytics — one brief, one synthesized plan.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => navigate('/dashboard/trends')}
              className="px-4 py-2 rounded-lg border border-white/10 text-zinc-200 hover:bg-white/5 text-sm flex items-center gap-2"
              data-testid="os-view-signals-btn"
            >
              <TrendingUp size={14} /> Signals
            </button>
            <button
              onClick={() => setRunOpen(true)}
              className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium flex items-center gap-2 shadow-[0_8px_30px_rgb(124_58_237_/_0.45)]"
              data-testid="os-run-cta"
            >
              <Play size={14} /> Run the OS
            </button>
          </div>
        </div>

        {/* Stat tiles */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile icon={Layers}       label="Active Campaigns"   value={data?.stats.campaigns_active ?? '—'} accent="cyan"   testid="stat-campaigns" />
          <StatTile icon={CheckSquare}  label="Pending Approvals"  value={data?.stats.pending_approvals ?? '—'} accent="amber"  testid="stat-approvals" />
          <StatTile icon={Flame}        label="Hot Signals"        value={data?.stats.signals_hot ?? '—'}     accent="violet" testid="stat-signals" />
          <StatTile icon={Trophy}       label="Recent Wins"        value={data?.stats.recent_wins ?? '—'}     accent="emerald" testid="stat-wins" />
        </div>

        {/* 5 roles strip */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] uppercase tracking-widest text-zinc-400 font-bold">The 5-Role Marketing OS</div>
            <span className="text-[10px] text-zinc-500">Each role maps to a CortexViral agent</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2" data-testid="os-roles-strip">
            {(data?.roles || []).map((r) => {
              const icon = {
                strategy: Brain, intelligence: Sparkles, content: Megaphone,
                distribution: Users, analytics: BarChart3,
              }[r.role] || Bot;
              const Icon = icon;
              return (
                <div key={r.role} className="rounded-lg border border-white/5 bg-zinc-950/50 p-3 flex items-center gap-2.5">
                  <span className={`w-8 h-8 rounded-md border flex items-center justify-center bg-${r.color}-500/10 border-${r.color}-500/30 text-${r.color}-300`}>
                    <Icon size={14} />
                  </span>
                  <div className="min-w-0">
                    <div className="text-[9px] uppercase tracking-widest text-zinc-500 font-semibold">{r.label}</div>
                    <div className="text-xs text-zinc-200 truncate capitalize">{r.agent_id}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Main 2-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Campaign Board (kanban) */}
          <div className="lg:col-span-2 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Layers size={14} className="text-cyan-300" /> Campaign Board</h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setNewCampOpen(true)}
                  className="text-xs px-2.5 py-1 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/25 flex items-center gap-1"
                  data-testid="new-campaign-btn"
                >
                  <Plus size={12} /> New
                </button>
                <button onClick={() => navigate('/dashboard/posts')} className="text-xs text-zinc-400 hover:text-white flex items-center gap-1" data-testid="os-campaigns-open">
                  Open posts <ChevronRight size={12} />
                </button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3" data-testid="campaign-board">
              {['draft', 'active', 'completed'].map((status) => {
                const isHover = hoverStatus === status && draggingId;
                return (
                  <div
                    key={status}
                    onDragOver={(e) => onColumnDragOver(e, status)}
                    onDragLeave={() => onColumnDragLeave(status)}
                    onDrop={(e) => onColumnDrop(e, status)}
                    data-testid={`kanban-col-${status}`}
                    className={`rounded-lg border bg-zinc-950/50 p-2 min-h-[160px] transition-colors ${
                      isHover ? 'border-cyan-400/60 bg-cyan-500/5' : 'border-white/5'
                    }`}
                  >
                    <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold px-1 pb-2 flex items-center justify-between">
                      <span>{status}</span>
                      <span className="text-zinc-600">{campaignsByStatus[status]?.length || 0}</span>
                    </div>
                    <div className="space-y-1.5">
                      {(campaignsByStatus[status] || []).length === 0 ? (
                        <div className="text-[11px] text-zinc-600 italic px-1 py-2">
                          {isHover ? 'Drop here' : 'No campaigns'}
                        </div>
                      ) : (
                        campaignsByStatus[status].map((c) => (
                          <div
                            key={c.id}
                            draggable
                            onDragStart={(e) => onCardDragStart(e, c.id)}
                            onDragEnd={onCardDragEnd}
                            data-testid={`campaign-card-${c.id}`}
                            className={`rounded-md border border-white/5 bg-zinc-900/60 p-2 cursor-grab active:cursor-grabbing select-none transition-opacity ${
                              draggingId === c.id ? 'opacity-40' : 'hover:bg-zinc-900/90'
                            }`}
                          >
                            <div className="text-xs text-white font-medium truncate">{c.name}</div>
                            <div className="flex items-center gap-1.5 mt-1">
                              <span className={`text-[9px] px-1.5 py-0.5 rounded border ${STATUS_PILL[status]}`}>{c.goal}</span>
                              {(c.platforms || []).slice(0, 2).map((p) => (
                                <span key={p} className="text-[9px] text-zinc-500">{p}</span>
                              ))}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="text-[10px] text-zinc-600 mt-2 px-1">Drag a card between columns to change status.</div>
          </div>

          {/* Opportunity Signals */}
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Flame size={14} className="text-violet-300" /> Opportunity Signals</h3>
              <button onClick={() => navigate('/dashboard/trends')} className="text-xs text-zinc-400 hover:text-white" data-testid="os-signals-open">all →</button>
            </div>
            <div className="space-y-2" data-testid="signals-stack">
              {(data?.signals || []).length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-4">No signals ingested yet. Open Trends to seed your feed.</div>
              ) : (
                (data?.signals || []).slice(0, 5).map((s) => {
                  const sig = (s.meta || {}).signal || {};
                  const ag = AGENT_PILL[sig.recommended_agent] || AGENT_PILL.nova;
                  const urg = URGENCY_STYLE[sig.urgency] || URGENCY_STYLE.monitor;
                  return (
                    <div key={s.id} className="rounded-lg border border-white/5 bg-zinc-950/50 p-2.5" data-testid={`signal-card-${s.id}`}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${urg.cls}`}>{urg.label}</span>
                        <span className="text-[10px] text-zinc-500 tabular-nums">{sig.virality_score ?? 0}</span>
                      </div>
                      <div className="text-xs text-zinc-200 line-clamp-2 leading-snug">{s.text}</div>
                      {sig.content_angle && (
                        <div className="text-[10px] text-zinc-500 italic mt-1.5 line-clamp-2">{sig.content_angle}</div>
                      )}
                      <div className="flex items-center justify-between mt-2">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border ${ag.cls}`}>→ {ag.label}</span>
                        <button onClick={() => navigate('/dashboard/trends')} className="text-[10px] text-violet-400 hover:text-violet-300 flex items-center gap-0.5">
                          Draft <ArrowRight size={10} />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Bottom row: Approvals + Activity + Wins */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><CheckSquare size={14} className="text-amber-300" /> Approval Inbox</h3>
              <button onClick={() => navigate('/dashboard/approvals')} className="text-xs text-zinc-400 hover:text-white" data-testid="os-approvals-open">all →</button>
            </div>
            <div className="space-y-2" data-testid="approval-inbox">
              {(data?.approvals || []).length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-3">Empty — every queued post has been actioned.</div>
              ) : (
                (data?.approvals || []).map((p) => (
                  <div key={p.id} className="rounded-lg border border-white/5 bg-zinc-950/50 p-2.5">
                    <div className="text-xs text-zinc-200 line-clamp-2">{p.content || '(no content)'}</div>
                    <div className="flex items-center justify-between mt-1.5">
                      <div className="flex items-center gap-1">
                        {(p.platforms || []).slice(0, 3).map((pf) => (
                          <span key={pf} className="text-[9px] text-zinc-500 uppercase">{pf}</span>
                        ))}
                      </div>
                      <span className="text-[10px] text-zinc-500">{p.scheduled_at ? new Date(p.scheduled_at).toLocaleDateString() : ''}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Activity size={14} className="text-cyan-300" /> Agent Activity</h3>
              <span className="text-[10px] text-zinc-500">last {data?.runs?.length || 0} runs</span>
            </div>
            <div className="space-y-2" data-testid="activity-feed">
              {(data?.runs || []).length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-3">
                  No OS runs yet. Hit <span className="text-violet-300">Run the OS</span> to ship your first one.
                </div>
              ) : (
                (data?.runs || []).map((r) => (
                  <div key={r.id} className="rounded-lg border border-white/5 bg-zinc-950/50 p-2.5">
                    <div className="text-xs text-zinc-200 line-clamp-2 leading-snug">{r.brief || '(no brief)'}</div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                        r.status === 'completed' ? 'border-emerald-500/30 text-emerald-300 bg-emerald-500/10' : 'border-rose-500/30 text-rose-300 bg-rose-500/10'
                      }`}>{r.status}</span>
                      <span className="text-[10px] text-zinc-500">{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Trophy size={14} className="text-emerald-300" /> Recent Wins</h3>
              <button onClick={() => navigate('/dashboard/performance')} className="text-xs text-zinc-400 hover:text-white">view →</button>
            </div>
            <div className="space-y-2" data-testid="wins-feed">
              {(data?.wins || []).length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-3">No wins logged yet. Once published posts cross 50 impressions, the feedback loop picks the top performers automatically.</div>
              ) : (
                (data?.wins || []).map((w) => (
                  <div key={w.id} className="rounded-lg border border-emerald-500/15 bg-emerald-500/5 p-2.5">
                    <div className="text-xs text-zinc-200 line-clamp-2 leading-snug">{w.text}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {loading && (
          <div className="text-center text-xs text-zinc-500 py-4">Loading Command Center…</div>
        )}
      </div>

      <RunModal open={runOpen} onClose={() => setRunOpen(false)} onComplete={load} />
      <NewCampaignModal
        open={newCampOpen}
        onClose={() => setNewCampOpen(false)}
        onCreated={load}
      />
    </DashboardLayout>
  );
};

export default CommandCenter;
