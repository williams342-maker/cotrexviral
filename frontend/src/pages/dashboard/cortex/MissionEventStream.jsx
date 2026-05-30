import React from 'react';
import { Radio, Mail, Compass, Filter, Send, MessageCircle } from 'lucide-react';

/* MissionEventStream — renders live mission updates as an inline
   chat-thread entry. Looks like a system-style timeline. */

const LABEL_ICON = (label = '') => {
  const l = String(label).toLowerCase();
  if (l.includes('discover')) return Compass;
  if (l.includes('qualif')) return Filter;
  if (l.includes('outreach') || l.includes('sent') || l.includes('email')) return Send;
  if (l.includes('reply') || l.includes('interested') || l.includes('conversation')) return MessageCircle;
  if (l.includes('open') || l.includes('click')) return Mail;
  return Radio;
};

const fmtTime = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
};

export const MissionEventStream = ({ missionTitle, events = [] }) => {
  if (!events.length) return null;
  return (
    <div data-testid="mission-event-stream"
         className="my-3 rounded-xl border border-violet-500/15 bg-violet-500/[0.03] p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-violet-300 font-semibold mb-2">
        <Radio size={10} className="animate-pulse" /> Live updates
        {missionTitle && (
          <span className="text-zinc-500 normal-case tracking-normal font-normal">
            · {missionTitle}
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {events.slice(0, 8).map((ev, i) => {
          const Icon = LABEL_ICON(ev.label);
          return (
            <div key={ev.id || i} data-testid={`mission-event-${i}`}
                  className="flex items-start gap-2 text-[11.5px]">
              <span className="shrink-0 text-zinc-600 tabular-nums w-12">
                [{fmtTime(ev.created_at)}]
              </span>
              <Icon size={10} className="text-violet-300 mt-1 shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="text-zinc-200 capitalize">{ev.label}</span>
                {ev.body && (
                  <span className="text-zinc-500"> — {ev.body}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default MissionEventStream;
