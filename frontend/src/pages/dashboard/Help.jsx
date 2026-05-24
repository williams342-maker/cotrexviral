import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { useToast } from '../../hooks/use-toast';
import {
  MessageCircle, Send, Loader2, BookOpen, Inbox, Plus, Bot, User as UserIcon,
  Sparkles, ChevronRight, CheckCircle2, Clock, ArrowLeft,
} from 'lucide-react';

const Help = () => {
  const [tab, setTab] = useState('chat');

  return (
    <DashboardLayout title="Help & Support" subtitle="Chat with our AI assistant, browse the help center, or open a ticket with our team.">
      <div className="flex flex-wrap gap-2 mb-6">
        <TabBtn id="chat" cur={tab} setCur={setTab} icon={MessageCircle}>AI Assistant</TabBtn>
        <TabBtn id="faq" cur={tab} setCur={setTab} icon={BookOpen}>Help Articles</TabBtn>
        <TabBtn id="tickets" cur={tab} setCur={setTab} icon={Inbox}>My Tickets</TabBtn>
      </div>

      {tab === 'chat' && <ChatTab onEscalate={() => setTab('tickets')} />}
      {tab === 'faq' && <FaqTab />}
      {tab === 'tickets' && <TicketsTab />}
    </DashboardLayout>
  );
};

