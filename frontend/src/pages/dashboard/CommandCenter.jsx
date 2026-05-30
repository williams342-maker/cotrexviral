import React, { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Loader2, Brain, ArrowUp, Command,
  PanelRightClose, PanelRightOpen, GripVertical, Search,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';
import PlanCard from './cortex/PlanCard';
import OpportunityRail from './cortex/OpportunityRail';
import ExecutionLog from './cortex/ExecutionLog';
import useResizableRail from '../../hooks/useResizableRail';

/* /dashboard — the Conversational Command Center.

   v2 features (this iteration):
     · Right rail is collapsible + drag-resizable (persisted via localStorage)
     · PlanCard supports minimize / cancel / email / close
     · SSE-streamed chat shows live phases: classifying → recalling → planning → ready
     · Stale plan card is marked "superseded" when a new turn is sent
     · Memory continuity hint surfaces "Based on our prior conversation…" on plans
*/

const PHASE_COPY = {
  classifying: 'Understanding your goal…',
  recalling:   'Recalling our prior conversations…',
  planning:    'Cortex is drafting the plan…',
  ready:       'Done.',
};


const ChatMessage = ({ turn, onAction, busyId, isStale }) => {
  const isUser = turn.role === 'user';
  if (isUser) {
    return (
      <div data-testid="chat-user-turn" className="flex justify-end mb-3">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-violet-500/15 border border-violet-500/30 px-4 py-2.5 text-[13.5px] text-zinc-100 leading-relaxed">
          {turn.message}
        </div>
      </div>
    );
  }
  return (
    <div data-testid="chat-cortex-turn" className="flex items-start gap-3 mb-4">
      <span className="shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
        <Brain size={14} className="text-white" />
      </span>
      <div className="flex-1 min-w-0 space-y-3">
        <div className="text-[10px] uppercase tracking-widest font-semibold text-violet-300">
          Cortex {isStale && <span className="text-zinc-500 normal-case tracking-normal ml-2">· superseded</span>}
        </div>
        {turn.message && (
          <div className={`text-[13.5px] leading-relaxed whitespace-pre-line ${
            isStale ? 'text-zinc-500' : 'text-zinc-200'
          }`}>
            {turn.message}
          </div>
        )}
        {turn.recommendation && (
          <PlanCard rec={turn.recommendation}
                    memoryHint={turn.memoryHint}
                    busy={busyId === turn.id}
                    initiallyMinimized={isStale && !turn._dismissed}
                    dismissed={turn._dismissed || isStale}
                    onPreview={() => onAction('preview', turn)}
                    onExecute={() => onAction('execute', turn)}
                    onAutomate={() => onAction('automate', turn)}
                    onCancel={(onDone) => onAction('cancel', turn, onDone)}
                    onEmail={() => onAction('email', turn)} />
        )}
      </div>
    </div>
  );
};


const Composer = ({ value, onChange, onSubmit, sending }) => {
  const ref = useRef(null);
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 144) + 'px';
  }, [value]);

  return (
    <div data-testid="cortex-composer"
         className="rounded-2xl border border-white/10 bg-white/[0.03] focus-within:border-violet-500/40 backdrop-blur-md transition">
      <div className="flex items-end gap-2 p-2">
        <textarea ref={ref} rows={1}
          data-testid="cortex-composer-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Message Cortex — try: 'recruit 50 woodworking sellers' or 'what should I focus on this week?'"
          className="flex-1 resize-none bg-transparent px-2 py-2 text-[13.5px] text-white placeholder:text-zinc-500 focus:outline-none leading-relaxed"
          disabled={sending} />
        <button onClick={onSubmit} disabled={sending || !value.trim()}
                data-testid="cortex-composer-send"
                className="shrink-0 w-9 h-9 rounded-lg bg-violet-500 hover:bg-violet-400 disabled:bg-white/5 disabled:cursor-not-allowed text-white flex items-center justify-center transition shadow-lg shadow-violet-500/20 disabled:shadow-none">
          {sending ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}
        </button>
      </div>
      <div className="px-3 pb-2 pt-0.5 text-[10px] text-zinc-500 flex items-center gap-2">
        <Command size={10} /> Press Enter to send, Shift+Enter for newline
      </div>
    </div>
  );
};


