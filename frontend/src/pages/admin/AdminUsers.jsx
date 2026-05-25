import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { useToast } from '../../hooks/use-toast';
import {
  Search, Loader2, Shield, ShieldOff, Pause, Play, Trash2,
  UserCog, AlertTriangle, Gift, UserPlus, Mail, Copy,
} from 'lucide-react';

const PLAN_OPTIONS = [
  { value: 'free', label: 'Free' },
  { value: 'starter', label: 'Starter' },
  { value: 'growth', label: 'Growth' },
  { value: 'agency', label: 'Agency' },
];

const PLAN_COLORS = {
  free: 'bg-neutral-50 text-neutral-700 border-neutral-200',
  starter: 'bg-sky-50 text-sky-700 border-sky-200',
  growth: 'bg-violet-50 text-violet-700 border-violet-200',
  agency: 'bg-amber-50 text-amber-700 border-amber-200',
  pro: 'bg-violet-50 text-violet-700 border-violet-200',
  scale: 'bg-amber-50 text-amber-700 border-amber-200',
};

const AdminUsers = () => {
  const { toast } = useToast();
  const { user: currentUser } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [resendingFor, setResendingFor] = useState(null);

  const load = async (query = '') => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/users${query ? `?q=${encodeURIComponent(query)}` : ''}`, { withCredentials: true });
      setUsers(r.data);
    } catch (e) {
      toast({ title: 'Could not load users' });
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const action = async (userId, kind) => {
    try {
      if (kind === 'delete') {
        await axios.delete(`${API}/admin/users/${userId}`, { withCredentials: true });
      } else {
        await axios.post(`${API}/admin/users/${userId}/${kind}`, {}, { withCredentials: true });
      }
      toast({ title: `User ${kind === 'delete' ? 'deleted' : kind + 'd'}` });
      await load(q);
    } catch (e) {
      toast({ title: 'Action failed', description: e.response?.data?.detail });
    }
  };

  const impersonate = async (userId, name, email) => {
    try {
      await axios.post(`${API}/admin/users/${userId}/impersonate`, {}, { withCredentials: true });
      sessionStorage.setItem('impersonating', JSON.stringify({ user_id: userId, name, email }));
      toast({ title: `Now viewing as ${name}`, description: 'Use the banner at the top to stop impersonating.' });
      window.location.href = '/dashboard';
    } catch (e) {
      toast({ title: 'Impersonation failed' });
    }
  };

  const setPlan = async (userId, plan, comped, currentPlan) => {
    if (plan === currentPlan) return;
    try {
      await axios.post(
        `${API}/admin/users/${userId}/plan`,
        { plan, comped, reason: 'Admin manual override' },
        { withCredentials: true },
      );
      toast({ title: `Plan updated to ${plan}`, description: comped ? 'Comped — immune to Stripe downgrades' : undefined });
      await load(q);
    } catch (e) {
      toast({ title: 'Plan update failed', description: e.response?.data?.detail });
    }
  };

  const toggleComped = async (u) => {
    try {
      await axios.post(
        `${API}/admin/users/${u.user_id}/plan`,
        { plan: u.plan || 'free', comped: !u.comped, reason: 'Admin toggled comp flag' },
        { withCredentials: true },
      );
      toast({ title: !u.comped ? 'Marked as comped' : 'Comped flag removed' });
      await load(q);
    } catch (e) {
      toast({ title: 'Toggle failed', description: e.response?.data?.detail });
    }
  };

  const resendInvite = async (u) => {
    setResendingFor(u.user_id);
    try {
      const r = await axios.post(
        `${API}/admin/users/${u.user_id}/resend-invite`, {},
        { withCredentials: true },
      );
      if (r.data?.email_sent) {
        toast({
          title: `Magic link emailed to ${u.email}`,
          description: 'They have 7 days to claim their account.',
        });
      } else {
        toast({
          title: 'Generated link — email failed to send',
          description: 'Copy the link from the browser network tab or try again.',
        });
      }
    } catch (e) {
      toast({ title: 'Could not generate link', description: e.response?.data?.detail });
    }
    setResendingFor(null);
  };

  return (
    <DashboardLayout title="Users" subtitle="Manage all accounts on Automatex.">
      <form
        onSubmit={(e) => { e.preventDefault(); load(q); }}
        className="flex gap-2 mb-5"
      >
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email…" className="h-11 rounded-xl border-neutral-300 pl-9" />
        </div>
        <button className="bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[13px] font-medium px-5 h-11 rounded-xl">Search</button>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          data-testid="admin-create-user-btn"
          className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[13px] font-medium px-4 h-11 rounded-xl"
        >
          <UserPlus size={14} /> Create user
        </button>
      </form>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden">
          <table className="w-full text-[14px]">
            <thead className="bg-neutral-50/60 border-b border-neutral-200/70">
              <tr className="text-left text-[12px] uppercase tracking-wider text-neutral-500">
                <th className="p-4">User</th>
                <th className="p-4">Status</th>
                <th className="p-4">Plan</th>
                <th className="p-4 text-center">Posts</th>
                <th className="p-4 text-center">Leads</th>
                <th className="p-4 text-center">Reports</th>
                <th className="p-4">Joined</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr><td colSpan={8} className="p-8 text-center text-neutral-500">No users found.</td></tr>
              )}
              {users.map((u) => {
                const isSelf = u.user_id === currentUser?.user_id;
                return (
                  <tr key={u.user_id} className="border-b border-neutral-100 last:border-0 hover:bg-neutral-50/40">
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        {u.picture ? (
                          <img src={u.picture} alt={u.name} className="w-9 h-9 rounded-full ring-2 ring-white shadow-sm" />
                        ) : (
                          <div className="w-9 h-9 rounded-full bg-[#1B7BFF] text-white flex items-center justify-center text-[12px] font-semibold">{u.name?.[0] || 'U'}</div>
                        )}
                        <div className="min-w-0">
                          <div className="text-[14px] font-medium truncate flex items-center gap-1.5">
                            {u.name} {isSelf && <span className="text-[10px] uppercase tracking-wider text-neutral-400 font-semibold">(you)</span>}
                          </div>
                          <div className="text-[12px] text-neutral-500 truncate">{u.email}</div>
                          {(u.brand_name || u.website || u.niche) && (
                            <div className="text-[11px] text-neutral-500 mt-0.5 flex items-center gap-1.5 flex-wrap" data-testid={`admin-user-profile-${u.user_id}`}>
                              {u.brand_name && <span className="font-medium text-neutral-700">{u.brand_name}</span>}
                              {u.website && (
                                <a href={u.website} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-violet-700 hover:underline truncate max-w-[160px]">
                                  {u.website.replace(/^https?:\/\//, '')}
                                </a>
                              )}
                              {u.niche && <span className="px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600">{u.niche}</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={u.status || 'active'} />
                        {u.is_admin && <span className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider font-semibold text-violet-700 bg-violet-50 border border-violet-100 px-2 py-0.5 rounded-full w-fit"><Shield size={9} /> Admin</span>}
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="flex flex-col gap-1.5">
                        <select
                          value={u.plan || 'free'}
                          onChange={(e) => setPlan(u.user_id, e.target.value, u.comped ?? true, u.plan || 'free')}
                          data-testid={`admin-plan-select-${u.user_id}`}
                          className={`text-[11.5px] font-semibold px-2.5 py-1 rounded-lg border outline-none cursor-pointer capitalize ${PLAN_COLORS[u.plan] || PLAN_COLORS.free}`}
                        >
                          {PLAN_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                          {(u.plan === 'pro' || u.plan === 'scale') && (
                            <option value={u.plan}>{u.plan === 'pro' ? 'Pro (legacy)' : 'Scale (legacy)'}</option>
                          )}
                        </select>
                        <button
                          type="button"
                          onClick={() => toggleComped(u)}
                          data-testid={`admin-comped-toggle-${u.user_id}`}
                          className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full w-fit border transition-colors ${
                            u.comped
                              ? 'text-emerald-700 bg-emerald-50 border-emerald-200 hover:bg-emerald-100'
                              : 'text-neutral-500 bg-neutral-50 border-neutral-200 hover:bg-neutral-100'
                          }`}
                          title={u.comped ? 'Click to remove comp (Stripe will re-sync this user)' : 'Click to mark as comped (immune to Stripe downgrades)'}
                        >
                          <Gift size={9} /> {u.comped ? 'Comped' : 'Not comped'}
                        </button>
                      </div>
                    </td>
                    <td className="p-4 text-center text-neutral-700">{u.stats?.posts || 0}</td>
                    <td className="p-4 text-center text-neutral-700">{u.stats?.leads || 0}</td>
                    <td className="p-4 text-center text-neutral-700">{u.stats?.reports || 0}</td>
                    <td className="p-4 text-[12.5px] text-neutral-500">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td className="p-4">
                      <div className="flex items-center justify-end gap-1">
                        <IconBtn title="Impersonate" disabled={isSelf} onClick={() => impersonate(u.user_id, u.name, u.email)}><UserCog size={14} /></IconBtn>
                        <IconBtn
                          title="Resend sign-in link"
                          onClick={() => resendInvite(u)}
                          variant="violet"
                          disabled={resendingFor === u.user_id}
                          data-testid={`admin-resend-invite-${u.user_id}`}
                        >
                          {resendingFor === u.user_id ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
                        </IconBtn>
                        {u.status === 'suspended' ? (
                          <IconBtn title="Unsuspend" onClick={() => action(u.user_id, 'unsuspend')} variant="green"><Play size={14} /></IconBtn>
                        ) : (
                          <IconBtn title="Suspend" disabled={isSelf} onClick={() => action(u.user_id, 'suspend')} variant="amber"><Pause size={14} /></IconBtn>
                        )}
                        {u.is_admin ? (
                          <IconBtn title="Demote admin" disabled={isSelf} onClick={() => action(u.user_id, 'demote')}><ShieldOff size={14} /></IconBtn>
                        ) : (
                          <IconBtn title="Promote to admin" onClick={() => action(u.user_id, 'promote')} variant="violet"><Shield size={14} /></IconBtn>
                        )}
                        <IconBtn title="Delete" disabled={isSelf} onClick={() => setConfirmDelete(u)} variant="red"><Trash2 size={14} /></IconBtn>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setConfirmDelete(null)}>
          <div className="bg-white rounded-3xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-rose-600 mb-3"><AlertTriangle size={20} /><h3 className="text-lg font-semibold">Delete user permanently?</h3></div>
            <p className="text-[14px] text-neutral-700 leading-relaxed mb-5">
              This will permanently delete <strong>{confirmDelete.email}</strong> and ALL their data (leads, posts, reports, channels, tickets). This cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDelete(null)} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100">Cancel</button>
              <button onClick={async () => { await action(confirmDelete.user_id, 'delete'); setConfirmDelete(null); }} className="inline-flex items-center gap-2 bg-rose-600 hover:bg-rose-700 text-white text-[13px] font-medium px-5 h-10 rounded-xl">
                <Trash2 size={14} /> Delete forever
              </button>
            </div>
          </div>
        </div>
      )}

      {createOpen && (
        <CreateUserModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); load(q); }}
        />
      )}
    </DashboardLayout>
  );
};

