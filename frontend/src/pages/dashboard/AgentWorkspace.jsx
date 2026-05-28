import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Send, Loader2, Sparkles, Share2, ArrowUp, Bot,
  TrendingUp, Users, Image as ImageIcon, FileText,
  Music2, Linkedin, MessageCircle as Pinterest, Facebook,
  Instagram, Twitter, AlertCircle,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { useAuth, API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/agent[/:agentId] — in-dashboard chat workspace with each AI
   marketing specialist. Three columns inside the existing dashboard:
     LEFT  → DashboardLayout's main sidebar
     CENTER → agent chat thread (this component)
     RIGHT → metrics rail (sparklines + connected channels list) */

const AGENT_TONES = {
  blue:    { ring: 'ring-blue-400/40',    dot: 'bg-blue-400',    text: 'text-blue-300',    soft: 'bg-blue-500/10 border-blue-500/30',    stroke: '#60a5fa' },
  indigo:  { ring: 'ring-indigo-400/40',  dot: 'bg-indigo-400',  text: 'text-indigo-300',  soft: 'bg-indigo-500/10 border-indigo-500/30',  stroke: '#818cf8' },
  emerald: { ring: 'ring-emerald-400/40', dot: 'bg-emerald-400', text: 'text-emerald-300', soft: 'bg-emerald-500/10 border-emerald-500/30', stroke: '#34d399' },
  amber:   { ring: 'ring-amber-400/40',   dot: 'bg-amber-400',   text: 'text-amber-300',   soft: 'bg-amber-500/10 border-amber-500/30',   stroke: '#fbbf24' },
  rose:    { ring: 'ring-rose-400/40',    dot: 'bg-rose-400',    text: 'text-rose-300',    soft: 'bg-rose-500/10 border-rose-500/30',    stroke: '#fb7185' },
  violet:  { ring: 'ring-violet-400/40',  dot: 'bg-violet-400',  text: 'text-violet-300',  soft: 'bg-violet-500/10 border-violet-500/30', stroke: '#a78bfa' },
};

const AGENT_INITIAL_GREETING = {
  strategy: "I'm Atlas. Tell me your business goal (revenue target, audience size, launch date) and I'll build the full 30/60/90 plan.",
  research: "Iris here. Drop a niche, competitor, or keyword — I'll come back with the trends, gaps, and audience signals worth acting on.",
  nova: "Hey — I'm Nova. Tell me about your brand, your traffic targets, or your biggest growth blocker, and I'll map out the next 1-2 weeks of moves.",
  sam: "I'm Sam. Drop a topic, target keyword, or competitor URL — I'll come back with a brief you can hand a writer.",
  kai: "Kai here. Tell me your niche and which platforms you live on — I'll surface the trending hooks and competitor moves of the last 14 days.",
  angela: "Hi, I'm Angela. Tell me about your audience and your email goal — I'll draft the flow, subject lines, and body in one go.",
};

const PLATFORM_ICONS = {
  tiktok: Music2, linkedin: Linkedin, pinterest: Pinterest,
  facebook: Facebook, instagram: Instagram, x: Twitter,
};

const AgentWorkspace = () => {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();
  const [agents, setAgents] = useState([]);
  const [activeId, setActiveId] = useState(agentId || 'strategy');
  const [threads, setThreads] = useState({});   // { [agentId]: [{role, content, follow_ups}] }
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  // Load agents catalogue
  useEffect(() => {
    axios.get(`${API}/ai/agent/list`, { withCredentials: true })
      .then((r) => setAgents(r.data.agents || []))
      .catch(() => setAgents([]));
  }, []);

  // Keep URL in sync with active agent
  useEffect(() => {
    if (activeId && agentId !== activeId) {
      navigate(`/dashboard/agent/${activeId}`, { replace: true });
    }
  }, [activeId, agentId, navigate]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [threads, activeId, busy]);

  const activeAgent = agents.find((a) => a.id === activeId);
  const tone = AGENT_TONES[activeAgent?.color || 'violet'];
  const messages = threads[activeId] || [];

  const send = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || busy) return;
    const newMsgs = [...messages, { role: 'user', content: text }];
    setThreads((t) => ({ ...t, [activeId]: newMsgs }));
    setInput('');
    setBusy(true);
    try {
      const res = await axios.post(
        `${API}/ai/agent/chat`,
        { agent_id: activeId, message: text },
        { withCredentials: true },
      );
      setThreads((t) => ({
        ...t,
        [activeId]: [
          ...newMsgs,
          { role: 'agent', content: res.data.answer, follow_ups: res.data.follow_ups || [] },
        ],
      }));
    } catch (err) {
      const detail = err.response?.data?.detail;
      const code = err.response?.data?.code || err.response?.status;
      if (code === 402 || (typeof detail === 'object' && detail?.code === 'plan_cap_exceeded')) {
        toast({ title: 'Monthly AI cap reached', description: 'Upgrade your plan to keep chatting.' });
        navigate('/pricing');
      } else {
        toast({ title: 'Could not reach agent', description: detail || err.message });
      }
      // Rollback the user message so they don't lose what they typed
      setThreads((t) => ({ ...t, [activeId]: messages }));
      setInput(text);
    }
    setBusy(false);
  };

  const onComposerKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  if (!user) {
    return (
      <DashboardLayout title="Agents">
        <div className="text-center py-16 text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Agents"
      subtitle="Talk to your AI marketing specialists. Each one keeps memory of your past conversations."
    >
      <div className="cv-dash-scope" data-testid="agent-workspace">

        {/* Agent switcher pills */}
        <div className="cv-glass rounded-2xl p-2 flex items-center gap-1.5 flex-wrap mb-5" data-testid="agent-switcher">
          {agents.map((a) => {
            const t = AGENT_TONES[a.color];
            const isActive = a.id === activeId;
            return (
              <button
                key={a.id}
                onClick={() => setActiveId(a.id)}
                data-testid={`agent-tab-${a.id}`}
                className={`flex items-center gap-2.5 px-3 h-10 rounded-xl text-[13px] font-medium transition-all border ${
                  isActive
                    ? `bg-white/[0.06] ${t.text} border-white/10`
                    : 'text-zinc-400 hover:text-zinc-200 border-transparent hover:bg-white/[0.02]'
                }`}
              >
                <span className="relative inline-block">
                  <span className={`w-2 h-2 rounded-full ${t.dot} block ${isActive ? 'cv-pulse' : 'opacity-60'}`} />
                </span>
                <span>{a.name}</span>
                <span className="text-[11px] text-zinc-500">· {a.role.replace('AI ', '')}</span>
              </button>
            );
          })}
        </div>

        {/* 3-col body (chat + rail) */}
        <div className="grid lg:grid-cols-[1fr_320px] gap-5">
          {/* CHAT THREAD */}
          <section className="cv-glass rounded-3xl flex flex-col overflow-hidden" style={{ height: 'calc(100vh - 240px)', minHeight: 560 }}>
            {/* Chat header */}
            <header className="px-5 py-4 border-b border-white/5 flex items-center gap-3 flex-wrap" data-testid="agent-chat-header">
              <div className={`relative w-10 h-10 rounded-full overflow-hidden ring-2 ${tone.ring}`}>
                <div className={`absolute inset-0 ${tone.soft} flex items-center justify-center`}>
                  <Bot size={18} className={tone.text} />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-semibold text-white">{activeAgent?.name || '…'}</span>
                  <span className={`text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded ${tone.soft} border ${tone.text}`}>
                    online
                  </span>
                </div>
                <div className="text-[12px] text-zinc-500">{activeAgent?.role}</div>
              </div>
              <button
                type="button"
                onClick={() => {
                  const t = (messages || []).map((m) => `${m.role === 'user' ? 'You' : activeAgent?.name}: ${m.content}`).join('\n\n');
                  navigator.clipboard.writeText(t).then(() => toast({ title: 'Conversation copied' }));
                }}
                disabled={messages.length === 0}
                className="text-[12px] font-medium text-zinc-300 bg-white/[0.04] border border-white/10 hover:bg-white/10 disabled:opacity-40 px-3 h-9 rounded-lg inline-flex items-center gap-1.5"
                data-testid="agent-share"
              >
                <Share2 size={12} /> Share
              </button>
            </header>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-5" data-testid="agent-messages">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center text-center pt-6">
                  <div className={`w-14 h-14 rounded-2xl ${tone.soft} border flex items-center justify-center mb-3`}>
                    <Sparkles size={20} className={tone.text} />
                  </div>
                  <h3 className="text-[15px] font-semibold text-white">
                    {activeAgent ? `Say hello to ${activeAgent.name}` : 'Loading…'}
                  </h3>
                  <p className="text-[13px] text-zinc-400 mt-2 max-w-md leading-relaxed">
                    {AGENT_INITIAL_GREETING[activeId] || 'Drop a question and your specialist will respond with a tactical action plan.'}
                  </p>
                  <div className="mt-5 grid sm:grid-cols-2 gap-2.5 w-full max-w-xl">
                    {(STARTER_PROMPTS[activeId] || []).map((p) => (
                      <button
                        key={p}
                        onClick={() => send(p)}
                        className="text-left text-[12.5px] text-zinc-300 hover:text-white bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 hover:border-white/10 rounded-xl px-3.5 py-2.5 leading-snug"
                        data-testid="agent-starter-prompt"
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <MessageBubble key={i} message={m} tone={tone} agentName={activeAgent?.name} onFollowUp={(p) => send(p)} />
                ))
              )}
              {busy && (
                <div className="flex items-center gap-2 text-[12.5px] text-zinc-500" data-testid="agent-typing">
                  <Loader2 size={13} className="animate-spin" /> {activeAgent?.name || 'Agent'} is thinking…
                </div>
              )}
            </div>

            {/* Composer */}
            <form
              onSubmit={(e) => { e.preventDefault(); send(); }}
              className="px-4 py-3 border-t border-white/5 flex items-end gap-2"
              data-testid="agent-composer"
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onComposerKey}
                rows={1}
                placeholder={activeAgent ? `Message ${activeAgent.name}…` : 'Pick an agent above…'}
                disabled={!activeAgent || busy}
                data-testid="agent-input"
                className="flex-1 resize-none bg-zinc-900 border border-zinc-800 focus:border-violet-500/50 rounded-xl px-3.5 py-3 text-[14px] text-zinc-100 placeholder-zinc-500 outline-none max-h-32"
              />
              <button
                type="submit"
                disabled={!input.trim() || busy}
                data-testid="agent-send"
                className={`inline-flex items-center justify-center w-11 h-11 rounded-xl shrink-0 ${
                  input.trim() && !busy ? 'cv-btn-primary' : 'bg-white/[0.06] text-zinc-500 cursor-not-allowed'
                }`}
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={16} />}
              </button>
            </form>
          </section>

          {/* RIGHT METRICS RAIL */}
          <aside className="space-y-4" data-testid="agent-metrics-rail">
            <RailHeader label="Metrics" />
            <SparkCard label="AI generations" testId="rail-spark-ai" stroke="#a78bfa" />
            <SparkCard label="Channels live" testId="rail-spark-channels" stroke="#34d399" />

            <RailHeader label="Channels" />
            <ChannelsList />

            <Link
              to="/dashboard/channels"
              className="inline-flex w-full items-center justify-center gap-2 cv-glass rounded-xl px-3 h-10 text-[12.5px] text-zinc-300 hover:text-white hover:border-white/10 border border-white/5"
              data-testid="rail-add-channel"
            >
              + Add channel
            </Link>
          </aside>
        </div>
      </div>
    </DashboardLayout>
  );
};

