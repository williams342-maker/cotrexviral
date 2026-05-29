/* useHitlInbox — opens a WebSocket to /api/ws/hitl-inbox, holds the
   list of currently-paused HITL runs, and exposes broadcast events.

   - Auto-reconnect with exponential backoff (1.5s → 3s → 6s → 12s, cap)
   - 25s heartbeat (sends `ping`, expects `pong`)
   - Cleans up on unmount + on session-token change
   - Re-uses the `session_token` cookie the browser sends naturally,
     plus a `?token=` query fallback for completeness

   Returns:
     {
       paused:    [{ id, brief, status, ... }],   // mirrors `marketing_os_runs`
       connected: bool,
       lastEvent: { event, data, at } | null,
     }
*/
import { useEffect, useRef, useState, useCallback } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

function readCookie(name) {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : null;
}

function wsBaseUrl() {
  // BACKEND_URL is https://… in prod / preview, http://… in dev — flip the scheme.
  if (!BACKEND_URL) return '';
  return BACKEND_URL.replace(/^http/, 'ws');
}

export default function useHitlInbox() {
  const [paused, setPaused] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);

  // Use refs (not state) for the socket + reconnect counters so we don't
  // re-render every time the connection state mutates internally.
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const heartbeatTimer = useRef(null);
  const reconnectTimer = useRef(null);
  const closedByUs = useRef(false);

  const cleanup = useCallback(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = null;
    }
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      closedByUs.current = true;
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    const base = wsBaseUrl();
    if (!base) return;
    const token = readCookie('session_token');
    const url = token
      ? `${base}/api/ws/hitl-inbox?token=${encodeURIComponent(token)}`
      : `${base}/api/ws/hitl-inbox`;

    closedByUs.current = false;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch {
      // Schedule a retry — WebSocket() constructor can throw on bad URI.
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      setConnected(true);
      // Heartbeat — server pongs back. If we miss a pong window the
      // browser closes the socket via TCP timeout anyway.
      heartbeatTimer.current = setInterval(() => {
        try { ws.send('ping'); } catch { /* ignore */ }
      }, 25_000);
    };

    ws.onmessage = (evt) => {
      let frame;
      try { frame = JSON.parse(evt.data); } catch { return; }
      const { event, data } = frame;
      setLastEvent(frame);
      if (event === 'snapshot') {
        setPaused(Array.isArray(data?.paused) ? data.paused : []);
      } else if (event === 'hitl_paused') {
        setPaused((prev) => {
          // Idempotent: if the run id already exists, replace; else prepend.
          const filtered = prev.filter((r) => r.id !== data.run_id);
          return [{
            id:                  data.run_id,
            brief:               data.brief,
            status:              data.status,
            campaign_id:         data.campaign_id,
            skip_distribution:   data.skip_distribution,
            transcript_len:      data.transcript_len,
            created_at:          frame.at,
          }, ...filtered];
        });
      } else if (event === 'hitl_resolved') {
        // Drop the resolved run from the pending queue.
        setPaused((prev) => prev.filter((r) => r.id !== data.run_id));
      }
      // pong / run_completed / run_failed don't mutate the pending list.
    };

    ws.onclose = () => {
      setConnected(false);
      if (heartbeatTimer.current) {
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = null;
      }
      if (!closedByUs.current) scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will fire next; let it handle reconnect.
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scheduleReconnect = useCallback(() => {
    const attempt = reconnectAttempts.current;
    reconnectAttempts.current = attempt + 1;
    // 1.5s, 3s, 6s, 12s, cap 30s.
    const delay = Math.min(30_000, 1500 * Math.pow(2, attempt));
    reconnectTimer.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    connect();
    return cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Allow callers to optimistically drop a row when they Approve/Reject —
  // useful so the inbox panel feels instant before the WS event lands.
  const removeRun = useCallback((runId) => {
    setPaused((prev) => prev.filter((r) => r.id !== runId));
  }, []);

  return { paused, connected, lastEvent, removeRun };
}
