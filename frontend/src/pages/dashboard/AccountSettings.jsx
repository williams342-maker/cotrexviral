import React, { useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Loader2, Trash2, ShieldAlert, User as UserIcon, Mail, Crown, Sparkles, Gift, ExternalLink } from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { useAuth, API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/settings/account — surfaces the user's own profile/billing
   summary and the destructive "Danger zone" (delete my account). Same
   backend endpoint as /data-deletion. We keep this in the dashboard so it's
   discoverable to logged-in users; the public /data-deletion page stays for
   GDPR / Meta-review compliance. */
const AccountSettings = () => {
  const { user, logout } = useAuth();
  const { toast } = useToast();
  const [showConfirm, setShowConfirm] = useState(false);

  if (!user) {
    return (
      <DashboardLayout title="Account">
        <div className="text-center py-16 text-zinc-400">
          <Loader2 className="animate-spin mx-auto" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Account" subtitle="Your profile, plan, and account-level controls.">
      {/* Profile */}
      <section className="mb-6" data-testid="account-profile-section">
        <SectionHeader icon={UserIcon} label="Profile" />
        <div className="cv-glass rounded-2xl p-5 flex items-center gap-4">
          {user.picture ? (
            <img src={user.picture} alt={user.name} className="w-14 h-14 rounded-full border border-white/10 object-cover" />
          ) : (
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white text-lg font-semibold">
              {(user.name || user.email || '?').slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-white" data-testid="account-name">{user.name || 'Unnamed'}</div>
            <div className="text-[13px] text-zinc-400 flex items-center gap-1.5 mt-0.5">
              <Mail size={12} /> <span data-testid="account-email">{user.email}</span>
            </div>
          </div>
          <Link
            to="/onboarding"
            data-testid="account-edit-profile"
            className="text-[12.5px] font-medium text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1"
          >
            Edit brand details <ExternalLink size={11} />
          </Link>
        </div>
      </section>

      {/* Plan */}
      <section className="mb-6" data-testid="account-plan-section">
        <SectionHeader icon={Crown} label="Plan & Billing" />
        <div className="cv-glass rounded-2xl p-5 flex items-center gap-4">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
            user.comped ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
              : 'bg-violet-500/10 border border-violet-500/30 text-violet-300'
          }`}>
            {user.comped ? <Gift size={20} /> : <Sparkles size={20} />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-white capitalize" data-testid="account-plan">
              {user.plan || 'Free'} {user.comped && <span className="ml-2 text-[11px] uppercase tracking-wider text-emerald-300 font-bold">Comped</span>}
            </div>
            <div className="text-[12.5px] text-zinc-400 mt-0.5">
              {user.comped
                ? 'You have complimentary access — no card required.'
                : 'Current subscription tier.'}
            </div>
          </div>
          {!user.comped && (
            <Link
              to="/pricing"
              data-testid="account-manage-billing"
              className="text-[12.5px] font-medium bg-white/5 hover:bg-white/10 text-white px-3.5 h-9 rounded-lg inline-flex items-center gap-1.5 border border-white/10"
            >
              Manage <ExternalLink size={11} />
            </Link>
          )}
        </div>
      </section>

      {/* Privacy / data export */}
      <section className="mb-10" data-testid="account-privacy-section">
        <SectionHeader icon={ShieldAlert} label="Privacy" />
        <div className="cv-glass rounded-2xl divide-y divide-white/5">
          <Row
            title="Privacy policy"
            description="How we collect, use, and protect your data."
            cta={<a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-[12.5px] text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1">View <ExternalLink size={11} /></a>}
          />
          <Row
            title="Data deletion instructions"
            description="Public GDPR / Meta-review compliant page."
            cta={<a href="/data-deletion" target="_blank" rel="noopener noreferrer" className="text-[12.5px] text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1">View <ExternalLink size={11} /></a>}
          />
          <Row
            title="Export my data"
            description="Email privacy@cortexviral.com — we'll send a JSON archive within 30 days (GDPR)."
            cta={<a href="mailto:privacy@cortexviral.com?subject=Data%20export%20request" className="text-[12.5px] text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1">Request <ExternalLink size={11} /></a>}
          />
        </div>
      </section>

      {/* Danger zone */}
      <section data-testid="account-danger-zone">
        <SectionHeader icon={ShieldAlert} label="Danger zone" tone="rose" />
        <div className="rounded-2xl p-5 border border-rose-500/30 bg-rose-500/[0.04]">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center shrink-0">
              <Trash2 className="text-rose-300" size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[14.5px] font-semibold text-white">Delete account</div>
              <p className="text-[13px] text-zinc-400 mt-0.5 leading-relaxed">
                Permanently remove your account, all posts, scheduled content, leads, OAuth tokens, and support tickets. This action <strong className="text-rose-300">cannot be undone</strong>.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowConfirm(true)}
              data-testid="account-delete-trigger"
              className="bg-rose-500 hover:bg-rose-400 text-white text-[12.5px] font-semibold px-4 h-10 rounded-lg inline-flex items-center gap-1.5 shrink-0"
            >
              <Trash2 size={13} /> Delete account
            </button>
          </div>
        </div>
      </section>

      {showConfirm && (
        <ConfirmDeleteModal
          email={user.email}
          onClose={() => setShowConfirm(false)}
          onConfirmed={async () => {
            try { await logout(); } catch (e) { /* server already cleared session */ }
            toast({ title: 'Account deleted', description: 'All your data has been removed. Goodbye for now.' });
            window.location.href = '/';
          }}
        />
      )}
    </DashboardLayout>
  );
};

const SectionHeader = ({ icon: Icon, label, tone = 'zinc' }) => (
  <div className="flex items-center gap-2 mb-3">
    <Icon size={14} className={tone === 'rose' ? 'text-rose-300' : 'text-zinc-400'} />
    <span className={`text-[11px] uppercase tracking-[0.18em] font-semibold ${tone === 'rose' ? 'text-rose-300' : 'text-zinc-400'}`}>{label}</span>
  </div>
);

const Row = ({ title, description, cta }) => (
  <div className="flex items-center gap-4 p-4">
    <div className="flex-1 min-w-0">
      <div className="text-[13.5px] font-semibold text-white">{title}</div>
      <div className="text-[12.5px] text-zinc-400 mt-0.5 leading-relaxed">{description}</div>
    </div>
    <div className="shrink-0">{cta}</div>
  </div>
);

const ConfirmDeleteModal = ({ email, onClose, onConfirmed }) => {
  const { toast } = useToast();
  const [phrase, setPhrase] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const required = 'DELETE MY ACCOUNT';

  const submit = async (e) => {
    e.preventDefault();
    if (phrase !== required) {
      toast({ title: 'Type the phrase exactly to continue' });
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/account/delete`, { confirmation: phrase, reason }, { withCredentials: true });
      onConfirmed();
    } catch (err) {
      toast({
        title: 'Could not delete account',
        description: err.response?.data?.detail || err.message,
      });
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={() => { if (!busy) onClose(); }}
      data-testid="account-delete-modal"
    >
      <div
        className="bg-zinc-950 border border-rose-500/30 rounded-3xl max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-rose-300 mb-1">
          <ShieldAlert size={20} />
          <h3 className="text-lg font-semibold">Permanently delete account</h3>
        </div>
        <p className="text-[13.5px] text-zinc-400 leading-relaxed mt-2">
          You're about to delete <strong className="text-white">{email}</strong> and every piece of data tied to it. Type <code className="text-rose-300 bg-rose-500/10 px-1.5 py-0.5 rounded text-[12px]">{required}</code> to confirm.
        </p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            type="text"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder={required}
            data-testid="account-delete-phrase"
            autoFocus
            className="w-full h-11 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 px-3.5 text-[13.5px] font-mono outline-none focus:border-rose-500/50"
          />
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="(Optional) Tell us why you're leaving — it helps us improve."
            data-testid="account-delete-reason"
            className="w-full rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 px-3.5 py-2.5 text-[13px] outline-none focus:border-rose-500/50 resize-none"
          />
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="text-[13px] font-medium text-zinc-300 px-4 h-10 rounded-xl hover:bg-zinc-800/80"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || phrase !== required}
              data-testid="account-delete-submit"
              className="inline-flex items-center gap-2 bg-rose-500 hover:bg-rose-400 disabled:opacity-40 text-white text-[13px] font-semibold px-5 h-10 rounded-xl"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              {busy ? 'Deleting…' : 'Delete forever'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AccountSettings;
