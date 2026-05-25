import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../context/AuthContext';
import { Info, AlertCircle, AlertTriangle, CheckCircle2, X } from 'lucide-react';

const SEVERITY_META = {
  info: { icon: Info, bg: 'bg-sky-50', text: 'text-sky-900', border: 'border-sky-200', accent: 'text-sky-600' },
  success: { icon: CheckCircle2, bg: 'bg-emerald-50', text: 'text-emerald-900', border: 'border-emerald-200', accent: 'text-emerald-600' },
  warning: { icon: AlertTriangle, bg: 'bg-amber-50', text: 'text-amber-900', border: 'border-amber-200', accent: 'text-amber-600' },
  critical: { icon: AlertCircle, bg: 'bg-rose-50', text: 'text-rose-900', border: 'border-rose-200', accent: 'text-rose-600' },
};

const BroadcastBanner = () => {
  const [broadcasts, setBroadcasts] = useState([]);
  const [dismissed, setDismissed] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dismissed_broadcasts') || '[]'); } catch { return []; }
  });

  useEffect(() => {
    axios.get(`${API}/broadcasts/active`, { withCredentials: true })
      .then((r) => setBroadcasts(Array.isArray(r.data) ? r.data : []))
      .catch(() => {});
  }, []);

  const dismiss = (id) => {
    const next = [...dismissed, id];
    setDismissed(next);
    localStorage.setItem('dismissed_broadcasts', JSON.stringify(next));
  };

  const visible = (broadcasts || []).filter((b) => !dismissed.includes(b.id));
  if (visible.length === 0) return null;

  return (
    <div className="space-y-2 mb-6">
      {visible.map((b) => {
        const meta = SEVERITY_META[b.severity] || SEVERITY_META.info;
        const Icon = meta.icon;
        return (
          <div key={b.id} className={`flex items-start gap-3 p-4 rounded-2xl border ${meta.bg} ${meta.border}`}>
            <Icon size={18} className={`${meta.accent} shrink-0 mt-0.5`} />
            <div className="flex-1 min-w-0">
              <div className={`text-[14px] font-semibold ${meta.text}`}>{b.title}</div>
              <p className={`text-[13.5px] ${meta.text} opacity-90 leading-relaxed mt-0.5`}>{b.body}</p>
            </div>
            <button onClick={() => dismiss(b.id)} className={`shrink-0 p-1 rounded-md hover:bg-white/60 ${meta.accent}`}>
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default BroadcastBanner;
