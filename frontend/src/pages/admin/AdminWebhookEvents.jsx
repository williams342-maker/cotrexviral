import React, { useEffect, useState } from 'react';
import axios from 'axios';
import DashboardLayout from '../../components/DashboardLayout';
import { Webhook, RefreshCw, CheckCircle2, Repeat, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const AdminWebhookEvents = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/admin/webhook-events?limit=50`, { withCredentials: true });
      setData(r.data);
    } catch (e) {
      // Auth guard already redirects; nothing to do here.
    }
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <DashboardLayout title="Webhook Events" subtitle="Recent Stripe events received by /api/webhook/stripe">
      <div className="cv-dashboard-light p-7 space-y-6">
        {/* Summary */}
        <div className="bg-white rounded-2xl p-6 border border-neutral-200/70 flex items-center justify-between gap-4 flex-wrap" data-testid="webhook-events-summary">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-violet-50 text-violet-700 border border-violet-100 flex items-center justify-center">
              <Webhook size={18} />
            </div>
            <div>
              <div className="text-[13px] text-neutral-500 font-medium">Stripe → CortexViral</div>
              <div className="text-[18px] font-semibold text-neutral-900">
                {data?.total?.toLocaleString() || 0}
                <span className="text-[13px] font-normal text-neutral-500 ml-1.5">events received</span>
              </div>
            </div>
          </div>
          <button
            onClick={refresh}
            disabled={refreshing}
            className="cv-btn-secondary inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-[13px] font-semibold disabled:opacity-60"
            data-testid="webhook-events-refresh"
          >
            {refreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Refresh
          </button>
        </div>

        {/* Top event types */}
        {data?.top_event_types?.length > 0 && (
          <div className="bg-white rounded-2xl p-5 border border-neutral-200/70" data-testid="webhook-events-by-type">
            <div className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold mb-3">By event type</div>
            <div className="flex flex-wrap gap-2">
              {data.top_event_types.map((t) => (
                <span key={t.type} className="inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1 rounded-full bg-neutral-50 border border-neutral-200/70 text-neutral-700">
                  <span className="font-mono text-neutral-600 truncate max-w-[200px]">{t.type}</span>
                  <span className="font-semibold text-neutral-900 tabular-nums">{t.n}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Recent events table */}
        <div className="bg-white rounded-2xl border border-neutral-200/70 overflow-hidden">
          <div className="px-5 py-4 border-b border-neutral-200/70">
            <div className="text-[14px] font-semibold text-neutral-900">Last {data?.items?.length || 0} events</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">Sorted newest first. <span className="font-semibold">Repeat</span> = Stripe re-delivered the same event_id (idempotency check fired).</div>
          </div>
          <table className="w-full text-[13.5px]" data-testid="webhook-events-table">
            <thead className="bg-neutral-50/50">
              <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500">
                <th className="p-3 px-5">Received</th>
                <th className="p-3">Event ID</th>
                <th className="p-3">Type</th>
                <th className="p-3 text-right pr-5">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={4} className="p-8 text-center text-neutral-500"><Loader2 size={14} className="animate-spin inline mr-2" />Loading…</td></tr>
              )}
              {!loading && (!data?.items || data.items.length === 0) && (
                <tr><td colSpan={4} className="p-8 text-center text-neutral-500" data-testid="webhook-events-empty">No Stripe events received yet. After you wire the webhook in Stripe → Developers → Webhooks, events will appear here within seconds.</td></tr>
              )}
              {!loading && data?.items?.map((ev) => (
                <tr key={ev.event_id} className="border-t border-neutral-100" data-testid={`webhook-event-row-${ev.event_id}`}>
                  <td className="p-3 px-5 text-neutral-700 tabular-nums whitespace-nowrap">{formatWhen(ev.received_at)}</td>
                  <td className="p-3 font-mono text-[12px] text-neutral-500">{ev.event_id}</td>
                  <td className="p-3"><span className="font-mono text-[12px] text-neutral-800">{ev.type}</span></td>
                  <td className="p-3 pr-5 text-right">
                    {(ev.redeliveries || 0) > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200" title={`Stripe redelivered this event ${ev.redeliveries} time(s)`}>
                        <Repeat size={9} /> +{ev.redeliveries} repeat
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                        <CheckCircle2 size={9} /> Processed
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardLayout>
  );
};

const formatWhen = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    if (diffMs < 60_000) return `${Math.max(1, Math.floor(diffMs / 1000))}s ago`;
    if (diffMs < 3600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
    if (diffMs < 86400_000) return `${Math.floor(diffMs / 3600_000)}h ago`;
    return d.toLocaleString();
  } catch {
    return iso;
  }
};

export default AdminWebhookEvents;
