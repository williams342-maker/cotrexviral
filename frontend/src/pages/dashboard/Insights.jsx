import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Textarea } from '../../components/ui/textarea';
import {
  Sparkles, Loader2, TrendingUp, Calendar, Lightbulb, ArrowRight,
  MessageSquare, RotateCcw,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

/* AI Marketing Insights — conversational version.

   Flow:
   1. User submits initial context → /api/ai/insights → renders structured
      sections (Insights / Trends / 1-week plan) + 4 pre-canned follow-up chips.
   2. User clicks a chip OR types a follow-up → /api/ai/insights/followup →
      appended to conversation thread below the structured insights. Each AI
      turn returns 3 fresh contextual follow-up chips so the conversation
      keeps moving.
   3. "Start over" button resets everything and unlocks the initial brief
      form for a fresh topic. */

const Insights = () => {
  const [context, setContext] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);          // initial structured insights
  const [followUps, setFollowUps] = useState([]);      // current suggested chips
  const [conversation, setConversation] = useState([]); // [{role, content}]
  const [pending, setPending] = useState(false);       // a follow-up is in flight
  const [draft, setDraft] = useState('');              // user's typed follow-up
  const threadRef = useRef(null);
  const { toast } = useToast();

  // Auto-scroll the conversation thread when new messages land.
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [conversation, pending]);

  const run = async (e) => {
    e.preventDefault();
    if (!context.trim()) return;
    setLoading(true); setResult(null); setConversation([]); setFollowUps([]);
    try {
      const res = await axios.post(`${API}/ai/insights`, { context }, { withCredentials: true });
      setResult(res.data.insights);
      setFollowUps(res.data.follow_ups || []);
    } catch (err) {
      toast({ title: 'Failed', description: err.response?.data?.detail || 'Try again' });
    } finally {
      setLoading(false);
    }
  };

  const sendFollowup = async (msg) => {
    const text = (msg || '').trim();
    if (!text || pending) return;
    setDraft('');
    setConversation((c) => [...c, { role: 'user', content: text }]);
    setFollowUps([]);
    setPending(true);
    try {
      const r = await axios.post(`${API}/ai/insights/followup`,
        { message: text }, { withCredentials: true });
      setConversation((c) => [...c, { role: 'assistant', content: r.data.answer }]);
      setFollowUps(r.data.follow_ups || []);
    } catch (err) {
      setConversation((c) => [...c, {
        role: 'assistant',
        content: '⚠️ Sorry — could not generate a follow-up. Please try again.',
      }]);
      toast({ title: 'Follow-up failed', description: err.response?.data?.detail });
    }
    setPending(false);
  };

  const startOver = () => {
    setResult(null); setConversation([]); setFollowUps([]); setContext('');
  };

  return (
    <DashboardLayout
      title="AI Marketing Insights"
      subtitle="Tell Nova about your business, get a tailored playbook, then keep the conversation going."
    >
      {/* Initial brief form */}
      {!result && (
        <form onSubmit={run} className="bg-white rounded-3xl p-6 border border-neutral-200/70 mb-7">
          <Textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="e.g. We sell sustainable yoga mats to women 25-40 in North America. Currently 5k Instagram followers, posting 3x/week. Struggling with engagement and ROAS."
            rows={5}
            className="rounded-xl border-neutral-300 mb-3 text-[14.5px]"
            required
            data-testid="insights-context-input"
          />
          <button
            type="submit"
            disabled={loading}
            data-testid="insights-generate-btn"
            className="inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white px-7 h-11 rounded-xl text-[14px] font-medium"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {loading ? 'Thinking…' : 'Generate Insights'}
          </button>
        </form>
      )}

      {loading && (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Loader2 className="animate-spin text-[#1B7BFF] mx-auto mb-3" size={28} />
          <p className="text-neutral-700 font-medium">Nova is thinking…</p>
        </div>
      )}

      {result && !result.raw && (
        <div className="space-y-5 mb-7">
          {result.insights?.length > 0 && (
            <Section icon={Lightbulb} title="Key insights" color="text-amber-600" tint="bg-amber-50">
              {result.insights.map((s, i) => <Item key={i} idx={i + 1} text={s} />)}
            </Section>
          )}
          {result.trends?.length > 0 && (
            <Section icon={TrendingUp} title="Trends to watch" color="text-violet-600" tint="bg-violet-50">
              {result.trends.map((s, i) => <Item key={i} idx={i + 1} text={s} />)}
            </Section>
          )}
          {result.action_plan?.length > 0 && (
            <Section icon={Calendar} title="Your 1-week action plan" color="text-emerald-600" tint="bg-emerald-50">
              {result.action_plan.map((s, i) => <Item key={i} idx={`Day ${i + 1}`} text={s} />)}
            </Section>
          )}
        </div>
      )}

      {result?.raw && (
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 whitespace-pre-wrap text-[13px] text-neutral-700 mb-7">{result.raw}</div>
      )}

      {/* Conversation thread + follow-up input */}
      {result && (
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70" data-testid="insights-conversation">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-neutral-900">
              <span className="w-7 h-7 rounded-lg bg-blue-50 text-[#1B7BFF] flex items-center justify-center">
                <MessageSquare size={14} />
              </span>
              Keep the conversation going
            </div>
            <button
              type="button"
              onClick={startOver}
              data-testid="insights-start-over"
              className="text-[12px] font-medium text-neutral-500 hover:text-neutral-700 inline-flex items-center gap-1"
            >
              <RotateCcw size={11} /> Start over
            </button>
          </div>

          <p className="text-[13px] text-neutral-600 mb-4 leading-relaxed">
            Want to turn this into a content calendar? Draft posts for Day 1? Pick a path below — or ask Nova anything.
          </p>

          {/* Conversation messages */}
          {conversation.length > 0 && (
            <div
              ref={threadRef}
              className="max-h-[480px] overflow-y-auto mb-4 space-y-3 pr-1 -mr-1"
              data-testid="insights-thread"
            >
              {conversation.map((m, i) => (
                <Bubble key={i} role={m.role} content={m.content} />
              ))}
              {pending && (
                <div className="flex items-center gap-2 text-[12.5px] text-neutral-500 px-3 py-2">
                  <Loader2 size={12} className="animate-spin" /> Nova is thinking…
                </div>
              )}
            </div>
          )}

          {/* Follow-up suggestion chips */}
          {followUps.length > 0 && !pending && (
            <div className="flex flex-wrap gap-2 mb-4" data-testid="insights-followup-chips">
              {followUps.map((q, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => sendFollowup(q)}
                  data-testid={`insights-followup-chip-${i}`}
                  className="inline-flex items-center gap-1.5 text-[12.5px] font-medium border border-violet-300 text-violet-700 hover:bg-violet-50 px-3 h-8 rounded-full transition-colors"
                >
                  <Sparkles size={11} /> {q} <ArrowRight size={11} />
                </button>
              ))}
            </div>
          )}

          {/* Free-form follow-up input */}
          <form
            onSubmit={(e) => { e.preventDefault(); sendFollowup(draft); }}
            className="flex gap-2"
          >
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault(); sendFollowup(draft);
                }
              }}
              placeholder="Ask anything — e.g. 'Build me a 2-week calendar for the action plan'…"
              rows={2}
              data-testid="insights-followup-input"
              className="rounded-xl border-neutral-300 text-[14px] flex-1 resize-none"
              disabled={pending}
            />
            <button
              type="submit"
              disabled={pending || !draft.trim()}
              data-testid="insights-followup-submit"
              className="bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-40 text-white text-[13px] font-medium px-5 rounded-xl h-auto self-stretch min-w-[88px] inline-flex items-center justify-center gap-1"
            >
              {pending ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={14} />}
            </button>
          </form>
          <p className="text-[10.5px] text-neutral-400 mt-1.5 hidden sm:block">Press ⌘/Ctrl + Enter to send</p>
        </div>
      )}
    </DashboardLayout>
  );
};

