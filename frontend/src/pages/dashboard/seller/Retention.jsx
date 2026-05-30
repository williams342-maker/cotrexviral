import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import { Loader2, ShieldAlert, Activity, Inbox, ArrowRight } from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

const SEV_TONE = {
  inactive: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  churn:    'bg-rose-500/15 text-rose-300 border-rose-500/30',
  at_risk:  'bg-orange-500/15 text-orange-300 border-orange-500/30',
};

const scoreTone = (n) => n >= 60 ? 'text-rose-300'
                       : n >= 40 ? 'text-orange-300'
                       : n >= 20 ? 'text-amber-300'
                       : 'text-emerald-300';

const Retention = () => {
  const { toast } = useToast();
  const [alerts, setAlerts] = useState([]);
  const [scores, setScores] = useState([]);
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [intelScanning, setIntelScanning] = useState(false);
  const [advancing, setAdvancing] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [a, s, w] = await Promise.all([
        axios.get(`${API}/seller-retention/alerts?limit=100`, { withCredentials: true }),
        axios.get(`${API}/seller-retention/intel/scores?limit=100`, { withCredentials: true }),
        axios.get(`${API}/seller-retention/intel/workflows?limit=50`, { withCredentials: true }),
      ]);
      setAlerts(a.data?.alerts || []);
      setScores(s.data?.scores || []);
      setWorkflows(w.data?.workflows || []);
    } catch (e) {
      toast({ title: 'Load failed', variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const runScan = async () => {
    setScanning(true);
    try {
      const r = await axios.post(`${API}/seller-retention/scan`, {}, { withCredentials: true });
      toast({ title: `Heuristic scan complete`,
              description: `Inactive: ${r.data.flagged_inactive} · Churned: ${r.data.flagged_churn}` });
      load();
    } catch (e) {
      toast({ title: 'Scan failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setScanning(false); }
  };

  const runIntelScan = async () => {
    setIntelScanning(true);
    try {
      const r = await axios.post(`${API}/seller-retention/intel/score`, {}, { withCredentials: true });
      toast({ title: `Churn intel scan complete`,
              description: `Scanned ${r.data.scanned} · At risk ${r.data.at_risk} · Workflows ${r.data.workflows_launched}` });
      load();
    } catch (e) {
      toast({ title: 'Intel scan failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setIntelScanning(false); }
  };

  const advanceWorkflow = async (wf) => {
    setAdvancing((b) => ({ ...b, [wf.id]: true }));
    try {
      await axios.post(`${API}/seller-retention/intel/workflows/${wf.id}/advance`,
        {}, { withCredentials: true });
      toast({ title: 'Workflow advanced' });
      load();
    } catch (e) {
      toast({ title: 'Advance failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setAdvancing((b) => ({ ...b, [wf.id]: false })); }
  };

  return (
    <DashboardLayout
      title="Seller OS · Retention"
      subtitle="Multi-signal churn-risk scoring + auto-launched retention workflows."
      headerExtra={
        <div className="flex items-center gap-2">
          <button onClick={runScan} disabled={scanning}
                  data-testid="retention-scan-btn"
                  className="text-[12px] font-semibold px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-zinc-200 transition flex items-center gap-1.5 disabled:opacity-50">
            {scanning ? <Loader2 className="animate-spin" size={13} /> : <Activity size={13} />}
            {scanning ? 'Scanning…' : 'Heuristic scan'}
          </button>
          <button onClick={runIntelScan} disabled={intelScanning}
                  data-testid="retention-intel-scan-btn"
                  className="text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-50">
            {intelScanning ? <Loader2 className="animate-spin" size={13} /> : <ShieldAlert size={13} />}
            {intelScanning ? 'Scoring…' : 'Score churn risk'}
          </button>
        </div>
      }
    >
      <div className="space-y-5" data-testid="seller-retention-page">
        {loading && <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>}

        {/* Active workflows */}
        {workflows.length > 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <div className="flex items-center gap-2 mb-3">
              <ShieldAlert size={14} className="text-violet-300" />
              <div className="text-[13px] font-semibold text-white">Active retention workflows</div>
              <span className="text-[11px] text-zinc-500">· {workflows.length}</span>
            </div>
            <div className="space-y-3">
              {workflows.map((wf) => (
                <div key={wf.id} className="rounded-xl bg-white/[0.03] border border-white/5 p-3"
                     data-testid={`retention-wf-${wf.id}`}>
                  <div className="flex items-center gap-3 mb-2.5">
                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${
                      wf.status === 'complete'
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                        : 'bg-violet-500/15 text-violet-300 border-violet-500/30'
                    }`}>{wf.status}</span>
                    <div className="text-[12px] text-zinc-300 flex-1 truncate">
                      <strong className="text-white">{(wf.reasons || [])[0] || 'Multi-signal churn risk'}</strong>
                      <span className="text-zinc-500"> · score </span>
                      <span className={scoreTone(wf.score) + ' font-semibold tabular-nums'}>{Math.round(wf.score)}</span>
                    </div>
                    {wf.status === 'running' && (
                      <button onClick={() => advanceWorkflow(wf)} disabled={advancing[wf.id]}
                              data-testid={`retention-wf-advance-${wf.id}`}
                              className="text-[11px] font-semibold px-2.5 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 transition flex items-center gap-1 disabled:opacity-50">
                        {advancing[wf.id] ? <Loader2 className="animate-spin" size={10} /> : <ArrowRight size={10} />}
                        Advance step
                      </button>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {wf.steps.map((s) => (
                      <div key={s.step}
                           data-testid={`retention-wf-step-${wf.id}-${s.step}`}
                           title={`${s.step} · ${s.status}${s.detail ? ' · ' + s.detail : ''}`}
                           className={`flex-1 h-1.5 rounded-full ${
                             s.status === 'ok' ? 'bg-emerald-500'
                             : s.status === 'failed' ? 'bg-rose-500'
                             : 'bg-white/10'
                           }`} />
                    ))}
                  </div>
                  <div className="grid grid-cols-3 gap-1.5 mt-1.5">
                    {wf.steps.map((s) => (
                      <div key={s.step} className="text-[10px] text-zinc-500 uppercase tracking-wider">
                        {s.step.replace('_', ' ')}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Churn-risk scores */}
        {scores.length > 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <div className="flex items-center gap-2 mb-3">
              <Activity size={14} className="text-blue-300" />
              <div className="text-[13px] font-semibold text-white">Churn-risk scores</div>
              <span className="text-[11px] text-zinc-500">· top {scores.length}</span>
            </div>
            <div className="space-y-2">
              {scores.slice(0, 12).map((s) => (
                <div key={s.lead_id} className="flex items-center gap-3 py-1.5"
                     data-testid={`retention-score-${s.lead_id}`}>
                  <div className={`text-base tabular-nums font-semibold w-10 text-right ${scoreTone(s.score)}`}>
                    {Math.round(s.score)}
                  </div>
                  <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div className={`h-full rounded-full ${
                      s.score >= 60 ? 'bg-rose-500'
                      : s.score >= 40 ? 'bg-orange-500'
                      : s.score >= 20 ? 'bg-amber-500'
                      : 'bg-emerald-500'
                    }`} style={{ width: `${Math.min(100, s.score)}%` }} />
                  </div>
                  <div className="text-[11.5px] text-zinc-400 w-64 truncate">
                    {(s.reasons || []).slice(0, 2).join(' · ') || 'Healthy'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Heuristic alerts (legacy) */}
        {alerts.length > 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
            <div className="flex items-center gap-2 mb-3">
              <Inbox size={14} className="text-amber-300" />
              <div className="text-[13px] font-semibold text-white">Retention alerts</div>
              <span className="text-[11px] text-zinc-500">· {alerts.length}</span>
            </div>
            <div className="space-y-2">
              {alerts.map((a) => (
                <div key={a.id} className="rounded-xl border border-white/5 bg-white/[0.03] p-3 flex items-center gap-3"
                     data-testid={`retention-alert-${a.id}`}>
                  <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full border ${SEV_TONE[a.severity] || SEV_TONE.inactive}`}>
                    {a.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] text-white truncate">{a.reason}</div>
                    <div className="text-[10.5px] text-zinc-500 mt-0.5">{new Date(a.created_at).toLocaleString()}</div>
                  </div>
                  <div className="text-[10.5px] text-zinc-500 font-mono">{a.lead_id.slice(0, 8)}…</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {!loading && alerts.length === 0 && scores.length === 0 && workflows.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            <ShieldAlert size={20} className="mx-auto mb-2 text-zinc-600" />
            No retention signals yet. Click <strong className="text-white">Score churn risk</strong> to evaluate every active seller.
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Retention;
