import React from 'react';
import { Loader2 } from 'lucide-react';

/* PhaseIndicator — live "thinking out loud" status while SSE streams.
   Shows the current phase prominently + a faded breadcrumb of completed phases. */

export const PhaseIndicator = ({ phase, phaseHistory = [] }) => {
  if (!phase) return null;
  return (
    <div data-testid="cortex-phase-indicator"
         className="flex flex-col gap-1 mt-2">
      <div className="flex items-center gap-2 text-[12px] text-violet-300 italic">
        <Loader2 size={11} className="animate-spin" />
        <span className="font-medium">{phase.label}</span>
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">
          · {phase.phase}
        </span>
      </div>
      {phaseHistory.length > 1 && (
        <div className="flex items-center gap-1.5 ml-5 text-[10px] text-zinc-600 flex-wrap">
          {phaseHistory.slice(0, -1).map((p, i) => (
            <React.Fragment key={i}>
              <span className="text-emerald-500/60">✓</span>
              <span>{p.phase}</span>
              <span>·</span>
            </React.Fragment>
          ))}
          <span className="text-violet-400">{phase.phase}…</span>
        </div>
      )}
    </div>
  );
};

export default PhaseIndicator;
