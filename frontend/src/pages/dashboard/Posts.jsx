import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Send, RefreshCw, Eye, Bookmark, MousePointer, ExternalLink } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const Posts = () => {
  const { toast } = useToast();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => {
    return axios.get(`${API}/posts`, { withCredentials: true })
      .then((r) => setPosts(r.data))
      .catch(() => {});
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const refreshMetrics = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const r = await axios.post(`${API}/posts/metrics/refresh`, {}, { withCredentials: true });
      await load();
      toast({
        title: r.data.refreshed > 0 ? `Refreshed metrics for ${r.data.refreshed} post${r.data.refreshed === 1 ? '' : 's'}` : 'Metrics are up to date',
        description: 'Pinterest is live. TikTok / LinkedIn / Meta coming soon.',
      });
    } catch (e) {
      toast({ title: 'Refresh failed', description: e.response?.data?.detail || e.message });
    }
    setRefreshing(false);
  };

  return (
    <DashboardLayout
      title="Published Posts"
      subtitle="Everything CortexViral has shipped on your behalf."
      headerExtra={
        <button
          onClick={refreshMetrics}
          disabled={refreshing || posts.length === 0}
          data-testid="posts-refresh-metrics"
          className="inline-flex items-center gap-1.5 text-[12.5px] font-medium bg-white/[0.04] hover:bg-white/10 border border-white/10 text-zinc-200 px-3.5 h-9 rounded-lg disabled:opacity-40"
        >
          {refreshing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh metrics
        </button>
      }
    >
      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : posts.length === 0 ? (
        <div className="bg-white rounded-3xl p-10 border border-neutral-200/70 text-center">
          <div className="w-12 h-12 rounded-full bg-neutral-100 flex items-center justify-center mx-auto mb-3">
            <Send className="text-neutral-400" size={20} />
          </div>
          <p className="text-neutral-700 font-medium">No posts yet</p>
          <p className="text-[13px] text-neutral-500 mt-1">Head to Compose & Publish to ship your first one.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {posts.map((p) => (
            <div key={p.id} className="bg-white rounded-2xl p-5 border border-neutral-200/70" data-testid={`post-card-${p.id}`}>
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                {p.platforms.map((pl) => (
                  <span key={pl} className="text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#1B7BFF]/10 text-[#1B7BFF] font-semibold">{pl}</span>
                ))}
                <span className="text-[11px] text-emerald-600 font-semibold ml-1">● {p.status}</span>
                <span className="text-[11px] text-neutral-400 ml-auto">{new Date(p.created_at).toLocaleString()}</span>
              </div>
              <pre className="text-[14px] text-neutral-800 whitespace-pre-wrap font-sans leading-relaxed">{p.content}</pre>
              <PostMetricsRow post={p} />
            </div>
          ))}
        </div>
      )}
    </DashboardLayout>
  );
};

const PostMetricsRow = ({ post }) => {
  const metrics = post.metrics || {};
  const dispatch = post.dispatch || {};
  const platforms = Object.keys(metrics).filter((k) => k !== 'last_refreshed_at');

  // Build display rows in this order: live-analytics first (Pinterest), then
  // platforms where we have a successful dispatch but no analytics yet.
  const dispatched = Object.keys(dispatch).filter((p) => dispatch[p]?.ok);
  const all = Array.from(new Set([...platforms, ...dispatched]));

  if (all.length === 0) return null;

  return (
    <div className="mt-4 pt-4 border-t border-neutral-200/70 flex flex-wrap gap-2" data-testid={`post-metrics-${post.id}`}>
      {all.map((plat) => {
        const m = metrics[plat];
        const d = dispatch[plat] || {};
        if (plat === 'pinterest' && m) {
          return (
            <a
              key={plat}
              href={d.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-xl px-3 py-2 text-[12px] text-neutral-800 transition-colors"
              data-testid="post-metrics-pinterest"
            >
              <span className="text-[10.5px] uppercase tracking-wider font-bold text-rose-700">Pinterest</span>
              <span className="inline-flex items-center gap-1"><Eye size={11} className="text-neutral-500" /> {m.impressions.toLocaleString()}</span>
              <span className="inline-flex items-center gap-1"><Bookmark size={11} className="text-neutral-500" /> {m.saves.toLocaleString()}</span>
              <span className="inline-flex items-center gap-1"><MousePointer size={11} className="text-neutral-500" /> {m.clicks.toLocaleString()}</span>
              {d.permalink && <ExternalLink size={11} className="text-neutral-400" />}
            </a>
          );
        }
        if (d.ok) {
          return (
            <span
              key={plat}
              className="inline-flex items-center gap-2 bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-[12px] text-neutral-500"
              data-testid={`post-metrics-${plat}-pending`}
            >
              <span className="text-[10.5px] uppercase tracking-wider font-bold text-neutral-600">{plat}</span>
              <span className="text-neutral-400">Analytics coming soon</span>
            </span>
          );
        }
        return null;
      })}
      {metrics.last_refreshed_at && (
        <span className="text-[10.5px] text-neutral-400 self-center ml-auto">
          Updated {new Date(metrics.last_refreshed_at).toLocaleString()}
        </span>
      )}
    </div>
  );
};

export default Posts;