const TabBtn = ({ id, cur, setCur, icon: Icon, children }) => (
  <button
    onClick={() => setCur(id)}
    className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-[13.5px] font-medium border transition-all ${
      cur === id
        ? 'bg-[#1B7BFF] text-white border-[#1B7BFF]'
        : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
    }`}
  >
    <Icon size={14} />{children}
  </button>
);

// ---------- AI Chat ----------
const ChatTab = ({ onEscalate }) => {
  const { toast } = useToast();
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    { role: 'assistant', text: `Hi ${user?.name?.split(' ')[0] || 'there'} 👋 I'm CortexBot, your support assistant. Ask me anything about CortexViral — features, navigation, or troubleshooting.` },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const scrollerRef = useRef(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const send = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text) return;
    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    setLoading(true);
    try {
      const r = await axios.post(
        `${API}/support/chat`,
        { message: text, session_id: sessionId },
        { withCredentials: true }
      );
      setSessionId(r.data.session_id);
      setMessages((m) => [...m, { role: 'assistant', text: r.data.reply }]);
    } catch (err) {
      toast({ title: 'Chat failed', description: 'Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  const quickAsks = [
    'How do I generate a newsletter?',
    'What is Site Scan?',
    'How do I connect social channels?',
    'How does SEO Review work?',
  ];

  return (
    <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden flex flex-col h-[600px]">
      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center ${
              m.role === 'user' ? 'bg-[#1B7BFF] text-white' : 'bg-gradient-to-br from-emerald-200 to-emerald-50 text-emerald-700'
            }`}>
              {m.role === 'user' ? <UserIcon size={15} /> : <Bot size={15} />}
            </div>
            <div className={`max-w-[78%] rounded-2xl px-4 py-3 text-[14px] leading-relaxed ${
              m.role === 'user'
                ? 'bg-[#1B7BFF] text-white rounded-tr-sm'
                : 'bg-neutral-100 text-neutral-800 rounded-tl-sm'
            }`}>
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="shrink-0 w-9 h-9 rounded-full bg-gradient-to-br from-emerald-200 to-emerald-50 text-emerald-700 flex items-center justify-center"><Bot size={15} /></div>
            <div className="bg-neutral-100 rounded-2xl rounded-tl-sm px-4 py-3 inline-flex items-center gap-1.5 text-neutral-500 text-[13px]">
              <Sparkles size={13} className="animate-pulse" /> thinking…
            </div>
          </div>
        )}
      </div>

      {messages.length <= 1 && (
        <div className="px-6 pb-3 flex flex-wrap gap-2">
          {quickAsks.map((q) => (
            <button key={q} onClick={() => { setInput(q); }} className="text-[12.5px] bg-neutral-50 hover:bg-neutral-100 text-neutral-700 border border-neutral-200 px-3 py-1.5 rounded-full transition-colors">
              {q}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={send} className="p-4 border-t border-neutral-200/70 bg-neutral-50/40 flex items-center gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask CortexBot anything…" className="h-11 rounded-xl border-neutral-300 bg-white" />
        <button type="submit" disabled={loading || !input.trim()} className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-xl bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-50 text-white">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
        <button type="button" onClick={onEscalate} className="shrink-0 text-[12px] font-medium text-neutral-600 hover:text-[#1B7BFF] px-3 py-2">
          Talk to a human →
        </button>
      </form>
    </div>
  );
};

// ---------- FAQ ----------
const FaqTab = () => {
  const [articles, setArticles] = useState([]);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    axios.get(`${API}/support/faq`).then((r) => setArticles(r.data)).catch(() => {});
  }, []);

  const categories = [...new Set(articles.map((a) => a.category))];

  return (
    <div className="space-y-6">
      {categories.map((cat) => (
        <div key={cat}>
          <h3 className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">{cat}</h3>
          <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
            {articles.filter((a) => a.category === cat).map((a, i, arr) => (
              <div key={a.id} className={`${i < arr.length - 1 ? 'border-b border-neutral-100' : ''}`}>
                <button onClick={() => setOpen(open === a.id ? null : a.id)} className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-neutral-50/60 transition-colors">
                  <span className="text-[14.5px] font-medium">{a.title}</span>
                  <ChevronRight size={15} className={`text-neutral-400 transition-transform ${open === a.id ? 'rotate-90' : ''}`} />
                </button>
                {open === a.id && (
                  <div className="px-5 pb-5 text-[14px] text-neutral-700 leading-relaxed">{a.body}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// ---------- Tickets ----------
const TicketsTab = () => {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/support/tickets`, { withCredentials: true });
      setTickets(r.data);
    } catch (e) {}
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  if (activeId) return <TicketDetail id={activeId} onBack={() => { setActiveId(null); load(); }} />;

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <p className="text-[14px] text-neutral-600">View your open conversations with our team.</p>
        <button onClick={() => setCreating(true)} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[13px] font-medium px-4 h-10 rounded-xl">
          <Plus size={15} /> New ticket
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : tickets.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Inbox className="text-neutral-300 mx-auto mb-2" size={28} />
          <p className="text-neutral-700 font-medium">No tickets yet</p>
          <p className="text-[13px] text-neutral-500 mt-1">If the AI can't help, open a ticket and a human will reply.</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          {tickets.map((t, i, arr) => (
            <button key={t.id} onClick={() => setActiveId(t.id)} className={`w-full px-5 py-4 flex items-center gap-4 hover:bg-neutral-50/60 transition-colors ${i < arr.length - 1 ? 'border-b border-neutral-100' : ''} text-left`}>
              <StatusPill status={t.status} />
              <div className="flex-1 min-w-0">
                <div className="text-[14.5px] font-medium truncate">{t.subject}</div>
                <div className="text-[12px] text-neutral-500 mt-0.5">Updated {new Date(t.updated_at).toLocaleString()}</div>
              </div>
              <ChevronRight size={15} className="text-neutral-400" />
            </button>
          ))}
        </div>
      )}

      {creating && <NewTicketModal onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setActiveId(id); }} />}
    </div>
  );
};

