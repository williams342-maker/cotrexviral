import React from 'react';
import { Clock3, Loader2 } from 'lucide-react';
import ApprovalStatusBadge from './ApprovalStatusBadge';

const statusColor = {
  success: 'text-emerald-300',
  error: 'text-rose-300',
  needs_approval: 'text-amber-300',
};

const AIRunHistory = ({ runs = [], loading, selectedId, onSelect }) => (
  <section className="rounded-2xl border border-white/10 bg-white/[0.035] overflow-hidden">
    <div className="px-4 py-3 border-b border-white/10 flex items-center gap-2">
      <Clock3 size={14} className="text-violet-300" />
      <h2 className="text-sm font-semibold text-white">Recent runs</h2>
    </div>
    <div className="max-h-[620px] overflow-y-auto">
      {loading && (
        <div className="p-8 flex justify-center"><Loader2 size={18} className="animate-spin text-violet-300" /></div>
      )}
      {!loading && runs.length === 0 && (
        <p className="p-6 text-sm text-zinc-500">No AI runs yet. Start one above.</p>
      )}
      {runs.map((run) => (
        <button
          key={run.run_id}
          onClick={() => onSelect(run)}
          className={`w-full text-left px-4 py-3 border-b border-white/5 transition ${
            selectedId === run.run_id ? 'bg-violet-500/15' : 'hover:bg-white/[0.04]'
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <span className="text-[13px] font-semibold text-zinc-100">{run.task_type.replace(/_/g, ' ')}</span>
            <span className={`text-[10px] uppercase font-bold ${statusColor[run.status] || 'text-zinc-400'}`}>
              {run.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-[11px] text-zinc-500">
              {[run.provider_used, run.model_used].filter(Boolean).join(' · ')}
            </span>
            <ApprovalStatusBadge status={run.approval_status} />
          </div>
        </button>
      ))}
    </div>
  </section>
);

export default AIRunHistory;
