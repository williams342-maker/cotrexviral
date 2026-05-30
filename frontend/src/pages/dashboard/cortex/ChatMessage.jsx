import React from 'react';
import { Brain } from 'lucide-react';
import PlanCard from './PlanCard';
import MissionEventStream from './MissionEventStream';

/* ChatMessage — renders a single turn (user, cortex, or mission-events).
   Extracted from CommandCenter.jsx for clarity + testability. */

export const ChatMessage = ({ turn, onAction, busyId, isStale }) => {
  // Mission-events timeline (live updates inline in the thread).
  if (turn._kind === 'mission_events') {
    return (
      <MissionEventStream missionTitle={turn.missionTitle}
                            events={turn.events || []} />
    );
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

  // Cortex turn (with optional inline plan card).
  return (
    <div data-testid="chat-cortex-turn" className="flex items-start gap-3 mb-4">
      <span className="shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
        <Brain size={14} className="text-white" />
      </span>
      <div className="flex-1 min-w-0 space-y-3">
        <div className="text-[10px] uppercase tracking-widest font-semibold text-violet-300">
          Cortex
          {isStale && (
            <span className="text-zinc-500 normal-case tracking-normal ml-2">
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
        {turn.recommendation && (
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
