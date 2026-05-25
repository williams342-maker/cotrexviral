import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Switch } from '../../components/ui/switch';
import { useToast } from '../../hooks/use-toast';
import { Loader2, Plus, Trash2, Megaphone, Info, AlertCircle, AlertTriangle, CheckCircle2, Mail, Send } from 'lucide-react';

const SEVERITY_META = {
  info: { label: 'Info', icon: Info, color: 'bg-sky-50 text-sky-700 border-sky-200' },
  success: { label: 'Success', icon: CheckCircle2, color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  warning: { label: 'Warning', icon: AlertTriangle, color: 'bg-amber-50 text-amber-700 border-amber-200' },
  critical: { label: 'Critical', icon: AlertCircle, color: 'bg-rose-50 text-rose-700 border-rose-200' },
};

const AdminBroadcasts = () => {
  const { toast } = useToast();
  const [broadcasts, setBroadcasts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [emailing, setEmailing] = useState(null); // {broadcast}

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/broadcasts`, { withCredentials: true });
      setBroadcasts(r.data);
    } catch (e) {}
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const toggle = async (b) => {
    try {
      await axios.patch(`${API}/admin/broadcasts/${b.id}`, { active: !b.active }, { withCredentials: true });
      await load();
    } catch (e) { toast({ title: 'Failed to update' }); }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/admin/broadcasts/${id}`, { withCredentials: true });
      toast({ title: 'Broadcast deleted' });
      await load();
    } catch (e) { toast({ title: 'Failed to delete' }); }
  };

  return (
    <DashboardLayout title="Broadcasts" subtitle="Send platform-wide announcements that appear as a banner on every dashboard.">
      <div className="flex items-center justify-between mb-5">
        <p className="text-[14px] text-neutral-600">Active broadcasts show as a banner at the top of every user's dashboard.</p>
        <button onClick={() => setCreating(true)} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[13px] font-medium px-4 h-10 rounded-xl">
          <Plus size={15} /> New broadcast
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : broadcasts.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Megaphone className="text-neutral-300 mx-auto mb-2" size={28} />
          <p className="text-neutral-700 font-medium">No broadcasts yet</p>
          <p className="text-[13px] text-neutral-500 mt-1">Create one to announce updates, scheduled maintenance, or new features.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {broadcasts.map((b) => {
            const meta = SEVERITY_META[b.severity] || SEVERITY_META.info;
            const Icon = meta.icon;
            return (
              <div key={b.id} className="bg-white rounded-2xl p-5 border border-neutral-200/70 flex items-start gap-4">
                <div className={`shrink-0 w-10 h-10 rounded-xl border ${meta.color} flex items-center justify-center`}>
                  <Icon size={17} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-[15px] font-semibold">{b.title}</span>
                    <span className={`text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border ${meta.color}`}>{b.severity}</span>
                    {!b.active && <span className="text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500 border border-neutral-200">Inactive</span>}
                    {b.emailed_at && (
                      <span
                        className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200"
                        title={`Emailed ${b.emailed_sent}/${b.emailed_recipients} on ${new Date(b.emailed_at).toLocaleString()}`}
                      >
                        <Mail size={9} /> Emailed {b.emailed_sent || 0}/{b.emailed_recipients || 0}
                      </span>
                    )}
                  </div>
                  <p className="text-[14px] text-neutral-700 leading-relaxed">{b.body}</p>
                  <p className="text-[12px] text-neutral-500 mt-2">Created by {b.created_by_name} • {new Date(b.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => setEmailing(b)}
                    className="inline-flex items-center gap-1.5 text-[12px] font-semibold px-3 h-8 rounded-full bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100"
                    title="Send as email blast"
                    data-testid={`broadcast-email-btn-${b.id}`}
                  >
                    <Mail size={12} /> Email blast
                  </button>
                  <Switch checked={b.active} onCheckedChange={() => toggle(b)} />
                  <button onClick={() => remove(b.id)} className="w-8 h-8 rounded-lg text-rose-600 hover:bg-rose-50 flex items-center justify-center" title="Delete"><Trash2 size={14} /></button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {creating && <NewBroadcastModal onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
      {emailing && <EmailBlastModal broadcast={emailing} onClose={() => setEmailing(null)} onSent={() => { setEmailing(null); load(); }} />}
    </DashboardLayout>
  );
};

const NewBroadcastModal = ({ onClose, onCreated }) => {
  const { toast } = useToast();
  const [form, setForm] = useState({ title: '', body: '', severity: 'info', active: true });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/admin/broadcasts`, form, { withCredentials: true });
      toast({ title: 'Broadcast created' });
      onCreated();
    } catch (e) { toast({ title: 'Failed to create' }); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-xl font-semibold tracking-tight mb-1">Create broadcast announcement</h3>
        <p className="text-[13px] text-neutral-500 mb-4">Visible as a banner to every logged-in user.</p>
        <form onSubmit={submit} className="space-y-3">
          <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title" required className="h-11 rounded-xl border-neutral-300" />
          <Textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="Message body…" rows={4} required className="rounded-xl border-neutral-300" />
          <div className="grid grid-cols-2 gap-3">
            <Select value={form.severity} onValueChange={(v) => setForm({ ...form, severity: v })}>
              <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="info">Info</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="warning">Warning</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
            <label className="flex items-center gap-2 px-3 h-11 rounded-xl border border-neutral-300 bg-white">
              <Switch checked={form.active} onCheckedChange={(v) => setForm({ ...form, active: v })} />
              <span className="text-[13px] font-medium text-neutral-700">Publish now</span>
            </label>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100">Cancel</button>
            <button type="submit" disabled={busy} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white text-[13px] font-medium px-5 h-10 rounded-xl">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Megaphone size={14} />} Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AdminBroadcasts;

const ALL_PLANS = [
  { id: 'free', label: 'Free' },
  { id: 'starter', label: 'Starter' },
  { id: 'growth', label: 'Growth' },
  { id: 'agency', label: 'Agency' },
];

const EmailBlastModal = ({ broadcast, onClose, onSent }) => {
  const { toast } = useToast();
  const [plans, setPlans] = useState(null);   // null = all plans
  const [includeComped, setIncludeComped] = useState(true);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);

  const togglePlan = (p) => {
    const cur = plans || ALL_PLANS.map((x) => x.id);
    const next = cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p];
    setPlans(next.length === ALL_PLANS.length ? null : next);
  };
  const isSelected = (p) => (plans === null ? true : plans.includes(p));

  const runDry = async () => {
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/admin/broadcasts/${broadcast.id}/email`,
        { plans, include_comped: includeComped, dry_run: true },
        { withCredentials: true },
      );
      setPreview(r.data);
    } catch (e) {
      toast({ title: 'Preview failed', description: e?.response?.data?.detail });
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!window.confirm(`Send "${broadcast.title}" to ${preview?.would_send_to ?? '?'} users? This cannot be undone.`)) return;
    setSending(true);
    try {
      const r = await axios.post(
        `${API}/admin/broadcasts/${broadcast.id}/email`,
        { plans, include_comped: includeComped, dry_run: false },
        { withCredentials: true, timeout: 5 * 60 * 1000 },
      );
      toast({
        title: 'Broadcast sent',
        description: `${r.data.sent || 0} delivered · ${r.data.failed || 0} failed`,
      });
      onSent?.();
    } catch (e) {
      toast({ title: 'Send failed', description: e?.response?.data?.detail || e.message });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="email-blast-modal">
        <div className="flex items-center gap-2 mb-1">
          <Mail size={18} className="text-violet-700" />
          <h3 className="text-xl font-semibold tracking-tight">Email blast</h3>
        </div>
        <p className="text-[13px] text-neutral-500 mb-4">Send <strong>"{broadcast.title}"</strong> as an email to selected users via Mailtrap.</p>

        <div className="space-y-4 mb-4">
          <div>
            <div className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-2">Recipient plans</div>
            <div className="flex flex-wrap gap-1.5">
              {ALL_PLANS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => togglePlan(p.id)}
                  data-testid={`plan-pill-${p.id}`}
                  className={`text-[12px] font-semibold px-3 h-8 rounded-full border transition-colors ${
                    isSelected(p.id)
                      ? 'bg-violet-600 text-white border-violet-600'
                      : 'bg-white text-neutral-600 border-neutral-300 hover:border-neutral-400'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <p className="text-[11.5px] text-neutral-500 mt-1.5">
              {plans === null ? 'All plans selected' : `${plans.length} of ${ALL_PLANS.length} plans selected`}
            </p>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <Switch checked={includeComped} onCheckedChange={setIncludeComped} />
            <span className="text-[13px] text-neutral-700">Include comped users</span>
          </label>
        </div>

        <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-3 mb-4 text-[13px]">
          {preview ? (
            <div>
              <span className="font-semibold text-neutral-900">{preview.would_send_to?.toLocaleString() || 0}</span>
              <span className="text-neutral-600"> users match the filter.</span>
              {preview.would_send_to === 0 && (
                <span className="text-amber-700 block mt-1 text-[12px]">No users match this filter. Adjust above.</span>
              )}
            </div>
          ) : (
            <span className="text-neutral-500 italic">Click "Preview" to see how many users will receive this email.</span>
          )}
        </div>

        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100" data-testid="email-blast-cancel">Cancel</button>
          <button
            type="button" onClick={runDry} disabled={busy || sending}
            className="text-[13px] font-medium px-4 h-10 rounded-xl border border-neutral-300 hover:bg-neutral-50 disabled:opacity-60"
            data-testid="email-blast-preview"
          >
            {busy ? <Loader2 size={13} className="animate-spin inline mr-1.5" /> : null}Preview
          </button>
          <button
            type="button" onClick={send}
            disabled={sending || !preview || preview.would_send_to === 0}
            className="inline-flex items-center gap-1.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-50 text-white text-[13px] font-medium px-5 h-10 rounded-xl"
            data-testid="email-blast-send"
          >
            {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
            {sending ? 'Sending…' : preview ? `Send to ${preview.would_send_to}` : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};
