import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Loader2, Send } from 'lucide-react';

const Posts = () => {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/posts`, { withCredentials: true })
      .then((r) => setPosts(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardLayout title="Published Posts" subtitle="Everything Automatex has shipped on your behalf.">
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
            <div key={p.id} className="bg-white rounded-2xl p-5 border border-neutral-200/70">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                {p.platforms.map((pl) => (
                  <span key={pl} className="text-[11px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-[#1B7BFF]/10 text-[#1B7BFF] font-semibold">{pl}</span>
                ))}
                <span className="text-[11px] text-emerald-600 font-semibold ml-1">● {p.status}</span>
                <span className="text-[11px] text-neutral-400 ml-auto">{new Date(p.created_at).toLocaleString()}</span>
              </div>
              <pre className="text-[14px] text-neutral-800 whitespace-pre-wrap font-sans leading-relaxed">{p.content}</pre>
            </div>
          ))}
        </div>
      )}
    </DashboardLayout>
  );
};

export default Posts;
