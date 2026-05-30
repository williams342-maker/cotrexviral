import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  Radar, AlertTriangle, TrendingUp, Loader2, RefreshCw,
  ArrowRight, Sparkles,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* OptimizationStatus — "Cortex is monitoring your business" panel.

   Surfaces the autonomous OODA loop's most recent finding + a count
   of detections in the last 24h / 7d. Click 'Scan now' to force a
   fresh iteration. Click a detection to drop it into the chat
   composer as a discussion seed.

   This is the headline component that makes Cortex feel like a CGO
   actively working for the user rather than waiting to be asked. */

const fmtAge = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso); const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60)    return 'just now';
    if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    return `${Math.floor(diff/86400)}d ago`;
  } catch { return ''; }
};

export const OptimizationStatus = ({ onDiscuss }) => {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/cortex/optimization/status`,
                                  { withCredentials: true });
      setStatus(r.data || null);
    } catch (_e) { /* */ }
    finally { setBusy(false); }
  }, []);

  const scanNow = async () => {
    setScanning(true);
    try {
      await axios.post(`${API}/cortex/optimization/run-now`, {},
                        { withCredentials: true });
      await load();
    } catch (_e) { /* */ }
    finally { setScanning(false); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);   // poll every minute
    return () => clearInterval(t);
  }, [load]);

  const latest = status?.latest;
  const confidence = latest ? Math.round((latest.confidence || 0) * 100) : 0;

  return (
    <section data-testid="cortex-optimization-status"
              className="mb-3">
      <div className="text-[10px] uppercase tracking-widest font-semibold mb-2 flex items-center gap-1.5">
        <span className="relative flex items-center justify-center">
          <Radar size={11} className="text-emerald-400" />
          <span className="absolute -inset-1 rounded-full bg-emerald-400/20 animate-ping" />
        </span>
        <span className="text-emerald-300">Cortex is monitoring</span>
        {busy && <Loader2 size={10} className="animate-spin ml-1 text-zinc-500" />}
        <button onClick={scanNow} disabled={scanning}
                data-testid="optimization-scan-now"
                title="Scan now"
                className="ml-auto w-6 h-6 rounded-md hover:bg-white/10 text-zinc-500 hover:text-zinc-300 flex items-center justify-center transition disabled:opacity-40">
          <RefreshCw size={10} className={scanning ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Quick stats row */}
      <div className="grid grid-cols-3 gap-1 mb-2">
        <div className="rounded-md bg-white/[0.02] border border-white/5 p-1.5 text-center">
          <div className="text-[9px] uppercase text-zinc-500 tracking-wider">24h</div>
          <div className="text-[13px] font-bold text-white tabular-nums">{status?.detections_24h ?? 0}</div>
        </div>
        <div className="rounded-md bg-white/[0.02] border border-white/5 p-1.5 text-center">
          <div className="text-[9px] uppercase text-zinc-500 tracking-wider">7d</div>
          <div className="text-[13px] font-bold text-white tabular-nums">{status?.detections_7d ?? 0}</div>
        </div>
        <div className="rounded-md bg-emerald-500/[0.06] border border-emerald-500/15 p-1.5 text-center">
          <div className="text-[9px] uppercase text-emerald-400 tracking-wider">Improved</div>
          <div className="text-[13px] font-bold text-emerald-300 tabular-nums">{status?.improved_7d ?? 0}</div>
        </div>
      </div>

      {/* Latest detection */}
      {latest ? (
        <button onClick={() => onDiscuss?.(latest)}
                data-testid="optimization-latest"
                className="w-full text-left rounded-xl border border-amber-500/20 hover:border-amber-500/40 bg-amber-500/[0.04] hover:bg-amber-500/[0.06] p-3 transition group">
          <div className="flex items-start gap-2 mb-1.5">
            <AlertTriangle size={11} className="text-amber-300 mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-wider text-amber-300 font-semibold">
                Bottleneck detected · {fmtAge(latest.created_at)}
              </div>
              <div className="text-[12.5px] text-white leading-tight mt-0.5">
                {latest.bottleneck}
              </div>
            </div>
          </div>
          {latest.recommendation && (
            <div className="text-[11px] text-zinc-400 leading-relaxed mb-1.5 pl-5">
              <span className="text-zinc-500">Recommendation:</span> {latest.recommendation}
            </div>
          )}
          <div className="flex items-center gap-1.5 pl-5 text-[10px] text-zinc-500">
            <span>confidence</span>
            <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden max-w-[80px]">
              <div className="h-full bg-amber-400"
                    style={{ width: `${confidence}%` }} />
            </div>
            <span className="tabular-nums">{confidence}%</span>
            <span className="ml-auto text-violet-300 opacity-0 group-hover:opacity-100 transition flex items-center gap-0.5">
              Discuss <ArrowRight size={9} />
            </span>
          </div>
        </button>
      ) : (
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[11px] text-zinc-500 italic">
          <div className="flex items-start gap-2">
            <Sparkles size={11} className="text-emerald-400 mt-0.5 shrink-0" />
            <span>Healthy — no bottlenecks detected. Cortex is watching your funnel, outreach, and conversions in the background.</span>
          </div>
        </div>
      )}
    </section>
  );
};

export default OptimizationStatus;
