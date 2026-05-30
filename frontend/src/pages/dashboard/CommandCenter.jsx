import React, { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles, Send, Loader2, Brain, ArrowUp, Command,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';
import PlanCard from './cortex/PlanCard';
import OpportunityRail from './cortex/OpportunityRail';
import ExecutionLog from './cortex/ExecutionLog';

/* /dashboard — the Conversational Command Center.

   This is the primary product surface. Users interact with Cortex
   through natural language. Cortex understands goals, proposes plans
   with reasoning/confidence/cost/timeline/risk, and executes through
   the autonomy engine (L0-L5).

   Layout:
     ┌─────────────────────────────┬──────────────┐
     │   Conversation thread       │              │
     │   (chat + inline plan cards)│  Opportunity │
     │                             │  Rail        │
     │                             │  · Strategy  │
     │   Composer (Message Cortex) │  · Opps      │
     ├─────────────────────────────┴──────────────┤
     │   Execution Log (collapsible)              │
     └────────────────────────────────────────────┘
*/

const ChatMessage = ({ turn, onAction, busyId, onPrompt }) => {
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
  // Cortex turn
  return (
    <div data-testid="chat-cortex-turn" className="flex items-start gap-3 mb-4">
      <span className="shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
        <Brain size={14} className="text-white" />
      </span>
      <div className="flex-1 min-w-0 space-y-3">
        <div className="text-[10px] uppercase tracking-widest font-semibold text-violet-300">
          Cortex
        </div>
        {turn.message && (
          <div className="text-[13.5px] text-zinc-200 leading-relaxed whitespace-pre-line">
            {turn.message}
          </div>
        )}
        {turn.recommendation && (
          <PlanCard rec={turn.recommendation}
                    busy={busyId === turn.id}
                    onPreview={() => onAction('preview', turn)}
                    onExecute={() => onAction('execute', turn)}
                    onAutomate={() => onAction('automate', turn)} />
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
  // Auto-resize textarea up to 6 lines.
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


const CommandCenter = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [thread, setThread]   = useState([]);     // chat turns
  const [draft, setDraft]     = useState('');
  const [sending, setSending] = useState(false);
  const [busyId, setBusyId]   = useState(null);
  const [strategy, setStrategy] = useState(null);
  const [opportunities, setOpps] = useState([]);
  const [oppLoading, setOppLoading] = useState(true);
  const [execItems, setExecItems] = useState([]);
  const [execLoading, setExecLoading] = useState(true);

  const scrollRef = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/console/history?limit=40`,
                                  { withCredentials: true });
      setThread(r.data?.turns || []);
    } catch (e) {
      // Empty history is fine on first load.
    }
  }, []);
  const loadStrategy = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/memory/strategy`,
                                  { withCredentials: true });
      setStrategy(r.data || null);
    } catch (_e) { /* non-fatal */ }
  }, []);
  const loadOpps = useCallback(async () => {
    setOppLoading(true);
    try {
      const r = await axios.get(`${API}/cortex/console/opportunities?limit=8`,
                                  { withCredentials: true });
      setOpps(r.data?.opportunities || []);
    } catch (_e) {
      setOpps([]);
    } finally { setOppLoading(false); }
  }, []);
  const loadExec = useCallback(async () => {
    setExecLoading(true);
    try {
      const r = await axios.get(`${API}/cortex/execution-log?limit=20`,
                                  { withCredentials: true });
      setExecItems(r.data?.items || []);
    } catch (_e) {
      setExecItems([]);
    } finally { setExecLoading(false); }
  }, []);

  useEffect(() => {
    loadHistory();
    loadStrategy();
    loadOpps();
    loadExec();
  }, [loadHistory, loadStrategy, loadOpps, loadExec]);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [thread]);

  const send = async () => {
    const msg = draft.trim();
    if (!msg || sending) return;
    setSending(true);
    // Optimistic user turn.
    const userTurn = {
      id: `u-${Date.now()}`, role: 'user',
      message: msg, created_at: new Date().toISOString(),
    };
    setThread((t) => [...t, userTurn]);
    setDraft('');
    try {
      const r = await axios.post(`${API}/cortex/console/chat`,
                                   { message: msg },
                                   { withCredentials: true });
      const cortexTurn = {
        id: `c-${Date.now()}`,
        role: 'cortex',
        message: r.data?.ack || '',
        intent: r.data?.intent,
        params: r.data?.params,
        recommendation: r.data?.recommendation,
        created_at: new Date().toISOString(),
      };
      setThread((t) => [...t, cortexTurn]);
      // Refresh side data after each turn.
      loadOpps();
      loadStrategy();
    } catch (e) {
      toast({
        title: 'Cortex failed to respond',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setSending(false); }
  };

  const handleAction = async (action, turn) => {
    const rec = turn.recommendation;
    if (!rec) return;
    if (action === 'preview') {
      // Just scroll/highlight; no execution. Show toast for now.
      toast({
        title: 'Preview',
        description: rec.expected_outcome || rec.summary || 'See reasoning above.',
      });
      return;
    }
    setBusyId(turn.id);
    try {
      const body = { recommendation: rec };
      if (action === 'automate') {
        body.override_autonomy = 5;   // full autopilot
      }
      const r = await axios.post(`${API}/cortex/console/execute`, body,
                                   { withCredentials: true });
      const taken = r.data?.action_taken || 'queued';
      const lvl = r.data?.autonomy_level;
      toast({
        title: `Cortex · ${taken.toUpperCase()}`,
        description: r.data?.message || `Action complete (autonomy L${lvl}).`,
      });
      // Append a small system message into the thread.
      setThread((t) => [...t, {
        id: `s-${Date.now()}`, role: 'cortex',
        message: r.data?.message || `Executed (L${lvl})`,
        created_at: new Date().toISOString(),
      }]);
      // If a mission was launched, hint the user toward Mission Control.
      if (r.data?.mission_id) {
        setTimeout(() => {
          toast({
            title: 'Mission launched',
            description: 'Tap to open Mission Control →',
            action: <button onClick={() => navigate('/dashboard/missions')}
                            className="text-[11px] font-semibold text-violet-300">
                      Open
                    </button>,
          });
        }, 600);
      }
      loadExec();
      loadOpps();
    } catch (e) {
      toast({
        title: 'Execution failed',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally { setBusyId(null); }
  };

  const handlePrompt = (item) => {
    // OpportunityRail clicked — pre-fill composer with a smart prompt.
    if (item.prompt) {
      setDraft(item.prompt);
      return;
    }
    const t = item.title || item.type || 'this opportunity';
    setDraft(`Tell me more about: ${t}`);
  };

  const hasHistory = thread.length > 0;

  return (
    <DashboardLayout
      title="Cortex · Command Center"
      subtitle="Your AI executive. Ask anything — Cortex plans, explains, and executes."
    >
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* Left: conversation */}
        <div className="flex flex-col gap-3 min-h-[70vh]">
          {/* Thread */}
          <div ref={scrollRef}
               data-testid="cortex-chat-thread"
               className="flex-1 rounded-2xl border border-white/5 bg-white/[0.02] p-5 overflow-y-auto max-h-[68vh] min-h-[50vh]">
            {!hasHistory && (
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
            {hasHistory && thread.map((turn) => (
              <ChatMessage key={turn.id || turn.created_at}
                            turn={turn}
                            busyId={busyId}
                            onAction={handleAction} />
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-[12px] text-zinc-500 italic">
                <Loader2 size={11} className="animate-spin" /> Cortex is thinking…
              </div>
            )}
          </div>
          {/* Composer */}
          <Composer value={draft} onChange={setDraft}
                    onSubmit={send} sending={sending} />
          {/* Execution log */}
          <ExecutionLog items={execItems} loading={execLoading}
                          onRefresh={loadExec} />
        </div>

        {/* Right: opportunity rail */}
        <div className="lg:max-h-[90vh] lg:sticky lg:top-4">
          <OpportunityRail
            opportunities={opportunities}
            loading={oppLoading}
            strategy={strategy}
            onPrompt={handlePrompt}
          />
        </div>
      </div>
    </DashboardLayout>
  );
};

export default CommandCenter;
