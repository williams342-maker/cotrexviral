import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Compass, Inbox, Check, X, Pencil, Trash2, Sparkles, Zap, Power, AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* Briefs — Atlas's proposal inbox. Phase 3 of the Autonomous Growth Team.
   Top: Atlas hero card with manual/autopilot toggle + "Propose now" CTA.
   Body: 4 KPI tiles + card grid for pending briefs.
   Each card shows title, hypothesis, rationale, suggested platforms, and
   3 actions: Approve (creates campaign), Edit body, Reject (writes memory). */

const STATUS_META = {
  pending:  { label: 'Pending',  color: 'bg-sky-100 text-sky-700 border-sky-200' },
  approved: { label: 'Approved', color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  rejected: { label: 'Rejected', color: 'bg-rose-100 text-rose-700 border-rose-200' },
};

const Briefs = () => {
  const { toast } = useToast();
  const [briefs, setBriefs] = useState([]);
  const [stats, setStats] = useState({ pending_count: 0, approved_count: 0, rejected_count: 0, avg_decision_minutes: 0 });
  const [settings, setSettings] = useState({ briefs_mode: 'manual', cadence_label: 'Manual only', last_scan_at: null, max_per_scan: 3 });
  const [loading, setLoading] = useState(true);
  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState(null);  // brief_id of in-flight action
  const [editId, setEditId] = useState(null);
  const [editBody, setEditBody] = useState('');
  const [statusFilter, setStatusFilter] = useState('pending');

  const load = async () => {
    setLoading(true);
    try {
      const [b, s] = await Promise.all([
        axios.get(`${API}/briefs${statusFilter ? `?status=${statusFilter}` : ''}`, { withCredentials: true }),
        axios.get(`${API}/briefs/settings`, { withCredentials: true }),
      ]);
      setBriefs(b.data.items || []);
      setStats({
        pending_count:         b.data.pending_count,
        approved_count:        b.data.approved_count,
        rejected_count:        b.data.rejected_count,
        avg_decision_minutes:  b.data.avg_decision_minutes,
      });
      setSettings(s.data);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [statusFilter]);

  const propose = async () => {
    setProposing(true);
    try {
      const r = await axios.post(`${API}/briefs/propose`, { max_briefs: settings.max_per_scan || 3 }, { withCredentials: true });
      if (r.data.count === 0) {
        toast({ title: 'No new briefs proposed', description: 'Atlas didn\'t find strong enough signals or goals to justify a brief right now.' });
      } else {
        toast({ title: `Atlas proposed ${r.data.count} brief${r.data.count > 1 ? 's' : ''}`, description: 'Review them below.' });
      }
      setStatusFilter('pending');
      await load();
    } catch (e) {
      toast({ title: 'Propose failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setProposing(false); }
  };

  const toggleAutopilot = async () => {
    const next = settings.briefs_mode === 'autopilot' ? 'manual' : 'autopilot';
    try {
      const r = await axios.put(`${API}/briefs/settings`, { briefs_mode: next }, { withCredentials: true });
      setSettings(r.data);
      toast({
        title: next === 'autopilot' ? 'Autopilot ON' : 'Autopilot OFF',
        description: next === 'autopilot'
          ? 'Atlas will scan + propose daily at 09:00 UTC.'
          : 'Atlas will only propose when you click "Propose now".',
      });
    } catch (e) {
      toast({ title: 'Update failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const approve = async (b) => {
    setBusy(b.id);
    try {
      const r = await axios.post(`${API}/briefs/${b.id}/approve`, {}, { withCredentials: true });
      toast({ title: 'Brief approved', description: `Campaign "${r.data.campaign.name}" created in draft.` });
      await load();
    } catch (e) {
      toast({ title: 'Approve failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy(null); }
  };

  const reject = async (b) => {
    if (!window.confirm(`Reject "${b.title}"? Atlas will learn from this and avoid similar proposals.`)) return;
    setBusy(b.id);
    try {
      await axios.post(`${API}/briefs/${b.id}/reject`, {}, { withCredentials: true });
      toast({ title: 'Brief rejected', description: 'Learning saved — Atlas will avoid this pattern next scan.' });
      await load();
    } catch (e) {
      toast({ title: 'Reject failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy(null); }
  };

  const startEdit = (b) => {
    setEditId(b.id);
    setEditBody(b.edited_body || b.body);
  };

  const saveEdit = async () => {
    setBusy(editId);
    try {
      await axios.patch(`${API}/briefs/${editId}/edit`, { body: editBody }, { withCredentials: true });
      toast({ title: 'Edit saved', description: 'Approve to spawn the campaign with your edits.' });
      setEditId(null); setEditBody('');
      await load();
    } catch (e) {
      toast({ title: 'Save failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy(null); }
  };

  const remove = async (b) => {
    if (!window.confirm(`Permanently delete "${b.title}"?`)) return;
    try {
      await axios.delete(`${API}/briefs/${b.id}`, { withCredentials: true });
      toast({ title: 'Brief deleted' });
      await load();
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  const autopilotOn = settings.briefs_mode === 'autopilot';

  return (
    <DashboardLayout title="Briefs Inbox" subtitle="Campaign proposals from Atlas — Approve, Edit, or Reject.">
      <div className="space-y-8" data-testid="briefs-page">

        {/* Atlas hero card */}
        <div className="rounded-2xl border border-sky-200/60 bg-gradient-to-br from-sky-50 via-white to-sky-50 p-6">
          <div className="flex items-start gap-5">
            <span className="w-12 h-12 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center shrink-0">
              <Compass size={22} />
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-sky-600 font-bold mb-1">Atlas · Strategist</div>
              <h2 className="text-lg font-semibold text-neutral-900 mb-1">Pattern-finder. Proposes campaigns tied to your goals + signals.</h2>
              <p className="text-[13px] text-neutral-600 leading-relaxed">
                Atlas reads your open <strong>Goals</strong> and recent <strong>Listening Signals</strong>, then drafts up to {settings.max_per_scan || 3} campaign brief(s) for you to review. Approve a brief to spawn a real campaign; reject one to teach Atlas to avoid the pattern next time.
              </p>
            </div>
            <div className="flex flex-col items-end gap-2 shrink-0">
              <button
                onClick={propose}
                disabled={proposing}
                className="text-[12.5px] font-semibold px-4 py-2 rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 flex items-center gap-1.5"
                data-testid="propose-now-btn"
              >
                {proposing ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                Propose now
              </button>
              <button
                onClick={toggleAutopilot}
                className={`text-[11.5px] font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1.5 border transition-colors ${
                  autopilotOn
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-700 hover:bg-emerald-100'
                    : 'bg-white border-neutral-300 text-neutral-600 hover:bg-neutral-50'
                }`}
                data-testid="autopilot-toggle"
              >
                {autopilotOn ? <Zap size={12} /> : <Power size={12} />}
                Autopilot: {autopilotOn ? 'ON' : 'OFF'}
              </button>
              <span className="text-[10.5px] text-neutral-500 tabular-nums">{settings.cadence_label}</span>
            </div>
          </div>
          {settings.last_scan_at && (
            <div className="mt-3 text-[11px] text-neutral-500 flex items-center gap-1.5">
              <Clock size={11} /> Last scan: {new Date(settings.last_scan_at).toLocaleString()}
            </div>
          )}
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Kpi label="Pending"          value={stats.pending_count}                              tone="sky"     icon={<Inbox size={14} />}         testid="kpi-pending" />
          <Kpi label="Approved"         value={stats.approved_count}                             tone="emerald" icon={<CheckCircle2 size={14} />} testid="kpi-approved" />
          <Kpi label="Rejected"         value={stats.rejected_count}                             tone="rose"    icon={<X size={14} />}             testid="kpi-rejected" />
          <Kpi label="Avg decision min" value={`${stats.avg_decision_minutes.toFixed(1)}m`}      tone="violet"  icon={<Clock size={14} />}         testid="kpi-decision-time" />
        </div>

        {/* Filter pills */}
        <div className="flex items-center gap-2">
          {['pending', 'approved', 'rejected', ''].map((s) => (
            <button
              key={s || 'all'}
              onClick={() => setStatusFilter(s)}
              className={`text-[11.5px] font-semibold px-3 py-1.5 rounded-full border ${
                statusFilter === s
                  ? 'bg-sky-600 text-white border-sky-600'
                  : 'bg-white text-neutral-600 border-neutral-300 hover:bg-neutral-50'
              }`}
              data-testid={`filter-${s || 'all'}`}
            >
              {s ? s[0].toUpperCase() + s.slice(1) : 'All'}
            </button>
          ))}
        </div>

        {loading && <div className="flex items-center gap-2 text-neutral-500"><Loader2 className="animate-spin" size={14} /> Loading briefs…</div>}

        {!loading && briefs.length === 0 && (
          <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-300" data-testid="empty">
            <Inbox size={28} className="mx-auto text-neutral-400 mb-3" />
            <p className="text-neutral-600 font-medium">
              {statusFilter === 'pending' ? 'No briefs waiting for review.' : `No ${statusFilter || 'briefs'} yet.`}
            </p>
            <p className="text-[12.5px] text-neutral-500 mt-1 mb-5">
              {statusFilter === 'pending' ? 'Click "Propose now" or turn on Autopilot for a daily drip.' : '—'}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {briefs.map((b) => {
            const meta = STATUS_META[b.status] || STATUS_META.pending;
            const isEditing = editId === b.id;
            const displayBody = b.edited_body || b.body;
            return (
              <div key={b.id} className="rounded-2xl border border-neutral-200/70 bg-white p-5" data-testid={`brief-card-${b.id}`}>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] uppercase tracking-widest text-neutral-500 font-bold mb-1 flex items-center gap-2">
                      {b.proposer_agent === 'atlas' ? 'Atlas' : b.proposer_agent} · {b.source === 'autopilot' ? '🤖 autopilot' : 'manual'}
                    </div>
                    <h3 className="text-[15px] font-semibold text-neutral-900 leading-snug">{b.title}</h3>
                    {b.hypothesis && (
                      <div className="text-[12px] text-sky-700 italic mt-1 line-clamp-2 bg-sky-50/60 rounded-md px-2 py-1 mt-2">
                        💡 {b.hypothesis}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border font-bold ${meta.color}`}>
                      {meta.label}
                    </span>
                    <button onClick={() => remove(b)} className="text-neutral-400 hover:text-rose-600 p-1" title="Delete">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Body or editor */}
                {isEditing ? (
                  <div className="space-y-2">
                    <textarea
                      value={editBody}
                      onChange={(e) => setEditBody(e.target.value)}
                      rows={5}
                      className="w-full text-[12.5px] px-3 py-2 rounded-lg border border-sky-300 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 outline-none font-mono leading-relaxed"
                      data-testid={`edit-body-${b.id}`}
                    />
                    <div className="flex items-center justify-end gap-2">
                      <button onClick={() => { setEditId(null); setEditBody(''); }} className="text-[11.5px] px-3 py-1.5 rounded-lg text-neutral-600 hover:bg-neutral-100">Cancel</button>
                      <button
                        onClick={saveEdit}
                        disabled={busy === b.id || editBody.trim().length < 10}
                        className="text-[11.5px] font-semibold px-3 py-1.5 rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-40 flex items-center gap-1.5"
                        data-testid={`save-edit-${b.id}`}
                      >
                        {busy === b.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                        Save edit
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-[12.5px] text-neutral-700 leading-relaxed whitespace-pre-wrap mb-3 line-clamp-4">
                    {displayBody}
                    {b.edited_body && (
                      <span className="ml-2 text-[10px] uppercase tracking-widest text-amber-600 font-bold">EDITED</span>
                    )}
                  </div>
                )}

                {/* Rationale + platforms */}
                {(b.rationale || (b.suggested_platforms || []).length > 0) && (
                  <div className="border-t border-neutral-100 pt-3 mb-3 space-y-1.5">
                    {b.rationale && (
                      <div className="text-[11.5px] text-neutral-600 leading-relaxed">
                        <span className="font-bold uppercase tracking-widest text-[9.5px] text-neutral-500 mr-1.5">Why now</span>
                        {b.rationale}
                      </div>
                    )}
                    {(b.suggested_platforms || []).length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap">
                        <span className="font-bold uppercase tracking-widest text-[9.5px] text-neutral-500 mr-1">Platforms</span>
                        {b.suggested_platforms.map((p) => (
                          <span key={p} className="text-[10px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-700">{p}</span>
                        ))}
                      </div>
                    )}
                    {b.target_metric && (
                      <div className="text-[10.5px] text-neutral-500 uppercase tracking-widest font-bold">
                        Target: {b.target_metric}
                      </div>
                    )}
                  </div>
                )}

                {/* Actions or conclusion */}
                {b.status === 'pending' && !isEditing && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => approve(b)}
                      disabled={busy === b.id}
                      className="flex-1 text-[12px] font-semibold px-3 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 flex items-center justify-center gap-1.5"
                      data-testid={`approve-${b.id}`}
                    >
                      {busy === b.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                      Approve
                    </button>
                    <button
                      onClick={() => startEdit(b)}
                      className="text-[12px] font-semibold px-3 py-2 rounded-lg border border-neutral-300 text-neutral-700 hover:bg-neutral-50 flex items-center gap-1.5"
                      data-testid={`edit-${b.id}`}
                    >
                      <Pencil size={12} /> Edit
                    </button>
                    <button
                      onClick={() => reject(b)}
                      disabled={busy === b.id}
                      className="text-[12px] font-semibold px-3 py-2 rounded-lg border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-50 flex items-center gap-1.5"
                      data-testid={`reject-${b.id}`}
                    >
                      <X size={12} /> Reject
                    </button>
                  </div>
                )}

                {b.status === 'approved' && (
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-[12px] text-emerald-800 leading-relaxed flex items-start gap-2" data-testid={`approved-note-${b.id}`}>
                    <CheckCircle2 size={14} className="text-emerald-600 shrink-0 mt-0.5" />
                    <div>Approved · campaign created in draft. Decided by {b.decided_by}.</div>
                  </div>
                )}

                {b.status === 'rejected' && (
                  <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-[12px] text-rose-800 leading-relaxed flex items-start gap-2" data-testid={`rejected-note-${b.id}`}>
                    <AlertTriangle size={14} className="text-rose-600 shrink-0 mt-0.5" />
                    <div>Rejected — Atlas saved this as a learning. Decided by {b.decided_by}.</div>
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

const Kpi = ({ label, value, tone, icon, testid }) => {
  const toneMap = {
    sky:     'text-sky-700 bg-sky-50 border-sky-200',
    emerald: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    rose:    'text-rose-700 bg-rose-50 border-rose-200',
    violet:  'text-violet-700 bg-violet-50 border-violet-200',
  };
  return (
    <div className={`rounded-xl border p-4 ${toneMap[tone]}`} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold mb-1.5 opacity-80">{icon} {label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
};

export default Briefs;
