import React from 'react';
import { Braces, ShieldCheck } from 'lucide-react';
import ApprovalStatusBadge from './ApprovalStatusBadge';
import AutonomyLevelBadge from './AutonomyLevelBadge';
import CostEstimateBadge from './CostEstimateBadge';

const AIRunDetail = ({ run }) => {
  if (!run) {
    return (
      <section className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center text-sm text-zinc-500">
        Select a run to inspect its structured output.
      </section>
    );
  }
  const tokens = run.tokens || {
    input: run.input_tokens || 0,
    output: run.output_tokens || 0,
    total: run.total_tokens || 0,
  };
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] overflow-hidden">
      <div className="px-5 py-4 border-b border-white/10 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Braces size={15} className="text-cyan-300" />
            <h2 className="text-base font-semibold text-white">{run.task_type?.replace(/_/g, ' ')}</h2>
          </div>
          <p className="text-[11px] text-zinc-500 mt-1 font-mono">{run.run_id}</p>
        </div>
        <span className={`text-xs font-bold uppercase ${
          run.status === 'success' ? 'text-emerald-300' :
          run.status === 'error' ? 'text-rose-300' : 'text-amber-300'
        }`}>{run.status?.replace(/_/g, ' ')}</span>
      </div>

      <div className="p-5 space-y-5">
        <div className="flex flex-wrap gap-2">
          <AutonomyLevelBadge level={run.autonomy_level} />
          <CostEstimateBadge cost={run.cost_estimate} />
          <ApprovalStatusBadge status={run.approval_status} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            ['Provider', run.provider_used],
            ['Model', run.model_used],
            ['Prompt', run.prompt_version],
            ['Input tokens', tokens.input],
            ['Output tokens', tokens.output],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-white/5 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
              <div className="text-xs text-zinc-200 mt-1 break-words">{value ?? '—'}</div>
            </div>
          ))}
        </div>

        {run.error_message && (
          <div className="rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-200">
            {run.error_message}
          </div>
        )}

        <div>
          <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-zinc-300">
            <ShieldCheck size={13} className="text-violet-300" />
            Structured result
          </div>
          <pre className="rounded-xl border border-white/5 bg-black/30 p-4 text-[12px] leading-relaxed text-cyan-100 overflow-auto max-h-[420px] whitespace-pre-wrap">
            {JSON.stringify(run.result || {}, null, 2)}
          </pre>
        </div>
      </div>
    </section>
  );
};

export default AIRunDetail;
