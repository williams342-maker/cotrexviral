import React, { useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Input } from '../../components/ui/input';
import { Radar, Loader2, Lightbulb, FileText, Send, Copy } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import { useNavigate } from 'react-router-dom';

const SiteScan = () => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const { toast } = useToast();
  const navigate = useNavigate();

  const run = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setReport(null);
    try {
      const res = await axios.post(`${API}/ai/site-scan`, { url }, { withCredentials: true });
      setReport(res.data.report);
    } catch (err) {
      toast({ title: 'Scan failed', description: err.response?.data?.detail || 'Try again' });
    } finally {
      setLoading(false);
    }
  };

  const pushToCompose = (idea) => {
    navigate('/dashboard/compose', { state: { draft: `${idea.title}\n\n${idea.caption}`, platform: idea.platform } });
  };

  return (
    <DashboardLayout title="Site Scan" subtitle="Nova scans your site for new listings and generates post ideas to publish.">
      <form onSubmit={run} className="bg-white rounded-3xl p-6 border border-neutral-200/70 mb-7">
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
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Radar size={16} />}
            {loading ? 'Scanning…' : 'Scan Site'}
          </button>
        </div>
      </form>

      {loading && (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <Loader2 className="animate-spin text-[#1B7BFF] mx-auto mb-3" size={28} />
          <p className="text-neutral-700 font-medium">Scanning your site…</p>
        </div>
      )}

      {report && !report.raw && (
        <div className="space-y-5">
          {report.summary && (
            <div className="rounded-3xl p-6 border border-blue-500/30" style={{ background: 'rgba(37, 99, 235, 0.12)' }}>
              <div className="flex items-center gap-2 text-[12px] uppercase tracking-wider font-semibold mb-2" style={{ color: '#93C5FD' }}>
                <Lightbulb size={14} /> Summary
              </div>
              <p className="text-[15px] leading-relaxed" style={{ color: '#F4F4F5' }}>{report.summary}</p>
            </div>
          )}

          {report.notable_items?.length > 0 && (
            <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
              <div className="flex items-center gap-2 text-[15px] font-semibold mb-4">
                <FileText size={17} className="text-emerald-600" /> Detected on your site
              </div>
              <ul className="space-y-2">
                {report.notable_items.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-[14px] text-neutral-800">
                    <span className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-700 text-[11px] font-semibold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.post_ideas?.length > 0 && (
            <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
              <div className="flex items-center gap-2 text-[15px] font-semibold mb-4">
                <Send size={17} className="text-violet-600" /> Suggested social posts
              </div>
              <div className="grid md:grid-cols-3 gap-3">
                {report.post_ideas.map((p, i) => (
                  <div key={i} className="rounded-2xl p-4 border border-violet-500/30" style={{ background: 'rgba(124, 58, 237, 0.12)' }}>
                    <div className="text-[11px] uppercase tracking-wider font-semibold mb-1" style={{ color: '#C4B5FD' }}>{p.platform}</div>
                    <div className="text-[14px] font-semibold mb-2" style={{ color: '#F4F4F5' }}>{p.title}</div>
                    <p className="text-[13px] leading-relaxed mb-3" style={{ color: '#D4D4D8' }}>{p.caption}</p>
                    <button onClick={() => pushToCompose(p)} className="w-full text-[12px] font-medium border border-violet-400/40 hover:border-violet-300/60 px-3 py-2 rounded-lg inline-flex items-center justify-center gap-1.5 transition-colors" style={{ background: 'rgba(124, 58, 237, 0.15)', color: '#DDD6FE' }}>
                      <Copy size={12} /> Use this draft
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.improvements?.length > 0 && (
            <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
              <div className="flex items-center gap-2 text-[15px] font-semibold mb-4">
                <Lightbulb size={17} className="text-amber-600" /> Improvement opportunities
              </div>
              <ul className="space-y-2">
                {report.improvements.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-[14px] text-neutral-800">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-2 shrink-0" /> {s}
                  </li>
                ))}
              </ul>
            </div>
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

export default SiteScan;
