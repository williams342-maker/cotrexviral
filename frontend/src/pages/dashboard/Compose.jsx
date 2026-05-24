import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Sparkles, Send, Loader2, AlertTriangle } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

const PLATFORM_LIMITS = {
  instagram: 2200, tiktok: 2200, x: 280, facebook: 63206, linkedin: 3000,
  youtube: 5000, pinterest: 500, threads: 500, reddit: 40000,
  substack: 100000, blogger: 100000,
};

const Compose = () => {
  const { toast } = useToast();
  const location = useLocation();
  const [topic, setTopic] = useState('');
  const [content, setContent] = useState(location.state?.draft || '');
  const [tone, setTone] = useState('friendly');
  const [platform, setPlatform] = useState(location.state?.platform || 'instagram');
  const [selected, setSelected] = useState({ instagram: true });
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [channels, setChannels] = useState([]);
  const [hashtags, setHashtags] = useState([]);
  const [scheduleAt, setScheduleAt] = useState('');

  useEffect(() => {
    axios.get(`${API}/channels`, { withCredentials: true })
      .then((r) => {
        setChannels(r.data);
        const init = {};
        r.data.filter((c) => c.connected).forEach((c) => { init[c.platform] = true; });
        if (Object.keys(init).length) setSelected(init);
      })
      .catch(() => {});
  }, []);

  const generate = async () => {
    if (!topic.trim()) {
      toast({ title: 'Add a topic first' });
      return;
    }
    setGenerating(true);
    try {
      const r = await axios.post(`${API}/ai/generate-post`, { topic, tone, platform }, { withCredentials: true });
      const caption = r.data.caption || '';
      const hook = r.data.hook ? r.data.hook + '\n\n' : '';
      const cta = r.data.cta ? '\n\n' + r.data.cta : '';
      setContent(`${hook}${caption}${cta}`);
      setHashtags(r.data.hashtags || []);
    } catch (e) {
      toast({ title: 'Generation failed' });
    } finally {
      setGenerating(false);
    }
  };

  const publish = async () => {
    const platforms = Object.keys(selected).filter((k) => selected[k]);
    if (!content.trim() || platforms.length === 0) {
      toast({ title: 'Add content and select at least one channel' });
      return;
    }
    setPublishing(true);
    try {
      const fullContent = hashtags.length
        ? `${content}\n\n${hashtags.map((h) => (h.startsWith('#') ? h : `#${h}`)).join(' ')}`
        : content;
      const payload = { content: fullContent, platforms };
      if (scheduleAt) {
        payload.scheduled_at = new Date(scheduleAt).toISOString();
      }
      const r = await axios.post(`${API}/channels/publish`, payload, { withCredentials: true });
      const isScheduled = r.data.status === 'scheduled';
      toast({
        title: isScheduled
          ? `Scheduled for ${new Date(scheduleAt).toLocaleString()}`
          : `Published to ${platforms.length} channel${platforms.length > 1 ? 's' : ''}!`,
        description: 'MOCKED — stored in your feed/calendar.',
      });
      setContent('');
      setTopic('');
      setHashtags([]);
      setScheduleAt('');
    } catch (e) {
      toast({ title: 'Publishing failed' });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <DashboardLayout title="Compose & Publish" subtitle="Generate a post with AI, pick your channels, and push it live.">
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left: Generator */}
        <div className="lg:col-span-2 bg-white rounded-3xl p-6 border border-neutral-200/70 space-y-4">
          <div className="grid md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">Topic / Listing</label>
              <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="New summer yoga mat launch" className="h-11 rounded-xl border-neutral-300" />
            </div>
            <div>
              <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">Tone</label>
              <Select value={tone} onValueChange={setTone}>
                <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="friendly">Friendly</SelectItem>
                  <SelectItem value="professional">Professional</SelectItem>
                  <SelectItem value="playful">Playful</SelectItem>
                  <SelectItem value="inspirational">Inspirational</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <button onClick={generate} disabled={generating} className="inline-flex items-center gap-2 bg-neutral-900 hover:bg-neutral-800 text-white text-[13px] font-medium px-4 h-10 rounded-xl disabled:opacity-60">
            {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} Generate with AI
          </button>

          <div>
            <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">Post content</label>
            <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={9} placeholder="Your post will appear here…" className="rounded-xl border-neutral-300 text-[14.5px] leading-relaxed" />
            {(() => {
              const len = (content + (hashtags.length ? '\n\n' + hashtags.map(h => h.startsWith('#') ? h : '#' + h).join(' ') : '')).length;
              const selectedPlatforms = Object.keys(selected).filter((k) => selected[k]);
              const tightestLimit = selectedPlatforms.length
                ? Math.min(...selectedPlatforms.map((p) => PLATFORM_LIMITS[p] || 2000))
                : null;
              const tightestPlatform = selectedPlatforms.length
                ? selectedPlatforms.reduce((a, b) => (PLATFORM_LIMITS[a] || 9999) < (PLATFORM_LIMITS[b] || 9999) ? a : b)
                : null;
              if (!tightestLimit) return <div className="text-[11.5px] text-neutral-500 mt-1.5">{len.toLocaleString()} characters</div>;
              const over = len > tightestLimit;
              return (
                <div className={`mt-1.5 flex items-center gap-1.5 text-[11.5px] ${over ? 'text-rose-600 font-medium' : 'text-neutral-500'}`}>
                  {over && <AlertTriangle size={12} />}
                  {len.toLocaleString()} / {tightestLimit.toLocaleString()} chars
                  <span className="text-neutral-400">(limited by {tightestPlatform})</span>
                </div>
              );
            })()}
          </div>

          {hashtags.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {hashtags.map((h, i) => (
                <span key={i} className="px-2.5 py-1 rounded-full bg-sky-50 text-sky-700 text-[12px] font-medium border border-sky-100">
                  {h.startsWith('#') ? h : `#${h}`}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Right: Channels + publish */}
        <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 h-fit">
          <h3 className="text-[15px] font-semibold mb-1">Channels</h3>
          <p className="text-[12.5px] text-neutral-500 mb-4">Pick where to publish</p>
          <div className="space-y-2">
            {channels.length === 0 && (
              <div className="text-[13px] text-neutral-500 p-3 bg-neutral-50 rounded-xl">No channels yet. <a href="/dashboard/channels" className="text-[#1B7BFF] font-medium">Connect one →</a></div>
            )}
            {channels.filter((c) => c.connected).map((c) => (
              <label key={c.platform} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-neutral-50 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!selected[c.platform]}
                  onChange={(e) => setSelected({ ...selected, [c.platform]: e.target.checked })}
                  className="w-4 h-4 accent-[#1B7BFF]"
                />
                <span className="text-[14px] capitalize flex-1">{c.platform}</span>
                <span className="text-[11px] text-neutral-500">{c.handle}</span>
              </label>
            ))}
          </div>
          <button onClick={publish} disabled={publishing} className="mt-5 w-full inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[14px] font-medium h-11 rounded-xl disabled:opacity-60">
            {publishing ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            {publishing ? (scheduleAt ? 'Scheduling…' : 'Publishing…') : (scheduleAt ? 'Schedule' : 'Publish now')}
          </button>
          <div className="mt-3">
            <label className="text-[11.5px] font-medium text-neutral-600 mb-1 block">Schedule for later (optional)</label>
            <Input type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} className="h-10 rounded-xl border-neutral-300 text-[13px]" />
          </div>
          <p className="mt-3 text-[11.5px] text-neutral-500 text-center">MOCKED: posts are stored in your feed/calendar, not pushed to live platforms.</p>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Compose;