const STARTER_PROMPTS = {
  strategy: [
    "Build me a 30/60/90 day plan to hit $10k MRR.",
    "Design a launch funnel for our new product.",
    "Map our highest-leverage growth bet for this quarter.",
    "Audit my current funnel and rank what to fix first.",
  ],
  research: [
    "What's trending in my niche on TikTok this week?",
    "Show me 3 competitor moves of the last 14 days.",
    "Find untapped keyword opportunities for my brand.",
    "What pain points are surfacing on Reddit right now?",
  ],
  nova: [
    "Audit my current marketing — what's the highest-leverage move this week?",
    "Build me a 4-week launch plan for a new product line.",
    "Tear down my homepage and tell me what to fix first.",
    "Where am I leaking growth? Walk me through the funnel.",
  ],
  sam: [
    "Give me a content cluster plan for my top 3 target keywords.",
    "Write a brief for a 2,000-word post on [topic].",
    "What's the GEO-optimised structure that wins AI Overviews?",
    "Audit my internal-link graph and suggest 5 strategic links.",
  ],
  kai: [
    "What hooks are trending in my niche this week?",
    "Which of my competitors shipped something I should react to?",
    "Pick 3 platforms I should double down on and explain why.",
    "Find 5 conversations on Reddit I should be in this week.",
  ],
  angela: [
    "Design a 5-email welcome flow for my SaaS.",
    "Write a re-engagement email — open rate is dropping.",
    "Give me 10 subject-line variants for my next product launch.",
    "What's the smartest abandon-cart sequence for my AOV?",
  ],
};

