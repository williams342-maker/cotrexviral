import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Link, useSearchParams } from 'react-router-dom';
import { Loader2, Trash2, ShieldAlert, User as UserIcon, Mail, Crown, Sparkles, Gift, ExternalLink, KeyRound, Eye, EyeOff, AlertCircle, CheckCircle2, LogOut, PauseCircle, Monitor, Brain, Pin, PinOff, Search, CheckSquare, Square, X } from 'lucide-react';
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
  const [showPause, setShowPause] = useState(false);

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

      {/* Password */}
      <PasswordSection />

      {/* Cortex preferences */}
      <CortexPreferencesSection />

      {/* AI autonomy */}
      <AIAutonomySection />

      {/* Active sessions */}
      <SessionsSection />

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

        {/* Pause account (reversible) */}
        <div className="rounded-2xl p-5 border border-amber-500/30 bg-amber-500/[0.04] mb-3" data-testid="account-pause-card">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0">
              <PauseCircle className="text-amber-300" size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[14.5px] font-semibold text-white">Pause my account</div>
              <p className="text-[13px] text-zinc-400 mt-0.5 leading-relaxed">
                Take a break. We'll sign you out of every device and stop sending emails. <strong className="text-amber-300">Nothing is deleted</strong> — sign back in any time to pick up where you left off.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowPause(true)}
              data-testid="account-pause-trigger"
              className="bg-amber-500 hover:bg-amber-400 text-zinc-950 text-[12.5px] font-semibold px-4 h-10 rounded-lg inline-flex items-center gap-1.5 shrink-0"
            >
              <PauseCircle size={13} /> Pause account
            </button>
          </div>
        </div>

        {/* Delete account (irreversible) */}
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

      {showPause && (
        <ConfirmPauseModal
          email={user.email}
          onClose={() => setShowPause(false)}
          onConfirmed={async () => {
            toast({ title: 'Account paused', description: 'Sign in any time to come back.' });
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

const PasswordSection = () => {
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const forceChange = searchParams.get('force_change') === '1' || user?.must_change_password;
  const sectionRef = useRef(null);

  // Auto-scroll + auto-expand the section if the user was redirected here to
  // change their temp password.
  const [expanded, setExpanded] = useState(forceChange);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    if (forceChange && sectionRef.current) {
      sectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [forceChange]);

  const hasPassword = !!user?.has_password;
  // Show 3 states:
  //   1. Forced change (temp pw user): no current_pw field, prominent rose box
  //   2. Change existing pw (hasPassword=true, !forced): all 3 fields
  //   3. Set initial pw (hasPassword=false, Google-only user): no current_pw field

  const submit = async (e) => {
    e?.preventDefault?.();
    setErr('');
    if (newPw.length < 8) { setErr('Use at least 8 characters'); return; }
    if (newPw !== confirmPw) { setErr('Passwords do not match'); return; }
    setBusy(true);
    try {
      if (forceChange) {
        await axios.post(`${API}/auth/password/set-initial`,
          { new_password: newPw }, { withCredentials: true });
      } else {
        await axios.post(`${API}/auth/password/change`,
          { current_password: currentPw, new_password: newPw },
          { withCredentials: true });
      }
      toast({
        title: forceChange ? 'Password set' : (hasPassword ? 'Password updated' : 'Password added'),
        description: forceChange
          ? 'Welcome to CortexViral — you can now sign in with this password going forward.'
          : 'Use this new password the next time you sign in.',
      });
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      // Strip ?force_change=1 from the URL after success
      if (searchParams.get('force_change')) {
        searchParams.delete('force_change');
        setSearchParams(searchParams, { replace: true });
      }
      await refresh();
      if (!forceChange) setExpanded(false);
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Could not save password');
    }
    setBusy(false);
  };

  return (
    <section ref={sectionRef} className="mb-6" data-testid="account-password-section">
      <SectionHeader icon={KeyRound} label="Password" tone={forceChange ? 'rose' : 'zinc'} />
      <div className={`rounded-2xl border ${
        forceChange ? 'border-rose-500/40 bg-rose-500/[0.05]' : 'cv-glass border-transparent'
      } overflow-hidden`}>
        <div className="p-5">
          {forceChange ? (
            <div>
              <div className="flex items-center gap-2 text-rose-300 mb-1">
                <AlertCircle size={16} />
                <span className="text-[13.5px] font-semibold">Set a permanent password</span>
              </div>
              <p className="text-[13px] text-zinc-400 leading-relaxed">
                You signed in with a temporary password. Choose a permanent one now to keep using CortexViral.
              </p>
            </div>
          ) : hasPassword ? (
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 text-emerald-300 mb-0.5">
                  <CheckCircle2 size={14} />
                  <span className="text-[13.5px] font-semibold text-white">Password sign-in is enabled</span>
                </div>
                <p className="text-[12.5px] text-zinc-400 leading-relaxed">
                  You can sign in with Google or with your email + password.
                </p>
              </div>
              {!expanded && (
                <button
                  onClick={() => setExpanded(true)}
                  data-testid="account-password-change-toggle"
                  className="text-[12.5px] font-medium text-cyan-300 hover:text-cyan-200"
                >
                  Change password
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="text-[13.5px] font-semibold text-white">Add password sign-in</div>
                <p className="text-[12.5px] text-zinc-400 leading-relaxed mt-0.5">
                  Right now you can only sign in with Google. Add a password to also use email + password.
                </p>
              </div>
              {!expanded && (
                <button
                  onClick={() => setExpanded(true)}
                  data-testid="account-password-add-toggle"
                  className="text-[12.5px] font-semibold bg-white/5 hover:bg-white/10 text-white px-3.5 h-9 rounded-lg border border-white/10 inline-flex items-center gap-1.5"
                >
                  <KeyRound size={12} /> Add password
                </button>
              )}
            </div>
          )}
        </div>

        {expanded && (
          <form onSubmit={submit} className="px-5 pb-5 space-y-3 border-t border-white/5 pt-4">
            {hasPassword && !forceChange && (
              <PwField
                label="Current password"
                value={currentPw}
                onChange={setCurrentPw}
                autoComplete="current-password"
                show={showPw}
                onToggleShow={() => setShowPw((v) => !v)}
                testId="account-password-current"
              />
            )}
            <PwField
              label={forceChange ? 'New password (min 8 chars)' : hasPassword ? 'New password' : 'Password (min 8 chars)'}
              value={newPw}
              onChange={setNewPw}
              autoComplete="new-password"
              show={showPw}
              onToggleShow={() => setShowPw((v) => !v)}
              testId="account-password-new"
            />
            <PwField
              label="Confirm new password"
              value={confirmPw}
              onChange={setConfirmPw}
              autoComplete="new-password"
              show={showPw}
              testId="account-password-confirm"
            />
            {err && (
              <div className="flex items-start gap-2 text-[12.5px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2.5" data-testid="account-password-error">
                <AlertCircle size={13} className="shrink-0 mt-0.5" /> <span>{err}</span>
              </div>
            )}
            <div className="flex gap-2 justify-end pt-1">
              {!forceChange && (
                <button
                  type="button"
                  onClick={() => { setExpanded(false); setErr(''); setCurrentPw(''); setNewPw(''); setConfirmPw(''); }}
                  disabled={busy}
                  className="text-[12.5px] font-medium text-zinc-400 hover:text-zinc-200 px-3 h-9 rounded-lg"
                >
                  Cancel
                </button>
              )}
              <button
                type="submit"
                disabled={busy || !newPw || !confirmPw || (hasPassword && !forceChange && !currentPw)}
                data-testid="account-password-submit"
                className={`inline-flex items-center gap-2 text-[12.5px] font-semibold px-4 h-9 rounded-lg disabled:opacity-50 ${
                  forceChange ? 'bg-rose-500 hover:bg-rose-400 text-white'
                              : 'bg-emerald-500 hover:bg-emerald-400 text-white'
                }`}
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />}
                {busy ? 'Saving…' : forceChange ? 'Set password' : hasPassword ? 'Update password' : 'Add password'}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
};

const PwField = ({ label, value, onChange, autoComplete, show, onToggleShow, testId }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-wider font-semibold text-zinc-500 mb-1 block">{label}</span>
    <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-3 h-11 focus-within:border-cyan-500/40">
      <KeyRound size={14} className="text-zinc-500 shrink-0" />
      <input
        type={show ? 'text' : 'password'}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
        className="flex-1 bg-transparent text-[14px] text-zinc-100 outline-none"
      />
      {onToggleShow && (
        <button type="button" onClick={onToggleShow} className="text-zinc-500 hover:text-zinc-300">
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      )}
    </div>
  </label>
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

const SessionsSection = () => {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/account/sessions`, { withCredentials: true });
      setData(r.data);
    } catch (e) {
      setData(null);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const revokeOthers = async () => {
    if (busy) return;
    if (!data || data.others < 1) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/account/sessions/revoke-others`, {}, { withCredentials: true });
      toast({
        title: `Signed out of ${r.data.revoked} other device${r.data.revoked === 1 ? '' : 's'}`,
        description: 'You\'re still signed in on this device.',
      });
      load();
    } catch (e) {
      toast({ title: 'Could not sign out other sessions', description: e.response?.data?.detail || e.message });
    }
    setBusy(false);
  };

  const revokeAll = async () => {
    if (busy) return;
    const yes = window.confirm('Sign out of every device, including this one?');
    if (!yes) return;
    setBusy(true);
    try {
      await axios.post(`${API}/account/sessions/revoke-all`, {}, { withCredentials: true });
      toast({ title: 'Signed out everywhere', description: 'You\'ll need to sign back in.' });
      window.location.href = '/';
    } catch (e) {
      toast({ title: 'Could not sign out everywhere', description: e.response?.data?.detail || e.message });
      setBusy(false);
    }
  };

  const totalLabel = data
    ? `${data.total} active session${data.total === 1 ? '' : 's'}`
    : '—';

  return (
    <section className="mb-6" data-testid="account-sessions-section">
      <SectionHeader icon={Monitor} label="Active sessions" />
      <div className="cv-glass rounded-2xl p-5">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 flex items-center justify-center shrink-0">
            <Monitor size={20} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[15px] font-semibold text-white" data-testid="account-sessions-count">
              {loading ? <Loader2 size={14} className="animate-spin inline" /> : totalLabel}
            </div>
            <div className="text-[12.5px] text-zinc-400 mt-0.5 leading-relaxed">
              {data && data.others > 0
                ? `You're signed in on ${data.others} other device${data.others === 1 ? '' : 's'}. Lost a laptop or phone? Sign out everywhere to lock it down.`
                : 'This is your only active session. You\'re good.'}
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              onClick={revokeOthers}
              disabled={busy || loading || !data || data.others < 1}
              data-testid="account-revoke-others"
              className="inline-flex items-center gap-1.5 text-[12.5px] font-medium bg-white/5 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed text-white px-3.5 h-9 rounded-lg border border-white/10"
            >
              <LogOut size={12} /> Sign out other devices
            </button>
            <button
              type="button"
              onClick={revokeAll}
              disabled={busy || loading}
              data-testid="account-revoke-all"
              className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 px-3.5 h-9 rounded-lg border border-rose-500/30 disabled:opacity-40"
            >
              <LogOut size={12} /> Sign out everywhere
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

const ConfirmPauseModal = ({ email, onClose, onConfirmed }) => {
  const { toast } = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/account/pause`, { reason }, { withCredentials: true });
      onConfirmed();
    } catch (err) {
      toast({
        title: 'Could not pause account',
        description: err.response?.data?.detail || err.message,
      });
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={() => { if (!busy) onClose(); }}
      data-testid="account-pause-modal"
    >
      <div
        className="bg-zinc-950 border border-amber-500/30 rounded-3xl max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 text-amber-300 mb-1">
          <PauseCircle size={20} />
          <h3 className="text-lg font-semibold">Pause your account</h3>
        </div>
        <p className="text-[13.5px] text-zinc-400 leading-relaxed mt-2">
          We'll sign <strong className="text-white">{email}</strong> out of every device and stop sending emails. Your posts, schedules, and connections stay intact. Sign back in any time to reactivate — no support ticket needed.
        </p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="(Optional) Anything we can improve before you go?"
            data-testid="account-pause-reason"
            className="w-full rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 px-3.5 py-2.5 text-[13px] outline-none focus:border-amber-500/50 resize-none"
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
              disabled={busy}
              data-testid="account-pause-submit"
              className="inline-flex items-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-zinc-950 text-[13px] font-semibold px-5 h-10 rounded-xl"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <PauseCircle size={14} />}
              {busy ? 'Pausing…' : 'Pause account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AccountSettings;


// ---------------------------------------------------------------------
// Cortex preferences — keyed off the new /api/user/preferences pair.
// Currently exposes one toggle (conversation_mode) but extensible.
// ---------------------------------------------------------------------
function CortexPreferencesSection() {
  const { toast } = useToast();
  const [mode, setMode] = useState(null);   // null = loading
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/user/preferences`, { withCredentials: true });
        setMode(r.data?.preferences?.conversation_mode || 'fresh_every_visit');
      } catch (_e) {
        setMode('fresh_every_visit');
      }
    })();
  }, []);

  const save = async (next) => {
    if (next === mode || saving) return;
    setSaving(true);
    const prev = mode;
    setMode(next);
    try {
      await axios.put(`${API}/user/preferences`,
                          { conversation_mode: next },
                          { withCredentials: true });
      toast({ title: 'Saved',
              description: next === 'fresh_every_visit'
                ? 'Cortex will start a new conversation each visit.'
                : 'Cortex will resume your last conversation.' });
    } catch (e) {
      setMode(prev);
      toast({ title: 'Could not save',
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setSaving(false); }
  };

  return (
    <section className="mb-6" data-testid="account-cortex-prefs-section">
      <SectionHeader icon={Sparkles} label="Cortex preferences" />
      <div className="cv-glass rounded-2xl p-5">
        <div className="text-[13px] font-semibold text-white mb-1">Conversation mode</div>
        <div className="text-[11.5px] text-zinc-500 mb-3">
          Cortex is designed for discrete missions, with History as the memory.
          The default starts each visit fresh — turn this off to resume your last thread.
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {[
            { id: 'fresh_every_visit',
              title: 'Fresh session every visit',
              hint:  'Recommended. Empty Command Center on entry. Past threads live in History.' },
            { id: 'resume_last',
              title: 'Resume last session',
              hint:  'Restore the most recent conversation when you open Command Center.' },
          ].map((opt) => {
            const active = mode === opt.id;
            return (
              <button key={opt.id} onClick={() => save(opt.id)}
                      data-testid={`conversation-mode-${opt.id}`}
                      disabled={mode === null || saving}
                      className={`text-left p-3 rounded-lg border transition ${
                        active
                          ? 'border-violet-500/50 bg-violet-500/10'
                          : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                      }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`w-3.5 h-3.5 rounded-full border flex-shrink-0 ${active ? 'border-violet-400 bg-violet-400' : 'border-white/30'}`} />
                  <span className="text-[12.5px] font-semibold text-white">{opt.title}</span>
                  {opt.id === 'fresh_every_visit' && (
                    <span className="text-[9px] uppercase tracking-wider font-bold text-violet-300 bg-violet-500/20 border border-violet-500/30 px-1.5 py-0.5 rounded">Recommended</span>
                  )}
                </div>
                <div className="text-[11px] text-zinc-500 leading-relaxed">{opt.hint}</div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}


// ---------------------------------------------------------------------
// <CortexMemorySection /> — Account Settings → Cortex Memory.
// Surfaces what Cortex has stored about this user (strategy summary +
// the last N conversation turns from cortex_memory_v2), lets the user
// pin important turns so they survive the per-user cap pruner, delete
// individual turns, and nuke everything.
// ---------------------------------------------------------------------

const AI_AUTONOMY_LEVELS = [
  { level: 0, title: 'L0 · Suggest only', hint: 'Ideas and recommendations only—no finished drafts.' },
  { level: 1, title: 'L1 · Draft only', hint: 'Creates reviewable drafts. Nothing is executed.', recommended: true },
  { level: 2, title: 'L2 · Prepare for approval', hint: 'Prepares actions and marks external work as needing approval.' },
  { level: 3, title: 'L3 · Explicit approval', hint: 'Execution would require explicit approval. External execution remains disabled.' },
  { level: 4, title: 'L4 · Rules-bounded', hint: 'Reserved for predefined rules. External execution remains disabled.' },
  { level: 5, title: 'L5 · Fully autonomous', hint: 'Disabled by platform safety policy.' },
];

function AIAutonomySection() {
  const { toast } = useToast();
  const [level, setLevel] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/user/preferences`, { withCredentials: true })
      .then((r) => setLevel(Number(r.data?.preferences?.ai_autonomy_level ?? 1)))
      .catch(() => setLevel(1));
  }, []);

  const save = async (next) => {
    if (next === level || saving) return;
    const previous = level;
    setLevel(next);
    setSaving(true);
    try {
      await axios.put(
        `${API}/user/preferences`,
        { ai_autonomy_level: next },
        { withCredentials: true },
      );
      toast({
        title: `AI autonomy set to L${next}`,
        description: AI_AUTONOMY_LEVELS[next].hint,
      });
    } catch (e) {
      setLevel(previous);
      toast({
        title: 'Could not save autonomy level',
        description: e?.response?.data?.detail || e.message,
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mb-6" data-testid="account-ai-autonomy-section">
      <SectionHeader icon={Brain} label="AI autonomy" />
      <div className="cv-glass rounded-2xl p-5">
        <div className="text-[13px] font-semibold text-white mb-1">Default autonomy level</div>
        <div className="text-[11.5px] text-zinc-500 mb-4">
          This becomes the default for AI Command Center and migrated AI generators.
          Publishing, email, ads, and marketplace execution remain disabled at every level.
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {AI_AUTONOMY_LEVELS.map((option) => {
            const active = level === option.level;
            return (
              <button
                key={option.level}
                type="button"
                onClick={() => save(option.level)}
                disabled={level === null || saving}
                data-testid={`ai-autonomy-level-${option.level}`}
                className={`text-left p-3 rounded-lg border transition ${
                  active
                    ? 'border-cyan-500/50 bg-cyan-500/10'
                    : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`w-3.5 h-3.5 rounded-full border flex-shrink-0 ${
                    active ? 'border-cyan-400 bg-cyan-400' : 'border-white/30'
                  }`} />
                  <span className="text-[12.5px] font-semibold text-white">{option.title}</span>
                  {option.recommended && (
                    <span className="text-[9px] uppercase tracking-wider font-bold text-cyan-300 bg-cyan-500/20 border border-cyan-500/30 px-1.5 py-0.5 rounded">
                      Recommended
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-zinc-500 leading-relaxed">{option.hint}</div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
function CortexMemorySection() {
  const { toast } = useToast();
  const [strategy, setStrategy] = useState(null);
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({ total_stored: 0, pinned_count: 0 });
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [showWipe, setShowWipe] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const searchTimer = useRef(null);

  // ---- bulk selection state ----
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = async (query = '') => {
    setLoading(true);
    try {
      const [memR, stratR] = await Promise.all([
        axios.get(`${API}/cortex/memory/me`,
                   { params: { limit: 50, q: query }, withCredentials: true }),
        axios.get(`${API}/cortex/memory/strategy`,
                   { withCredentials: true }),
      ]);
      setItems(memR.data?.items || []);
      setStats({
        total_stored: memR.data?.total_stored || 0,
        pinned_count: memR.data?.pinned_count || 0,
      });
      setStrategy(stratR.data || null);
    } catch (e) {
      toast({ title: "Couldn't load memory",
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(''); /* initial */ }, []);

  // Debounced search — 350ms after last keystroke.
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => { load(q); }, 350);
    return () => clearTimeout(searchTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const togglePin = async (turn, next) => {
    setBusyId(turn.id);
    try {
      await axios.post(`${API}/cortex/memory/pin/${turn.id}`,
                          { pinned: next }, { withCredentials: true });
      setItems((prev) => prev.map((t) =>
        t.id === turn.id ? { ...t, pinned: next } : t));
      setStats((s) => ({
        ...s, pinned_count: s.pinned_count + (next ? 1 : -1),
      }));
    } catch (e) {
      toast({ title: "Couldn't update pin",
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const removeOne = async (turn) => {
    setBusyId(turn.id);
    try {
      await axios.delete(`${API}/cortex/memory/turn/${turn.id}`,
                            { withCredentials: true });
      setItems((prev) => prev.filter((t) => t.id !== turn.id));
      setStats((s) => ({
        total_stored: Math.max(0, s.total_stored - 1),
        pinned_count: Math.max(0, s.pinned_count - (turn.pinned ? 1 : 0)),
      }));
    } catch (e) {
      toast({ title: "Couldn't delete",
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else              next.add(id);
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectMode(false);
  };

  const selectAllUnpinned = () => {
    const ids = items.filter((t) => !t.pinned).map((t) => t.id);
    if (ids.length === 0) {
      toast({ title: 'Nothing to select',
              description: 'All visible turns are pinned.' });
      return;
    }
    setSelectMode(true);
    setSelectedIds(new Set(ids));
  };

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!window.confirm(`Delete ${ids.length} memory turn${ids.length > 1 ? 's' : ''}? This cannot be undone.`)) return;
    setBulkBusy(true);
    try {
      const r = await axios.post(`${API}/cortex/memory/bulk-delete`,
                                    { ids }, { withCredentials: true });
      const deleted = r.data?.deleted ?? ids.length;
      // Count pinned among the about-to-be-deleted set so stats stay
      // accurate after the optimistic update.
      const pinnedDeleted = items.filter((t) =>
        selectedIds.has(t.id) && t.pinned).length;
      setItems((prev) => prev.filter((t) => !selectedIds.has(t.id)));
      setStats((s) => ({
        total_stored: Math.max(0, s.total_stored - deleted),
        pinned_count: Math.max(0, s.pinned_count - pinnedDeleted),
      }));
      clearSelection();
      toast({ title: 'Memory cleared',
              description: `Removed ${deleted} of ${ids.length} turns.` });
    } catch (e) {
      toast({ title: "Bulk delete failed",
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    } finally { setBulkBusy(false); }
  };

  const wipeAll = async () => {
    setShowWipe(false);
    try {
      const r = await axios.delete(`${API}/cortex/memory/all`,
                                       { withCredentials: true });
      toast({ title: 'Memory wiped',
              description: `Cortex forgot ${r.data.deleted_vectors} turns and its strategy doc. It'll start fresh on your next message.` });
      setItems([]);
      setStats({ total_stored: 0, pinned_count: 0 });
      setStrategy(null);
    } catch (e) {
      toast({ title: "Couldn't wipe memory",
              description: e?.response?.data?.detail || e.message,
              variant: 'destructive' });
    }
  };

  const fmt = (iso) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const now = new Date();
      const diff = (now - d) / 1000;
      if (diff < 60) return 'just now';
      if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  return (
    <section className="mb-6" data-testid="account-memory-section">
      <SectionHeader icon={Brain} label="Cortex memory" />

      {/* Strategy summary — Mongo-backed long-term memory */}
      <div className="cv-glass rounded-2xl p-5 mb-3" data-testid="memory-strategy-card">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[13px] font-semibold text-white">What Cortex believes about you</div>
          <span className="text-[10.5px] uppercase tracking-wider text-zinc-500">Auto-distilled</span>
        </div>
        {strategy?.summary ? (
          <p className="text-[13px] text-zinc-300 leading-relaxed whitespace-pre-line" data-testid="memory-strategy-summary">
            {strategy.summary}
          </p>
        ) : (
          <p className="text-[12.5px] text-zinc-500 italic">
            Cortex hasn&apos;t formed an opinion yet — keep chatting and a strategy summary will appear here.
          </p>
        )}
        {Array.isArray(strategy?.goals) && strategy.goals.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {strategy.goals.slice(0, 6).map((g, i) => (
              <span key={i} className="text-[10.5px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-200 border border-violet-500/20">
                {g}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Stored turns — semantic memory inspection */}
      <div className="cv-glass rounded-2xl p-5">
        <div className="flex flex-wrap items-center gap-3 justify-between mb-3">
          <div className="text-[13px] font-semibold text-white flex items-center gap-2">
            Stored conversation turns
            <span className="text-[10.5px] font-normal text-zinc-500" data-testid="memory-stats">
              {stats.total_stored} total · {stats.pinned_count} pinned
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
              <input
                type="text"
                placeholder="Search memory…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                data-testid="memory-search-input"
                className="h-8 w-44 sm:w-56 pl-7 pr-2 text-[12px] rounded-md bg-black/30 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-violet-500/40"
              />
            </div>
            {stats.total_stored > 0 && (
              <>
                <button
                  onClick={() => {
                    if (selectMode) clearSelection();
                    else setSelectMode(true);
                  }}
                  data-testid="memory-toggle-select-mode"
                  title={selectMode ? 'Exit selection mode' : 'Select multiple turns'}
                  className={`h-8 text-[11.5px] font-medium px-2.5 rounded-md border inline-flex items-center gap-1.5 transition ${
                    selectMode
                      ? 'bg-violet-500/20 text-violet-100 border-violet-500/40'
                      : 'text-zinc-300 border-white/10 hover:bg-white/[0.05]'}`}>
                  {selectMode ? <CheckSquare size={11} /> : <Square size={11} />}
                  {selectMode ? 'Selecting' : 'Select'}
                </button>
                {items.some((t) => !t.pinned) && (
                  <button
                    onClick={selectAllUnpinned}
                    data-testid="memory-select-unpinned"
                    title="Select every unpinned turn"
                    className="h-8 text-[11.5px] font-medium px-2.5 rounded-md border inline-flex items-center gap-1.5 text-amber-200 hover:bg-amber-500/10 border-amber-500/25 transition">
                    <PinOff size={11} /> Select unpinned
                  </button>
                )}
                <button
                  onClick={() => setShowWipe(true)}
                  data-testid="memory-wipe-btn"
                  className="h-8 text-[11.5px] font-medium text-rose-300 hover:text-rose-200 hover:bg-rose-500/10 px-2.5 rounded-md border border-rose-500/20 inline-flex items-center gap-1.5"
                >
                  <Trash2 size={11} /> Wipe all
                </button>
              </>
            )}
          </div>
        </div>

        {selectedIds.size > 0 && (
          <div data-testid="memory-selection-bar"
               className="mb-3 rounded-xl border border-violet-500/30 bg-violet-500/[0.08] px-3 py-2 flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-[12px] text-violet-100 font-semibold">
              <CheckSquare size={13} />
              <span data-testid="memory-selection-count">
                {selectedIds.size} selected
              </span>
              <span className="text-violet-300/70 font-normal">· of {items.length} visible</span>
            </div>
            <button onClick={() => setSelectedIds(new Set(items.map((t) => t.id)))}
                    data-testid="memory-selection-select-all"
                    disabled={bulkBusy || selectedIds.size >= items.length}
                    className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-zinc-200 border border-white/10 transition disabled:opacity-40 disabled:cursor-not-allowed">
              Select all visible
            </button>
            <div className="flex-1" />
            <button onClick={clearSelection}
                    data-testid="memory-selection-cancel"
                    disabled={bulkBusy}
                    className="text-[11px] font-semibold px-2 py-1 rounded-md text-zinc-300 hover:text-white hover:bg-white/[0.06] transition flex items-center gap-1">
              <X size={11} /> Cancel
            </button>
            <button onClick={bulkDelete}
                    data-testid="memory-selection-delete"
                    disabled={bulkBusy}
                    className="text-[11.5px] font-semibold px-3 py-1.5 rounded-md bg-rose-500 hover:bg-rose-400 text-white transition flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-rose-500/20">
              <Trash2 size={12} />
              {bulkBusy ? 'Deleting…' : `Delete ${selectedIds.size}`}
            </button>
          </div>
        )}

        {loading ? (
          <div className="py-10 text-center text-zinc-500">
            <Loader2 className="animate-spin mx-auto" size={16} />
          </div>
        ) : items.length === 0 ? (
          <div className="py-8 text-center text-[12.5px] text-zinc-500" data-testid="memory-empty">
            {q.trim() ? 'No matches for that search.' : 'No conversation turns stored yet.'}
          </div>
        ) : (
          <ul className="divide-y divide-white/5" data-testid="memory-list">
            {items.map((t) => {
              const isSelected = selectedIds.has(t.id);
              const inSelectMode = selectMode || selectedIds.size > 0;
              const onRowClick = inSelectMode ? () => toggleSelect(t.id) : undefined;
              return (
              <li key={t.id}
                   onClick={onRowClick}
                   className={`py-3 flex items-start gap-3 transition ${
                     inSelectMode ? 'cursor-pointer hover:bg-white/[0.02] -mx-2 px-2 rounded' : ''
                   } ${isSelected ? 'bg-violet-500/[0.07] -mx-2 px-2 rounded' : ''}`}
                   data-testid={`memory-turn-${t.id}`}>
                {inSelectMode && (
                  <span data-testid={`memory-checkbox-${t.id}`}
                        className={`mt-0.5 w-4 h-4 rounded shrink-0 flex items-center justify-center border transition ${
                          isSelected
                            ? 'bg-violet-500 border-violet-400 text-white'
                            : 'bg-white/[0.04] border-white/20 text-transparent'}`}>
                    {isSelected ? <CheckSquare size={10} /> : null}
                  </span>
                )}
                <span className={`mt-0.5 text-[9.5px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded shrink-0 ${
                  t.role === 'cortex'
                    ? 'bg-violet-500/15 text-violet-200 border border-violet-500/25'
                    : 'bg-cyan-500/10 text-cyan-200 border border-cyan-500/20'
                }`}>
                  {t.role === 'cortex' ? 'Cortex' : 'You'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-zinc-200 leading-relaxed">
                    {t.preview}
                  </div>
                  <div className="text-[10.5px] text-zinc-500 mt-1 flex items-center gap-2">
                    <span>{fmt(t.created_at)}</span>
                    {t.pinned && (
                      <span className="text-amber-300 font-semibold inline-flex items-center gap-0.5">
                        <Pin size={9} /> pinned
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0"
                     onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => togglePin(t, !t.pinned)}
                    disabled={busyId === t.id}
                    data-testid={`memory-pin-${t.id}`}
                    title={t.pinned ? 'Unpin' : 'Pin so this never gets pruned'}
                    className={`p-1.5 rounded-md transition ${
                      t.pinned
                        ? 'text-amber-300 hover:bg-amber-500/10'
                        : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/5'
                    }`}>
                    {t.pinned ? <PinOff size={13} /> : <Pin size={13} />}
                  </button>
                  <button
                    onClick={() => removeOne(t)}
                    disabled={busyId === t.id}
                    data-testid={`memory-delete-${t.id}`}
                    title="Delete this turn"
                    className="p-1.5 rounded-md text-zinc-500 hover:text-rose-300 hover:bg-rose-500/10 transition">
                    <Trash2 size={13} />
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Wipe confirmation */}
      {showWipe && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" data-testid="memory-wipe-modal">
          <div className="cv-glass-strong rounded-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle className="text-rose-300" size={18} />
              <div className="text-[15px] font-semibold text-white">Wipe Cortex&apos;s memory?</div>
            </div>
            <p className="text-[13px] text-zinc-300 leading-relaxed mb-4">
              This deletes all {stats.total_stored} stored conversation turns and your strategy summary. Cortex will start completely fresh on your next message. <strong className="text-white">This cannot be undone.</strong>
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowWipe(false)}
                       className="px-3.5 h-9 text-[12.5px] font-medium rounded-md text-zinc-300 hover:bg-white/5">
                Cancel
              </button>
              <button onClick={wipeAll}
                       data-testid="memory-wipe-confirm"
                       className="px-3.5 h-9 text-[12.5px] font-semibold rounded-md bg-rose-500/20 text-rose-200 border border-rose-500/30 hover:bg-rose-500/30">
                Yes, wipe everything
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
