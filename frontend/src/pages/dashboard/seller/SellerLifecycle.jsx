import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, MessageSquare, Send, ArrowRight, Sparkles, Mail,
  Instagram, Facebook, Globe, ExternalLink, CheckCircle2, Inbox,
  BarChart3, Target, TrendingUp, Users, FileText, ShieldAlert, Activity,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';

const CHANNEL_ICONS = {
  email: Mail, instagram_dm: Instagram, facebook_message: Facebook,
  linkedin_inmail: Globe, contact_form: Globe,
};

const EVENT_TONE = {
  sent:     'text-blue-300',
  delivered:'text-blue-300',
  opened:   'text-amber-300',
  replied:  'text-emerald-300',
  interested:'text-emerald-300',
  bounced:  'text-rose-300',
  unsubscribed:'text-rose-300',
  not_interested:'text-zinc-500',
};

const SellerConversationsLive = () => {
  const { toast } = useToast();
  const [missions, setMissions] = useState([]);
  const [missionId, setMissionId] = useState('');
  const [threads, setThreads] = useState([]);
  const [active, setActive] = useState(null);
  const [thread, setThread] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const ms = await axios.get(`${API}/missions`, { withCredentials: true });
      const sel = (ms.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
      setMissions(sel);
      if (!missionId && sel.length) {
        setMissionId(sel[0].id);
        return; // useEffect will refire with mid set
      }
      if (missionId) {
        const r = await axios.get(`${API}/seller-outreach/threads/${missionId}`, { withCredentials: true });
        setThreads(r.data?.threads || []);
      }
    } catch (e) {
      toast({ title: 'Failed to load conversations',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [missionId]);

  const openThread = async (lead) => {
    setActive(lead);
    try {
      const r = await axios.get(`${API}/seller-outreach/events/${lead.id}`, { withCredentials: true });
      setThread(r.data);
    } catch (e) {
      toast({ title: 'Failed to load thread', variant: 'destructive' });
    }
  };

  const generateOffer = async (withArtifact = false) => {
    if (!active) return;
    try {
      const r = await axios.post(`${API}/seller-outreach/generate`,
        { lead_id: active.id, attach_artifact: withArtifact },
        { withCredentials: true });
      const extra = r.data.artifact ? ' + audit attached' : '';
      toast({ title: `Outreach sent (${r.data.offer_type})${extra}` });
      openThread(active);
    } catch (e) {
      toast({ title: 'Outreach failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    }
  };

  return (
    <DashboardLayout
      title="Seller OS · Conversations"
      subtitle="Every outreach thread Cortex is running, in one inbox."
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-[60vh]" data-testid="seller-conversations">
        {/* Threads sidebar */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 lg:col-span-1">
          <div className="px-2 py-2 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Threads</div>
            <span className="text-[11px] text-zinc-500">{threads.length}</span>
          </div>
          <select value={missionId} onChange={(e) => setMissionId(e.target.value)}
                  data-testid="conv-mission-select"
                  className="w-full mb-2 px-2.5 py-1.5 rounded-md bg-white/5 border border-white/10 text-white text-[12px]">
            {missions.map((m) => (
              <option key={m.id} value={m.id}>{m.title}</option>
            ))}
          </select>
          {loading ? (
            <div className="flex items-center gap-2 text-zinc-500 text-[12px] px-2"><Loader2 className="animate-spin" size={12} /> Loading…</div>
          ) : threads.length === 0 ? (
            <div className="text-[12px] text-zinc-500 italic px-2 py-4">No active threads. Send outreach from <strong className="text-zinc-300">Discovery</strong>.</div>
          ) : (
            <div className="space-y-1 max-h-[55vh] overflow-y-auto">
              {threads.map((t) => {
                const Icon = CHANNEL_ICONS[t.last_outreach_channel] || MessageSquare;
                const isActive = active?.id === t.id;
                return (
                  <button key={t.id} onClick={() => openThread(t)}
                          data-testid={`conv-thread-${t.id}`}
                          className={`w-full text-left p-2.5 rounded-lg transition ${
                            isActive ? 'bg-violet-500/15 border border-violet-500/30'
                                     : 'hover:bg-white/5 border border-transparent'
                          }`}>
                    <div className="flex items-center gap-2 mb-0.5">
                      <Icon size={12} className="text-zinc-400 shrink-0" />
                      <div className="text-[13px] font-semibold text-white truncate">{t.business_name}</div>
                    </div>
                    <div className="text-[11px] text-zinc-500 flex items-center gap-1.5">
                      <span className="capitalize">{t.stage}</span>
                      {t.last_event && (
                        <>
                          <span>·</span>
                          <span className={EVENT_TONE[t.last_event.event] || 'text-zinc-500'}>
                            {t.last_event.event.replace('_', ' ')}
                          </span>
                        </>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Thread detail */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5 lg:col-span-2">
          {!active ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-zinc-500 text-[13px] py-16">
              <Inbox size={28} className="mb-2 text-zinc-700" />
              Pick a thread to view the full event timeline.
            </div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3 mb-4 pb-4 border-b border-white/5">
                <div className="flex-1 min-w-0">
                  <div className="text-[15px] font-semibold text-white">{active.business_name}</div>
                  <div className="text-[11.5px] text-zinc-500 flex items-center gap-2 mt-0.5">
                    <span className="capitalize">{active.source.replace('_', ' ')}</span>
                    {active.niche && <><span>·</span><span>{active.niche}</span></>}
                    {active.seller_score != null && <><span>·</span><span>score <strong className="text-white">{active.seller_score}</strong></span></>}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  {(() => {
                    const canOutreach = ['qualified', 'discovered', 'outreached', 'interested'].includes(active.stage);
                    return (
                      <>
                        <button onClick={() => generateOffer(false)} disabled={!canOutreach}
                                data-testid="conv-send-offer"
                                title={!canOutreach ? `Outreach paused — lead is ${active.stage}` : 'Generate a fresh outreach message'}
                                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-white/5 hover:bg-white/10 text-zinc-200 transition flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed">
                          <Send size={11} /> Send offer
                        </button>
                        <button onClick={() => generateOffer(true)} disabled={!canOutreach}
                                data-testid="conv-send-offer-artifact"
                                title={!canOutreach ? `Outreach paused — lead is ${active.stage}` : 'Generate a personalized audit and attach it to the message'}
                                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 transition flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed">
                          <FileText size={11} /> Send + audit
                        </button>
                      </>
                    );
                  })()}
                </div>
              </div>
              {thread?.events?.length ? (
                <div className="space-y-2.5 max-h-[55vh] overflow-y-auto">
                  {thread.events.map((e) => {
                    const Icon = CHANNEL_ICONS[e.channel] || MessageSquare;
                    return (
                      <div key={e.id} className="rounded-lg bg-white/[0.03] border border-white/5 p-3"
                           data-testid={`conv-event-${e.id}`}>
                        <div className="flex items-center gap-2 text-[11px] mb-1.5">
                          <Icon size={11} className="text-zinc-400" />
                          <span className={`uppercase tracking-wider font-semibold ${EVENT_TONE[e.event] || 'text-zinc-300'}`}>{e.event.replace('_', ' ')}</span>
                          {e.offer_type && <span className="text-zinc-500">· {e.offer_type.replace(/_/g, ' ')}</span>}
                          <span className="ml-auto text-zinc-500">{new Date(e.created_at).toLocaleString()}</span>
                        </div>
                        {e.body && <div className="text-[12.5px] text-zinc-300 whitespace-pre-line">{e.body}</div>}
                        {e.artifact_id && (
                          <a href={`${API}/seller-offers/${e.artifact_id}/download.html`}
                             target="_blank" rel="noopener noreferrer"
                             data-testid={`conv-artifact-${e.id}`}
                             className="mt-2 text-[11.5px] font-semibold text-violet-300 hover:text-violet-200 inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-violet-500/10 hover:bg-violet-500/20 transition">
                            <FileText size={11} /> View attached audit <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-[12px] text-zinc-500 italic">No events yet.</div>
              )}
            </>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

const SellerOnboardingLive = () => {
  const { toast } = useToast();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const interested = await axios.get(`${API}/seller-leads?stage=interested&limit=50`, { withCredentials: true });
      const onboarding = await axios.get(`${API}/seller-leads?stage=onboarding&limit=50`, { withCredentials: true });
      const active = await axios.get(`${API}/seller-leads?stage=active&limit=50`, { withCredentials: true });
      setLeads([...(interested.data?.leads || []),
                ...(onboarding.data?.leads || []),
                ...(active.data?.leads || [])]);
    } catch (e) {
      toast({ title: 'Load failed', variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const onboard = async (lead) => {
    setBusy((b) => ({ ...b, [lead.id]: true }));
    try {
      const r = await axios.post(`${API}/seller-onboarding/start`,
        { lead_id: lead.id }, { withCredentials: true });
      toast({ title: r.data.reused ? 'Already onboarded' : 'Onboarding complete',
              description: `${(r.data.steps || []).length} steps · status=${r.data.status}` });
      load();
    } catch (e) {
      toast({ title: 'Onboarding failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setBusy((b) => ({ ...b, [lead.id]: false })); }
  };

  return (
    <DashboardLayout
      title="Seller OS · Onboarding"
      subtitle="Promote interested sellers into active marketplace members in under 10 minutes."
    >
      <div className="space-y-3" data-testid="seller-onboarding-page">
        {loading && <div className="flex items-center gap-2 text-zinc-500"><Loader2 className="animate-spin" size={14} /> Loading…</div>}
        {!loading && leads.length === 0 && (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            No interested or onboarding sellers yet. Once a thread converts (event=replied), it surfaces here.
          </div>
        )}
        {leads.map((lead) => (
          <div key={lead.id} className="rounded-2xl border border-white/5 bg-white/[0.03] p-4 flex items-center gap-3"
               data-testid={`onboard-row-${lead.id}`}>
            <div className="flex-1 min-w-0">
              <div className="text-[14px] font-semibold text-white truncate">{lead.business_name}</div>
              <div className="text-[11.5px] text-zinc-500 mt-0.5 flex items-center gap-2">
                <span className="capitalize">{lead.stage}</span>
                {lead.niche && <><span>·</span><span>{lead.niche}</span></>}
                {lead.seller_score != null && <><span>·</span><span>score {lead.seller_score}</span></>}
              </div>
            </div>
            {lead.stage === 'active' ? (
              <span className="text-[11.5px] font-semibold text-emerald-300 flex items-center gap-1">
                <CheckCircle2 size={12} /> Onboarded
              </span>
            ) : (
              <button onClick={() => onboard(lead)} disabled={busy[lead.id]}
                      data-testid={`onboard-start-${lead.id}`}
                      className="text-[12px] font-semibold px-3 py-1.5 rounded-md bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 transition flex items-center gap-1.5 disabled:opacity-50">
                {busy[lead.id] ? <Loader2 className="animate-spin" size={12} /> : <Sparkles size={12} />}
                Onboard now
              </button>
            )}
          </div>
        ))}
      </div>
    </DashboardLayout>
  );
};

const SellerRetentionLive = () => {
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

  const SEV_TONE = {
    inactive: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    churn:    'bg-rose-500/15 text-rose-300 border-rose-500/30',
    at_risk:  'bg-orange-500/15 text-orange-300 border-orange-500/30',
  };

  const scoreTone = (n) => n >= 60 ? 'text-rose-300'
                       : n >= 40 ? 'text-orange-300'
                       : n >= 20 ? 'text-amber-300'
                       : 'text-emerald-300';

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
                    {wf.steps.map((s, i) => (
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

export { SellerConversationsLive, SellerOnboardingLive, SellerRetentionLive, SellerAnalyticsLive };

// ---------------------------------------------------------------------
// Seller Analytics — unified funnel report across all seller missions
// ---------------------------------------------------------------------
function SellerAnalyticsLive() {
  return <SellerAnalyticsInner />;
}

function SellerAnalyticsInner() {
  const { toast } = useToast();
  const [missions, setMissions] = useState([]);
  const [funnels, setFunnels] = useState({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/missions`, { withCredentials: true });
      const sel = (r.data.missions || []).filter((m) => m.mission_type === 'seller_acquisition');
      setMissions(sel);
      const out = {};
      await Promise.all(sel.map(async (m) => {
        try {
          const f = await axios.get(`${API}/missions/${m.id}/seller-funnel`, { withCredentials: true });
          out[m.id] = f.data;
        } catch (e) { /* keep going */ }
      }));
      setFunnels(out);
    } catch (e) {
      toast({ title: 'Analytics load failed',
              description: e?.response?.data?.detail || e.message, variant: 'destructive' });
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  // Aggregate KPIs across all missions
  const totals = React.useMemo(() => {
    const acc = { discovered: 0, qualified: 0, outreached: 0, interested: 0,
                  onboarding: 0, active: 0, churned: 0, unresponsive: 0,
                  target: 0, onboarded: 0 };
    Object.values(funnels).forEach((f) => {
      const fn = f.funnel || {};
      Object.keys(acc).forEach((k) => { if (fn[k] != null) acc[k] += fn[k]; });
      acc.target += (f.target || 0);
      acc.onboarded += (f.projected_completion?.current || 0);
    });
    return acc;
  }, [funnels]);

  const pct = (n, d) => (d > 0 ? Math.round((n / d) * 1000) / 10 : 0);
  const convRates = [
    { label: 'Discovery → Qualified', from: 'discovered', to: 'qualified' },
    { label: 'Qualified → Outreached', from: 'qualified', to: 'outreached' },
    { label: 'Outreached → Interested', from: 'outreached', to: 'interested' },
    { label: 'Interested → Onboarding', from: 'interested', to: 'onboarding' },
    { label: 'Onboarding → Active', from: 'onboarding', to: 'active' },
  ];

  return (
    <DashboardLayout
      title="Seller OS · Analytics"
      subtitle="The unified seller funnel across every mission Cortex is running."
    >
      <div className="space-y-5" data-testid="seller-analytics-page">
        {loading ? (
          <div className="flex items-center gap-2 text-zinc-500">
            <Loader2 className="animate-spin" size={14} /> Loading analytics…
          </div>
        ) : missions.length === 0 ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-10 text-center text-[13px] text-zinc-500">
            <BarChart3 size={20} className="mx-auto mb-2 text-zinc-600" />
            No seller missions yet. Brief Cortex with a seller-acquisition goal to start.
          </div>
        ) : (
          <>
            {/* Hero KPI tiles */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KpiTile icon={Users} label="Discovered" value={totals.discovered} tone="cyan" />
              <KpiTile icon={Sparkles} label="Qualified" value={totals.qualified} tone="violet" />
              <KpiTile icon={Send} label="Outreached" value={totals.outreached} tone="blue" />
              <KpiTile icon={CheckCircle2} label="Active sellers" value={totals.active} tone="emerald" />
            </div>

            {/* Conversion funnel */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={14} className="text-violet-300" />
                <div className="text-[13px] font-semibold text-white">Funnel conversion</div>
              </div>
              <div className="space-y-3">
                {convRates.map((c) => {
                  const fromN = totals[c.from] || 0;
                  const toN = totals[c.to] || 0;
                  const r = pct(toN, fromN);
                  return (
                    <div key={c.label} data-testid={`analytics-conv-${c.from}-${c.to}`}>
                      <div className="flex items-center justify-between text-[11.5px] text-zinc-400 mb-1">
                        <span>{c.label}</span>
                        <span className="tabular-nums"><strong className="text-white">{toN}</strong> / {fromN} <span className="text-zinc-500">·</span> <strong className="text-violet-300">{r}%</strong></span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500"
                             style={{ width: `${Math.min(100, r)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Per-mission rollup */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <Target size={14} className="text-blue-300" />
                <div className="text-[13px] font-semibold text-white">Mission velocity</div>
              </div>
              <div className="space-y-2.5">
                {missions.map((m) => {
                  const f = funnels[m.id];
                  const proj = f?.projected_completion || {};
                  const target = m.target || 0;
                  const current = proj.current || 0;
                  const pctDone = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
                  return (
                    <div key={m.id} className="p-3 rounded-lg bg-white/[0.03] border border-white/5"
                         data-testid={`analytics-mission-${m.id}`}>
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <div className="text-[13px] font-semibold text-white truncate flex-1 min-w-0">{m.title}</div>
                        <span className="text-[11px] text-zinc-500 tabular-nums">
                          <strong className="text-white">{current}</strong> / {target}
                          {proj.eta_days != null && <> · <span className="text-violet-300">{proj.eta_days}d ETA</span></>}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-blue-500"
                             style={{ width: `${pctDone}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Stage waterfall */}
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={14} className="text-emerald-300" />
                <div className="text-[13px] font-semibold text-white">Stage waterfall (all missions)</div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {['discovered', 'qualified', 'outreached', 'interested',
                  'onboarding', 'active', 'churned', 'unresponsive'].map((k) => (
                  <div key={k} className="p-3 rounded-lg bg-white/[0.03] border border-white/5"
                       data-testid={`analytics-stage-${k}`}>
                    <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">{k}</div>
                    <div className="text-xl tabular-nums font-semibold text-white">{totals[k] || 0}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}

const KPI_TONES = {
  cyan:    'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
  violet:  'bg-violet-500/10 border-violet-500/20 text-violet-300',
  blue:    'bg-blue-500/10 border-blue-500/20 text-blue-300',
  emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
};

function KpiTile({ icon: Icon, label, value, tone = 'violet' }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4"
         data-testid={`analytics-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border ${KPI_TONES[tone]} mb-2`}>
        <Icon size={14} />
      </div>
      <div className="text-[10.5px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
      <div className="text-2xl tabular-nums font-semibold text-white mt-0.5">{value}</div>
    </div>
  );
}