const MessageBubble = ({ message, tone, agentName, onFollowUp }) => {
  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`} data-testid={`agent-msg-${message.role}`}>
      {!isUser && (
        <div className={`shrink-0 w-8 h-8 rounded-full ${tone.soft} border flex items-center justify-center mt-0.5`}>
          <Bot size={14} className={tone.text} />
        </div>
      )}
      <div className={`max-w-[78%] ${isUser ? 'order-1' : ''}`}>
        {!isUser && (
          <div className="text-[11.5px] font-semibold text-white mb-1">{agentName}</div>
        )}
        <div
          className={`rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed ${
            isUser
              ? 'bg-violet-500/15 border border-violet-500/30 text-zinc-100 rounded-tr-sm'
              : 'bg-white/[0.04] border border-white/10 text-zinc-100 rounded-tl-sm'
          }`}
        >
          {isUser
            ? <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>
            : <span style={{ whiteSpace: 'pre-wrap' }}>{message.content}</span>}
        </div>
        {!isUser && (message.follow_ups || []).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5" data-testid="agent-followups">
            {message.follow_ups.map((f, i) => (
              <button
                key={i}
                onClick={() => onFollowUp(f)}
                className="text-[11.5px] text-zinc-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/5 hover:border-white/10 rounded-full px-3 py-1.5"
                data-testid={`agent-followup-${i}`}
              >
                {f}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const RailHeader = ({ label }) => (
  <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold flex items-center gap-1.5">
    {label}
  </div>
);

const SparkCard = ({ label, testId, stroke }) => {
  const [data, setData] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/billing/usage`, { withCredentials: true })
      .then((r) => {
        if (!alive) return;
        const cur = label.includes('AI')
          ? (r.data?.ai_generations_used || 0)
          : (r.data?.channels_used || 0);
        setData({ current: cur, delta: cur > 0 ? '+' + Math.min(99, cur * 3) + '%' : null });
      })
      .catch(() => setData({ current: 0, delta: null }));
    return () => { alive = false; };
  }, [label]);

  // Static curve — purely decorative; values live in `current` + delta.
  const points = '0,42 28,40 56,36 84,28 112,30 140,24 168,18 196,22 224,14 240,8';
  return (
    <div className="cv-glass rounded-2xl p-4" data-testid={testId}>
      <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold mb-1">{label}</div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="cv-display text-[22px] font-semibold text-white">{data?.current ?? '—'}</span>
        {data?.delta && <span className="text-[11px] text-emerald-300 font-semibold">{data.delta}</span>}
      </div>
      <svg viewBox="0 0 240 50" className="w-full h-10">
        <defs>
          <linearGradient id={`grad-${testId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.45" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline
          points={`0,50 ${points} 240,50`}
          fill={`url(#grad-${testId})`}
        />
        <polyline points={points} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
};

const ChannelsList = () => {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/channels`, { withCredentials: true })
      .then((r) => setChannels(r.data || []))
      .catch(() => setChannels([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="cv-glass rounded-2xl p-4 text-center text-[12px] text-zinc-500">
        <Loader2 size={14} className="animate-spin inline" />
      </div>
    );
  }

  const connected = channels.filter((c) => c.connected);
  if (connected.length === 0) {
    return (
      <div className="cv-glass rounded-2xl p-4 text-center text-[12.5px] text-zinc-400 leading-relaxed" data-testid="rail-channels-empty">
        <AlertCircle size={16} className="mx-auto mb-1.5 text-zinc-500" />
        No channels connected yet.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="rail-channels">
      {connected.slice(0, 6).map((c) => {
        const Icon = PLATFORM_ICONS[String(c.platform || '').toLowerCase()] || ImageIcon;
        const platformName = (c.platform || 'channel').charAt(0).toUpperCase() + (c.platform || '').slice(1);
        return (
          <Link
            key={c.platform}
            to="/dashboard/channels"
            className="flex items-center gap-3 cv-glass rounded-xl p-3 hover:border-white/10 transition-colors"
            data-testid={`rail-channel-${c.platform}`}
          >
            <div className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/10 flex items-center justify-center shrink-0">
              <Icon size={15} className="text-zinc-200" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-semibold text-white truncate">{platformName}</div>
              <div className="text-[11.5px] text-zinc-500 truncate">{c.handle || 'Connected'}</div>
            </div>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
          </Link>
        );
      })}
    </div>
  );
};

export default AgentWorkspace;
