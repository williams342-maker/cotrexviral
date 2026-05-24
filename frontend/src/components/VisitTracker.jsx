/* Anonymous page-view ping for the marketing funnel.
   Mounts once at the App root; fires on every public route change.
   Skips /dashboard, /admin, /auth-callback so we never log authenticated views.
   Failures are swallowed — analytics must never break the page. */
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SKIP_PREFIXES = ['/dashboard', '/admin', '/auth-callback'];

export default function VisitTracker() {
  const { pathname } = useLocation();
  const lastSent = useRef(null);

  useEffect(() => {
    if (SKIP_PREFIXES.some((p) => pathname.startsWith(p))) return;
    if (lastSent.current === pathname) return; // de-dupe identical re-mounts
    lastSent.current = pathname;

    const referrer = typeof document !== 'undefined' ? document.referrer || '' : '';
    axios
      .post(`${API}/track/visit`, { path: pathname, referrer }, { withCredentials: false })
      .catch(() => {});
  }, [pathname]);

  return null;
}
