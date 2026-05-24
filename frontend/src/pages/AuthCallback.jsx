import React, { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API, useAuth } from '../context/AuthContext';
import { Loader2 } from 'lucide-react';

const AuthCallback = () => {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const run = async () => {
      const hash = window.location.hash;
      const m = hash.match(/session_id=([^&]+)/);
      if (!m) {
        navigate('/');
        return;
      }
      const sessionId = m[1];
      try {
        const res = await axios.post(
          `${API}/auth/session`,
          {},
          {
            headers: { 'X-Session-ID': sessionId },
            withCredentials: true,
          }
        );
        setUser(res.data);
        // clean hash
        window.history.replaceState(null, '', '/dashboard');
        navigate('/dashboard', { state: { user: res.data }, replace: true });
      } catch (e) {
        console.error('Auth callback failed', e);
        navigate('/');
      }
    };
    run();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F6F4ED]">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="animate-spin text-[#1B7BFF]" size={32} />
        <p className="text-neutral-700 text-sm">Signing you in…</p>
      </div>
    </div>
  );
};

export default AuthCallback;
