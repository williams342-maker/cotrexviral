import React from 'react';
import {
  Search, Activity, Sparkles, Rocket, CheckCircle2,
} from 'lucide-react';

/* Stage pill + "Recommendation lite" card for the Discovery-First flow.
   Plan cards are gated behind the funnel — until the user accepts the
   recommendation, Cortex stays in conversation mode with text + soft CTAs. */

const STAGES = {
  discovery: {
    label: 'Discovery',
    icon: Search,
    cls: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  },
  analysis: {
    label: 'Analysis',
    icon: Activity,
    cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  },
  recommendation: {
    label: 'Recommendation',
    icon: Sparkles,
    cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  },
  mission_proposal: {
    label: 'Mission Proposal',
    icon: Rocket,
    cls: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30',
  },
  execution: {
    label: 'Execution',
    icon: CheckCircle2,
    cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  },
};


export const StagePill = ({ stage }) => {
  const meta = STAGES[stage];
  if (!meta) return null;
  const Icon = meta.icon;
  return (
    <span data-testid={`stage-pill-${stage}`}
          className={`inline-flex items-center gap-1 text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border ${meta.cls}`}>
      <Icon size={9} /> {meta.label}
    </span>
  );
};


/* ClarifyingQuestionsCard — discovery-stage card.
   Per the Discovery & Consultant redesign:
     · `answer_shortcuts` (clickable answer chips) are the PRIMARY
       affordance. Each click submits the answer as a tagged user
       message and advances state — it never repeats the question.
     · `questions` render below as supporting context so the user can
       see what's being asked, but they're click-to-insert (low key)
       rather than the main interaction.
   Discovery Budget: if `budget_used >= 2`, the card shows a "moving on"
   hint so the user knows Cortex is wrapping discovery up. */
export const ClarifyingQuestionsCard = ({
  questions = [], answerShortcuts = [], budgetUsed = 0,
  onPick, onPickShortcut,
}) => {
  if (!questions.length && !answerShortcuts.length) return null;
  return (
    <div data-testid="clarifying-questions"
         className="rounded-xl border border-cyan-500/15 bg-cyan-500/[0.03] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold flex items-center gap-1">
          <Search size={10} /> Help Cortex understand
        </div>
        {budgetUsed > 0 && (
          <div data-testid="discovery-budget-indicator"
                className="text-[9px] uppercase tracking-wider text-zinc-500 font-mono">
            Discovery {Math.min(budgetUsed, 2)}/2
          </div>
        )}
      </div>

      {/* Primary affordance: answer shortcuts. Click → advance state. */}
      {answerShortcuts.length > 0 && (
        <div data-testid="answer-shortcuts" className="flex flex-wrap gap-1.5 mb-2">
          {answerShortcuts.map((s, i) => (
            <button key={i} onClick={() => onPickShortcut?.(s)}
                    data-testid={`answer-shortcut-${i}`}
                    className="text-[11.5px] font-medium px-2.5 py-1.5 rounded-full bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-200 border border-cyan-500/30 hover:border-cyan-400/50 transition">
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Subordinate: clarifying questions stay click-to-insert but
          appear smaller / secondary when shortcuts exist. */}
      {questions.length > 0 && (
        <div className={`space-y-1 ${answerShortcuts.length > 0 ? 'mt-2 pt-2 border-t border-white/5' : ''}`}>
          {questions.map((q, i) => (
            <button key={i} onClick={() => onPick?.(q)}
                    data-testid={`clarifying-question-${i}`}
                    className={`w-full text-left rounded-md transition px-2.5 py-1.5
                                ${answerShortcuts.length > 0
                                  ? 'text-[10.5px] text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03]'
                                  : 'text-[12px] text-zinc-300 hover:text-white bg-white/[0.02] hover:bg-white/[0.05] border border-white/5'}`}>
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};


/* RecommendationLiteCard — appears in stage=recommendation. Shows
   findings + reasoning summary + alternatives + a "Create Mission?"
   CTA. NO plan card yet — that comes only when the user accepts. */
export const RecommendationLiteCard = ({
  summary, findings = [], alternatives = [],
  onAccept, onDecline, busy,
}) => {
  if (!summary && findings.length === 0) return null;
  return (
    <div data-testid="recommendation-lite-card"
         className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-500/[0.05] to-fuchsia-500/[0.02] p-4 backdrop-blur-md">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-7 h-7 rounded-md bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
          <Sparkles size={12} />
        </span>
        <span className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold">
          My recommendation
        </span>
      </div>

      {summary && (
        <div className="text-[13px] text-zinc-200 leading-relaxed mb-3">
          {summary}
        </div>
      )}

      {findings.length > 0 && (
        <div className="mb-3 rounded-lg bg-white/[0.02] border border-white/5 p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
            Findings
          </div>
          <ul className="space-y-1">
            {findings.map((f, i) => (
              <li key={i} className="text-[12px] text-zinc-300 leading-relaxed flex items-start gap-1.5">
                <span className="text-violet-400 mt-1 shrink-0">•</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {alternatives.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
            Alternatives to consider
          </div>
          <ul className="space-y-1">
            {alternatives.map((a, i) => (
              <li key={i} className="text-[11.5px] text-zinc-400 leading-relaxed flex items-start gap-1.5">
                <span className="text-zinc-600 mt-1 shrink-0">·</span>
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
        <div className="text-[11px] text-zinc-400 flex-1">
          Would you like me to create a mission for this?
        </div>
        <button onClick={onDecline} disabled={busy}
                data-testid="recommendation-decline-btn"
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/5 transition disabled:opacity-40">
          Not yet
        </button>
        <button onClick={onAccept} disabled={busy}
                data-testid="recommendation-accept-btn"
                className="text-[11.5px] font-semibold px-3 py-1.5 rounded-md bg-violet-500 hover:bg-violet-400 text-white transition disabled:opacity-40 shadow-lg shadow-violet-500/20 flex items-center gap-1">
          <Rocket size={11} /> Create Mission
        </button>
      </div>
    </div>
  );
};


/* FindingsCard — shown in stage=analysis as Cortex scans/researches.
   Includes an animated indeterminate progress bar so the user can see
   the analysis is in progress (not just static findings). */
export const FindingsCard = ({ findings = [], live = true }) => {
  if (!findings.length) return null;
  return (
    <div data-testid="analysis-findings-card"
         className="rounded-xl border border-amber-500/15 bg-amber-500/[0.03] p-3">
      <div className="text-[10px] uppercase tracking-widest text-amber-300 font-semibold mb-2 flex items-center gap-1">
        <Activity size={10} className={live ? 'animate-pulse' : ''} /> What I'm finding
        {live && <span className="ml-auto normal-case tracking-normal text-amber-400/70 font-normal">analyzing…</span>}
      </div>
      {live && (
        <div data-testid="analysis-progress-bar"
             className="h-1 bg-amber-500/10 rounded-full overflow-hidden mb-2.5 relative">
          <div className="absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-amber-400 to-transparent rounded-full animate-[cv-indeterminate_1.4s_ease-in-out_infinite]" />
        </div>
      )}
      <ul className="space-y-1">
        {findings.map((f, i) => (
          <li key={i} className="text-[12px] text-zinc-300 leading-relaxed flex items-start gap-1.5">
            <span className="text-amber-400 mt-1 shrink-0">•</span>
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};