/* Memory search modal — semantic recall across all past conversations. */
const MemorySearch = ({ open, onClose }) => {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState([]);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/cortex/memory/recall`,
                                  { query: q, k: 8 },
                                  { withCredentials: true });
      setHits(r.data?.hits || []);
    } finally { setBusy(false); }
  };
  if (!open) return null;
  return (
    <div data-testid="cortex-memory-search-modal"
         className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center pt-24 px-4"
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className="w-full max-w-2xl rounded-2xl border border-white/10 bg-zinc-950 shadow-2xl">
        <div className="p-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Search size={14} className="text-violet-300" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && run()}
                    data-testid="memory-search-input"
                    placeholder="Search past conversations: e.g. 'Etsy sellers', 'Father's Day'"
                    className="flex-1 bg-transparent text-[14px] text-white placeholder:text-zinc-500 focus:outline-none" />
            {busy && <Loader2 size={13} className="animate-spin text-zinc-500" />}
            <button onClick={onClose} className="text-zinc-500 hover:text-white text-[11px]">Esc</button>
          </div>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-4 space-y-2">
          {hits.length === 0 && !busy && q && (
            <div className="text-[12px] text-zinc-500 italic">No relevant past messages found.</div>
          )}
          {hits.map((h, i) => (
            <div key={i} data-testid={`memory-hit-${i}`}
                  className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
              <div className="flex items-center gap-2 text-[10px] text-zinc-500 mb-1 uppercase tracking-wider">
                <span>{h.role}</span>
                <span>· {(h.created_at || '').slice(0, 10)}</span>
                <span className="ml-auto">score {Math.round(h.score * 100) / 100}</span>
              </div>
              <div className="text-[13px] text-zinc-200 leading-relaxed">{h.text}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};


const CommandCenter = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [thread, setThread]   = useState([]);
  const [draft, setDraft]     = useState('');
  const [sending, setSending] = useState(false);
  const [phase, setPhase]     = useState(null);          // SSE phase indicator
  const [busyId, setBusyId]   = useState(null);
  const [strategy, setStrategy] = useState(null);
  const [opportunities, setOpps] = useState([]);
  const [oppLoading, setOppLoading] = useState(true);
  const [execItems, setExecItems] = useState([]);
  const [execLoading, setExecLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const lastPlanIdRef = useRef(null);                    // for stale-marking

  const rail = useResizableRail({
    key: 'cortex-right-rail',
    defaultWidth: 320, min: 240, max: 520, side: 'right',
  });

  const scrollRef = useRef(null);
  const esRef = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/console/history?limit=40`,
                                  { withCredentials: true });
      const turns = r.data?.turns || [];
      // Mark all but the latest plan card as superseded so old proposals collapse.
      let latestPlanIdx = -1;
      for (let i = turns.length - 1; i >= 0; i--) {
        if (turns[i].recommendation) { latestPlanIdx = i; break; }
      }
      const annotated = turns.map((t, i) => ({
        ...t,
        _stale: t.recommendation && i !== latestPlanIdx,
      }));
      setThread(annotated);
      lastPlanIdRef.current = latestPlanIdx >= 0 ? turns[latestPlanIdx].id : null;
    } catch (_e) { /* empty history is fine */ }
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

  useEffect(() => {
    loadHistory(); loadStrategy(); loadOpps(); loadExec();
  }, [loadHistory, loadStrategy, loadOpps, loadExec]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thread, phase]);

  // Cmd/Ctrl+K → memory search
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && !e.shiftKey) {
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
    // Mark prior plan card as superseded immediately (stale UX fix).
    setThread((t) => t.map((turn) =>
      turn.recommendation ? { ...turn, _stale: true } : turn
    ));

    // Optimistic user turn.
    const userTurn = {
      id: `u-${Date.now()}`, role: 'user', message: msg,
      created_at: new Date().toISOString(),
    };
    setThread((t) => [...t, userTurn]);
    setDraft('');

    // SSE stream.
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
            message: d?.ack || '', intent: d?.intent, params: d?.params,
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
      es.addEventListener('error', (ev) => {
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
        // Mark turn dismissed — card stays visible with grey/dismissed styling
        // and disabled actions (per spec). Does NOT close (X) the card.
        setThread((t) => t.map((x) => x.id === turn.id
          ? { ...x, _stale: true, _dismissed: true } : x));
        // Note: doneCb intentionally NOT called — we want the dismissed card to remain.
      } else if (action === 'email') {
        const r = await axios.post(`${API}/cortex/plan/email`,
                                     { recommendation: rec },
                                     { withCredentials: true });
        toast({ title: 'Plan emailed',
                description: r.data?.message || 'Sent to your inbox.' });
      } else {
        // execute / automate
        const body = { recommendation: rec };
        if (action === 'automate') body.override_autonomy = 5;
        const r = await axios.post(`${API}/cortex/console/execute`, body,
                                     { withCredentials: true });
        const taken = r.data?.action_taken || 'queued';
        toast({
          title: `Cortex · ${taken.toUpperCase()}`,
          description: r.data?.message || `Autonomy L${r.data?.autonomy_level}.`,
        });
        setThread((t) => [...t, {
          id: `s-${Date.now()}`, role: 'cortex',
          message: r.data?.message || `Executed (L${r.data?.autonomy_level})`,
          created_at: new Date().toISOString(),
        }]);
        if (r.data?.mission_id) {
          setTimeout(() => toast({
            title: 'Mission launched',
            description: 'Tap to open Mission Control →',
            action: <button onClick={() => navigate('/dashboard/missions')}
                            className="text-[11px] font-semibold text-violet-300">Open</button>,
          }), 600);
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
                  title="Search past conversations (⌘K)"
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
        {/* Left: conversation */}
        <div className="flex flex-col gap-3 min-h-[70vh]">
          <div ref={scrollRef}
               data-testid="cortex-chat-thread"
               className="flex-1 rounded-2xl border border-white/5 bg-white/[0.02] p-5 overflow-y-auto max-h-[68vh] min-h-[50vh]">
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
                            onAction={handleAction} />
            ))}
            {sending && phase && (
              <div data-testid="cortex-phase-indicator"
                   className="flex flex-col gap-1 mt-2">
                <div className="flex items-center gap-2 text-[12px] text-violet-300 italic">
                  <Loader2 size={11} className="animate-spin" />
                  <span className="font-medium">{phase.label}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-wider">· {phase.phase}</span>
                </div>
                {phaseHistory.length > 1 && (
                  <div className="flex items-center gap-1.5 ml-5 text-[10px] text-zinc-600">
                    {phaseHistory.slice(0, -1).map((p, i) => (
                      <React.Fragment key={i}>
                        <span className="text-emerald-500/60">✓</span>
                        <span>{p.phase}</span>
                        <span>·</span>
                      </React.Fragment>
                    ))}
                    <span className="text-violet-400">{phase.phase}…</span>
                  </div>
                )}
              </div>
            )}
          </div>
          <Composer value={draft} onChange={setDraft}
                    onSubmit={send} sending={sending} />
          <ExecutionLog items={execItems} loading={execLoading}
                          onRefresh={loadExec} />
        </div>

        {/* Drag handle (visible on lg+) */}
        {!rail.collapsed && (
          <div {...rail.dragProps} data-testid="rail-drag-handle"
               className="hidden lg:flex items-center justify-center cursor-col-resize group">
            <div className="w-1 h-12 rounded-full bg-white/5 group-hover:bg-violet-500/40 transition">
              <GripVertical size={12} className="text-zinc-700 group-hover:text-violet-300 mx-auto -mt-1 opacity-0 group-hover:opacity-100" />
            </div>
          </div>
        )}

        {/* Right rail */}
        {!rail.collapsed && (
          <div className="lg:max-h-[90vh] lg:sticky lg:top-4">
            <OpportunityRail
              opportunities={opportunities}
              loading={oppLoading}
              strategy={strategy}
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
