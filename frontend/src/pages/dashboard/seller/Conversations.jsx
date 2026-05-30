import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../../context/AuthContext';
import DashboardLayout from '../../../components/DashboardLayout';
import {
  Loader2, MessageSquare, Send, Inbox, ExternalLink, FileText,
} from 'lucide-react';
import { useToast } from '../../../hooks/use-toast';
import { CHANNEL_ICONS, EVENT_TONE } from './_shared';

const Conversations = () => {
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
        return;
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

export default Conversations;
