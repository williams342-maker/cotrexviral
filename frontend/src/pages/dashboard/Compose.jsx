import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Sparkles, Send, Loader2, AlertTriangle, Wand2, Repeat } from 'lucide-react';
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
  const [suggestingTime, setSuggestingTime] = useState(false);
  const [aiTimeMeta, setAiTimeMeta] = useState(null); // { platform, day, hour }
  const [repeatWeekly, setRepeatWeekly] = useState(false);
  const [repeatWeeks, setRepeatWeeks] = useState(4);
  // Pinterest-specific publishing state. Surfaces only when Pinterest is selected.
  const [pinterestBoards, setPinterestBoards] = useState([]);
  const [boardsLoading, setBoardsLoading] = useState(false);
  const [pinBoardId, setPinBoardId] = useState('');
  const [pinImageUrl, setPinImageUrl] = useState('');
  const [pinLink, setPinLink] = useState('');
  const [pinTitle, setPinTitle] = useState('');

  const pinterestSelected = !!selected.pinterest;

  // Fetch the user's boards the first time Pinterest is selected, then cache.
  useEffect(() => {
    if (!pinterestSelected || pinterestBoards.length > 0 || boardsLoading) return;
    setBoardsLoading(true);
    axios.get(`${API}/oauth/pinterest/boards`, { withCredentials: true })
      .then((r) => {
        setPinterestBoards(r.data.boards || []);
        if ((r.data.boards || []).length && !pinBoardId) {
          setPinBoardId(r.data.boards[0].id);
        }
      })
      .catch((e) => {
        toast({
          title: 'Could not load Pinterest boards',
          description: e.response?.data?.detail || e.message,
        });
      })
      .finally(() => setBoardsLoading(false));
  }, [pinterestSelected]);

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

  const suggestOptimalTime = async () => {
    const platforms = Object.keys(selected).filter((k) => selected[k]);
    if (platforms.length !== 1) {
      toast({ title: 'Select exactly one channel for an AI time suggestion' });
      return;
    }
    setSuggestingTime(true);
    try {
      const r = await axios.post(
        `${API}/ai/optimal-times`,
        { platforms },
        { withCredentials: true }
      );
      const slot = (r.data.slots?.[platforms[0]] || [])[0];
      if (!slot) {
        toast({ title: 'No suggestion available' });
        return;
      }
      const d = new Date(slot.datetime);
      const pad = (n) => String(n).padStart(2, '0');
      const local = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      setScheduleAt(local);
      setAiTimeMeta({ platform: platforms[0], day: slot.day, hour: slot.hour });
      toast({
        title: `AI suggests ${d.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`,
        description: `Next best slot for ${platforms[0]}`,
      });
    } catch (e) {
      toast({ title: 'Could not fetch AI optimal time' });
    } finally {
      setSuggestingTime(false);
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
        if (repeatWeekly && repeatWeeks > 1) {
          payload.repeat_weeks = Math.min(12, Math.max(2, parseInt(repeatWeeks, 10) || 2));
        }
      }
      if (platforms.includes('pinterest')) {
        if (!pinImageUrl.trim()) {
          toast({ title: 'Pinterest needs an image URL', description: 'Pinterest requires an image for every Pin.' });
          setPublishing(false);
          return;
        }
        if (!pinBoardId) {
          toast({ title: 'Pick a Pinterest board' });
          setPublishing(false);
          return;
        }
        payload.media_url = pinImageUrl.trim();
        payload.pinterest_board_id = pinBoardId;
        if (pinLink.trim()) payload.pinterest_link = pinLink.trim();
        if (pinTitle.trim()) payload.pinterest_title = pinTitle.trim();
      }
      const r = await axios.post(`${API}/channels/publish`, payload, { withCredentials: true });
      const isScheduled = r.data.status === 'scheduled';
      const wasSeries = Array.isArray(r.data.ids) && r.data.ids.length > 1;
      toast({
        title: wasSeries
          ? `Scheduled ${r.data.ids.length} weekly posts starting ${new Date(scheduleAt).toLocaleDateString()}`
          : isScheduled
            ? `Scheduled for ${new Date(scheduleAt).toLocaleString()}`
            : `Published to ${platforms.length} channel${platforms.length > 1 ? 's' : ''}!`,
        description: 'MOCKED — stored in your feed/calendar.',
      });
      setContent('');
      setTopic('');
      setHashtags([]);
      setScheduleAt('');
      setAiTimeMeta(null);
      setRepeatWeekly(false);
    } catch (e) {
      toast({ title: 'Publishing failed' });
    } finally {
      setPublishing(false);
    }
  };

  const singleChannelSelected = Object.values(selected).filter(Boolean).length === 1;

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
          <button onClick={publish} disabled={publishing} className="mt-5 w-full inline-flex items-center justify-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[14px] font-medium h-11 rounded-xl disabled:opacity-60" data-testid="compose-publish-btn">
            {publishing ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            {publishing ? (scheduleAt ? 'Scheduling…' : 'Publishing…') : (scheduleAt ? 'Schedule' : 'Publish now')}
          </button>

          {pinterestSelected && (
            <div className="mt-4 rounded-2xl border border-rose-100 bg-rose-50/40 p-3.5 space-y-2.5" data-testid="compose-pinterest-block">
              <div className="text-[11px] uppercase tracking-wider text-rose-700 font-bold">📌 Pinterest details</div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Board *</label>
                {boardsLoading ? (
                  <div className="text-[12px] text-neutral-500 inline-flex items-center gap-1.5">
                    <Loader2 size={11} className="animate-spin" /> Loading your boards…
                  </div>
                ) : pinterestBoards.length === 0 ? (
                  <div className="text-[12px] text-rose-700">No boards found on your Pinterest account.</div>
                ) : (
                  <select
                    value={pinBoardId}
                    onChange={(e) => setPinBoardId(e.target.value)}
                    data-testid="compose-pin-board"
                    className="w-full h-9 rounded-lg border border-neutral-300 bg-white px-2 text-[12.5px]"
                  >
                    {pinterestBoards.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </select>
                )}
              </div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Image URL *</label>
                <Input
                  type="url"
                  value={pinImageUrl}
                  onChange={(e) => setPinImageUrl(e.target.value)}
                  placeholder="https://…/image.jpg"
                  data-testid="compose-pin-image"
                  className="h-9 rounded-lg border-neutral-300 text-[12.5px]"
                />
                <div className="text-[10.5px] text-neutral-500 mt-1">Required by Pinterest. Direct URL to a JPG/PNG.</div>
              </div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Destination link <span className="text-neutral-400">(optional)</span></label>
                <Input
                  type="url"
                  value={pinLink}
                  onChange={(e) => setPinLink(e.target.value)}
                  placeholder="https://yourshop.com/product"
                  data-testid="compose-pin-link"
                  className="h-9 rounded-lg border-neutral-300 text-[12.5px]"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Pin title <span className="text-neutral-400">(optional, ≤ 100 chars)</span></label>
                <Input
                  value={pinTitle}
                  onChange={(e) => setPinTitle(e.target.value.slice(0, 100))}
                  placeholder="Short, scroll-stopping title"
                  data-testid="compose-pin-title"
                  className="h-9 rounded-lg border-neutral-300 text-[12.5px]"
                />
              </div>
            </div>
          )}
          <div className="mt-3">
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11.5px] font-medium text-neutral-600 block">Schedule for later (optional)</label>
              {singleChannelSelected && (
                <button
                  type="button"
                  onClick={suggestOptimalTime}
                  disabled={suggestingTime}
                  data-testid="compose-ai-time-btn"
                  className="inline-flex items-center gap-1 text-[10.5px] font-semibold text-violet-700 hover:text-violet-900 disabled:opacity-60"
                  title="Auto-pick the next best posting slot from AI"
                >
                  {suggestingTime ? <Loader2 size={10} className="animate-spin" /> : <Wand2 size={10} />}
                  AI optimal time
                </button>
              )}
            </div>
            <Input
              type="datetime-local"
              value={scheduleAt}
              onChange={(e) => { setScheduleAt(e.target.value); setAiTimeMeta(null); }}
              className="h-10 rounded-xl border-neutral-300 text-[13px]"
              data-testid="compose-schedule-input"
            />
            {aiTimeMeta && (
              <div className="mt-1 inline-flex items-center gap-1 text-[10.5px] text-violet-700 font-medium" data-testid="compose-ai-time-meta">
                <Sparkles size={9} /> Picked by AI · {aiTimeMeta.day} {aiTimeMeta.hour}:00 (best for {aiTimeMeta.platform})
              </div>
            )}
            {scheduleAt && (
              <div className="mt-3 rounded-xl border border-violet-100 bg-violet-50/60 p-3" data-testid="compose-repeat-block">
                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={repeatWeekly}
                    onChange={(e) => setRepeatWeekly(e.target.checked)}
                    data-testid="compose-repeat-toggle"
                    className="w-4 h-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500"
                  />
                  <Repeat size={12} className="text-violet-600 shrink-0" />
                  <span className="text-[12.5px] text-violet-900 font-medium leading-snug">Repeat weekly</span>
                </label>
                {repeatWeekly && (
                  <div className="mt-2 flex items-center gap-2 pl-6.5">
                    <span className="text-[11.5px] text-violet-800">for</span>
                    <Input
                      type="number"
                      min={2}
                      max={12}
                      value={repeatWeeks}
                      onChange={(e) => setRepeatWeeks(e.target.value)}
                      data-testid="compose-repeat-weeks"
                      className="h-7 w-16 rounded-lg border-violet-200 text-[12.5px] text-center bg-white"
                    />
                    <span className="text-[11.5px] text-violet-800">weeks (max 12). Each instance posts at the same time, +7 days apart.</span>
                  </div>
                )}
              </div>
            )}
          </div>
          <p className="mt-3 text-[11.5px] text-neutral-500 text-center">MOCKED: posts are stored in your feed/calendar, not pushed to live platforms.</p>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Compose;