const CreateUserModal = ({ onClose, onCreated }) => {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('free');
  const [comped, setComped] = useState(false);
  const [sendEmail, setSendEmail] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { magic_link, email_sent, new_user }

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email.trim() || !name.trim()) {
      toast({ title: 'Email and name are required' });
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/admin/users/create`,
        {
          email: email.trim(),
          name: name.trim(),
          plan,
          comped,
          send_email: sendEmail,
        },
        { withCredentials: true },
      );
      setResult(r.data);
      if (r.data?.email_sent) {
        toast({
          title: r.data.new_user ? 'Account created' : 'User already existed — fresh link sent',
          description: `Magic link emailed to ${r.data.email}`,
        });
      } else if (sendEmail) {
        toast({
          title: 'Account created — email failed',
          description: 'Copy the magic link below and send it manually.',
        });
      } else {
        toast({ title: r.data.new_user ? 'Account created' : 'Magic link refreshed' });
      }
    } catch (err) {
      toast({
        title: 'Could not create user',
        description: err.response?.data?.detail || err.message,
      });
    }
    setSubmitting(false);
  };

  const copy = () => {
    if (!result?.magic_link) return;
    navigator.clipboard?.writeText(result.magic_link);
    toast({ title: 'Link copied to clipboard' });
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={() => { if (!submitting) onClose(); }}
      data-testid="admin-create-user-modal"
    >
      <div
        className="bg-white rounded-3xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-emerald-600 mb-1">
          <UserPlus size={20} />
          <h3 className="text-lg font-semibold text-neutral-900">Create user manually</h3>
        </div>
        <p className="text-[13px] text-neutral-500 mb-5 leading-relaxed">
          For inbound leads who don't use Google Auth. We'll email them a single-use sign-in link — no password required.
        </p>

        {!result ? (
          <form onSubmit={submit} className="space-y-4">
            <Field label="Email *">
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="creator@example.com"
                data-testid="admin-create-user-email"
                className="h-10 rounded-xl border-neutral-300"
              />
            </Field>
            <Field label="Name *">
              <Input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Alex Rivera"
                data-testid="admin-create-user-name"
                className="h-10 rounded-xl border-neutral-300"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Plan">
                <select
                  value={plan}
                  onChange={(e) => setPlan(e.target.value)}
                  data-testid="admin-create-user-plan"
                  className="w-full h-10 rounded-xl border border-neutral-300 px-3 text-[14px] bg-white capitalize"
                >
                  {PLAN_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Comped">
                <button
                  type="button"
                  onClick={() => setComped((c) => !c)}
                  data-testid="admin-create-user-comped"
                  className={`w-full h-10 rounded-xl border text-[13px] font-medium inline-flex items-center justify-center gap-1.5 transition-colors ${
                    comped
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                      : 'bg-white border-neutral-300 text-neutral-600 hover:bg-neutral-50'
                  }`}
                >
                  <Gift size={14} /> {comped ? 'Yes — comped' : 'No'}
                </button>
              </Field>
            </div>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sendEmail}
                onChange={(e) => setSendEmail(e.target.checked)}
                data-testid="admin-create-user-send-email"
                className="w-4 h-4 rounded border-neutral-300 text-violet-600 focus:ring-violet-500"
              />
              <span className="text-[13px] text-neutral-700">
                Email them the magic sign-in link now
              </span>
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                data-testid="admin-create-user-submit"
                className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white text-[13px] font-medium px-5 h-10 rounded-xl disabled:opacity-50"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                {submitting ? 'Creating…' : 'Create + email link'}
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-4" data-testid="admin-create-user-result">
            <div className={`rounded-2xl border p-4 ${result.email_sent ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
              <div className={`flex items-center gap-2 text-[13.5px] font-semibold ${result.email_sent ? 'text-emerald-800' : 'text-amber-800'}`}>
                {result.email_sent ? '✓ Magic link emailed' : '⚠ Email failed — copy the link below'}
              </div>
              <p className="text-[12.5px] text-neutral-600 mt-1">
                {result.new_user ? 'New user created.' : 'User already existed — issued a fresh link.'} Link expires in 7 days, single-use.
              </p>
            </div>
            <Field label="Sign-in link (single-use, 7-day expiry)">
              <div className="flex gap-2">
                <Input
                  readOnly
                  value={result.magic_link}
                  data-testid="admin-create-user-link"
                  className="h-10 rounded-xl border-neutral-300 text-[12px] font-mono"
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  onClick={copy}
                  data-testid="admin-create-user-copy"
                  className="inline-flex items-center gap-1.5 bg-neutral-900 hover:bg-neutral-800 text-white text-[13px] font-medium px-4 h-10 rounded-xl"
                >
                  <Copy size={13} /> Copy
                </button>
              </div>
            </Field>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={onCreated}
                data-testid="admin-create-user-done"
                className="text-[13px] font-medium bg-[#1B7BFF] hover:bg-[#1668e0] text-white px-5 h-10 rounded-xl"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const Field = ({ label, children }) => (
  <label className="block">
    <span className="text-[12px] uppercase tracking-wider text-neutral-500 font-medium mb-1.5 block">{label}</span>
    {children}
  </label>
);

const StatusBadge = ({ status }) => {
  const map = {
    active: 'bg-emerald-50 text-emerald-700 border-emerald-100',
    suspended: 'bg-rose-50 text-rose-700 border-rose-100',
  };
  return (
    <span className={`inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full border ${map[status] || map.active} w-fit capitalize`}>
      {status}
    </span>
  );
};

const IconBtn = ({ children, onClick, disabled, title, variant = 'gray', 'data-testid': testId }) => {
  const colors = {
    gray: 'text-neutral-600 hover:bg-neutral-100',
    red: 'text-rose-600 hover:bg-rose-50',
    amber: 'text-amber-600 hover:bg-amber-50',
    green: 'text-emerald-600 hover:bg-emerald-50',
    violet: 'text-violet-600 hover:bg-violet-50',
  };
  return (
    <button title={title} onClick={onClick} disabled={disabled} data-testid={testId} className={`w-8 h-8 rounded-lg disabled:opacity-30 disabled:hover:bg-transparent flex items-center justify-center transition-colors ${colors[variant]}`}>
      {children}
    </button>
  );
};

export default AdminUsers;
