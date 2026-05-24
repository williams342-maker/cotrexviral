import React from 'react';
import { Link } from 'react-router-dom';
import { Lock, ArrowRight, Sparkles } from 'lucide-react';

/**
 * FeatureLock — wraps a feature surface. When the user lacks the entitlement,
 * renders a blurred preview of the children with an upgrade overlay on top.
 *
 * Props:
 *   unlocked: boolean — true when the user has this feature
 *   feature: string — display name ("Trend Engine", "A/B Hook Lab")
 *   requires: string — minimum tier label ("Growth", "Agency")
 *   blurb?: string — short value prop shown in overlay
 *   children: ReactNode — the actual feature UI (always rendered, blurred when locked)
 */
const FeatureLock = ({ unlocked, feature, requires, blurb, children }) => {
  if (unlocked) return children;
  return (
    <div className="relative" data-testid={`feature-lock-${feature.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
      <div
        aria-hidden
        className="pointer-events-none select-none filter blur-sm opacity-40 grayscale"
      >
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center p-6">
        <div className="cv-glass-strong rounded-3xl p-8 max-w-md text-center shadow-2xl">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 text-white flex items-center justify-center mx-auto mb-4">
            <Lock size={18} />
          </div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold mb-1.5">
            Unlocks on {requires}
          </div>
          <h3 className="cv-display text-2xl font-semibold text-white">{feature}</h3>
          {blurb && <p className="mt-2.5 text-[13.5px] text-zinc-400 leading-relaxed">{blurb}</p>}
          <Link
            to="/pricing"
            className="cv-btn-primary inline-flex items-center gap-1.5 mt-5 px-5 h-10 rounded-full text-[13px] font-semibold"
            data-testid="feature-lock-upgrade"
          >
            <Sparkles size={13} /> Upgrade to {requires} <ArrowRight size={13} />
          </Link>
        </div>
      </div>
    </div>
  );
};

export default FeatureLock;