const StatusPill = ({ status }) => {
  const map = {
    open: { bg: 'bg-amber-50 text-amber-700 border-amber-100', icon: Clock, label: 'Open' },
    answered: { bg: 'bg-sky-50 text-sky-700 border-sky-100', icon: MessageCircle, label: 'Answered' },
    closed: { bg: 'bg-emerald-50 text-emerald-700 border-emerald-100', icon: CheckCircle2, label: 'Closed' },
  };
  const m = map[status] || map.open;
  const I = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full border ${m.bg}`}>
      <I size={11} /> {m.label}
    </span>
  );
};

const NewTicketModal = ({ onClose, onCreated }) => {
  const { toast } = useToast();
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await axios.post(`${API}/support/tickets`, { subject, message }, { withCredentials: true });
      toast({ title: 'Ticket created', description: 'A team member will reply soon.' });
      onCreated(r.data.id);
    } catch (e) {
      toast({ title: 'Failed to create ticket' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-xl font-semibold tracking-tight mb-1">Open a support ticket</h3>
        <p className="text-[13px] text-neutral-500 mb-4">Our team will reply within 1 business day.</p>
        <form onSubmit={submit} className="space-y-3">
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" required className="h-11 rounded-xl border-neutral-300" />
          <Textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Describe your issue or question…" rows={5} required className="rounded-xl border-neutral-300" />
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100">Cancel</button>
            <button type="submit" disabled={busy} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white text-[13px] font-medium px-5 h-10 rounded-xl">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Submit
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const TicketDetail = ({ id, onBack }) => {
  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();
  const { user } = useAuth();

  const load = async () => {
    try {
      const r = await axios.get(`${API}/support/tickets/${id}`, { withCredentials: true });
      setTicket(r.data.ticket);
      setMessages(r.data.messages);
    } catch (e) {}
  };
  useEffect(() => { load(); }, [id]);

  const send = async (e) => {
    e.preventDefault();
    if (!reply.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/support/tickets/${id}/message`, { message: reply }, { withCredentials: true });
      setReply('');
      await load();
    } catch (e) {
      toast({ title: 'Could not send' });
    } finally {
      setBusy(false);
    }
  };

  const close = async () => {
    try {
      await axios.post(`${API}/support/tickets/${id}/close`, {}, { withCredentials: true });
      toast({ title: 'Ticket closed' });
      await load();
    } catch (e) {}
  };

  if (!ticket) return <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>;

  return (
    <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
      <div className="p-5 border-b border-neutral-200/70 flex items-center gap-3">
        <button onClick={onBack} className="text-neutral-500 hover:text-neutral-800"><ArrowLeft size={17} /></button>
        <div className="flex-1 min-w-0">
          <div className="text-[15px] font-semibold truncate">{ticket.subject}</div>
          <div className="text-[12px] text-neutral-500 mt-0.5">Opened {new Date(ticket.created_at).toLocaleDateString()}</div>
        </div>
        <StatusPill status={ticket.status} />
        {ticket.status !== 'closed' && (
          <button onClick={close} className="text-[12px] font-medium text-neutral-600 hover:text-rose-600 px-3 py-1.5 rounded-lg hover:bg-rose-50 transition-colors">Close ticket</button>
        )}
      </div>
      <div className="p-6 space-y-4 max-h-[440px] overflow-y-auto">
        {messages.map((m) => (
          <div key={m.id} className={`flex gap-3 ${m.author_role === 'user' && m.author_id === user?.user_id ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-[12px] font-semibold ${
              m.author_role === 'admin' ? 'bg-emerald-100 text-emerald-700' : 'bg-[#1B7BFF] text-white'
            }`}>
              {m.author_name?.[0] || 'U'}
            </div>
            <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed ${
              m.author_role === 'admin' ? 'bg-emerald-50 text-emerald-900' : 'bg-neutral-100 text-neutral-800'
            }`}>
              <div className="text-[11px] font-medium opacity-70 mb-0.5">{m.author_name} {m.author_role === 'admin' && '• team'}</div>
              <p className="whitespace-pre-wrap">{m.message}</p>
            </div>
          </div>
        ))}
      </div>
      {ticket.status !== 'closed' && (
        <form onSubmit={send} className="p-4 border-t border-neutral-200/70 bg-neutral-50/40 flex items-center gap-2">
          <Input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Type your reply…" className="h-11 rounded-xl border-neutral-300 bg-white" />
          <button type="submit" disabled={busy || !reply.trim()} className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-xl bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-50 text-white">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </form>
      )}
    </div>
  );
};

export default Help;
