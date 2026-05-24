import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Switch } from '../../components/ui/switch';
import { useToast } from '../../hooks/use-toast';
import { Loader2, Plus, Trash2, Megaphone, Info, AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';

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
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[15px] font-semibold">{b.title}</span>
                    <span className={`text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border ${meta.color}`}>{b.severity}</span>
                    {!b.active && <span className="text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500 border border-neutral-200">Inactive</span>}
                  </div>
                  <p className="text-[14px] text-neutral-700 leading-relaxed">{b.body}</p>
                  <p className="text-[12px] text-neutral-500 mt-2">Created by {b.created_by_name} • {new Date(b.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Switch checked={b.active} onCheckedChange={() => toggle(b)} />
                  <button onClick={() => remove(b.id)} className="w-8 h-8 rounded-lg text-rose-600 hover:bg-rose-50 flex items-center justify-center" title="Delete"><Trash2 size={14} /></button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {creating && <NewBroadcastModal onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
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
