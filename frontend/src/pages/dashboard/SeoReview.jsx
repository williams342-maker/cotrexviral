import React, { useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { Search, Loader2, AlertTriangle, CheckCircle2, Lightbulb, Tag } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const SeoReview = () => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const { toast } = useToast();

  const handleRun = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setReport(null);
    try {
      const res = await axios.post(`${API}/ai/execute`, {
        task_type: 'seo_recommendation',
        user_goal: `Audit ${url} and prioritize the SEO improvements.`,
        context: { url },
      }, { withCredentials: true });
      setReport(res.data.result);
    } catch (err) {
      toast({ title: 'Failed', description: err.response?.data?.detail || 'Could not run audit' });
    } finally {
      setLoading(false);
    }
  };

  const sevColor = (s) => ({
    high: 'bg-rose-100 text-rose-700 border-rose-200',
    medium: 'bg-amber-100 text-amber-700 border-amber-200',
    low: 'bg-sky-100 text-sky-700 border-sky-200',
  }[s] || 'bg-neutral-100 text-neutral-700');

  return (
    <DashboardLayout title="SEO Review" subtitle="Run an AI-powered audit on any URL. Sam analyzes content, structure, and opportunities.">
      <form onSubmit={handleRun} className="bg-white rounded-3xl p-6 border border-neutral-200/70 mb-7">
        <div className="flex flex-col md:flex-row gap-3">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://yourwebsite.com"
            className="h-12 rounded-xl border-neutral-300 text-[15px]"
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white px-7 h-12 rounded-xl text-[14px] font-medium whitespace-nowrap"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            {loading ? 'Auditing…' : 'Run Audit'}
          </button>
        </div>
        <p className="mt-3 text-[13px] text-neutral-500">We fetch your page, analyze content & meta, then return scored insights.</p>
      </form>

      {loading && (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 flex flex-col items-center justify-center text-center">
          <Loader2 className="animate-spin text-[#1B7BFF] mb-3" size={28} />
          <p className="text-neutral-700 font-medium">Sam is analyzing your site…</p>
          <p className="text-[13px] text-neutral-500 mt-1">This usually takes 10–20 seconds.</p>
        </div>
      )}

      {report && !report.raw && (
        <div className="space-y-5">
          {/* Score */}
          <div className="bg-white rounded-3xl p-7 border border-neutral-200/70 flex items-center gap-7">
            <ScoreRing value={report.score || 0} />
            <div>
              <div className="text-[12px] uppercase tracking-wider text-neutral-500 font-medium">SEO Score</div>
              <div className="text-4xl font-medium tracking-tight mt-1">{report.score || 0}<span className="text-xl text-neutral-400">/100</span></div>
              <div className="text-[13px] text-neutral-600 mt-1">For {url}</div>
            </div>
          </div>

          {/* Strengths */}
          {report.strengths?.length > 0 && (
            <Section icon={CheckCircle2} title="Top strengths" color="text-emerald-600">
              <ul className="space-y-2">
                {report.strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-[14px] text-neutral-800">
                    <CheckCircle2 size={16} className="text-emerald-500 mt-0.5 shrink-0" />
                    {s}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Issues */}
          {report.issues?.length > 0 && (
            <Section icon={AlertTriangle} title="Issues found" color="text-rose-600">
              <div className="space-y-3">
                {report.issues.map((it, i) => (
                  <div key={i} className="border border-neutral-200 rounded-2xl p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${sevColor(it.severity)}`}>{it.severity}</span>
                      <span className="text-[14.5px] font-semibold">{it.title}</span>
                    </div>
                    <p className="text-[13.5px] text-neutral-600 leading-relaxed">{it.fix}</p>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Recommendations */}
          {report.recommendations?.length > 0 && (
            <Section icon={Lightbulb} title="Quick-win recommendations" color="text-amber-600">
              <ul className="space-y-2">
                {report.recommendations.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-[14px] text-neutral-800">
                    <span className="w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-[11px] font-semibold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                    {s}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {/* Keywords */}
          {report.keywords?.length > 0 && (
            <Section icon={Tag} title="Suggested keywords" color="text-violet-600">
              <div className="flex flex-wrap gap-2">
                {report.keywords.map((k, i) => (
                  <span key={i} className="px-3 py-1.5 rounded-full bg-violet-50 text-violet-700 text-[13px] font-medium border border-violet-100">
                    {k}
                  </span>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}

      {report?.raw && (
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 whitespace-pre-wrap text-[13px] text-neutral-700">
          {report.raw}
        </div>
      )}
    </DashboardLayout>
  );
};

const ScoreRing = ({ value }) => {
  const r = 36;
  const c = 2 * Math.PI * r;
  const off = c - (value / 100) * c;
  const color = value >= 75 ? '#10b981' : value >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <svg width="96" height="96" viewBox="0 0 96 96">
      <circle cx="48" cy="48" r={r} stroke="#f1f1ef" strokeWidth="10" fill="none" />
      <circle
        cx="48" cy="48" r={r}
        stroke={color}
        strokeWidth="10"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={off}
        transform="rotate(-90 48 48)"
        style={{ transition: 'stroke-dashoffset 0.8s ease' }}
      />
    </svg>
  );
};

const Section = ({ icon: Icon, title, color, children }) => (
  <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
    <div className={`flex items-center gap-2 mb-4 font-semibold ${color}`}>
      <Icon size={17} />
      <span className="text-neutral-900 text-[15px]">{title}</span>
    </div>
    {children}
  </div>
);

export default SeoReview;
