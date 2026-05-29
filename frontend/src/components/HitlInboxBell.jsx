/* HitlInboxBell — floating bottom-right bell + popover that shows
   currently-paused HITL runs in real time. Mounted once at the
   dashboard layout level so every dashboard route sees the same
   inbox without re-subscribing to the WebSocket.

   States:
     • Hidden when there are zero paused runs and the WS is connected
       (no-noise default).
     • Visible amber bell with count badge when ≥1 paused run.
     • Click → popover with per-run rows: brief preview, age, jump-to
       Command Center CTA (deep-link with `?expand_run=<id>`).
     • Tiny dot indicator turns red if the WS disconnects, so users
       know they might be missing updates.

   Why a bell, not the sidebar?
     The sidebar is dense. The inbox needs to be glanceable from any
     dashboard route. A bottom-right bell with a count badge is the
     standard pattern (Slack, Linear, GitHub) and stays out of the way
     until it has something to say. */
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, X, ArrowUpRight, Loader2, WifiOff } from 'lucide-react';
import useHitlInbox from '../hooks/useHitlInbox';
import { useToast } from '../hooks/use-toast';

function relativeAge(iso) {
  if (!iso) return '';
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '';
  const secs = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86_400) return `${Math.floor(secs / 3600)}h`;
  return `${Math.floor(secs / 86_400)}d`;
}

const HitlInboxBell = () => {
  const { paused, connected, lastEvent } = useHitlInbox();
  const [open, setOpen] = useState(false);
  const popoverRef = useRef(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const lastEventIdRef = useRef(null);

  // Pop a toast whenever a NEW paused run arrives (don't toast on
  // initial snapshot — the bell badge is enough for at-rest signaling).
  useEffect(() => {
    if (!lastEvent) return;
    const sig = `${lastEvent.event}:${lastEvent.data?.run_id}:${lastEvent.at}`;
    if (sig === lastEventIdRef.current) return;
    lastEventIdRef.current = sig;
    if (lastEvent.event === 'hitl_paused') {
      toast({
        title: 'A run is awaiting your approval',
        description: (lastEvent.data?.brief || '').slice(0, 110) + '…',
      });
    } else if (lastEvent.event === 'hitl_resolved') {
      const decision = lastEvent.data?.decision || 'resolved';
      toast({
        title: decision === 'approved' ? 'Run approved & published path complete' : 'Run rejected — summary ready',
        description: 'Activity feed updated.',
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  // Don't render at all if there's nothing and we're connected — keeps
  // the dashboard quiet when there's no signal.
  const hasPaused = paused.length > 0;
  if (!hasPaused && connected) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50" ref={popoverRef} data-testid="hitl-inbox-bell">
      {/* Popover */}
      {open && (
        <div className="absolute bottom-14 right-0 w-[360px] max-h-[480px] rounded-2xl border border-amber-500/30 bg-zinc-950/95 backdrop-blur-xl shadow-2xl shadow-amber-500/5 overflow-hidden flex flex-col" data-testid="hitl-inbox-popover">
          <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.28em] text-amber-300 font-bold">Approval inbox</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-300 tabular-nums" data-testid="hitl-inbox-count">
                {paused.length}
              </span>
              {!connected && (
                <span className="flex items-center gap-1 text-[10px] text-rose-400" title="WebSocket disconnected — reconnecting…">
                  <WifiOff size={10} /> reconnecting
                </span>
              )}
            </div>
            <button
              onClick={() => setOpen(false)}
              className="text-zinc-500 hover:text-white"
              aria-label="Close approval inbox"
            >
              <X size={14} />
            </button>
          </div>
          <div className="overflow-y-auto flex-1">
            {paused.length === 0 ? (
              <div className="px-4 py-8 text-center text-zinc-500 text-xs">
                Nothing waiting on you.{' '}
                {!connected && <span className="text-rose-400">Trying to reconnect…</span>}
              </div>
            ) : (
              paused.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => {
                    navigate(`/dashboard/command-center?expand_run=${encodeURIComponent(r.id)}`);
                    setOpen(false);
                  }}
                  className="w-full text-left px-4 py-3 border-b border-white/5 hover:bg-amber-500/5 transition-colors flex gap-3 group"
                  data-testid={`hitl-inbox-row-${r.id}`}
                >
                  <div className="mt-1 w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] text-zinc-100 line-clamp-2 leading-snug">
                      {r.brief || '(no brief)'}
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-1 flex items-center gap-2 tabular-nums">
                      <span>{relativeAge(r.created_at)} old</span>
                      {typeof r.transcript_len === 'number' && (
                        <span>· {r.transcript_len} agents finished</span>
                      )}
                    </div>
                  </div>
                  <ArrowUpRight
                    size={14}
                    className="mt-1 text-zinc-600 group-hover:text-amber-300 group-hover:-translate-y-0.5 transition-all shrink-0"
                  />
                </button>
              ))
            )}
          </div>
          <div className="px-4 py-2 border-t border-white/5 text-[10px] text-zinc-600 flex items-center justify-between">
            <span>Live · WebSocket</span>
            <button
              onClick={() => {
                navigate('/dashboard/command-center');
                setOpen(false);
              }}
              className="text-amber-400 hover:text-amber-300"
              data-testid="hitl-inbox-open-command-center"
            >
              Open Command Center →
            </button>
          </div>
        </div>
      )}

      {/* Bell */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`relative w-12 h-12 rounded-full border shadow-lg flex items-center justify-center transition-all ${
          hasPaused
            ? 'bg-amber-500 border-amber-400 text-white hover:bg-amber-400 shadow-amber-500/30'
            : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-white'
        }`}
        aria-label="Approval inbox"
        data-testid="hitl-inbox-toggle"
        title={hasPaused ? `${paused.length} run${paused.length === 1 ? '' : 's'} awaiting your approval` : 'Inbox empty'}
      >
        {hasPaused
          ? <Bell size={20} className="animate-[wiggle_1s_ease-in-out_infinite]" />
          : <Loader2 size={18} className={connected ? '' : 'animate-spin'} />
        }
        {hasPaused && (
          <span
            className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center border-2 border-zinc-950 tabular-nums"
            data-testid="hitl-inbox-badge"
          >
            {paused.length > 99 ? '99+' : paused.length}
          </span>
        )}
        {!connected && hasPaused && (
          <span
            className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-rose-500 border-2 border-zinc-950"
            title="WebSocket disconnected"
          />
        )}
      </button>
    </div>
  );
};

export default HitlInboxBell;
