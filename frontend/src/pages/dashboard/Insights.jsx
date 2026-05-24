import React, { useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Textarea } from '../../components/ui/textarea';
import { Sparkles, Loader2, TrendingUp, Calendar, Lightbulb } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const Insights = () => {
  const [context, setContext] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const { toast } = useToast();

  const run = async (e) => {
    e.preventDefault();
    if (!context.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post(`${API}/ai/insights`, { context }, { withCredentials: true });
      setResult(res.data.insights);
    } catch (err) {
      toast({ title: 'Failed', description: err.response?.data?.detail || 'Try again' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardLayout title="AI Marketing Insights" subtitle="Tell Nova about your business and get tailored insights, trends, and a 1-week action plan.">
      <form onSubmit={run} className="bg-white rounded-3xl p-6 border border-neutral-200/70 mb-7">
        <Textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="e.g. We sell sustainable yoga mats to women 25-40 in North America. Currently 5k Instagram followers, posting 3x/week. Struggling with engagement and ROAS."
          rows={5}
          className="rounded-xl border-neutral-300 mb-3 text-[14.5px]"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white px-7 h-11 rounded-xl text-[14px] font-medium"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          {loading ? 'Thinking…' : 'Generate Insights'}
        </button>
      </form>

      {loading && (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Loader2 className="animate-spin text-[#1B7BFF] mx-auto mb-3" size={28} />
          <p className="text-neutral-700 font-medium">Nova is thinking…</p>
        </div>
      )}

      {result && !result.raw && (
        <div className="space-y-5">
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
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 whitespace-pre-wrap text-[13px] text-neutral-700">{result.raw}</div>
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
    <span className="leading-relaxed">{text}</span>
  </div>
);

export default Insights;
