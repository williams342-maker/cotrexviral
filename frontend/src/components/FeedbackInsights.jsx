import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Trophy, Sparkles, ChevronDown, ChevronUp, AlertTriangle, ArrowUpRight } from 'lucide-react';
import { API } from '../context/AuthContext';

/* Reusable callout that surfaces the user's feedback-loop insights:
   what hooks WON (top engagement) and which patterns FAILED (bottom
   engagement). Drives the "why this hook is recommended" moment on
   Nova's drafts and on the Compose page.

   Two variants:
     compact = true  → a single "Top winning hook" line + expand toggle
                       (good for tight rails like AgentWorkspace).
     compact = false → full card with winners + failed patterns
                       (good for full-width contexts like Compose).

   Auto-hides when both lists are empty so brand-new users don't see a
   "no data yet" panel. Falls back gracefully on network error. */

const FeedbackInsights = ({ compact = false, limit = 3, testid = 'feedback-insights', theme = 'dark', onUseHook = null }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(!compact);

  // Theme-aware text classes — dark variant for AgentWorkspace, light
  // for Compose. Emerald/rose stay the same (work on both bg's).
  const t = theme === 'light' ? {
    cardBg:    'bg-emerald-50 border-emerald-200',
    bodyText:  'text-zinc-700',
    mutedText: 'text-zinc-500',
    subText:   'text-zinc-400',
    accentChip:'bg-emerald-100 border-emerald-200 text-emerald-700',
    divider:   'border-emerald-200',
    losersBg:  'text-rose-700/90',
    losersItalic: 'text-zinc-500',
  } : {
    cardBg:    'bg-emerald-500/[0.04] border-emerald-500/25',
    bodyText:  'text-zinc-300',
    mutedText: 'text-zinc-500',
    subText:   'text-zinc-400',
    accentChip:'bg-emerald-500/15 border-emerald-500/30 text-emerald-300',
    divider:   'border-emerald-500/15',
    losersBg:  'text-rose-300/90',
    losersItalic: 'text-zinc-400',
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/feedback/insights?limit=${limit}`, { withCredentials: true });
        if (!cancelled) setData(r.data);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [limit]);

  if (loading || !data) return null;
  const winners = data.winning_hooks || [];
  const losers = data.failed_patterns || [];
  if (winners.length === 0 && losers.length === 0) return null;

  const top = winners[0];
  const topRate = top ? Math.round((top.meta?.engagement_rate || 0) * 1000) / 10 : 0;
  const topPlat = top?.meta?.platform || '';

  // Compact form: one-line summary + caret expand.
  if (compact) {
    return (
      <div data-testid={testid} className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] p-2.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center gap-2 text-left"
          data-testid={`${testid}-toggle`}
        >
          <span className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-300 shrink-0">
            <Trophy size={11} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[9px] uppercase tracking-widest text-emerald-300 font-bold">Top winning hook</div>
            {top ? (
              <div className="text-[11px] text-zinc-300 truncate">
                <span className="text-emerald-300 tabular-nums">{topRate}%</span>
                <span className="text-zinc-500"> · {topPlat}</span>
                <span className="text-zinc-400"> · {(top.text || '').replace(/^\[.+?\]\s*/, '').slice(0, 70)}</span>
              </div>
            ) : (
              <div className="text-[11px] text-zinc-500">No winners yet — keep publishing.</div>
            )}
          </div>
          {open ? <ChevronUp size={12} className="text-zinc-500" /> : <ChevronDown size={12} className="text-zinc-500" />}
        </button>

        {open && (
          <div className="mt-2 space-y-1.5 pl-8" data-testid={`${testid}-expanded`}>
            {winners.slice(0, 3).map((w) => (
              <div key={w.id} className="text-[10px] text-zinc-400 leading-snug">
                <span className="text-emerald-300 tabular-nums">{Math.round((w.meta?.engagement_rate || 0) * 1000) / 10}%</span>
                <span className="text-zinc-500"> · </span>
                <span className="text-zinc-300">{(w.text || '').replace(/^\[.+?\]\s*/, '').replace(/\s*\(engagement.*$/, '').slice(0, 100)}</span>
              </div>
            ))}
            {losers.length > 0 && (
              <div className="text-[9px] text-rose-300/80 mt-1.5 italic flex items-center gap-1">
                <AlertTriangle size={9} /> Avoid {losers.length} pattern{losers.length === 1 ? '' : 's'} that recently underperformed.
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Full form: emerald winners card + amber failed-patterns line below.
  return (
    <div data-testid={testid} className={`rounded-xl border p-3.5 ${t.cardBg}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-7 h-7 rounded-md flex items-center justify-center ${t.accentChip} border`}>
          <Sparkles size={13} />
        </span>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-emerald-600 font-bold">What's working for you</div>
          <div className={`text-[11px] ${t.subText}`}>Patterns Nova will lean on when she drafts your next post.</div>
        </div>
      </div>
      {winners.length === 0 ? (
        <div className={`text-[11px] italic ${t.mutedText}`}>No winning hooks yet — publish a few posts and the feedback loop will surface them automatically.</div>
      ) : (
        <ul className="space-y-1.5">
          {winners.slice(0, limit).map((w) => {
            const cleanText = (w.text || '').replace(/^\[.+?\]\s*/, '').replace(/\s*\(engagement.*$/, '');
            return (
              <li key={w.id} className={`flex items-start gap-2 text-xs ${t.bodyText} group`} data-testid={`${testid}-winner-${w.id}`}>
                <span className="shrink-0 text-emerald-600 font-semibold tabular-nums min-w-[42px]">
                  {Math.round((w.meta?.engagement_rate || 0) * 1000) / 10}%
                </span>
                <span className={`text-[10px] uppercase tracking-wider min-w-[58px] ${t.mutedText}`}>
                  {w.meta?.platform || '—'}
                </span>
                <span className="flex-1 leading-snug">{cleanText}</span>
                {onUseHook && (
                  <button
                    type="button"
                    onClick={() => onUseHook(cleanText, w)}
                    aria-label={`Use this winning hook as your topic: ${cleanText.slice(0, 80)}`}
                    className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded border opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus:opacity-100 focus:outline-none focus:ring-2 transition-opacity flex items-center gap-1 ${
                      theme === 'light'
                        ? 'border-emerald-300 text-emerald-700 hover:bg-emerald-100 focus:ring-emerald-400/40'
                        : 'border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/15 focus:ring-emerald-500/40'
                    }`}
                    data-testid={`${testid}-use-${w.id}`}
                    title="Use this hook as your topic"
                  >
                    Use <ArrowUpRight size={9} />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {losers.length > 0 && (
        <div className={`mt-3 pt-2.5 border-t text-[10px] flex items-center gap-1.5 ${t.divider} ${t.losersBg}`} data-testid={`${testid}-losers`}>
          <AlertTriangle size={11} />
          Avoid <span className="font-semibold">{losers.length}</span> recent pattern{losers.length === 1 ? '' : 's'} that underperformed —
          <span className={`italic ml-1 truncate ${t.losersItalic}`}>{(losers[0]?.text || '').replace(/^\[.+?\]\s*/, '').replace(/\s*\(engagement.*$/, '').slice(0, 80)}</span>
        </div>
      )}
    </div>
  );
};

export default FeedbackInsights;
