import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { useToast } from '../../hooks/use-toast';
import { Loader2, Send, ArrowLeft, Clock, MessageCircle, CheckCircle2, ChevronRight, Inbox } from 'lucide-react';

const AdminTickets = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const [tickets, setTickets] = useState([]);
  const [filter, setFilter] = useState('open');
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/tickets${filter !== 'all' ? `?status=${filter}` : ''}`, { withCredentials: true });
      setTickets(r.data);
    } catch (e) {}
    setLoading(false);
  };
  useEffect(() => { load(); }, [filter]);

  if (activeId) return <AdminTicketDetail id={activeId} onBack={() => { setActiveId(null); load(); }} />;

  return (
    <DashboardLayout title="Support Inbox" subtitle="Reply to escalated tickets from your users.">
      <div className="flex flex-wrap gap-2 mb-5">
        {['open', 'answered', 'closed', 'all'].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={`px-4 py-1.5 rounded-full text-[13px] font-medium border capitalize transition-all ${
            filter === f
              ? 'bg-[#1B7BFF] text-white border-[#1B7BFF]'
              : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
          }`}>{f}</button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : tickets.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Inbox className="text-neutral-300 mx-auto mb-2" size={28} />
          <p className="text-neutral-700 font-medium">No tickets in this view</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          {tickets.map((t, i, arr) => (
            <button key={t.id} onClick={() => setActiveId(t.id)} className={`w-full px-5 py-4 flex items-center gap-4 hover:bg-neutral-50/60 transition-colors ${i < arr.length - 1 ? 'border-b border-neutral-100' : ''} text-left`}>
              <StatusPill status={t.status} />
              <div className="flex-1 min-w-0">
                <div className="text-[14.5px] font-medium truncate">{t.subject}</div>
                <div className="text-[12px] text-neutral-500 mt-0.5">From {t.user_name} ({t.user_email}) • {new Date(t.updated_at).toLocaleString()}</div>
              </div>
              <ChevronRight size={15} className="text-neutral-400" />
            </button>
          ))}
        </div>
      )}
    </DashboardLayout>
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

const AdminTicketDetail = ({ id, onBack }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);

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

  if (!ticket) return <DashboardLayout><div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div></DashboardLayout>;

  return (
    <DashboardLayout>
      <button onClick={onBack} className="text-[13px] text-neutral-500 hover:text-neutral-800 flex items-center gap-1 mb-3"><ArrowLeft size={14} /> Back to inbox</button>
      <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
        <div className="p-5 border-b border-neutral-200/70 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[16px] font-semibold truncate">{ticket.subject}</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">From {ticket.user_name} ({ticket.user_email}) • Opened {new Date(ticket.created_at).toLocaleDateString()}</div>
          </div>
          <StatusPill status={ticket.status} />
          {ticket.status !== 'closed' && (
            <button onClick={close} className="text-[12px] font-medium text-neutral-600 hover:text-rose-600 px-3 py-1.5 rounded-lg hover:bg-rose-50 transition-colors">Close ticket</button>
          )}
        </div>
        <div className="p-6 space-y-4 max-h-[500px] overflow-y-auto">
          {messages.map((m) => (
            <div key={m.id} className={`flex gap-3 ${m.author_role === 'admin' ? 'flex-row-reverse' : ''}`}>
              <div className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-[12px] font-semibold ${
                m.author_role === 'admin' ? 'bg-emerald-100 text-emerald-700' : 'bg-[#1B7BFF] text-white'
              }`}>{m.author_name?.[0] || 'U'}</div>
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
            <Input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply as Automatex team…" className="h-11 rounded-xl border-neutral-300 bg-white" />
            <button type="submit" disabled={busy || !reply.trim()} className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-xl bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-50 text-white">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </form>
        )}
      </div>
    </DashboardLayout>
  );
};

export default AdminTickets;
