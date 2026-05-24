import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Calendar as CalIcon, ChevronLeft, ChevronRight,
  Instagram, Twitter, Facebook, Linkedin, Youtube, Plus, X as XIcon,
} from 'lucide-react';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { useToast } from '../../hooks/use-toast';

const PLATFORM_ROWS = [
  { id: 'linkedin', label: 'LinkedIn', icon: Linkedin, color: 'text-sky-700 bg-sky-50' },
  { id: 'x', label: 'X', icon: Twitter, color: 'text-neutral-900 bg-neutral-100' },
  { id: 'instagram', label: 'Instagram', icon: Instagram, color: 'text-pink-600 bg-pink-50' },
  { id: 'pinterest', label: 'Pinterest', icon: () => <span className="text-[11px] font-bold">P</span>, color: 'text-red-600 bg-red-50' },
  { id: 'tiktok', label: 'TikTok', icon: () => <span className="text-[11px] font-bold">T</span>, color: 'text-neutral-900 bg-neutral-100' },
  { id: 'facebook', label: 'Facebook', icon: Facebook, color: 'text-blue-700 bg-blue-50' },
  { id: 'youtube', label: 'YouTube', icon: Youtube, color: 'text-red-700 bg-red-50' },
  { id: 'threads', label: 'Threads', icon: () => <span className="text-[11px] font-bold">@</span>, color: 'text-neutral-900 bg-neutral-100' },
];

