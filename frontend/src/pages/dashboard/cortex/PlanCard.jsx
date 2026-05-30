import React from 'react';
import {
  CheckCircle2, AlertTriangle, Clock, DollarSign, TrendingUp,
  Sparkles, Play, Eye, Zap, ChevronRight,
} from 'lucide-react';

/* PlanCard — renders a Cortex recommendation as a structured plan tile.
   Surfaces: reasoning · confidence · expected outcome · cost · timeline · risk.
   Action buttons drive the autonomy-aware execute endpoint. */

const RISK_TONE = {
  low:    { label: 'LOW RISK',    cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  medium: { label: 'MEDIUM RISK', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  high:   { label: 'HIGH RISK',   cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
};

const TYPE_ICON = {
  launch_seller_mission:     Sparkles,
  run_bulk_outreach:         Zap,
  launch_retention_workflow: TrendingUp,
  launch_ads_campaign:       TrendingUp,
  generate_content_plan:     Sparkles,
  analyze_competitors:       Eye,
  find_opportunities:        Sparkles,
  improve_conversions:       TrendingUp,
  explain:                   Sparkles,
};

const ConfidenceBar = ({ value = 0 }) => {
  const pct = Math.max(0, Math.min(100, Math.round((Number(value) || 0) * 100)));
  const tone = pct >= 75 ? 'bg-emerald-400' : pct >= 50 ? 'bg-amber-400' : 'bg-rose-400';
  return (
    <div data-testid="plan-confidence" className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-semibold tabular-nums text-zinc-300 w-8 text-right">
        {pct}%
      </span>
    </div>
  );
};

const Stat = ({ label, value, icon: Icon, tone = 'text-zinc-300' }) => (
  <div className="flex flex-col gap-0.5">
    <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
      <Icon size={10} /> {label}
    </div>
    <div className={`text-[13px] font-semibold ${tone}`}>{value}</div>
  </div>
);

export const PlanCard = ({ rec, onPreview, onExecute, onAutomate, busy }) => {
  if (!rec) return null;
  const Icon = TYPE_ICON[rec.type] || Sparkles;
  const risk = RISK_TONE[String(rec.risk_level || 'medium').toLowerCase()] || RISK_TONE.medium;
  const confidence = rec.confidence != null ? rec.confidence
                    : rec.confidence_score != null ? rec.confidence_score
                    : 0.5;
  const cost = rec.estimated_cost_usd != null ? `$${Math.round(rec.estimated_cost_usd)}` : '—';
  const timeline = rec.estimated_timeline_days
    ? `${rec.estimated_timeline_days}d`
    : '—';
  const reasoning = Array.isArray(rec.reasoning) ? rec.reasoning
                   : rec.reasoning ? [rec.reasoning] : [];

  return (
    <div data-testid="cortex-plan-card"
         className="rounded-2xl border border-violet-500/20 bg-gradient-to-br from-violet-500/[0.06] to-fuchsia-500/[0.03] p-5 backdrop-blur-md">
      {/* Header */}
      <div className="flex items-start gap-3 mb-4">
        <span className="shrink-0 w-9 h-9 rounded-lg bg-violet-500/15 border border-violet-500/30 text-violet-300 flex items-center justify-center">
          <Icon size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold">
              Recommended Mission
            </span>
            <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border ${risk.cls}`}>
              {risk.label}
            </span>
          </div>
          <div className="text-[15px] font-semibold text-white leading-snug">
            {rec.title || 'Plan'}
          </div>
          {rec.summary && (
            <div className="text-[12px] text-zinc-400 mt-1 leading-relaxed">
              {rec.summary}
            </div>
          )}
        </div>
      </div>

      {/* Reasoning */}
      {reasoning.length > 0 && (
        <div data-testid="plan-reasoning" className="mb-4 rounded-lg bg-white/[0.02] border border-white/5 p-3">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1.5">
            Reasoning
          </div>
          <ul className="space-y-1">
            {reasoning.slice(0, 5).map((r, i) => (
              <li key={i} className="text-[12px] text-zinc-300 leading-relaxed flex items-start gap-1.5">
                <ChevronRight size={11} className="text-violet-400 mt-0.5 shrink-0" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-4 gap-3 mb-4 pb-4 border-b border-white/5">
        <Stat label="Confidence" value={
          <div className="-mt-0.5"><ConfidenceBar value={confidence} /></div>
        } icon={CheckCircle2} />
        <Stat label="Expected" value={rec.expected_outcome || '—'}
              icon={TrendingUp} tone="text-emerald-300" />
        <Stat label="Cost" value={cost} icon={DollarSign} tone="text-amber-300" />
        <Stat label="Timeline" value={timeline} icon={Clock} tone="text-cyan-300" />
      </div>

      {/* Autonomy hint */}
      {rec.autonomy_impact && (
        <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 mb-3">
          <AlertTriangle size={11} className="text-amber-400" />
          <span>{rec.autonomy_impact}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button onClick={onPreview} disabled={busy}
                data-testid="plan-preview-btn"
                className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 transition flex items-center gap-1.5 disabled:opacity-40">
          <Eye size={12} /> Preview
        </button>
        <button onClick={onExecute} disabled={busy}
                data-testid="plan-launch-btn"
                className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-violet-500 hover:bg-violet-400 text-white transition flex items-center gap-1.5 disabled:opacity-40 shadow-lg shadow-violet-500/20">
          <Play size={12} /> Launch Mission
        </button>
        <button onClick={onAutomate} disabled={busy}
                data-testid="plan-automate-btn"
                className="text-[12px] font-semibold px-3 py-2 rounded-lg border border-violet-500/40 hover:bg-violet-500/10 text-violet-300 transition flex items-center gap-1.5 disabled:opacity-40">
          <Zap size={12} /> Automate
        </button>
      </div>
    </div>
  );
};

export default PlanCard;
