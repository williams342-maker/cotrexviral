import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Activity, ChevronRight } from 'lucide-react';

/* CortexThinkingCard — surfaces the in-flight conversational analysis
   into the right-rail so users see "Cortex is analyzing…" without
   needing to scroll the chat. Rendered above the real analysis_jobs
   when the latest Cortex turn is `stage='analysis'`.

   Props:
     turn         — the latest Cortex turn (must have stage='analysis' + findings)
     onScrollToTurn — optional callback to scroll the chat to this turn */
const CortexThinkingCard = ({ turn, onScrollToTurn }) => {
  if (!turn || turn.stage !== 'analysis') return null;
  const findings = turn.findings || [];
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ duration: 0.3 }}
        data-testid="cortex-thinking-card"
        onClick={() => onScrollToTurn?.(turn.id)}
        className="rounded-xl border border-amber-500/25 bg-amber-500/[0.05]
                   p-3 cursor-pointer hover:bg-amber-500/[0.07] transition group">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="w-5 h-5 rounded-md bg-gradient-to-br from-violet-500 to-fuchsia-500
                            flex items-center justify-center shadow-sm shadow-violet-500/30">
            <Brain size={10} className="text-white" />
          </span>
          <span className="text-[10px] uppercase tracking-widest text-amber-300 font-semibold flex items-center gap-1">
            <Activity size={9} className="animate-pulse" /> Cortex is analyzing
          </span>
          <span className="ml-auto text-[10px] text-amber-400/70 normal-case tracking-normal">
            live
          </span>
        </div>

        {/* Indeterminate progress bar — same animation as the in-chat
            FindingsCard so it's clearly the same "in-progress" state. */}
        <div data-testid="cortex-thinking-progress"
             className="h-1 bg-amber-500/10 rounded-full overflow-hidden mb-2 relative">
          <div className="absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-amber-400 to-transparent rounded-full animate-[cv-indeterminate_1.4s_ease-in-out_infinite]" />
        </div>

        {findings.length > 0 && (
          <ul className="space-y-0.5 mb-1">
            {findings.slice(0, 3).map((f, i) => (
              <li key={i} className="text-[11px] text-zinc-300 leading-snug line-clamp-2 flex items-start gap-1.5">
                <span className="text-amber-400 mt-1 shrink-0">•</span>
                <span>{f}</span>
              </li>
            ))}
            {findings.length > 3 && (
              <li className="text-[10px] text-zinc-500 italic pl-3">
                +{findings.length - 3} more in chat
              </li>
            )}
          </ul>
        )}

        <div className="text-[10px] text-amber-300/80 mt-1.5 flex items-center gap-0.5 font-semibold group-hover:gap-1.5 transition-all">
          View in chat <ChevronRight size={9} />
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default CortexThinkingCard;
