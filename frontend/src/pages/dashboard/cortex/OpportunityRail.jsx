import React from 'react';
import { Sparkles, AlertCircle, ChevronRight, Loader2, TrendingUp, AlertTriangle } from 'lucide-react';
import ActiveMissionRail from './ActiveMissionRail';
import ActiveWorkRail from './ActiveWorkRail';
import OptimizationStatus from './OptimizationStatus';
import ExecutiveInsights from './ExecutiveInsights';
import CortexThinkingCard from './CortexThinkingCard';

/* OpportunityRail — right sidebar showing AI-surfaced opportunities,
   recommended actions, and recent discoveries. Each card is a
   one-click prompt that fires into Cortex's chat composer. */

const URGENCY = {
  now:       { label: 'ACT NOW',   cls: 'text-rose-300 bg-rose-500/15 border-rose-500/30' },
  this_week: { label: 'THIS WEEK', cls: 'text-amber-300 bg-amber-500/15 border-amber-500/30' },
  monitor:   { label: 'MONITOR',   cls: 'text-zinc-300 bg-zinc-500/15 border-zinc-500/30' },
};

export const OpportunityRail = ({
  opportunities = [], loading, onPrompt, strategy,
  activeMissions = [], missionsLoading = false, onOpenMission, onMissionCancelled,
  onDiscussFinding, onLaunchScan,
  thinkingTurn, onScrollToTurn,
}) => {
  return (
    <aside data-testid="cortex-opportunity-rail"
           className="h-full flex flex-col gap-4 overflow-y-auto pr-1">
      {/* Live "Cortex is analyzing" card — surfaces the in-flight
          conversational analysis stage into the right rail so the user
          sees the progress bar regardless of chat scroll position. */}
      {thinkingTurn && (
        <CortexThinkingCard turn={thinkingTurn}
                              onScrollToTurn={onScrollToTurn} />
      )}

      {/* Autonomous monitoring status — TOP (the headline) */}
      <OptimizationStatus onDiscuss={onDiscussFinding} />

      {/* Active missions */}
      <ActiveMissionRail missions={activeMissions} loading={missionsLoading}
                            onOpenDetails={onOpenMission}
                            onCancelled={onMissionCancelled} />

      {/* Active Work — long-running analyses with real job IDs */}
      <ActiveWorkRail onLaunchScan={onLaunchScan} />

      {/* Executive Insights — recent Cortex Recommendation Bridges
          sorted by confidence × recency. The single source of truth
          for "what should I do next?" across all completed analyses. */}
      <ExecutiveInsights />

      {/* Strategic memory header */}
      {(strategy?.summary || (strategy?.goals && strategy.goals.length > 0)) && (
        <div data-testid="cortex-strategy-summary"
             className="rounded-xl border border-violet-500/20 bg-violet-500/[0.04] p-3">
          <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold mb-1.5 flex items-center gap-1">
            <Sparkles size={10} /> Strategic Memory
          </div>
          {strategy?.summary && (
            <p className="text-[12px] text-zinc-300 leading-relaxed mb-2">
              {strategy.summary}
            </p>
          )}
          {strategy?.goals?.length > 0 && (
            <div>
              <div className="text-[10px] text-zinc-500 font-semibold mb-1">Active goals</div>
              <ul className="space-y-0.5">
                {strategy.goals.slice(0, 4).map((g, i) => (
                  <li key={i} className="text-[11px] text-zinc-400 flex items-start gap-1">
                    <span className="text-violet-400 mt-0.5">•</span>
                    <span>{g}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Opportunities */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-2 flex items-center gap-1">
          <TrendingUp size={10} /> AI Opportunities
          {loading && <Loader2 size={10} className="animate-spin ml-1" />}
        </div>

        {!loading && opportunities.length === 0 && (
          <div className="text-[11px] text-zinc-500 italic">
            Cortex is scanning. Opportunities will surface here as your data grows.
          </div>
        )}

        <div className="space-y-2">
          {opportunities.map((opp, i) => {
            const urg = URGENCY[opp.urgency] || URGENCY.monitor;
            const detected = opp.detected_by_cortex === true;
            const borderCls = detected
              ? 'border-amber-500/25 hover:border-amber-500/50 bg-amber-500/[0.04] hover:bg-amber-500/[0.06]'
              : 'border-white/5 hover:border-violet-500/30 bg-white/[0.02] hover:bg-white/[0.04]';
            return (
              <button key={opp.id || i} onClick={() => onPrompt?.(opp)}
                      data-testid={`opportunity-${i}`}
                      className={`w-full text-left rounded-xl border ${borderCls} p-3 transition group`}>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="flex items-start gap-1.5 flex-1 min-w-0">
                    {detected && (
                      <AlertTriangle size={10} className="text-amber-300 mt-1 shrink-0" />
                    )}
                    <div className="text-[12.5px] font-semibold text-white leading-tight">
                      {opp.title || opp.type}
                    </div>
                  </div>
                  {detected ? (
                    <span data-testid="opp-detected-tag"
                          className="shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-amber-500/15 text-amber-300 border-amber-500/30">
                      DETECTED
                    </span>
                  ) : (
                    <span className={`shrink-0 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${urg.cls}`}>
                      {urg.label}
                    </span>
                  )}
                </div>
                {(opp.subtitle || opp.summary) && (
                  <div className="text-[11px] text-zinc-500 leading-relaxed line-clamp-2">
                    {opp.subtitle || opp.summary}
                  </div>
                )}
                {(opp.expected_outcome || opp.confidence != null) && (
                  <div className="flex items-center gap-2 mt-1.5 text-[10px]">
                    {opp.expected_outcome && (
                      <span className="text-emerald-400">{opp.expected_outcome}</span>
                    )}
                    {opp.confidence != null && (
                      <span className="text-zinc-500">
                        · {Math.round(opp.confidence * 100)}% confidence
                      </span>
                    )}
                  </div>
                )}
                <div className="text-[10px] text-violet-300 mt-1 opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition">
                  {detected ? 'Discuss with Cortex' : 'Ask Cortex about this'} <ChevronRight size={9} />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Quick-prompts — starter ideas if conversation is empty */}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-2 flex items-center gap-1">
          <AlertCircle size={10} /> Try Asking
        </div>
        <div className="space-y-1.5">
          {[
            "Recruit 50 woodworking sellers",
            "What are my top growth opportunities right now?",
            "Find sellers at risk of churning",
            "Build a content plan for next week",
          ].map((q, idx) => (
            <button key={q} onClick={() => onPrompt?.({ prompt: q })}
                    data-testid={`starter-prompt-${idx}`}
                    className="w-full text-left text-[11.5px] text-zinc-400 hover:text-white px-2.5 py-1.5 rounded-md bg-white/[0.02] hover:bg-white/[0.05] border border-white/5 transition">
              {q}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
};

export default OpportunityRail;
