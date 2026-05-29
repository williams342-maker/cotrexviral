import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Sparkles, Send, Loader2, AlertTriangle, Wand2, Repeat, Layers } from 'lucide-react';
import { useToast } from '../../hooks/use-toast';
import FeedbackInsights from '../../components/FeedbackInsights';

const PLATFORM_LIMITS = {
  instagram: 2200, tiktok: 2200, x: 280, facebook: 63206, linkedin: 3000,
  youtube: 5000, pinterest: 500, threads: 500, reddit: 40000,
  substack: 100000, blogger: 100000,
};

const Compose = () => {
  const { toast } = useToast();
  const location = useLocation();
  // Initial values can arrive from either:
  //   • react-router `state` (e.g., regenerate-from-post, posts page)
  //   • URL query params (`?content=&platform=&source=trend`) — used by
  //     the Trends page "Open in Compose" CTA on signal drafts.
  const initialParams = new URLSearchParams(location.search);
  const initialContent = location.state?.draft ?? initialParams.get('content') ?? '';
  const initialPlatform = location.state?.platform ?? initialParams.get('platform') ?? 'instagram';
  const initialSource = initialParams.get('source');  // e.g., "trend"
  // Optional campaign link arriving from CampaignDetail's "New post" CTA.
  // Persists for the life of this Compose session so every publish or
  // schedule call carries it through to the posts collection.
  const initialCampaignId = initialParams.get('campaign_id') || null;
  const [topic, setTopic] = useState('');
  const [content, setContent] = useState(initialContent);
  const [tone, setTone] = useState('friendly');
  const [platform, setPlatform] = useState(initialPlatform);
  // The campaign this Compose session is attached to (or null).
  const [campaign, setCampaign] = useState(null);
  // Pre-select the incoming platform so the user doesn't have to tick
  // its checkbox after landing here from Trends/Posts.
  const [selected, setSelected] = useState(() => {
    const init = { instagram: true };
    if (initialPlatform && initialPlatform !== 'instagram') {
      init[initialPlatform] = true;
    }
    return init;
  });
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
  // Carousel pins: additional images beyond `pinImageUrl`. Pinterest caps
  // a carousel at 5 total images, so we allow up to 4 extras here.
  const [pinExtraImages, setPinExtraImages] = useState([]);
  const [pinLink, setPinLink] = useState('');
  const [pinTitle, setPinTitle] = useState('');
  // YouTube-specific publishing state. Surfaces only when YouTube is selected.
  const [ytVideoUrl, setYtVideoUrl] = useState('');
  const [ytTitle, setYtTitle] = useState('');
  const [ytPrivacy, setYtPrivacy] = useState('private');
  const [ytUploading, setYtUploading] = useState(false);
  const [ytUploadName, setYtUploadName] = useState('');

  const pinterestSelected = !!selected.pinterest;
  const youtubeSelected = !!selected.youtube;

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
        // Start with all the user's connected platforms ticked, then
        // ALSO preserve any platform we pre-selected from the route
        // (URL `?platform=` / nav state) so the trend-draft handoff
        // doesn't get clobbered. If no channels are connected yet we
        // fall back to whatever the route asked for.
        const init = {};
        r.data.filter((c) => c.connected).forEach((c) => { init[c.platform] = true; });
        setSelected((prev) => {
          const merged = { ...init };
          for (const [k, v] of Object.entries(prev || {})) {
            if (v) merged[k] = true;
          }
          return Object.keys(merged).length ? merged : { instagram: true };
        });
      })
      .catch(() => {});
  }, []);

  // One-time: when arriving from the Trends "Open in Compose" CTA,
  // announce it and strip the query string so a refresh doesn't keep
  // re-prefilling. Runs once on mount only.
  useEffect(() => {
    if (initialSource === 'trend' && initialContent) {
      toast({
        title: 'Draft loaded from a trend',
        description: 'Nova drafted this from a viral signal. Edit before publishing.',
      });
    }
    if (initialParams.get('content') || initialParams.get('platform') || initialParams.get('source') || initialParams.get('campaign_id')) {
      const url = new URL(window.location.href);
      url.search = '';
      window.history.replaceState(null, '', url.toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Resolve `?campaign_id=` once — pull the campaign's brief so the topic
  // input is pre-populated and the user sees what they're writing FOR.
  useEffect(() => {
    if (!initialCampaignId) return;
    let cancelled = false;
    axios.get(`${API}/campaigns/${initialCampaignId}`, { withCredentials: true })
      .then((r) => {
        if (cancelled) return;
        const c = r.data;
        setCampaign({ id: c.id, name: c.name, goal: c.custom_goal || c.goal, audience: c.audience });
        // Only auto-fill the topic if the user hasn't already typed something.
        setTopic((t) => t || `${c.name} — ${c.custom_goal || c.goal}`);
        toast({
          title: 'Composing for a campaign',
          description: `Posts you publish here will link to "${c.name}".`,
        });
      })
      .catch(() => {
        // Bad campaign_id → silently drop the link; user can still publish.
        if (!cancelled) setCampaign(null);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCampaignId]);

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
      if (campaign?.id) payload.campaign_id = campaign.id;
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
        // Carousel: send the full array when the user added extras.
        const allImages = [pinImageUrl.trim(), ...pinExtraImages.map((s) => s.trim()).filter(Boolean)];
        if (allImages.length > 1) {
          payload.pinterest_images = allImages.slice(0, 5);
        }
      }
      // Instagram requires an image URL (text-only IG posts aren't supported by the API).
      if (platforms.includes('instagram') && !payload.media_url && !pinImageUrl.trim()) {
        toast({
          title: 'Instagram needs an image URL',
          description: 'Drop an image into the Pinterest "Image URL" field above — Instagram will reuse it.',
        });
        setPublishing(false);
        return;
      }
      // If Instagram is selected without Pinterest, still let the FB photo
      // dispatcher use the Pinterest image as a generic media_url.
      if (!payload.media_url && pinImageUrl.trim()) {
        payload.media_url = pinImageUrl.trim();
      }
      // YouTube needs a downloadable video URL. The scheduler dispatcher
      // reads {video_url, youtube_title, youtube_tags, youtube_privacy}.
      if (platforms.includes('youtube')) {
        if (!ytVideoUrl.trim()) {
          toast({ title: 'YouTube needs a video URL', description: 'Paste a direct .mp4/.mov URL — YouTube requires a video file.' });
          setPublishing(false);
          return;
        }
        payload.video_url = ytVideoUrl.trim();
        if (ytTitle.trim()) payload.youtube_title = ytTitle.trim().slice(0, 100);
        if (hashtags.length) payload.youtube_tags = hashtags;
        payload.youtube_privacy = ytPrivacy;
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
      setPinExtraImages([]);
      setYtVideoUrl('');
      setYtTitle('');
      setYtPrivacy('private');
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
          {campaign && (
            <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-3 flex items-center justify-between gap-3" data-testid="compose-campaign-chip">
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-8 h-8 rounded-md bg-cyan-100 border border-cyan-200 text-cyan-700 flex items-center justify-center shrink-0">
                  <Layers size={14} />
                </span>
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-widest text-cyan-700 font-bold">Composing for campaign</div>
                  <div className="text-sm font-semibold text-zinc-800 truncate">{campaign.name}</div>
                  <div className="text-[11px] text-zinc-500 truncate">Goal: {campaign.goal}{campaign.audience ? ` · Audience: ${campaign.audience}` : ''}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => { setCampaign(null); toast({ title: 'Detached', description: 'New posts will no longer link to that campaign.' }); }}
                className="text-[11px] text-cyan-700 hover:text-cyan-900 underline shrink-0"
                data-testid="compose-campaign-detach"
              >
                Detach
              </button>
            </div>
          )}
          <FeedbackInsights
            testid="compose-feedback-insights"
            limit={3}
            theme="light"
            onUseHook={(hookText) => {
              setTopic(hookText);
              toast({
                title: 'Hook applied',
                description: 'Generated topic set. Hit "Generate with AI" to riff on this winning pattern.',
              });
              // Scroll the topic input into view + focus it so the user
              // can immediately edit / regenerate from there.
              setTimeout(() => {
                const el = document.querySelector('input[placeholder*="yoga"]');
                if (el) { el.focus(); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
              }, 50);
            }}
          />
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

                {/* Carousel pin support — up to 5 images total (1 main + 4 extras) */}
                {pinExtraImages.map((url, i) => (
                  <div key={i} className="mt-2 flex gap-2 items-center" data-testid={`compose-pin-extra-image-${i}`}>
                    <Input
                      type="url"
                      value={url}
                      onChange={(e) => {
                        const next = [...pinExtraImages];
                        next[i] = e.target.value;
                        setPinExtraImages(next);
                      }}
                      placeholder={`https://…/slide-${i + 2}.jpg`}
                      className="h-9 rounded-lg border-neutral-300 text-[12.5px] flex-1"
                    />
                    <button
                      type="button"
                      onClick={() => setPinExtraImages(pinExtraImages.filter((_, idx) => idx !== i))}
                      className="text-[11px] font-medium text-neutral-500 hover:text-rose-600 px-2 h-9 rounded-lg border border-neutral-200 bg-white"
                      data-testid={`compose-pin-extra-remove-${i}`}
                      title="Remove this carousel slide"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {pinExtraImages.length < 4 && (
                  <button
                    type="button"
                    onClick={() => setPinExtraImages([...pinExtraImages, ''])}
                    data-testid="compose-pin-add-carousel-image"
                    className="mt-2 text-[11.5px] font-semibold text-rose-700 hover:text-rose-900 inline-flex items-center gap-1"
                  >
                    + Add carousel slide ({pinExtraImages.length + 1} / 5)
                  </button>
                )}
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

          {youtubeSelected && (
            <div className="mt-4 rounded-2xl border border-red-100 bg-red-50/40 p-3.5 space-y-2.5" data-testid="compose-youtube-block">
              <div className="text-[11px] uppercase tracking-wider text-red-700 font-bold">▶ YouTube details</div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Video URL *</label>
                <Input
                  type="url"
                  value={ytVideoUrl}
                  onChange={(e) => setYtVideoUrl(e.target.value)}
                  placeholder="https://…/video.mp4 — or upload below"
                  data-testid="compose-yt-video-url"
                  className="h-9 rounded-lg border-neutral-300 text-[12.5px]"
                />
                <div className="text-[10.5px] text-neutral-500 mt-1">Paste a hosted URL, or click below to upload from your computer.</div>
                <div className="mt-2 flex items-center gap-2">
                  <label className={`text-[11.5px] font-semibold px-3 py-1.5 rounded-lg border cursor-pointer flex items-center gap-1.5 ${ytUploading ? 'bg-neutral-100 border-neutral-200 text-neutral-400 cursor-wait' : 'bg-white border-red-300 text-red-700 hover:bg-red-50'}`}>
                    {ytUploading ? <Loader2 size={12} className="animate-spin" /> : '⬆'}
                    {ytUploading ? 'Uploading…' : 'Upload from computer'}
                    <input
                      type="file"
                      accept="video/*"
                      disabled={ytUploading}
                      onChange={(e) => uploadYouTubeVideo(e.target.files?.[0])}
                      className="hidden"
                      data-testid="compose-yt-file"
                    />
                  </label>
                  {ytUploadName && !ytUploading && (
                    <span className="text-[11px] text-neutral-600 truncate" title={ytUploadName} data-testid="compose-yt-uploaded-name">
                      ✓ {ytUploadName}
                    </span>
                  )}
                </div>
              </div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Title <span className="text-neutral-400">(optional, ≤ 100 chars — defaults to first caption line)</span></label>
                <Input
                  value={ytTitle}
                  onChange={(e) => setYtTitle(e.target.value.slice(0, 100))}
                  placeholder="Catchy title or leave blank"
                  data-testid="compose-yt-title"
                  className="h-9 rounded-lg border-neutral-300 text-[12.5px]"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-neutral-600 mb-1 block">Privacy</label>
                <select
                  value={ytPrivacy}
                  onChange={(e) => setYtPrivacy(e.target.value)}
                  data-testid="compose-yt-privacy"
                  className="w-full h-9 rounded-lg border border-neutral-300 bg-white px-2 text-[12.5px]"
                >
                  <option value="private">Private (only you — recommended for first publish)</option>
                  <option value="unlisted">Unlisted (anyone with the link)</option>
                  <option value="public">Public</option>
                </select>
                <div className="text-[10.5px] text-neutral-500 mt-1">Tags below come from your hashtags. Description is your caption.</div>
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
