import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { X, Loader2, Mail, KeyRound, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { useAuth, API } from '../context/AuthContext';

/* AuthModal — single place to sign in.
   Two tabs: Google (one-click, redirects to Emergent Auth) + Email/password.
   When a user signs in with a temp password (must_change_password=true) we
   pivot to an inline "Set a new password" step before the modal closes. */

const AuthModal = ({ open, onClose, defaultTab = 'google' }) => {
  const navigate = useNavigate();
  const { login, refresh } = useAuth();
  const [tab, setTab] = useState(defaultTab);
  const [view, setView] = useState('signin'); // signin | reset | must_change
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [info, setInfo] = useState('');

  useEffect(() => {
    if (open) {
      setTab(defaultTab);
      setView('signin');
      setErr(''); setInfo('');
      setPassword(''); setNewPassword(''); setConfirmPassword('');
    }
  }, [open, defaultTab]);

  if (!open) return null;

  const close = () => { if (!busy) onClose(); };

  const submitLogin = async (e) => {
    e?.preventDefault?.();
    setErr(''); setInfo(''); setBusy(true);
    try {
      const r = await axios.post(`${API}/auth/password/login`,
        { email: email.trim().toLowerCase(), password },
        { withCredentials: true });
      if (r.data.must_change_password) {
        setView('must_change');
        setInfo('Welcome back — please choose a permanent password.');
        setBusy(false);
        return;
      }
      await refresh();
      onClose();
      navigate('/dashboard');
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Could not sign in');
      setBusy(false);
    }
  };

  const submitReset = async (e) => {
    e?.preventDefault?.();
    setErr(''); setInfo(''); setBusy(true);
    try {
      await axios.post(`${API}/auth/password/request-reset`,
        { email: email.trim().toLowerCase() });
      setInfo(`If ${email} is registered, we've emailed a temporary password. Check your inbox.`);
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Could not send reset email');
    }
    setBusy(false);
  };

  const submitSetInitial = async (e) => {
    e?.preventDefault?.();
    setErr(''); setBusy(true);
    if (newPassword.length < 8) {
      setErr('Use at least 8 characters');
      setBusy(false); return;
    }
    if (newPassword !== confirmPassword) {
      setErr('Passwords do not match');
      setBusy(false); return;
    }
    try {
      await axios.post(`${API}/auth/password/set-initial`,
        { new_password: newPassword }, { withCredentials: true });
      await refresh();
      onClose();
      navigate('/dashboard');
    } catch (ex) {
      setErr(ex.response?.data?.detail || 'Could not set new password');
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
      onClick={close}
      data-testid="auth-modal"
    >
      <div
        className="bg-zinc-950 border border-white/10 rounded-3xl max-w-md w-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-white/5">
          <h2 className="text-[18px] font-semibold tracking-tight text-white">
            {view === 'must_change'
              ? 'Set your permanent password'
              : view === 'reset'
                ? 'Reset your password'
                : 'Sign in to CortexViral'}
          </h2>
          <button
            onClick={close}
            disabled={busy}
            data-testid="auth-modal-close"
            className="w-8 h-8 rounded-lg hover:bg-white/5 flex items-center justify-center text-zinc-400"
          >
            <X size={16} />
          </button>
        </div>

        {view === 'signin' && (
          <>
            <div className="flex gap-1 m-5 mb-3 bg-white/5 rounded-xl p-1">
              <TabBtn id="google" active={tab === 'google'} onClick={() => setTab('google')}>Google</TabBtn>
              <TabBtn id="email" active={tab === 'email'} onClick={() => setTab('email')}>Email & password</TabBtn>
            </div>
            <div className="p-5 pt-2">
              {tab === 'google' ? (
                <div className="text-center py-3">
                  <button
                    onClick={login}
                    data-testid="auth-modal-google-btn"
                    className="w-full inline-flex items-center justify-center gap-2 bg-white text-zinc-900 hover:bg-zinc-100 text-[14px] font-semibold h-12 rounded-xl border border-zinc-200"
                  >
                    <GoogleIcon /> Continue with Google
                  </button>
                  <p className="text-[12px] text-zinc-500 mt-4 leading-relaxed">
                    One-click sign-in. No password to remember. Recommended.
                  </p>
                </div>
              ) : (
                <form onSubmit={submitLogin} className="space-y-3">
                  <Field
                    label="Email"
                    icon={Mail}
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={setEmail}
                    placeholder="you@example.com"
                    testId="auth-modal-email"
                  />
                  <Field
                    label="Password"
                    icon={KeyRound}
                    type={showPw ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={setPassword}
                    placeholder="Your password"
                    testId="auth-modal-password"
                    rightAdornment={
                      <button type="button" onClick={() => setShowPw((v) => !v)} className="text-zinc-500 hover:text-zinc-300">
                        {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    }
                  />
                  <Message err={err} info={info} />
                  <button
                    type="submit"
                    disabled={busy || !email || !password}
                    data-testid="auth-modal-submit"
                    className="w-full inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[14px] font-semibold h-11 rounded-xl disabled:opacity-50"
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                    {busy ? 'Signing in…' : 'Sign in'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setView('reset'); setErr(''); setInfo(''); }}
                    data-testid="auth-modal-forgot"
                    className="w-full text-[12.5px] text-cyan-300 hover:text-cyan-200 text-center pt-1"
                  >
                    Forgot password?
                  </button>
                </form>
              )}
            </div>
          </>
        )}

        {view === 'reset' && (
          <form onSubmit={submitReset} className="p-5 space-y-3">
            <p className="text-[13px] text-zinc-400 leading-relaxed">
              Enter your email and we'll send you a fresh temporary password. You'll set a permanent one on next login.
            </p>
            <Field
              label="Email"
              icon={Mail}
              type="email"
              value={email}
              onChange={setEmail}
              placeholder="you@example.com"
              testId="auth-modal-reset-email"
            />
            <Message err={err} info={info} />
            <button
              type="submit"
              disabled={busy || !email}
              data-testid="auth-modal-reset-submit"
              className="w-full inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[14px] font-semibold h-11 rounded-xl disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              {busy ? 'Sending…' : 'Send temporary password'}
            </button>
            <button
              type="button"
              onClick={() => setView('signin')}
              className="w-full text-[12.5px] text-zinc-400 hover:text-zinc-200 text-center pt-1"
            >
              ← Back to sign in
            </button>
          </form>
        )}

        {view === 'must_change' && (
          <form onSubmit={submitSetInitial} className="p-5 space-y-3">
            <p className="text-[13px] text-zinc-400 leading-relaxed">
              You signed in with a temporary password. Set a permanent one now — minimum 8 characters.
            </p>
            <Field
              label="New password"
              icon={KeyRound}
              type={showPw ? 'text' : 'password'}
              autoComplete="new-password"
              value={newPassword}
              onChange={setNewPassword}
              placeholder="At least 8 characters"
              testId="auth-modal-new-password"
              rightAdornment={
                <button type="button" onClick={() => setShowPw((v) => !v)} className="text-zinc-500 hover:text-zinc-300">
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              }
            />
            <Field
              label="Confirm new password"
              icon={KeyRound}
              type={showPw ? 'text' : 'password'}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              placeholder="Type it again"
              testId="auth-modal-confirm-password"
            />
            <Message err={err} info={info} />
            <button
              type="submit"
              disabled={busy || !newPassword || !confirmPassword}
              data-testid="auth-modal-set-initial-submit"
              className="w-full inline-flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-white text-[14px] font-semibold h-11 rounded-xl disabled:opacity-50"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              {busy ? 'Saving…' : 'Save password & continue'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

const TabBtn = ({ id, active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    data-testid={`auth-tab-${id}`}
    className={`flex-1 text-[12.5px] font-semibold py-2 rounded-lg transition-colors ${
      active ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-zinc-200'
    }`}
  >
    {children}
  </button>
);

const Field = ({ label, icon: Icon, value, onChange, placeholder, type = 'text',
                autoComplete, testId, rightAdornment }) => (
  <label className="block">
    <span className="text-[11px] uppercase tracking-wider font-semibold text-zinc-500 mb-1 block">{label}</span>
    <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 rounded-xl px-3 h-11 focus-within:border-cyan-500/40">
      <Icon size={14} className="text-zinc-500 shrink-0" />
      <input
        type={type}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testId}
        className="flex-1 bg-transparent text-[14px] text-zinc-100 placeholder:text-zinc-600 outline-none"
      />
      {rightAdornment}
    </div>
  </label>
);

const Message = ({ err, info }) => {
  if (!err && !info) return null;
  return err ? (
    <div className="flex items-start gap-2 text-[12.5px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2.5" data-testid="auth-modal-error">
      <AlertCircle size={13} className="shrink-0 mt-0.5" /> <span>{err}</span>
    </div>
  ) : (
    <div className="text-[12.5px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-2.5" data-testid="auth-modal-info">
      {info}
    </div>
  );
};

const GoogleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
);

export default AuthModal;