const MarketingCalendar = () => {
  const { toast } = useToast();
  const [view, setView] = useState('week');
  const [cursor, setCursor] = useState(new Date());
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(null);

  const range = useMemo(() => {
    const start = new Date(cursor);
    if (view === 'week') {
      start.setDate(start.getDate() - start.getDay()); // Sunday
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(end.getDate() + 7);
      return { start, end, days: 7 };
    }
    // month
    start.setDate(1);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setMonth(end.getMonth() + 1);
    return { start, end, days: Math.round((end - start) / (1000 * 60 * 60 * 24)) };
  }, [cursor, view]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/posts/scheduled?start=${range.start.toISOString()}&end=${range.end.toISOString()}`,
        { withCredentials: true }
      );
      setPosts(r.data);
    } catch (e) {}
    setLoading(false);
  };
  useEffect(() => { load(); }, [cursor, view]);

  const days = useMemo(() => {
    const arr = [];
    for (let i = 0; i < range.days; i++) {
      const d = new Date(range.start);
      d.setDate(d.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [range]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const cellKey = (platform, date) => `${platform}-${date.toISOString().slice(0, 10)}`;
  const postsByCell = useMemo(() => {
    const map = {};
    posts.forEach((p) => {
      const d = new Date(p.scheduled_at);
      const dKey = d.toISOString().slice(0, 10);
      p.platforms.forEach((pl) => {
        const k = `${pl}-${dKey}`;
        if (!map[k]) map[k] = [];
        map[k].push(p);
      });
    });
    return map;
  }, [posts]);

  const navigate = (dir) => {
    const d = new Date(cursor);
    if (view === 'week') d.setDate(d.getDate() + dir * 7);
    else d.setMonth(d.getMonth() + dir);
    setCursor(d);
  };

  const cancelPost = async (id) => {
    try {
      await axios.delete(`${API}/posts/scheduled/${id}`, { withCredentials: true });
      toast({ title: 'Scheduled post cancelled' });
      load();
    } catch (e) {}
  };

  return (
    <DashboardLayout title="Marketing Calendar" subtitle="Schedule and visualize your posts across every channel.">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(-1)} className="w-9 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 flex items-center justify-center"><ChevronLeft size={16} /></button>
          <button onClick={() => setCursor(new Date())} className="px-4 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 text-[13px] font-medium inline-flex items-center gap-1.5">
            <CalIcon size={13} /> Today
          </button>
          <button onClick={() => navigate(1)} className="w-9 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 flex items-center justify-center"><ChevronRight size={16} /></button>
          <div className="ml-3 text-[15px] font-semibold">
            {view === 'week'
              ? `${range.start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${new Date(range.end - 1).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`
              : range.start.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
            }
          </div>
        </div>
        <div className="inline-flex bg-white border border-neutral-200 rounded-lg p-1">
          <button onClick={() => setView('month')} className={`px-3 h-8 rounded-md text-[13px] font-medium transition-colors ${view === 'month' ? 'bg-neutral-900 text-white' : 'text-neutral-600 hover:bg-neutral-50'}`}>Month</button>
          <button onClick={() => setView('week')} className={`px-3 h-8 rounded-md text-[13px] font-medium transition-colors ${view === 'week' ? 'bg-[#1B7BFF] text-white' : 'text-neutral-600 hover:bg-neutral-50'}`}>Week</button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-x-auto">
          <div className="min-w-[900px]">
            {/* Header row with dates */}
            <div className="grid border-b border-neutral-200/70" style={{ gridTemplateColumns: `120px repeat(${days.length}, minmax(0, 1fr))` }}>
              <div className="p-3 text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">Channel</div>
              {days.map((d) => {
                const isToday = d.getTime() === today.getTime();
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <div key={d.toISOString()} className={`p-3 text-center ${isToday ? 'bg-emerald-50/50' : isWeekend ? 'bg-rose-50/20' : ''}`}>
                    <div className={`text-2xl font-medium tracking-tight ${isToday ? 'text-emerald-700' : isWeekend && d.getDay() === 0 ? 'text-rose-500' : 'text-neutral-900'}`}>{d.getDate()}</div>
                    <div className={`text-[10.5px] uppercase tracking-wider mt-0.5 ${isToday ? 'text-emerald-700 font-semibold' : 'text-neutral-500'}`}>{d.toLocaleDateString(undefined, { weekday: 'short' })}</div>
                  </div>
                );
              })}
            </div>

            {/* Platform rows */}
            {PLATFORM_ROWS.map((p) => {
              const PIcon = p.icon;
              return (
                <div key={p.id} className="grid border-b border-neutral-100 last:border-0" style={{ gridTemplateColumns: `120px repeat(${days.length}, minmax(0, 1fr))` }}>
                  <div className="p-3 flex items-center gap-2 border-r border-neutral-100">
                    <div className={`w-7 h-7 rounded-lg ${p.color} flex items-center justify-center`}>
                      <PIcon size={13} />
                    </div>
                    <span className="text-[13px] font-medium">{p.label}</span>
                  </div>
                  {days.map((d) => {
                    const isToday = d.getTime() === today.getTime();
                    const cellPosts = postsByCell[cellKey(p.id, d)] || [];
                    const isPast = d < today;
                    return (
                      <div key={d.toISOString()} className={`p-2 border-r border-neutral-100 last:border-0 min-h-[80px] group relative ${isToday ? 'bg-emerald-50/30' : isPast ? 'bg-neutral-50/40' : ''}`}>
                        {cellPosts.map((post) => (
                          <div key={post.id} className="mb-1 px-2 py-1.5 rounded-md bg-[#1B7BFF]/10 border border-[#1B7BFF]/20 text-[11px] cursor-pointer group/post">
                            <div className="flex items-start gap-1">
                              <span className="line-clamp-2 flex-1 text-[#1B7BFF] font-medium">{post.content.slice(0, 40)}</span>
                              <button onClick={(e) => { e.stopPropagation(); cancelPost(post.id); }} className="opacity-0 group-hover/post:opacity-100 text-rose-500"><XIcon size={10} /></button>
                            </div>
                            <span className="inline-block mt-0.5 text-[9px] uppercase tracking-wider font-semibold text-[#1B7BFF]/70">Scheduled</span>
                          </div>
                        ))}
                        {!isPast && (
                          <button
                            onClick={() => setComposing({ platform: p.id, date: d })}
                            className="opacity-0 group-hover:opacity-100 absolute inset-0 m-1 rounded-md border-2 border-dashed border-[#1B7BFF]/40 text-[#1B7BFF] flex items-center justify-center transition-opacity"
                            title="Schedule a post"
                          >
                            <Plus size={14} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {composing && (
        <ScheduleModal
          platform={composing.platform}
          date={composing.date}
          onClose={() => setComposing(null)}
          onCreated={() => { setComposing(null); load(); }}
        />
      )}
    </DashboardLayout>
  );
};

const ScheduleModal = ({ platform, date, onClose, onCreated }) => {
  const { toast } = useToast();
  const [content, setContent] = useState('');
  const [time, setTime] = useState('10:00');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const [hh, mm] = time.split(':');
      const at = new Date(date);
      at.setHours(parseInt(hh, 10), parseInt(mm, 10), 0, 0);
      await axios.post(`${API}/channels/publish`, {
        content,
        platforms: [platform],
        scheduled_at: at.toISOString(),
      }, { withCredentials: true });
      toast({ title: 'Post scheduled', description: `${platform} • ${at.toLocaleString()}` });
      onCreated();
    } catch (e) {
      toast({ title: 'Failed to schedule' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-xl font-semibold tracking-tight mb-1">Schedule a post</h3>
        <p className="text-[13px] text-neutral-500 mb-4">For <span className="font-medium capitalize text-neutral-700">{platform}</span> on {date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
        <form onSubmit={submit} className="space-y-3">
          <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={5} placeholder="Write your post…" required className="rounded-xl border-neutral-300" />
          <div>
            <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">Time</label>
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="h-11 rounded-xl border-neutral-300 w-40" required />
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100">Cancel</button>
            <button type="submit" disabled={busy} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white text-[13px] font-medium px-5 h-10 rounded-xl">
              {busy ? <Loader2 size={14} className="animate-spin" /> : 'Schedule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default MarketingCalendar;