const Section = ({ icon: Icon, title, color, tint, children }) => (
  <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
    <div className={`flex items-center gap-2 mb-4 font-semibold ${color}`}>
      <span className={`w-7 h-7 rounded-lg ${tint} flex items-center justify-center`}><Icon size={15} /></span>
      <span className="text-neutral-900 text-[15px]">{title}</span>
    </div>
    <div className="space-y-2">{children}</div>
  </div>
);

const Item = ({ idx, text }) => (
  <div className="flex items-start gap-3 text-[14px] text-neutral-800">
    <span className="min-w-[28px] h-6 px-2 rounded-md bg-neutral-100 text-neutral-700 text-[11px] font-semibold flex items-center justify-center shrink-0 mt-0.5">{idx}</span>
    <span className="leading-relaxed">{cleanMarkdown(text)}</span>
  </div>
);

const Bubble = ({ role, content }) => {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'bg-[#1B7BFF] text-white'
            : 'bg-neutral-100 text-neutral-800 border border-neutral-200/70'
        }`}
        data-testid={`bubble-${role}`}
      >
        {isUser ? content : cleanMarkdown(content)}
      </div>
    </div>
  );
};

// Strip the heaviest Markdown bits so the rendered text doesn't show literal
// `**bold**` and `## headers`. Lightweight, no extra deps.
function cleanMarkdown(s) {
  if (!s) return s;
  return String(s)
    .replace(/\*\*(.+?)\*\*/g, '$1')   // **bold**
    .replace(/__(.+?)__/g, '$1')        // __bold__
    .replace(/^#{1,6}\s+/gm, '')        // # headers
    .replace(/`([^`]+)`/g, '$1')        // `code`
    .trim();
}

export default Insights;
