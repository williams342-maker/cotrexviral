import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Command, Sparkles, Zap, TrendingUp, CheckSquare, Trophy,
  ChevronRight, Play, Activity, Loader2, Flame, ArrowRight, Bot,
  Layers, Users, BarChart3, Megaphone, Brain, Plus, Check, Star, SkipForward,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import RunOSModal from '../../components/RunOSModal';
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
      onClick={close} data-testid="new-campaign-modal"
      role="dialog" aria-modal="true" aria-labelledby="new-campaign-modal-title">
      <div className="w-full max-w-md rounded-2xl border border-cyan-500/30 bg-zinc-950 p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-cyan-400 font-bold mb-1">Campaign Board</div>
            <h2 id="new-campaign-modal-title" className="text-xl font-bold text-white">New campaign</h2>
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
  // Campaign context to seed the OS run with. null = blank free-form run.
  const [runCampaign, setRunCampaign] = useState(null); // {id, name, brief}
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

  // Build a sensible default brief for a campaign — the server already
  // enriches it with goal/audience/pillars when `campaign_id` is sent,
  // so we just give the chain a starting verb.
  const openRunForCampaign = (c) => {
    setRunCampaign({
      id: c.id,
      name: c.name,
      brief: `Plan the next 30 days of marketing for the "${c.name}" campaign. Goal: ${c.custom_goal || c.goal}.`,
    });
    setRunOpen(true);
  };

  // Track hooks that have been promoted in this session so the UI can
  // flip the button to a confirmed "Promoted" state without forcing a
  // dashboard refetch. Server-side promotion is idempotent (dedupe key),
  // so re-clicking is harmless even if state were lost.
  const [promotedHooks, setPromotedHooks] = useState(new Set());
  const [promoting, setPromoting] = useState(null); // id of in-flight promote

  const promoteHook = async (hookId) => {
    if (promotedHooks.has(hookId) || promoting === hookId) return;
    setPromoting(hookId);
    try {
      await axios.post(
        `${API}/memory/promote-hook`,
        { hook_id: hookId },
        { withCredentials: true },
      );
      setPromotedHooks((prev) => {
        const next = new Set(prev);
        next.add(hookId);
        return next;
      });
      toast({
        title: 'Promoted to Brand Voice',
        description: 'Nova will lean on this pattern in every future generation.',
      });
    } catch (e) {
      toast({
        title: 'Could not promote hook',
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setPromoting(null);
    }
  };

  // Bulk-promote: queues a POST for each un-promoted winner in parallel.
  // Capped at 3 to avoid accidentally pinning too many hooks at once
  // (the brand_voice prompt block already truncates at 5 anyway).
  const [bulkPromoting, setBulkPromoting] = useState(false);
  const promoteTopWins = async () => {
    const targets = (data?.wins || [])
      .filter((w) => !promotedHooks.has(w.id))
      .slice(0, 3);
    if (targets.length === 0) {
      toast({ title: 'Nothing to promote', description: 'All visible winners are already promoted.' });
      return;
    }
    setBulkPromoting(true);
    let ok = 0;
    let failed = 0;
    try {
      await Promise.all(targets.map(async (w) => {
        try {
          await axios.post(
            `${API}/memory/promote-hook`,
            { hook_id: w.id },
            { withCredentials: true },
          );
          setPromotedHooks((prev) => {
            const next = new Set(prev);
            next.add(w.id);
            return next;
          });
          ok += 1;
        } catch {
          failed += 1;
        }
      }));
      toast({
        title: `Promoted ${ok} hook${ok === 1 ? '' : 's'}`,
        description: failed > 0 ? `${failed} failed — retry individually.` : 'Nova will lean on these patterns.',
      });
    } finally {
      setBulkPromoting(false);
      load();  // Refresh brand-voice viewer count.
    }
  };

  // Brand-voice viewer state — lazy-loaded the first time the user opens
  // the popover (saves a roundtrip on initial paint).
  const [bvOpen, setBvOpen] = useState(false);
  const [bvData, setBvData] = useState(null);
  const [bvLoading, setBvLoading] = useState(false);
  // Drag-reorder state
  const [bvDragId, setBvDragId] = useState(null);
  // Inline "write a new anchor" form
  const [newAnchorText, setNewAnchorText] = useState('');
  const [newAnchorSaving, setNewAnchorSaving] = useState(false);
  // "Test this voice" widget
  const [testTopic, setTestTopic] = useState('');
  const [testDraft, setTestDraft] = useState('');
  const [testRunning, setTestRunning] = useState(false);

  const openBrandVoiceViewer = async () => {
    setBvOpen(true);
    if (bvData === null && !bvLoading) {
      setBvLoading(true);
      try {
        const r = await axios.get(`${API}/memory/brand-voice`, { withCredentials: true });
        setBvData(r.data.brand_voice || []);
      } catch {
        setBvData([]);
      } finally {
        setBvLoading(false);
      }
    }
  };
  const closeBrandVoiceViewer = () => {
    setBvOpen(false);
    setTestDraft(''); setTestTopic('');
    setNewAnchorText('');
  };
  const demoteBrandVoice = async (memId) => {
    if (!window.confirm('Remove this voice anchor? Nova will stop using it in future generations.')) return;
    try {
      await axios.delete(`${API}/memory/${memId}`, { withCredentials: true });
      setBvData((prev) => (prev || []).filter((r) => r.id !== memId));
      toast({ title: 'Voice anchor removed' });
    } catch (e) {
      toast({ title: 'Could not remove', description: e.response?.data?.detail || e.message });
    }
  };

  // ---- Reorder handlers (HTML5 drag-and-drop) ----------------------
  const onBvDragStart = (id) => setBvDragId(id);
  const onBvDragEnd = () => setBvDragId(null);
  const onBvDrop = async (targetId) => {
    if (!bvDragId || bvDragId === targetId) { setBvDragId(null); return; }
    const items = [...(bvData || [])];
    const fromIdx = items.findIndex((r) => r.id === bvDragId);
    const toIdx   = items.findIndex((r) => r.id === targetId);
    if (fromIdx === -1 || toIdx === -1) { setBvDragId(null); return; }
    const [moved] = items.splice(fromIdx, 1);
    items.splice(toIdx, 0, moved);
    setBvData(items);
    setBvDragId(null);
    try {
      await axios.patch(
        `${API}/memory/brand-voice/reorder`,
        { ids: items.map((r) => r.id) },
        { withCredentials: true },
      );
    } catch (e) {
      // Rollback on failure.
      toast({ title: 'Could not save order', description: e.response?.data?.detail || e.message });
      setBvData((prev) => prev);  // optimistic — server is authoritative on next reload
    }
  };

  // ---- "Write a new anchor" -----------------------------------------
  const saveNewAnchor = async () => {
    if (!newAnchorText.trim()) return;
    setNewAnchorSaving(true);
    try {
      const r = await axios.post(
        `${API}/memory/brand-voice`,
        { text: newAnchorText.trim() },
        { withCredentials: true },
      );
      // Re-fetch so order + ids are in sync with the server.
      const list = await axios.get(`${API}/memory/brand-voice`, { withCredentials: true });
      setBvData(list.data.brand_voice || []);
      setNewAnchorText('');
      toast({ title: 'Anchor added', description: 'Nova will lean on this pattern in every future draft.' });
      return r.data.id;
    } catch (e) {
      toast({ title: 'Could not save anchor', description: e.response?.data?.detail || e.message });
    } finally {
      setNewAnchorSaving(false);
    }
  };

  // ---- "Test this voice" --------------------------------------------
  const runVoiceTest = async () => {
    if (!testTopic.trim()) return;
    setTestRunning(true);
    setTestDraft('');
    try {
      const r = await axios.post(
        `${API}/memory/brand-voice/test`,
        { topic: testTopic.trim() },
        { withCredentials: true, timeout: 30000 },
      );
      setTestDraft(r.data.draft || '(empty draft — try a different topic)');
    } catch (e) {
      // Map known failure modes to friendly toast copy. Without this,
      // a budget-capped key just leaves the UI spinning forever.
      const code = e.response?.status;
      let title = 'Test failed';
      let description = e.response?.data?.detail || e.message;
      if (e.code === 'ECONNABORTED' || /timeout/i.test(e.message || '')) {
        title = 'Timed out';
        description = 'The LLM took too long — the universal key may be over budget. Try again in a few minutes.';
      } else if (code === 422) {
        title = 'Add an anchor first';
        description = 'Promote a winning hook or write a manual anchor, then test again.';
      } else if (code === 429) {
        title = 'LLM budget cap reached';
        description = 'Add balance in Profile → Universal Key, or try again later.';
      } else if (code === 504) {
        title = 'LLM is slow right now';
        description = description || 'The model timed out. Try again in a few minutes.';
      } else if (code === 503) {
        title = 'LLM unavailable';
      }
      toast({ title, description });
    } finally {
      setTestRunning(false);
    }
  };

  // Global Escape-to-close for any open modal — declared AFTER the
  // brand-voice state hooks so the closure can read `bvOpen` /
  // `closeBrandVoiceViewer` legally (TDZ-safe).
  useEffect(() => {
    if (!runOpen && !newCampOpen && !bvOpen) return;
    const handler = (e) => {
      if (e.key === 'Escape') {
        if (bvOpen) closeBrandVoiceViewer();
        else if (newCampOpen) setNewCampOpen(false);
        else if (runOpen) setRunOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runOpen, newCampOpen, bvOpen]);

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
              onClick={() => { setRunCampaign(null); setRunOpen(true); }}
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
                            onClick={() => { if (!draggingId) navigate(`/dashboard/campaigns/${c.id}`); }}
                            role="button"
                            tabIndex={0}
                            aria-label={`Campaign ${c.name} (${status}). Press Enter to open. Drag to change status.`}
                            aria-grabbed={draggingId === c.id || undefined}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                navigate(`/dashboard/campaigns/${c.id}`);
                              }
                            }}
                            data-testid={`campaign-card-${c.id}`}
                            className={`group relative rounded-md border border-white/5 bg-zinc-900/60 p-2 cursor-grab active:cursor-grabbing select-none transition-opacity ${
                              draggingId === c.id ? 'opacity-40' : 'hover:bg-zinc-900/90 hover:border-cyan-500/30'
                            }`}
                          >
                            <button
                              type="button"
                              draggable={false}
                              onClick={(e) => { e.stopPropagation(); openRunForCampaign(c); }}
                              onMouseDown={(e) => e.stopPropagation()}
                              className="absolute top-1.5 right-1.5 w-6 h-6 rounded-md border border-violet-500/40 bg-violet-500/10 text-violet-300 hover:bg-violet-500/25 hover:border-violet-400 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                              title="Run the OS on this campaign"
                              data-testid={`campaign-run-${c.id}`}
                              aria-label={`Run the Marketing OS on ${c.name}`}
                            >
                              <Play size={11} />
                            </button>
                            <div className="text-xs text-white font-medium truncate pr-7">{c.name}</div>
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
                    <div className="flex items-center justify-between mt-1.5 gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border shrink-0 ${
                          r.status === 'completed' ? 'border-emerald-500/30 text-emerald-300 bg-emerald-500/10' : 'border-rose-500/30 text-rose-300 bg-rose-500/10'
                        }`}>{r.status}</span>
                        {r.skip_distribution && (
                          <span
                            className="text-[9px] px-1.5 py-0.5 rounded border shrink-0 border-amber-500/30 text-amber-300 bg-amber-500/10 flex items-center gap-0.5"
                            title="Distribution role was skipped — no platforms connected on this campaign."
                            data-testid={`activity-skip-distribution-${r.id}`}
                          >
                            <SkipForward size={9} /> dist skipped
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-zinc-500 shrink-0">{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Trophy size={14} className="text-emerald-300" /> Recent Wins</h3>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={openBrandVoiceViewer}
                  className="text-[10px] px-2 py-0.5 rounded border border-violet-500/30 text-violet-300 hover:bg-violet-500/15 flex items-center gap-1"
                  data-testid="open-brand-voice-btn"
                  title="View all promoted voice anchors"
                >
                  <Star size={10} /> Brand voice
                </button>
                {(data?.wins || []).some((w) => !promotedHooks.has(w.id)) && (
                  <button
                    onClick={promoteTopWins}
                    disabled={bulkPromoting}
                    className="text-[10px] px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 flex items-center gap-1"
                    data-testid="bulk-promote-btn"
                    title="Promote the top 3 winners in one click"
                  >
                    {bulkPromoting ? <><Loader2 size={10} className="animate-spin" /> Promoting…</> : <><Star size={10} /> Promote top 3</>}
                  </button>
                )}
              </div>
            </div>
            <div className="space-y-2" data-testid="wins-feed">
              {(data?.wins || []).length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-3">No wins logged yet. Once published posts cross 50 impressions, the feedback loop picks the top performers automatically.</div>
              ) : (
                (data?.wins || []).map((w) => {
                  const promoted = promotedHooks.has(w.id);
                  const busy = promoting === w.id;
                  return (
                    <div key={w.id} className="rounded-lg border border-emerald-500/15 bg-emerald-500/5 p-2.5 group" data-testid={`win-card-${w.id}`}>
                      <div className="text-xs text-zinc-200 line-clamp-2 leading-snug">{w.text}</div>
                      <div className="flex items-center justify-end mt-1.5">
                        <button
                          type="button"
                          onClick={() => promoteHook(w.id)}
                          disabled={promoted || busy}
                          aria-label={promoted ? 'Hook already promoted to brand voice' : 'Promote this winning hook to your brand voice'}
                          className={`text-[10px] px-2 py-0.5 rounded border flex items-center gap-1 transition-colors ${
                            promoted
                              ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200 cursor-default'
                              : 'border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/15 focus:opacity-100 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/40'
                          }`}
                          data-testid={`win-promote-${w.id}`}
                          title={promoted ? 'Already promoted' : 'Promote to Brand Voice — Nova will lean on this in every future draft'}
                        >
                          {promoted ? <><Check size={10} /> Promoted</> :
                           busy ? <><Loader2 size={10} className="animate-spin" /> Promoting…</> :
                           <><Star size={10} /> Promote to Brand Voice</>}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {loading && (
          <div className="text-center text-xs text-zinc-500 py-4">Loading Command Center…</div>
        )}
      </div>

      <RunOSModal
        open={runOpen}
        onClose={() => setRunOpen(false)}
        onComplete={load}
        initialBrief={runCampaign?.brief || ''}
        campaignId={runCampaign?.id || null}
        campaignName={runCampaign?.name || ''}
      />
      <NewCampaignModal
        open={newCampOpen}
        onClose={() => setNewCampOpen(false)}
        onCreated={load}
      />

      {/* Brand-voice viewer modal — drag-reorder, write-from-scratch,
          and inline "test this voice" preview. */}
      {bvOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={closeBrandVoiceViewer}
          data-testid="brand-voice-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="bv-modal-title"
        >
          <div
            className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border border-violet-500/30 bg-zinc-950 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-violet-400 font-bold mb-1">Brand Voice</div>
                <h2 id="bv-modal-title" className="text-xl font-bold text-white">Pinned voice anchors</h2>
                <p className="text-xs text-zinc-400 mt-1">Drag to reorder · top = highest priority. Nova echoes these in every draft.</p>
              </div>
              <button
                onClick={closeBrandVoiceViewer}
                className="text-zinc-500 hover:text-white text-2xl leading-none focus:outline-none focus:ring-2 focus:ring-violet-500/40 rounded"
                data-testid="brand-voice-close"
                aria-label="Close brand voice viewer"
              >×</button>
            </div>

            {bvLoading ? (
              <div className="text-xs text-zinc-500 italic flex items-center gap-1.5 py-4">
                <Loader2 size={12} className="animate-spin" /> Loading…
              </div>
            ) : (bvData || []).length === 0 ? (
              <div className="rounded-lg border border-violet-500/20 bg-violet-500/[0.04] p-4 text-sm text-zinc-300 leading-relaxed" data-testid="brand-voice-empty">
                <div className="font-semibold mb-1">No voice anchors yet.</div>
                <div className="text-xs text-zinc-400">
                  Add an anchor below, or promote a winning hook from the <span className="text-emerald-300">Recent Wins</span> card. Once you have anchors, Nova will echo them in every Compose draft, signal-driven post, and OS chain run.
                </div>
              </div>
            ) : (
              <div className="space-y-2" data-testid="brand-voice-list">
                {(bvData || []).map((bv) => {
                  const m = (bv.text || '').match(/"([^"]+)"/);
                  const anchor = m ? m[1] : (bv.text || '');
                  const plat = bv.meta?.platform;
                  const rate = bv.meta?.engagement_rate;
                  const isManual = bv.meta?.source === 'manual';
                  return (
                    <div
                      key={bv.id}
                      draggable
                      onDragStart={() => onBvDragStart(bv.id)}
                      onDragEnd={onBvDragEnd}
                      onDragOver={(e) => { if (bvDragId && bvDragId !== bv.id) e.preventDefault(); }}
                      onDrop={() => onBvDrop(bv.id)}
                      className={`rounded-lg border bg-zinc-950/40 p-3 flex items-start gap-3 cursor-grab active:cursor-grabbing transition-colors ${
                        bvDragId === bv.id ? 'opacity-40 border-violet-500/60' : 'border-white/5 hover:border-violet-500/30'
                      }`}
                      data-testid={`brand-voice-row-${bv.id}`}
                    >
                      <span className="w-6 h-6 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center shrink-0 mt-0.5">
                        <Star size={11} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-zinc-200 leading-relaxed">{anchor}</div>
                        <div className="flex items-center gap-2 mt-1.5 text-[10px] text-zinc-500">
                          {plat && <span className="uppercase tracking-wider">{plat}</span>}
                          {rate != null && <span className="text-emerald-400 tabular-nums">{Math.round(rate * 1000) / 10}%</span>}
                          {isManual && <span className="text-violet-400 italic">manual</span>}
                          {bv.created_at && <span>· promoted {new Date(bv.created_at).toLocaleDateString()}</span>}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => demoteBrandVoice(bv.id)}
                        aria-label="Remove voice anchor"
                        className="text-zinc-500 hover:text-rose-300 shrink-0 p-1 focus:outline-none focus:ring-2 focus:ring-rose-500/40 rounded"
                        data-testid={`brand-voice-demote-${bv.id}`}
                        title="Remove this voice anchor"
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Write a new anchor from scratch */}
            <div className="mt-5 rounded-lg border border-white/10 bg-white/[0.02] p-3" data-testid="brand-voice-new-block">
              <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold mb-2">Add an anchor</div>
              <div className="flex gap-2">
                <input
                  value={newAnchorText}
                  onChange={(e) => setNewAnchorText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && newAnchorText.trim()) saveNewAnchor(); }}
                  placeholder="e.g. 'Stop measuring what's easy. Measure what matters.'"
                  maxLength={600}
                  className="flex-1 bg-zinc-900 border border-white/10 rounded-md p-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-violet-500/40"
                  data-testid="brand-voice-new-input"
                />
                <button
                  onClick={saveNewAnchor}
                  disabled={!newAnchorText.trim() || newAnchorSaving}
                  className="px-3 rounded-md bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium disabled:opacity-50 flex items-center gap-1"
                  data-testid="brand-voice-new-add"
                >
                  {newAnchorSaving ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                  Add
                </button>
              </div>
            </div>

            {/* Test this voice — instant Nova preview */}
            {(bvData || []).length > 0 && (
              <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-3" data-testid="brand-voice-test-block">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={12} className="text-emerald-300" />
                  <div className="text-[10px] uppercase tracking-widest text-emerald-300 font-bold">Test this voice</div>
                  <span className="text-[10px] text-zinc-500">— see what Nova would draft right now</span>
                </div>
                <div className="flex gap-2">
                  <input
                    value={testTopic}
                    onChange={(e) => setTestTopic(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && testTopic.trim() && !testRunning) runVoiceTest(); }}
                    placeholder="Topic — e.g. 'launching a pricing experiment'"
                    maxLength={240}
                    className="flex-1 bg-zinc-900 border border-white/10 rounded-md p-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/40"
                    data-testid="brand-voice-test-input"
                  />
                  <button
                    onClick={runVoiceTest}
                    disabled={!testTopic.trim() || testRunning}
                    className="px-3 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium disabled:opacity-50 flex items-center gap-1"
                    data-testid="brand-voice-test-run"
                  >
                    {testRunning ? <><Loader2 size={11} className="animate-spin" /> Drafting…</> : <><Play size={11} /> Test</>}
                  </button>
                </div>
                {testDraft && (
                  <div className="mt-3 rounded-md border border-emerald-500/30 bg-zinc-950/50 p-3 text-xs text-zinc-200 leading-relaxed whitespace-pre-wrap" data-testid="brand-voice-test-draft">
                    {testDraft}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default CommandCenter;
