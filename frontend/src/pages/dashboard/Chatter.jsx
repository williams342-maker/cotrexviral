import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, MessagesSquare, ArrowRight, CheckCircle2, AlertTriangle, Clock } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Chatter — agent-to-agent message audit log.
   Each row shows: from→to · query · response · status · time.
   Click a row to expand the full thread. */

const STATUS_META = {
  answered: { label: 'Answered', color: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  errored:  { label: 'Errored',  color: 'bg-rose-100 text-rose-700 border-rose-200', icon: AlertTriangle },
  pending:  { label: 'Pending',  color: 'bg-amber-100 text-amber-700 border-amber-200', icon: Clock },
};

const AGENT_COLORS = {
  vera:  '#8B5CF6', atlas: '#0EA5E9', nova: '#EC4899',
  rae:   '#22C55E', lyra:  '#F59E0B', echo: '#3B82F6',
  ori:   '#06B6D4', jules: '#EF4444',
};

const Chatter = () => {
  const { toast } = useToast();
  const [messages, setMessages] = useState([]);
  const [stats, setStats] = useState({ total: 0, answered: 0, errored: 0 });
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [thread, setThread] = useState([]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/agent-messages?limit=100`, { withCredentials: true });
      setMessages(r.data.items || []);
      setStats({ total: r.data.total, answered: r.data.answered, errored: r.data.errored });
    } catch (e) {
      toast({ title: 'Failed to load chatter', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const expand = async (m) => {
    if (expandedId === m.id) { setExpandedId(null); setThread([]); return; }
    setExpandedId(m.id);
    try {
      const r = await axios.get(`${API}/agent-messages/${m.id}`, { withCredentials: true });
      setThread(r.data.thread || []);
    } catch (e) {
      toast({ title: 'Failed to load thread', variant: 'destructive' });
    }
  };

  return (
    <DashboardLayout title="Agent Chatter" subtitle="When agents query each other before bothering you.">
      <div className="space-y-6" data-testid="chatter-page">

        {/* Hero */}
        <div className="rounded-2xl border border-indigo-200/60 bg-gradient-to-br from-indigo-50 via-white to-indigo-50 p-6 flex items-start gap-5">
          <span className="w-12 h-12 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center shrink-0">
            <MessagesSquare size={22} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-indigo-600 font-bold mb-1">Phase 6 · Agent ↔ Agent bus</div>
            <h2 className="text-lg font-semibold text-neutral-900 mb-1">Agents consult each other before routing to you.</h2>
            <p className="text-[13px] text-neutral-600 leading-relaxed">
              Atlas asks Lyra "what's the theme?" before proposing briefs. Ori asks Rae "is this audience worth testing?" before opening an experiment. Every hand-off is logged here for transparency.
            </p>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className="text-[11px] uppercase tracking-widest font-bold px-2.5 py-1 rounded-full border bg-indigo-50 border-indigo-200 text-indigo-700" data-testid="total-msgs">
              {stats.total} total
            </span>
            <span className="text-[11px] uppercase tracking-widest font-bold px-2.5 py-1 rounded-full border bg-emerald-50 border-emerald-200 text-emerald-700">
              {stats.answered} answered
            </span>
            {stats.errored > 0 && (
              <span className="text-[11px] uppercase tracking-widest font-bold px-2.5 py-1 rounded-full border bg-rose-50 border-rose-200 text-rose-700">
                {stats.errored} errored
              </span>
            )}
          </div>
        </div>

        {loading && <div className="flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading chatter…</div>}

        {!loading && messages.length === 0 && (
          <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-300" data-testid="empty">
            <MessagesSquare size={28} className="mx-auto text-neutral-400 mb-3" />
            <p className="text-neutral-600 font-medium">No agent chatter yet.</p>
            <p className="text-[12.5px] text-neutral-500 mt-1">Trigger a "Propose now" on the Briefs page — Atlas will consult Lyra and the message will appear here.</p>
          </div>
        )}

        <div className="space-y-2">
          {messages.map((m) => {
            const meta = STATUS_META[m.status] || STATUS_META.answered;
            const StatusIcon = meta.icon;
            const fromColor = AGENT_COLORS[m.from_agent] || '#737373';
            const toColor   = AGENT_COLORS[m.to_agent]   || '#737373';
            const isOpen = expandedId === m.id;
            return (
              <div key={m.id} className="rounded-xl border border-neutral-200/70 bg-white overflow-hidden" data-testid={`msg-${m.id}`}>
                <button
                  onClick={() => expand(m)}
                  className="w-full px-4 py-3 flex items-center gap-4 hover:bg-neutral-50 text-left"
                >
                  <div className="flex items-center gap-2 shrink-0">
                    <AgentPill id={m.from_agent} color={fromColor} />
                    <ArrowRight size={13} className="text-neutral-400" />
                    <AgentPill id={m.to_agent} color={toColor} />
                  </div>
                  <div className="flex-1 min-w-0 text-[12.5px] text-neutral-700 leading-relaxed truncate">
                    <span className="text-neutral-500">"</span>{m.query}<span className="text-neutral-500">"</span>
                  </div>
                  <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border font-bold flex items-center gap-1 ${meta.color}`}>
                    <StatusIcon size={10} /> {meta.label}
                  </span>
                  <span className="text-[10.5px] text-neutral-400 tabular-nums shrink-0">{new Date(m.created_at).toLocaleString()}</span>
                </button>
                {isOpen && (
                  <div className="px-5 py-4 bg-neutral-50/60 border-t border-neutral-100 space-y-3" data-testid={`thread-${m.id}`}>
                    {thread.map((t) => (
                      <div key={t.id} className="text-[12.5px] leading-relaxed">
                        <div className="text-[10px] uppercase tracking-widest font-bold mb-0.5" style={{ color: AGENT_COLORS[t.from_agent] || '#737373' }}>
                          {t.from_agent} → {t.to_agent}
                        </div>
                        <div className="bg-white rounded-lg border border-neutral-200 p-3">
                          <div className="text-neutral-500 italic mb-2">Q: {t.query}</div>
                          {t.context_summary && (
                            <div className="text-[11px] font-mono bg-neutral-100 text-neutral-600 rounded p-2 mb-2 whitespace-pre-wrap line-clamp-4">{t.context_summary}</div>
                          )}
                          <div className="text-neutral-800 whitespace-pre-wrap">A: {t.response || <span className="text-rose-600">{t.error || '(no response)'}</span>}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </DashboardLayout>
  );
};

const AgentPill = ({ id, color }) => (
  <span
    className="text-[10.5px] uppercase tracking-widest font-bold px-2 py-0.5 rounded-md border"
    style={{ color, borderColor: `${color}55`, backgroundColor: `${color}11` }}
  >
    {id}
  </span>
);

export default Chatter;
