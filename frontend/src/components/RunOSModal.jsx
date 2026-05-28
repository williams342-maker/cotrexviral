import React, { useEffect, useState } from 'react';
import {
  Sparkles, Play, Activity, Loader2, CheckSquare, Layers,
} from 'lucide-react';
import { API } from '../context/AuthContext';
import { useToast } from '../hooks/use-toast';

/* Reusable "Run the OS" modal — kicks off the 5-role Marketing OS chain
   via SSE (`POST /api/marketing-os/run/stream`). Used from:
     • CommandCenter   (no campaign context — user types a free brief)
     • CampaignDetail  (pre-seeded with `campaignId` + suggested brief)

   Props:
     open              bool   — visibility
     onClose           ()     — caller hides the modal
     onComplete        ()?    — called once the chain finishes successfully
     initialBrief      str?   — pre-fill the textarea
     campaignId        str?   — when set, sent as `campaign_id` so the
                                 server enriches the brief with the
                                 campaign's goal/audience/pillars.
     campaignName      str?   — purely for UI (shown as a chip in the header)
*/
const RunOSModal = ({
  open, onClose, onComplete,
  initialBrief = '', campaignId = null, campaignName = '',
}) => {
  const [brief, setBrief] = useState(initialBrief);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState([]);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const { toast } = useToast();

  // Reset whenever the modal opens with a new brief/campaign so consecutive
  // opens from different cards don't share stale state.
  useEffect(() => {
    if (!open) return;
    setBrief(initialBrief);
    setProgress([]);
    setSummary('');
    setError('');
    setRunning(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialBrief, campaignId]);

  if (!open) return null;

  const reset = () => {
    setProgress([]); setSummary(''); setError(''); setRunning(false);
  };

  const start = async () => {
    if (!brief.trim()) {
      toast({ title: 'Brief required', description: 'Tell the OS what to ship.' });
      return;
    }
    reset();
    setRunning(true);
    setProgress([{ status: 'starting', label: 'Booting Marketing OS' }]);
    try {
      const body = { brief: brief.trim() };
      if (campaignId) body.campaign_id = campaignId;
      const res = await fetch(`${API}/marketing-os/run/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`HTTP ${res.status}: ${t.slice(0, 200)}`);
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const blocks = buf.split('\n\n');
        buf = blocks.pop();
        for (const block of blocks) {
          const lines = block.split('\n');
          let event = 'message';
          let dataStr = '';
          for (const l of lines) {
            if (l.startsWith('event:')) event = l.slice(6).trim();
            else if (l.startsWith('data:')) dataStr += l.slice(5).trim();
          }
          if (!dataStr || event === 'keepalive') continue;
          let data;
          try { data = JSON.parse(dataStr); } catch { continue; }
          if (event === 'os_started') {
            setProgress([{
              label: `Chain: ${data.chain.join(' → ')} → ${data.summarizer}`,
              status: 'info',
            }]);
          } else if (event === 'agent_started') {
            setProgress((p) => [...p, {
              agent_id: data.agent_id, agent_name: data.agent_name,
              status: 'running', step: data.step, total: data.total,
            }]);
          } else if (event === 'agent_done') {
            setProgress((p) => p.map((r) =>
              (r.agent_id === data.agent_id && r.status === 'running')
                ? { ...r, status: 'done', answer: data.answer }
                : r,
            ));
          } else if (event === 'summarizing') {
            setProgress((p) => [...p, {
              agent_id: data.agent_id, agent_name: data.agent_name,
              status: 'summarizing',
            }]);
          } else if (event === 'complete') {
            setSummary(data.summary || '');
            setProgress((p) => p.map((r) =>
              r.status === 'summarizing' ? { ...r, status: 'done', answer: data.summary } : r,
            ));
          } else if (event === 'error') {
            setError(data.message || 'Run failed');
          }
        }
      }
      setRunning(false);
      onComplete && onComplete();
    } catch (e) {
      setError(e.message);
      setRunning(false);
    }
  };

  const close = () => {
    if (running) return;
    reset();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={close} data-testid="os-run-modal"
      role="dialog" aria-modal="true" aria-labelledby="os-run-modal-title">
      <div className="w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl border border-violet-500/30 bg-zinc-950 p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-violet-400 font-bold mb-1">5-Role Chain</div>
            <h2 id="os-run-modal-title" className="text-2xl font-bold text-white">Run Marketing OS</h2>
            <p className="text-xs text-zinc-400 mt-1">Strategy → Intelligence → Content → Distribution → Analytics</p>
            {campaignName && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 text-[10px] font-semibold uppercase tracking-wider" data-testid="os-run-campaign-pill">
                <Layers size={11} /> Campaign · {campaignName}
              </div>
            )}
          </div>
          <button onClick={close} className="text-zinc-500 hover:text-white text-2xl leading-none" data-testid="os-run-close">×</button>
        </div>

        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Brief for the team — e.g. &#10;&#10;'We're launching our analytics product to indie SaaS founders next month. Plan the launch.'"
          rows={5}
          disabled={running}
          className="w-full bg-zinc-900 border border-white/10 rounded-lg p-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-violet-500/50"
          data-testid="os-run-brief"
        />

        {progress.length === 0 ? (
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={close} className="px-4 py-2 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 text-sm">Cancel</button>
            <button onClick={start} className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium flex items-center gap-2" data-testid="os-run-start">
              <Play size={14} /> Run
            </button>
          </div>
        ) : (
          <div className="mt-5 space-y-2" data-testid="os-run-progress">
            {progress.map((p, i) => (
              <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
                <div className="flex items-center gap-2 text-xs">
                  {p.status === 'running' && <Loader2 size={14} className="animate-spin text-violet-400" />}
                  {p.status === 'summarizing' && <Loader2 size={14} className="animate-spin text-violet-400" />}
                  {p.status === 'done' && <CheckSquare size={14} className="text-emerald-400" />}
                  {(p.status === 'info' || p.status === 'starting') && <Activity size={14} className="text-cyan-400" />}
                  <span className="font-semibold text-white">{p.agent_name || p.label}</span>
                  {p.step && <span className="text-zinc-500">step {p.step}/{p.total}</span>}
                  <span className="ml-auto text-zinc-500 uppercase tracking-wider text-[10px]">{p.status}</span>
                </div>
                {p.answer && (
                  <div className="mt-2 text-xs text-zinc-300 whitespace-pre-wrap line-clamp-6 leading-relaxed">{p.answer}</div>
                )}
              </div>
            ))}
            {summary && (
              <div className="mt-4 rounded-xl border border-violet-500/40 bg-violet-500/5 p-4">
                <div className="flex items-center gap-2 text-violet-300 mb-2">
                  <Sparkles size={14} /><span className="text-xs uppercase tracking-widest font-bold">Executive summary</span>
                </div>
                <div className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed">{summary}</div>
              </div>
            )}
            {error && (
              <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">{error}</div>
            )}
            {!running && (
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={reset} className="px-3 py-1.5 rounded-lg border border-white/10 text-zinc-300 hover:bg-white/5 text-xs" data-testid="os-run-reset">New run</button>
                <button onClick={close} className="px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs">Done</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default RunOSModal;
