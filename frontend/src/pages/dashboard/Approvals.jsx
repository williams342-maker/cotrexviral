import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  CheckCircle2, XCircle, Loader2, Inbox, ShieldCheck, Clock,
  Calendar as CalendarIcon, ToggleLeft, ToggleRight, AlertCircle,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/approvals — review pending scheduled posts before they go live.
   Two surfaces:
     1. Settings toggle: require_post_approval (master kill-switch for the workflow)
     2. Inbox of pending posts with Approve / Reject actions */

const Approvals = () => {
  const { toast } = useToast();
  const [pending, setPending] = useState([]);
  const [requireApproval, setRequireApproval] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});  // {[post_id]: 'approve' | 'reject'}

  const load = async () => {
    const [s, p] = await Promise.all([
      axios.get(`${API}/approvals/settings`, { withCredentials: true }).catch(() => null),
      axios.get(`${API}/approvals`, { withCredentials: true }).catch(() => null),
    ]);
    if (s?.data) setRequireApproval(!!s.data.require_post_approval);
    if (p?.data) setPending(p.data.pending || []);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const toggleRequire = async () => {
    const next = !requireApproval;
    setRequireApproval(next);
    try {
      await axios.put(`${API}/approvals/settings`, { require_post_approval: next }, { withCredentials: true });
      toast({
        title: next ? 'Approval workflow ON' : 'Approval workflow OFF',
        description: next
          ? 'New scheduled posts will wait here until you approve them.'
          : 'Scheduled posts will publish automatically going forward.',
      });
    } catch (e) {
      setRequireApproval(!next);
      toast({ title: 'Could not save setting', description: e.response?.data?.detail || e.message });
    }
  };

  const approve = async (id) => {
    setBusy((b) => ({ ...b, [id]: 'approve' }));
    try {
      await axios.post(`${API}/approvals/${id}/approve`, {}, { withCredentials: true });
      setPending((ps) => ps.filter((p) => p.id !== id));
      toast({ title: 'Approved — scheduled for dispatch' });
    } catch (e) {
      toast({ title: 'Approval failed', description: e.response?.data?.detail || e.message });
    }
    setBusy((b) => ({ ...b, [id]: null }));
  };

  const reject = async (id) => {
    const reason = window.prompt('Reason for rejecting? (optional)') || '';
    setBusy((b) => ({ ...b, [id]: 'reject' }));
    try {
      await axios.post(`${API}/approvals/${id}/reject`, { reason }, { withCredentials: true });
      setPending((ps) => ps.filter((p) => p.id !== id));
      toast({ title: 'Rejected' });
    } catch (e) {
      toast({ title: 'Could not reject', description: e.response?.data?.detail || e.message });
    }
    setBusy((b) => ({ ...b, [id]: null }));
  };

  return (
    <DashboardLayout
      title="Approval inbox"
      subtitle="Review scheduled posts before they go live. Human-in-the-loop trust layer."
    >
      <div className="cv-dash-scope" data-testid="approvals-page">

        {/* Settings card */}
        <div className="cv-glass rounded-2xl p-5 mb-6 flex items-center gap-4" data-testid="approvals-settings-card">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 border ${requireApproval ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-zinc-500/10 border-zinc-500/30 text-zinc-400'}`}>
            <ShieldCheck size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[14.5px] font-semibold text-white">Require my approval before posts go live</div>
            <p className="text-[12.5px] text-zinc-400 mt-0.5 leading-relaxed">
              When on, every scheduled post waits here until you approve it. Immediate publishes (clicking "Publish now") still go straight through.
            </p>
          </div>
          <button
            onClick={toggleRequire}
            data-testid="approvals-toggle"
            className={`inline-flex items-center gap-2 px-3.5 h-10 rounded-lg font-medium text-[13px] border ${
              requireApproval
                ? 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border-emerald-500/30'
                : 'bg-white/[0.04] hover:bg-white/10 text-zinc-300 border-white/10'
            }`}
          >
            {requireApproval ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
            {requireApproval ? 'On' : 'Off'}
          </button>
        </div>

        {/* Pending list */}
        {loading ? (
          <div className="text-center py-12 text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
        ) : pending.length === 0 ? (
          <div className="cv-glass rounded-2xl p-10 text-center" data-testid="approvals-empty">
            <Inbox size={28} className="text-zinc-500 mx-auto mb-3" />
            <p className="text-white font-semibold">Inbox zero</p>
            <p className="text-[13px] text-zinc-400 mt-1.5 max-w-md mx-auto leading-relaxed">
              {requireApproval
                ? "No scheduled posts are waiting for your approval right now. As soon as one is created, it'll show up here."
                : "Approval workflow is off — scheduled posts publish automatically. Toggle it on above to gate them through this inbox."}
            </p>
          </div>
        ) : (
          <div className="space-y-3" data-testid="approvals-list">
            <div className="text-[11.5px] text-zinc-500 font-medium uppercase tracking-[0.18em] mb-2 flex items-center gap-1.5">
              <Clock size={11} /> {pending.length} pending
            </div>
            {pending.map((p) => (
              <div key={p.id} className="cv-glass rounded-2xl p-5" data-testid={`approvals-card-${p.id}`}>
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      {(p.platforms || []).map((pl) => (
                        <span key={pl} className="text-[10.5px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30">
                          {pl}
                        </span>
                      ))}
                      <span className="text-[11.5px] text-zinc-400 inline-flex items-center gap-1.5">
                        <CalendarIcon size={11} />
                        {p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : 'unscheduled'}
                      </span>
                    </div>
                    <p className="text-[13.5px] text-zinc-100 leading-relaxed whitespace-pre-wrap">
                      {p.content}
                    </p>
                    {p.media_url && (
                      <div className="mt-2.5 inline-flex items-center gap-1.5 text-[11.5px] text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 rounded-lg px-2 py-1">
                        <AlertCircle size={11} /> Has media URL
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex items-center justify-end gap-2 pt-3 border-t border-white/5">
                  <button
                    onClick={() => reject(p.id)}
                    disabled={!!busy[p.id]}
                    data-testid={`approvals-reject-${p.id}`}
                    className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-zinc-300 hover:text-rose-300 bg-white/[0.04] hover:bg-rose-500/10 border border-white/10 hover:border-rose-500/30 px-3.5 h-9 rounded-lg disabled:opacity-40"
                  >
                    {busy[p.id] === 'reject' ? <Loader2 size={11} className="animate-spin" /> : <XCircle size={11} />}
                    Reject
                  </button>
                  <button
                    onClick={() => approve(p.id)}
                    disabled={!!busy[p.id]}
                    data-testid={`approvals-approve-${p.id}`}
                    className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-emerald-600 hover:bg-emerald-500 text-white px-4 h-9 rounded-lg disabled:opacity-40"
                  >
                    {busy[p.id] === 'approve' ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                    Approve & schedule
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Approvals;
