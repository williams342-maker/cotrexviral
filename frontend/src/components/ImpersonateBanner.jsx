import React from 'react';
import axios from 'axios';
import { API, useAuth } from '../context/AuthContext';
import { UserCog, X } from 'lucide-react';
import { useToast } from '../hooks/use-toast';

const ImpersonateBanner = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [stopping, setStopping] = React.useState(false);

  // We approximate "impersonating" by checking if there is a special hint.
  // The backend only knows; the easiest signal is asking on mount.
  const [impersonating, setImpersonating] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      try {
        // We can't directly know, but we can call a small helper endpoint pattern:
        // If session token was set with impersonated_by, /api/auth/me still works for the target.
        // To detect, we attach the original_token hint via cookie name. For now, use sessionStorage flag.
        const flag = sessionStorage.getItem('impersonating');
        if (flag && !cancelled) setImpersonating(JSON.parse(flag));
      } catch (e) {}
    };
    ping();
    return () => { cancelled = true; };
  }, [user]);

  const stop = async () => {
    setStopping(true);
    try {
      await axios.post(`${API}/admin/stop-impersonating`, {}, { withCredentials: true });
      sessionStorage.removeItem('impersonating');
      toast({ title: 'Stopped impersonating' });
      window.location.href = '/admin';
    } catch (e) {
      toast({ title: 'Could not stop impersonating' });
    } finally {
      setStopping(false);
    }
  };

  if (!impersonating) return null;
  return (
    <div className="fixed top-0 left-0 right-0 z-[60] bg-amber-500 text-white py-2 px-4 text-[13px] flex items-center justify-center gap-3 font-medium">
      <UserCog size={15} />
      Viewing as <strong>{impersonating.name}</strong> ({impersonating.email})
      <button onClick={stop} disabled={stopping} className="ml-2 inline-flex items-center gap-1 bg-amber-700 hover:bg-amber-800 disabled:opacity-60 px-3 py-1 rounded-full text-[12px]">
        <X size={12} /> Stop
      </button>
    </div>
  );
};

export default ImpersonateBanner;
