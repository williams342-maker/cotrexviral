import React, { useState } from 'react';
import {
  Activity, ChevronUp, ChevronDown, Play, FileText, ListChecks,
  Bot, Loader2,
} from 'lucide-react';

/* ExecutionLog — bottom drawer showing live agent activity:
   launched missions, queued plans, drafts, agent ticks, etc.
   Collapsible to keep the chat focused. */

const KIND_STYLE = {
  auto_launched:        { icon: Play,       cls: 'text-emerald-300 bg-emerald-500/10' },
  queued_for_approval:  { icon: ListChecks, cls: 'text-amber-300 bg-amber-500/10' },
  draft_saved:          { icon: FileText,   cls: 'text-zinc-300 bg-zinc-500/10' },
  mission_launched:     { icon: Play,       cls: 'text-violet-300 bg-violet-500/10' },
  agent_tick:           { icon: Bot,        cls: 'text-cyan-300 bg-cyan-500/10' },
};

const fmtTime = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleDateString();
  } catch { return ''; }
};

export const ExecutionLog = ({ items = [], loading, onRefresh }) => {
  const [open, setOpen] = useState(false);

  return (
    <div data-testid="cortex-execution-log"
         className="rounded-2xl border border-white/5 bg-white/[0.02] backdrop-blur-md overflow-hidden">
      <button onClick={() => setOpen(!open)}
              data-testid="exec-log-toggle"
              className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-white/[0.02] transition">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-violet-300" />
          <span className="text-[12px] font-semibold text-zinc-200 uppercase tracking-wider">
            Execution Log
          </span>
          {loading && <Loader2 size={11} className="animate-spin text-zinc-500" />}
          {!loading && items.length > 0 && (
            <span className="text-[10px] text-zinc-500">· {items.length} recent</span>
          )}
        </div>
        {open ? <ChevronDown size={14} className="text-zinc-500" />
              : <ChevronUp size={14} className="text-zinc-500" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-2 border-t border-white/5 max-h-[40vh] overflow-y-auto">
          {!loading && items.length === 0 && (
            <div className="text-[11.5px] text-zinc-500 italic py-3">
              Nothing executing yet. Approve a plan above and Cortex will run it.
            </div>
          )}
          <div className="space-y-1.5">
            {items.map((item, i) => {
              const style = KIND_STYLE[item.kind] || KIND_STYLE.agent_tick;
              const Icon = style.icon;
              return (
                <div key={i} data-testid={`exec-log-item-${i}`}
                     className="flex items-start gap-2.5 rounded-lg bg-white/[0.02] border border-white/5 p-2.5">
                  <span className={`shrink-0 w-7 h-7 rounded-md flex items-center justify-center ${style.cls}`}>
                    <Icon size={11} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12px] font-medium text-zinc-200 truncate">
                      {item.title}
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 mt-0.5">
                      <span className="uppercase tracking-wider">{(item.kind || '').replace(/_/g, ' ')}</span>
                      {item.level != null && <span>· L{item.level}</span>}
                      {item.status && <span>· {item.status}</span>}
                      <span className="ml-auto">{fmtTime(item.created_at)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {onRefresh && (
            <button onClick={onRefresh} data-testid="exec-log-refresh"
                    className="mt-3 text-[10px] text-zinc-500 hover:text-zinc-300 uppercase tracking-wider font-semibold">
              Refresh
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default ExecutionLog;
