import React from 'react';
import { Brain } from 'lucide-react';
import PlanCard from './PlanCard';
import MissionEventStream from './MissionEventStream';
import {
  StagePill, ClarifyingQuestionsCard, RecommendationLiteCard,
  FindingsCard,
} from './StageComponents';

/* ChatMessage — Discovery-First aware.
   Renders different surfaces per stage:
     · discovery       → clarifying questions chips (no plan card)
     · analysis        → findings card (no plan card)
     · recommendation  → recommendation-lite card with [Create Mission] CTA
     · mission_proposal/execution → full plan card */

export const ChatMessage = ({ turn, onAction, busyId, isStale, onClarifyPick }) => {
  if (turn._kind === 'mission_events') {
    return <MissionEventStream missionTitle={turn.missionTitle}
                                  events={turn.events || []} />;
  }

  if (turn.role === 'user') {
    return (
      <div data-testid="chat-user-turn" className="flex justify-end mb-3">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-violet-500/15 border border-violet-500/30 px-4 py-2.5 text-[13.5px] text-zinc-100 leading-relaxed">
          {turn.message}
        </div>
      </div>
    );
  }

  const stage = turn.stage || (turn.recommendation ? 'mission_proposal' : null);
  const showPlanCard = !!turn.recommendation;
  const showClarify = stage === 'discovery' && (turn.clarifying_questions || []).length > 0;
  const showAnalysis = stage === 'analysis' && (turn.findings || []).length > 0;
  const showRecLite = stage === 'recommendation' && (
    turn.recommendation_summary
    || (turn.findings || []).length > 0
    || (turn.alternatives || []).length > 0
  );

  return (
    <div data-testid="chat-cortex-turn" className="flex items-start gap-3 mb-4">
      <span className="shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
        <Brain size={14} className="text-white" />
      </span>
      <div className="flex-1 min-w-0 space-y-3">
        <div className="flex items-center gap-2">
          <div className="text-[10px] uppercase tracking-widest font-semibold text-violet-300">
            Cortex
          </div>
          <StagePill stage={stage} />
          {isStale && (
            <span className="text-zinc-500 text-[10px] normal-case tracking-normal">
              · superseded
            </span>
          )}
        </div>

        {turn.message && (
          <div className={`text-[13.5px] leading-relaxed whitespace-pre-line ${
            isStale ? 'text-zinc-500' : 'text-zinc-200'
          }`}>
            {turn.message}
          </div>
        )}

        {showClarify && !isStale && (
          <ClarifyingQuestionsCard questions={turn.clarifying_questions}
                                       onPick={onClarifyPick} />
        )}

        {showAnalysis && !isStale && (
          <FindingsCard findings={turn.findings} />
        )}

        {showRecLite && !isStale && (
          <RecommendationLiteCard
            summary={turn.recommendation_summary}
            findings={turn.findings || []}
            alternatives={turn.alternatives || []}
            busy={busyId === turn.id}
            onAccept={() => onAction('accept-recommendation', turn)}
            onDecline={() => onAction('decline-recommendation', turn)}
          />
        )}

        {showPlanCard && (
          <PlanCard rec={turn.recommendation}
                    memoryHint={turn.memoryHint}
                    busy={busyId === turn.id}
                    initiallyMinimized={isStale && !turn._dismissed}
                    dismissed={turn._dismissed || isStale}
                    onPreview={() => onAction('preview', turn)}
                    onExecute={() => onAction('execute', turn)}
                    onAutomate={() => onAction('automate', turn)}
                    onCancel={(onDone) => onAction('cancel', turn, onDone)}
                    onEmail={() => onAction('email', turn)} />
        )}
      </div>
    </div>
  );
};

export default ChatMessage;
