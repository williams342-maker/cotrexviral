import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { useAuth, API } from '../context/AuthContext';

/* Magic-link claim page. Hits /api/auth/claim?token=... which sets the
   session_token cookie via Set-Cookie; we then re-fetch the user and bounce
   into the onboarding flow (or dashboard if already onboarded). */
const AuthClaim = () => {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { refresh } = useAuth();
  const [state, setState] = useState('working'); // working | ok | error
  const [error, setError] = useState('');

  useEffect(() => {
    const token = params.get('token');
    if (!token) {
      setState('error');
      setError('No sign-in token in the URL. Please use the link from your email.');
      return;
    }
    (async () => {
      try {
        await axios.get(`${API}/auth/claim`, {
          params: { token }, withCredentials: true,
        });
        await refresh();
        setState('ok');
        setTimeout(() => navigate('/dashboard', { replace: true }), 900);
      } catch (e) {
        setState('error');
        setError(e?.response?.data?.detail || 'This sign-in link is invalid or expired.');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0c0a1f] via-[#1a1442] to-[#0c0a1f] text-white flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white/[0.04] border border-white/10 backdrop-blur-xl rounded-3xl p-8 text-center" data-testid="auth-claim-card">
        {state === 'working' && (
          <>
            <Loader2 size={32} className="mx-auto mb-4 text-violet-300 animate-spin" />
            <h1 className="text-xl font-medium tracking-tight mb-2">Signing you in…</h1>
            <p className="text-[13.5px] text-neutral-400">Hang tight, exchanging your sign-in link.</p>
          </>
        )}
        {state === 'ok' && (
          <>
            <CheckCircle2 size={32} className="mx-auto mb-4 text-emerald-300" />
            <h1 className="text-xl font-medium tracking-tight mb-2">You're in!</h1>
            <p className="text-[13.5px] text-neutral-400">Taking you to your dashboard…</p>
          </>
        )}
        {state === 'error' && (
          <>
            <XCircle size={32} className="mx-auto mb-4 text-rose-300" />
            <h1 className="text-xl font-medium tracking-tight mb-2">Hmm, this link didn't work</h1>
            <p className="text-[13.5px] text-neutral-400 mb-6">{error}</p>
            <button
              onClick={() => navigate('/')}
              className="text-[13px] font-semibold text-violet-200 hover:text-violet-100 underline-offset-2 hover:underline"
              data-testid="auth-claim-back"
            >
              Back to homepage
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default AuthClaim;
