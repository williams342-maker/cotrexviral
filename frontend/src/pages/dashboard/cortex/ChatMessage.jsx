import React from 'react';
import axios from 'axios';
import { Brain, CheckCircle2, AlertTriangle, ChevronRight, RotateCw, Bug } from 'lucide-react';
import PlanCard from './PlanCard';
import MissionEventStream from './MissionEventStream';
import RecommendationBridgeCard from './RecommendationBridgeCard';
import {
  StagePill, ClarifyingQuestionsCard, RecommendationLiteCard,
  FindingsCard,
} from './StageComponents';
import { API } from '../../../context/AuthContext';

/* ChatMessage — Discovery-First aware.
   Renders different surfaces per stage:
     · discovery       → clarifying questions chips (no plan card)
     · analysis        → findings card (no plan card)
     · recommendation  → recommendation-lite card with [Create Mission] CTA
     · mission_proposal/execution → full plan card
     · analysis_complete / analysis_failed → embedded job CTAs (View / Retry / Debug) */

export const ChatMessage = ({ turn, onAction, busyId, isStale, onClarifyPick, onShortcutPick, discoveryBudgetUsed = 0 }) => {
  if (turn._kind === 'mission_events') {
    return <MissionEventStream missionTitle={turn.missionTitle}
                                  events={turn.events || []} />;
  }

  if (turn.role === 'user') {
    return (
      <div data-testid="chat-user-turn" className="flex justify-end mb-3">
        <div className="max-w-[80%] rounded-2xl rounded-tr-md bg-violet-500/15 border border-violet-500/30 px-4 py-2.5 text-[13.5px] text-zinc-100 leading-relaxed">
          {(turn.attachments && turn.attachments.length > 0) && (
            <div data-testid="chat-user-attachments"
                 className="flex flex-wrap gap-1.5 mb-2 -mt-0.5">
              {turn.attachments.map((a) => (
                <span key={a.id} data-testid={`chat-user-attachment-${a.id}`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-violet-500/20 border border-violet-400/30 text-[11px] text-violet-100">
                  <span className="opacity-70">📎</span>
                  <span className="truncate max-w-[180px]">{a.name}</span>
                </span>
              ))}
            </div>
          )}
          {turn.message}
        </div>
      </div>
    );
  }

  const stage = turn.stage || (turn.recommendation ? 'mission_proposal' : null);
  const showPlanCard = !!turn.recommendation;
  const showClarify = stage === 'discovery'
    && ((turn.clarifying_questions || []).length > 0
        || (turn.answer_shortcuts || []).length > 0);
  const showAnalysis = stage === 'analysis' && (turn.findings || []).length > 0;
  const showRecLite = stage === 'recommendation' && (
    turn.recommendation_summary
    || (turn.findings || []).length > 0
    || (turn.alternatives || []).length > 0
  );

  return (
    <div data-testid="chat-cortex-turn"
          data-turn-id={turn.id}
          className="flex items-start gap-3 mb-4">
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

        {/* Inline analysis-job CTAs — Cortex never silently completes a
            scan. View Report / Create Mission for completed; Retry +
            Debug for failed. Keeps everything in the conversation. */}
        {turn.kind === 'analysis_complete' && turn.job_id && (
          <AnalysisCompleteCard turn={turn} />
        )}
        {turn.kind === 'analysis_failed' && turn.job_id && (
          <AnalysisFailedCard turn={turn} />
        )}
        {/* Proactive Recommendation Bridge — posted as a SECOND turn
            after the metric-tile card. Renders the 4-part executive
            insight (Finding / Root Cause / Recommendation / Impact)
            with confidence meter + 3 CTAs. */}
        {turn.kind === 'recommendation_bridge' && turn.bridge && (
          <RecommendationBridgeCard turn={turn} />
        )}

        {showClarify && !isStale && (
          <ClarifyingQuestionsCard
            questions={turn.clarifying_questions || []}
            answerShortcuts={turn.answer_shortcuts || []}
            budgetUsed={discoveryBudgetUsed}
            onPick={onClarifyPick}
            onPickShortcut={onShortcutPick}
          />
        )}

        {/* Action-First inline summary cards — leads list, reports
            count, opportunities, missions — rendered when stage=action
            and a known action_kind is present. */}
        {turn.stage === 'action' && turn.action_data && (
          <ActionDataCard kind={turn.action_kind} data={turn.action_data} />
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


/* ActionDataCard — inline summary rendered for stage=action turns.
   Mirrors the consultative-summary visualization in Cortex's prose
   reply: highlight stats, top categories/items, plus a Deep Link
   button that drops the user into the relevant dashboard surface. */
function ActionDataCard({ kind, data }) {
  if (!data || !kind) return null;
  const deepLink = data.deep_link;

  // leads_summary: total + category chips + quality tiles
  if (kind === 'show_leads' && data.kind === 'leads_summary' && data.total > 0) {
    return (
      <div data-testid="action-card-leads"
            className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
        <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-2 flex items-center gap-1.5">
          {data.total} leads · top categories
        </div>
        {(data.categories || []).length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {data.categories.map((c, i) => (
              <span key={i}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/10 text-zinc-200">
                {c.count} <span className="text-zinc-500">{c.name}</span>
              </span>
            ))}
          </div>
        )}
        {data.quality && (
          <div className="grid grid-cols-3 gap-1.5">
            {[['high', 'High', 'text-emerald-200'],
                ['review', 'Review', 'text-amber-200'],
                ['low', 'Low', 'text-zinc-400']].map(([key, label, cls]) => (
              <div key={key} className="text-center bg-white/[0.03] rounded-md py-1.5">
                <div className={`text-[14px] font-bold tabular-nums leading-none ${cls}`}>
                  {data.quality[key] || 0}
                </div>
                <div className="text-[9px] text-zinc-500 mt-0.5 uppercase tracking-wider">
                  {label}
                </div>
              </div>
            ))}
          </div>
        )}
        {deepLink && (
          <a href={deepLink}
              data-testid="action-card-leads-deep-link"
              className="mt-2 inline-flex items-center gap-1 text-[10.5px] font-semibold text-cyan-200 hover:text-white">
            Open Leads Manager <ChevronRight size={9} />
          </a>
        )}
      </div>
    );
  }

  // reports_summary
  if (kind === 'show_reports' && data.recent?.length) {
    return (
      <div data-testid="action-card-reports"
            className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
        <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-2">
          {data.total} reports · most recent
        </div>
        <div className="space-y-1">
          {data.recent.slice(0, 5).map((r) => (
            <div key={r.id} className="flex items-center justify-between text-[11.5px] py-1 px-1.5 rounded hover:bg-white/[0.04]">
              <span className="text-zinc-200 truncate">{r.url || r.type}</span>
              <span className="text-zinc-500 ml-2 shrink-0">{r.type}</span>
            </div>
          ))}
        </div>
        {deepLink && (
          <a href={deepLink}
              data-testid="action-card-reports-deep-link"
              className="mt-2 inline-flex items-center gap-1 text-[10.5px] font-semibold text-cyan-200 hover:text-white">
            Open Reports <ChevronRight size={9} />
          </a>
        )}
      </div>
    );
  }

  // opportunities_summary
  if (kind === 'show_opportunities' && data.top?.length) {
    return (
      <div data-testid="action-card-opportunities"
            className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
        <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-2">
          Top opportunities
        </div>
        <div className="space-y-1">
          {data.top.map((o, i) => (
            <div key={i} className="text-[11.5px] py-1">
              <div className="text-zinc-200 leading-tight">{o.title}</div>
              {o.subtitle && (
                <div className="text-zinc-500 text-[10px] truncate">{o.subtitle}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // missions_summary
  if (kind === 'show_missions' && data.missions?.length) {
    return (
      <div data-testid="action-card-missions"
            className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.04] p-3">
        <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-2">
          {data.total} active missions
        </div>
        <div className="space-y-1">
          {data.missions.slice(0, 6).map((m) => (
            <div key={m.id} className="flex items-center justify-between text-[11.5px] py-1 px-1.5 rounded hover:bg-white/[0.04]">
              <span className="text-zinc-200 truncate">{m.title}</span>
              <span className="text-zinc-500 ml-2 shrink-0">L{m.autonomy_level ?? '–'}</span>
            </div>
          ))}
        </div>
        {deepLink && (
          <a href={deepLink}
              data-testid="action-card-missions-deep-link"
              className="mt-2 inline-flex items-center gap-1 text-[10.5px] font-semibold text-cyan-200 hover:text-white">
            Open Missions <ChevronRight size={9} />
          </a>
        )}
      </div>
    );
  }

  // run_scan_started — show a tiny "tracking on rail" callout
  if (kind === 'run_scan_started' && data.job_id) {
    return (
      <div data-testid="action-card-scan-started"
            className="rounded-xl border border-violet-500/25 bg-violet-500/[0.05] p-3 flex items-center gap-2">
        <div className="flex-1 text-[11.5px] text-zinc-300">
          Tracking on the right rail · Job <span className="font-mono text-violet-300">#{data.job_id.slice(0, 8)}</span>
        </div>
      </div>
    );
  }

  return null;
}


/* AnalysisCompleteCard — embedded CTAs inside Cortex's chat bubble
   when an `analysis_jobs` row finishes. Reads the kind-specific
   action labels off the turn metadata (view_label / create_label).
   Each button references the real job_id so the user can correlate
   with the Active Work rail. */
function AnalysisCompleteCard({ turn }) {
  const metrics = turn.metrics || {};
  const view = async () => {
    try {
      await axios.post(`${API}/cortex/analysis-jobs/${turn.job_id}/mark-reviewed`,
                        {}, { withCredentials: true });
    } catch (_e) { /* */ }
    // Naive: open reports list. Per-job result_link is on the rail card.
    window.open('/dashboard/reports', '_self');
  };
  const createMission = async () => {
    try {
      const r = await axios.post(
        `${API}/cortex/analysis-jobs/${turn.job_id}/create-mission`,
        {}, { withCredentials: true });
      window.location.href = `/dashboard/cortex/${r.data.mission_id}`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('create mission from chat failed', e?.response?.data);
    }
  };
  const optimizeAuto = async () => {
    try {
      const r = await axios.post(
        `${API}/cortex/analysis-jobs/${turn.job_id}/optimize`,
        {}, { withCredentials: true });
      window.location.href = `/dashboard/cortex/${r.data.mission_id}?tab=changes`;
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('optimize auto failed', e?.response?.data);
    }
  };
  // Optimize Automatically lives behind job_type. seo_scan only today —
  // matches the backend gate at /analysis-jobs/{id}/optimize.
  const optimizeEnabled = (turn.job_type || '') === 'seo_scan';
  return (
    <div data-testid={`chat-analysis-complete-${turn.job_id}`}
          className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.05] p-3 mt-1">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-emerald-300 font-semibold mb-1.5">
        <CheckCircle2 size={10} /> Analysis Complete · Job #{(turn.job_id || '').slice(0, 8)}
      </div>
      {Object.keys(metrics).length > 0 && (
        <div className="grid grid-cols-3 gap-1.5 mb-2">
          {Object.entries(metrics).slice(0, 3).map(([k, v]) => (
            <div key={k} className="text-center bg-white/[0.04] rounded-md py-1.5 px-1">
              <div className="text-[14px] text-emerald-200 font-bold tabular-nums leading-none">
                {typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v}
              </div>
              <div className="text-[9px] text-zinc-500 mt-0.5 uppercase tracking-wider truncate">
                {k.replace(/_/g, ' ')}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <button onClick={view}
                data-testid={`chat-analysis-view-${turn.job_id}`}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-500/30 transition flex items-center gap-1">
          View Report <ChevronRight size={9} />
        </button>
        <button onClick={createMission}
                data-testid={`chat-analysis-create-${turn.job_id}`}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition">
          Create Mission
        </button>
        <button onClick={optimizeAuto} disabled={!optimizeEnabled}
                title={optimizeEnabled
                  ? 'Auto-prepare prioritized fixes for review (L3)'
                  : 'Available after completion'}
                data-testid={`chat-analysis-optimize-${turn.job_id}`}
                className={`text-[10.5px] font-semibold px-2.5 py-1 rounded-md transition flex items-center gap-1 ${
                  optimizeEnabled
                    ? 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-200 border border-amber-500/30'
                    : 'bg-white/5 text-zinc-500 border border-white/10 opacity-60 cursor-not-allowed'
                }`}>
          ⚡ Optimize Automatically
        </button>
      </div>
    </div>
  );
}


/* AnalysisFailedCard — failure CTAs inside the Cortex chat bubble.
   Retry re-fires the runner via the analysis-jobs endpoint; Debug
   opens the debug pane scoped to the failed job. */
function AnalysisFailedCard({ turn }) {
  const err = (turn.metrics?.error || 'Unknown error');
  const retry = async () => {
    try {
      await axios.post(`${API}/cortex/analysis-jobs/${turn.job_id}/retry`,
                        {}, { withCredentials: true });
    } catch (_e) { /* */ }
  };
  return (
    <div data-testid={`chat-analysis-failed-${turn.job_id}`}
          className="rounded-xl border border-rose-500/30 bg-rose-500/[0.05] p-3 mt-1">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-rose-300 font-semibold mb-1.5">
        <AlertTriangle size={10} /> Analysis Failed · Job #{(turn.job_id || '').slice(0, 8)}
      </div>
      <div className="text-[11.5px] text-rose-100 leading-snug mb-2">
        <span className="text-zinc-500">Reason:</span> {err}
      </div>
      <div className="flex gap-1.5">
        <button onClick={retry}
                data-testid={`chat-analysis-retry-${turn.job_id}`}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded-md bg-rose-500/15 hover:bg-rose-500/25 text-rose-200 border border-rose-500/30 transition flex items-center gap-1">
          <RotateCw size={9} /> Retry
        </button>
        <button onClick={() => window.open('/dashboard?debug=1&job=' + turn.job_id, '_self')}
                data-testid={`chat-analysis-debug-${turn.job_id}`}
                className="text-[10.5px] font-semibold px-2.5 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 border border-white/10 transition flex items-center gap-1">
          <Bug size={9} /> Debug
        </button>
      </div>
    </div>
  );
}
