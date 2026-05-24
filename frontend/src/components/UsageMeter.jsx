import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Loader2, ArrowRight, Sparkles } from 'lucide-react';
import { API } from '../context/AuthContext';

/**
 * UsageMeter — small inline component that displays how many AI generations
 * the user has consumed this month against their plan's cap. Hidden for
 * unlimited plans (Pro/Scale).
 *
 * Used in the Studio, Compose, Insights pages so creators see their remaining
 * runway and the upgrade prompt right where the friction lives.
 */
const UsageMeter = ({ refreshKey = 0, compact = false }) => {
  const [u, setU] = useState(null);

  useEffect(() => {
    axios.get(`${API}/billing/usage`, { withCredentials: true })
      .then((r) => setU(r.data))
      .catch(() => setU(null));
  }, [refreshKey]);

  if (!u) {
    return compact ? null : (
      <div className="inline-flex items-center gap-2 text-[12px] text-neutral-400">
        <Loader2 size={11} className="animate-spin" /> Loading usage…
      </div>
    );
  }

  // Unlimited plan → show plan badge only.
  if (u.ai_generations_limit === null) {
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-50 text-violet-700 text-[11.5px] font-semibold border border-violet-100"
        data-testid="usage-meter-unlimited"
      >
        <Sparkles size={11} /> {u.plan_label} · Unlimited
      </div>
    );
  }

  const pct = Math.min(100, Math.round((u.ai_generations_used / u.ai_generations_limit) * 100));
  const exhausted = u.ai_generations_remaining === 0;
  const warn = pct >= 80;

  if (compact) {
    return (
      <div className="inline-flex items-center gap-2 text-[12px]" data-testid="usage-meter-compact">
        <div className="w-24 h-1.5 rounded-full bg-neutral-200 overflow-hidden">
          <div
            className={`h-full transition-all ${exhausted ? 'bg-rose-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={exhausted ? 'text-rose-600 font-semibold' : 'text-neutral-600'}>
          {u.ai_generations_used} / {u.ai_generations_limit}
        </span>
      </div>
    );
  }

  return (
    <div
      className={`rounded-2xl border p-4 ${exhausted ? 'bg-rose-50 border-rose-200' : warn ? 'bg-amber-50 border-amber-200' : 'bg-white border-neutral-200/70'}`}
      data-testid="usage-meter"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="text-[13px] font-semibold text-neutral-900">
          AI generations this month
        </div>
        <div className={`text-[13px] font-semibold ${exhausted ? 'text-rose-700' : warn ? 'text-amber-700' : 'text-neutral-700'}`}>
          {u.ai_generations_used} / {u.ai_generations_limit}
        </div>
      </div>
      <div className="w-full h-1.5 rounded-full bg-neutral-200 overflow-hidden">
        <div
          className={`h-full transition-all ${exhausted ? 'bg-rose-500' : warn ? 'bg-amber-500' : 'bg-emerald-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {(warn || exhausted) && (
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-[12.5px] text-neutral-700 leading-snug">
            {exhausted
              ? "You've hit your monthly limit. Upgrade for unlimited AI."
              : `Only ${u.ai_generations_remaining} left this month.`}
          </p>
          <Link
            to="/pricing"
            className="cv-btn-primary inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-[12px] font-semibold shrink-0"
            data-testid="usage-meter-upgrade"
          >
            Upgrade <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </div>
  );
};

export default UsageMeter;
