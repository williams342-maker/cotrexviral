import React, { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Loader2, PanelRightClose, PanelRightOpen, GripVertical, Search,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';
import OpportunityRail from './cortex/OpportunityRail';
import ExecutionLog from './cortex/ExecutionLog';
import ChatMessage from './cortex/ChatMessage';
import Composer from './cortex/Composer';
import PhaseIndicator from './cortex/PhaseIndicator';
import MemorySearch from './cortex/MemorySearch';
import useResizableRail from '../../hooks/useResizableRail';

/* /dashboard — the Conversational Command Center.

   This is the primary product surface. Users interact with Cortex
   through natural language. Cortex understands goals, proposes plans
   with reasoning/confidence/cost/timeline/risk, and executes through
   the autonomy engine (L0-L5) — but execution is a SIDE-EFFECT of
   conversation. Conversation never ends; missions stream live updates
   inline as Cortex works in the background.

   This file orchestrates state + side-effects. Visual components are
   in /pages/dashboard/cortex/. */

const PHASE_COPY = {
  classifying: 'Understanding your goal…',
  recalling:   'Recalling our prior conversations…',
  planning:    'Cortex is drafting the plan…',
  ready:       'Done.',
};


const CommandCenter = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [thread, setThread]   = useState([]);
  const [draft, setDraft]     = useState('');
  const [sending, setSending] = useState(false);
  const [phase, setPhase]     = useState(null);
  const [phaseHistory, setPhaseHistory] = useState([]);
  const [busyId, setBusyId]   = useState(null);
  const [strategy, setStrategy] = useState(null);
  const [opportunities, setOpps] = useState([]);
  const [oppLoading, setOppLoading] = useState(true);
  const [execItems, setExecItems] = useState([]);
  const [execLoading, setExecLoading] = useState(true);
  const [activeMissions, setActiveMissions] = useState([]);
  const [missionsLoading, setMissionsLoading] = useState(true);
  const trackedMissionsRef = useRef({});
  const [searchOpen, setSearchOpen] = useState(false);
  const lastPlanIdRef = useRef(null);

  const rail = useResizableRail({
    key: 'cortex-right-rail',
    defaultWidth: 320, min: 240, max: 520, side: 'right',
  });

  const scrollRef = useRef(null);
  const esRef = useRef(null);

  // ----- Initial + periodic data loaders -----------------------------
  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/console/history?limit=40`,
                                  { withCredentials: true });
      const turns = r.data?.turns || [];
      let latestPlanIdx = -1;
      for (let i = turns.length - 1; i >= 0; i--) {
        if (turns[i].recommendation) { latestPlanIdx = i; break; }
      }
      const annotated = turns.map((t, i) => ({
        ...t, _stale: t.recommendation && i !== latestPlanIdx,
      }));
      setThread(annotated);
      lastPlanIdRef.current = latestPlanIdx >= 0 ? turns[latestPlanIdx].id : null;
    } catch (_e) { /* */ }
  }, []);
  const loadStrategy = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/memory/strategy`,
                                  { withCredentials: true });
      setStrategy(r.data || null);
    } catch (_e) { /* */ }
  }, []);
  const loadOpps = useCallback(async () => {
    setOppLoading(true);
    try {
      const r = await axios.get(`${API}/cortex/console/opportunities?limit=8`,
                                  { withCredentials: true });
      setOpps(r.data?.opportunities || []);
    } catch (_e) { setOpps([]); }
    finally { setOppLoading(false); }
  }, []);
  const loadExec = useCallback(async () => {
    setExecLoading(true);
    try {
      const r = await axios.get(`${API}/cortex/execution-log?limit=20`,
                                  { withCredentials: true });
      setExecItems(r.data?.items || []);
    } catch (_e) { setExecItems([]); }
    finally { setExecLoading(false); }
  }, []);
  const loadActiveMissions = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/missions/active?limit=6`,
                                  { withCredentials: true });
      setActiveMissions(r.data?.missions || []);
    } catch (_e) { /* */ }
    finally { setMissionsLoading(false); }
  }, []);

  useEffect(() => {
    loadHistory(); loadStrategy(); loadOpps(); loadExec();
  }, [loadHistory, loadStrategy, loadOpps, loadExec]);

  // Poll active missions every 5s.
  useEffect(() => {
    loadActiveMissions();
    const t = setInterval(loadActiveMissions, 5000);
    return () => clearInterval(t);
  }, [loadActiveMissions]);

  // Seed tracked-missions from active list so we stream events for pre-existing missions too.
  useEffect(() => {
    if (activeMissions.length && Object.keys(trackedMissionsRef.current).length === 0) {
      const seed = {};
      for (const m of activeMissions.slice(0, 3)) {
        seed[m.id] = { title: m.title,
                        lastSeen: new Date(Date.now() - 30_000).toISOString() };
      }
      trackedMissionsRef.current = seed;
    }
  }, [activeMissions]);

  // Per-mission event polling — streams live updates into chat.
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const tracked = trackedMissionsRef.current;
      const ids = Object.keys(tracked);
      if (ids.length === 0) return;
      for (const mid of ids.slice(0, 3)) {
        try {
          const t = tracked[mid];
          const since = t?.lastSeen || new Date(Date.now() - 60_000).toISOString();
          const r = await axios.get(
            `${API}/cortex/missions/${mid}/events?since=${encodeURIComponent(since)}&limit=10`,
            { withCredentials: true });
          const evs = r.data?.events || [];
          if (cancelled) return;
          if (evs.length > 0) {
            tracked[mid].lastSeen = evs[0].created_at || new Date().toISOString();
            setThread((thread) => [...thread, {
              id: `mev-${mid}-${Date.now()}`,
              _kind: 'mission_events',
              missionTitle: t.title,
              events: evs.reverse(),
              created_at: new Date().toISOString(),
            }]);
          }
        } catch (_e) { /* */ }
      }
    };
    const iv = setInterval(poll, 8000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  // Auto-scroll on thread / phase change.
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thread, phase]);

  // Cmd/Ctrl+K → memory search. Use Cmd+Shift+K to avoid colliding with
  // the global QuickFind palette (which already owns Cmd+K).
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && e.shiftKey) {
        e.preventDefault();
        setSearchOpen((o) => !o);
      } else if (e.key === 'Escape') {
        setSearchOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // ----- Send (SSE-streamed) ----------------------------------------
  const send = async () => {
    const msg = draft.trim();
    if (!msg || sending) return;
    setSending(true);
    setPhase({ phase: 'classifying', label: PHASE_COPY.classifying });
    setPhaseHistory([{ phase: 'classifying', label: PHASE_COPY.classifying }]);

    // Mark prior plan cards as superseded immediately.
    setThread((t) => t.map((turn) =>
      turn.recommendation ? { ...turn, _stale: true } : turn
    ));

    const userTurn = {
      id: `u-${Date.now()}`, role: 'user', message: msg,
      created_at: new Date().toISOString(),
    };
    setThread((t) => [...t, userTurn]);
    setDraft('');

    try {
      const url = `${API}/cortex/console/chat/stream?message=${encodeURIComponent(msg)}`;
      const es = new EventSource(url, { withCredentials: true });
      esRef.current = es;
      let memoryRecallCount = 0;
      let memoryStrategyEcho = '';

      es.addEventListener('phase', (ev) => {
        try {
          const d = JSON.parse(ev.data);
          const p = { phase: d.phase, label: d.label || PHASE_COPY[d.phase] };
          setPhase(p);
          setPhaseHistory((h) => [...h.slice(-3), p]);
        } catch { /* */ }
      });
      es.addEventListener('memory', (ev) => {
        try {
          const d = JSON.parse(ev.data);
          memoryRecallCount = d.recalled_count || 0;
          memoryStrategyEcho = d.strategy_summary || '';
        } catch { /* */ }
      });
      es.addEventListener('ready', (ev) => {
        try {
          const d = JSON.parse(ev.data);
          const hint = memoryRecallCount > 1
            ? `recalled ${memoryRecallCount} relevant prior messages from your history.`
            : (memoryStrategyEcho ? memoryStrategyEcho.split('. ')[0] : null);
          const cortexTurn = {
            id: `c-${Date.now()}`, role: 'cortex',
            message: d?.ack || '',
            stage: d?.stage,
            intent: d?.intent,
            params: d?.params,
            clarifying_questions: d?.clarifying_questions || [],
            findings: d?.findings || [],
            recommendation_summary: d?.recommendation_summary || '',
            alternatives: d?.alternatives || [],
            recommendation: d?.recommendation, memoryHint: hint,
            created_at: new Date().toISOString(),
          };
          setThread((t) => [...t, cortexTurn]);
          lastPlanIdRef.current = cortexTurn.id;
        } catch { /* */ }
        finally {
          es.close(); esRef.current = null;
          setSending(false); setPhase(null);
          loadOpps(); loadStrategy();
        }
      });
      es.addEventListener('error', () => {
        toast({ title: 'Cortex failed to respond', variant: 'destructive' });
        es.close(); esRef.current = null;
        setSending(false); setPhase(null);
      });
    } catch (e) {
      toast({ title: 'Cortex stream failed', description: e.message, variant: 'destructive' });
      setSending(false); setPhase(null);
    }
  };

  // ----- Plan-card actions ------------------------------------------
  const handleAction = async (action, turn, doneCb) => {
    const rec = turn.recommendation;
    // Recommendation-lite actions don't require a rec object — handle first.
    if (action === 'decline-recommendation') {
      setThread((t) => t.map((x) => x.id === turn.id
        ? { ...x, _stale: true } : x));
      setDraft("Not yet — let's discuss this more first.");
      return;
    }
    if (action === 'accept-recommendation') {
      const summary = turn.recommendation_summary
        || turn.message?.split('\n')[0]
        || 'the recommended mission';
      setDraft(`Yes, please create the mission: ${summary}`);
      setTimeout(send, 80);
      return;
    }
    if (!rec) return;
    if (action === 'preview') {
      toast({ title: 'Preview',
              description: rec.expected_outcome || rec.summary || 'See reasoning above.' });
      return;
    }
    setBusyId(turn.id);
    try {
      if (action === 'cancel') {
        await axios.post(`${API}/cortex/plan/cancel`,
                          { recommendation: rec, reason: 'user_dismissed' },
                          { withCredentials: true });
        toast({ title: 'Plan dismissed',
                description: "Cortex won't re-suggest this for 7 days." });
        setThread((t) => t.map((x) => x.id === turn.id
          ? { ...x, _stale: true, _dismissed: true } : x));
      } else if (action === 'email') {
        const r = await axios.post(`${API}/cortex/plan/email`,
                                     { recommendation: rec },
                                     { withCredentials: true });
        toast({ title: 'Plan emailed',
                description: r.data?.message || 'Sent to your inbox.' });
      } else {
        const body = { recommendation: rec };
        if (action === 'automate') body.override_autonomy = 5;
        const r = await axios.post(`${API}/cortex/console/execute`, body,
                                     { withCredentials: true });
        const taken = r.data?.action_taken || 'queued';
        toast({
          title: `Cortex · ${taken.toUpperCase()}`,
          description: r.data?.message || `Autonomy L${r.data?.autonomy_level}.`,
        });
        if (r.data?.mission_id) {
          setThread((t) => t.map((x) => x.id === turn.id
            ? { ...x, _stale: true, _launched: true } : x));
          trackedMissionsRef.current[r.data.mission_id] = {
            title: rec.title || 'Mission',
            lastSeen: new Date().toISOString(),
          };
          setTimeout(loadActiveMissions, 400);
        }
        if (r.data?.followup?.message) {
          setThread((t) => [...t, {
            id: r.data.followup.id || `f-${Date.now()}`,
            role: 'cortex',
            message: r.data.followup.message,
            followup_for: r.data.followup.for,
            created_at: new Date().toISOString(),
          }]);
        } else {
          setThread((t) => [...t, {
            id: `s-${Date.now()}`, role: 'cortex',
            message: r.data?.message || `Executed (L${r.data?.autonomy_level})`,
            created_at: new Date().toISOString(),
          }]);
        }
        loadExec(); loadOpps();
      }
    } catch (e) {
      toast({ title: `${action} failed`,
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const handlePrompt = (item) => {
    if (item.prompt) { setDraft(item.prompt); return; }
    const t = item.title || item.type || 'this opportunity';
    setDraft(`Tell me more about: ${t}`);
  };

  const hasHistory = thread.length > 0;
  const railWidthCss = rail.collapsed ? '0px' : `${rail.width}px`;
  const gridTemplate = `1fr ${rail.collapsed ? '' : '8px'} ${railWidthCss}`.trim();

  return (
    <DashboardLayout
      title="Cortex · Command Center"
      subtitle="Your AI executive. Ask anything — Cortex plans, explains, and executes."
      headerExtra={
        <div className="flex items-center gap-2">
          <button onClick={() => setSearchOpen(true)} data-testid="memory-search-btn"
                  title="Search past conversations (⌘⇧K)"
                  className="text-[11px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/5 transition flex items-center gap-1.5">
            <Search size={11} /> Search memory
          </button>
          <button onClick={rail.toggle} data-testid="rail-toggle-btn"
                  title={rail.collapsed ? 'Show rail' : 'Hide rail'}
                  className="w-8 h-8 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/5 transition flex items-center justify-center">
            {rail.collapsed ? <PanelRightOpen size={13} /> : <PanelRightClose size={13} />}
          </button>
        </div>
      }
    >
      <div className="grid gap-0 lg:grid-cols-[1fr_auto_auto]"
            style={{ gridTemplateColumns: window.innerWidth >= 1024 ? gridTemplate : undefined }}>
        {/* Left: conversation — chat area is now the dominant surface */}
        <div className="flex flex-col gap-3 min-h-[85vh]">
          <div ref={scrollRef}
               data-testid="cortex-chat-thread"
               className="flex-1 rounded-2xl border border-white/5 bg-white/[0.02] p-5 overflow-y-auto min-h-[68vh] max-h-[80vh]">
            {!hasHistory && !sending && (
              <div data-testid="cortex-empty-state"
                   className="h-full flex flex-col items-center justify-center text-center py-12">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center mb-4 shadow-xl shadow-violet-500/30">
                  <Sparkles size={22} className="text-white" />
                </div>
                <div className="text-[18px] font-semibold text-white mb-1">
                  I'm Cortex — your AI executive.
                </div>
                <div className="text-[12.5px] text-zinc-400 max-w-md leading-relaxed">
                  Tell me what you want to grow. I'll analyze your business,
                  propose missions with reasoning, cost, timeline, and risk —
                  then execute through the autonomy you've granted me.
                </div>
              </div>
            )}
            {thread.map((turn) => (
              <ChatMessage key={turn.id || turn.created_at}
                            turn={turn}
                            busyId={busyId}
                            isStale={turn._stale}
                            onClarifyPick={(q) => setDraft(`${q} — `)}
                            onAction={handleAction} />
            ))}
            <PhaseIndicator phase={sending ? phase : null}
                              phaseHistory={phaseHistory} />
          </div>
          <Composer value={draft} onChange={setDraft}
                    onSubmit={send} sending={sending} />
          <ExecutionLog items={execItems} loading={execLoading}
                          onRefresh={loadExec} />
        </div>

        {!rail.collapsed && (
          <div {...rail.dragProps} data-testid="rail-drag-handle"
               className="hidden lg:flex items-center justify-center cursor-col-resize group">
            <div className="w-1 h-12 rounded-full bg-white/5 group-hover:bg-violet-500/40 transition">
              <GripVertical size={12} className="text-zinc-700 group-hover:text-violet-300 mx-auto -mt-1 opacity-0 group-hover:opacity-100" />
            </div>
          </div>
        )}

        {!rail.collapsed && (
          <div className="lg:max-h-[90vh] lg:sticky lg:top-4">
            <OpportunityRail
              opportunities={opportunities}
              loading={oppLoading}
              strategy={strategy}
              activeMissions={activeMissions}
              missionsLoading={missionsLoading}
              onOpenMission={() => navigate(`/dashboard/missions`)}
              onDiscussFinding={(f) => {
                setDraft(`I see Cortex flagged: "${f.bottleneck}". What's your reasoning, and what would you recommend?`);
              }}
              onPrompt={handlePrompt}
            />
          </div>
        )}
      </div>

      <MemorySearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </DashboardLayout>
  );
};

export default CommandCenter;
