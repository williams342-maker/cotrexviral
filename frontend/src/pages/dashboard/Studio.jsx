import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import UsageMeter from '../../components/UsageMeter';
import FeatureLock from '../../components/FeatureLock';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { useToast } from '../../hooks/use-toast';
import { usePaywallHandler } from '../../hooks/use-paywall';
import {
  Loader2, Mail, FileText, Megaphone, Video, Layers,
  Sparkles, Copy, Send, Clock, Hash, TrendingUp, FlaskConical, Lock,
} from 'lucide-react';

const TABS = [
  { id: 'newsletter', label: 'Newsletter', icon: Mail, color: 'text-violet-600 bg-violet-50' },
  { id: 'blog', label: 'Blog Article', icon: FileText, color: 'text-emerald-600 bg-emerald-50' },
  { id: 'update', label: 'Product Update', icon: Megaphone, color: 'text-amber-600 bg-amber-50' },
  { id: 'video', label: 'Video Script', icon: Video, color: 'text-rose-600 bg-rose-50' },
  { id: 'multi', label: 'Multi-Platform Posts', icon: Layers, color: 'text-sky-600 bg-sky-50' },
  { id: 'trends', label: 'Trend Engine', icon: TrendingUp, color: 'text-fuchsia-600 bg-fuchsia-50', requiresFeature: 'trend_engine' },
  { id: 'ab', label: 'A/B Hook Lab', icon: FlaskConical, color: 'text-cyan-600 bg-cyan-50', requiresFeature: 'ab_variations' },
];

const Studio = () => {
  const [tab, setTab] = useState('newsletter');
  const [usageKey, setUsageKey] = useState(0);
  const [features, setFeatures] = useState({});
  const refreshUsage = () => setUsageKey((k) => k + 1);

  useEffect(() => {
    axios.get(`${API}/billing/usage`, { withCredentials: true })
      .then((r) => setFeatures(r.data.features || {}))
      .catch(() => {});
  }, [usageKey]);

  return (
    <DashboardLayout title="Content Studio" subtitle="Generate newsletters, blog articles, product updates, video scripts, and platform-tailored posts.">
      <div className="mb-5">
        <UsageMeter refreshKey={usageKey} />
      </div>
      <div className="flex flex-wrap gap-2 mb-7">
        {TABS.map((t) => {
          const locked = t.requiresFeature && !features[t.requiresFeature];
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-[13.5px] font-medium border transition-all ${
                tab === t.id
                  ? 'bg-[#1B7BFF] text-white border-[#1B7BFF]'
                  : 'bg-white text-neutral-700 border-neutral-200 hover:border-neutral-300'
              }`}
              data-testid={`studio-tab-${t.id}`}
            >
              <t.icon size={14} />
              {t.label}
              {locked && <Lock size={11} className="opacity-60" />}
            </button>
          );
        })}
      </div>

      {tab === 'newsletter' && <NewsletterTab onGenerated={refreshUsage} />}
      {tab === 'blog' && <BlogTab onGenerated={refreshUsage} />}
      {tab === 'update' && <UpdateTab onGenerated={refreshUsage} />}
      {tab === 'video' && <VideoTab onGenerated={refreshUsage} />}
      {tab === 'multi' && <MultiTab onGenerated={refreshUsage} />}
      {tab === 'trends' && (
        <FeatureLock
          unlocked={!!features.trend_engine}
          feature="Trend Engine"
          requires="Growth"
          blurb="Get real-time TikTok/Reels/Shorts trend feeds with viral-velocity scoring, so you write hooks the algorithm is already pushing."
        >
          <TrendsTab onGenerated={refreshUsage} />
        </FeatureLock>
      )}
      {tab === 'ab' && (
        <FeatureLock
          unlocked={!!features.ab_variations}
          feature="A/B Hook Lab"
          requires="Growth"
          blurb="Generate 5 hook variations per idea, score each on scroll-stop probability, and ship the winner. Built on real engagement patterns."
        >
          <ABLabTab onGenerated={refreshUsage} />
        </FeatureLock>
      )}
    </DashboardLayout>
  );
};

// ---------- Shared ----------
const FieldLabel = ({ children }) => (
  <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">{children}</label>
);

const GenerateButton = ({ loading, label, onClick }) => (
  <button
    onClick={onClick}
    disabled={loading}
    className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white text-[14px] font-medium px-5 h-11 rounded-xl"
  >
    {loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
    {loading ? 'Generating…' : label}
  </button>
);

const ResultCard = ({ title, color, children }) => (
  <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
    <div className={`text-[12px] uppercase tracking-wider font-semibold mb-3 ${color || 'text-[#1B7BFF]'}`}>{title}</div>
    {children}
  </div>
);

const copyText = (text, toast) => {
  navigator.clipboard.writeText(text);
  toast({ title: 'Copied to clipboard' });
};

// ---------- Newsletter ----------
const NewsletterTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const [form, setForm] = useState({ topic: '', audience: 'general subscribers', tone: 'friendly', sections: 3 });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!form.topic.trim()) return toast({ title: 'Topic required' });
    setLoading(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/ai/generate-newsletter`, form, { withCredentials: true });
      setResult(r.data);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <FieldLabel>Topic</FieldLabel>
          <Input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="Spring collection launch + customer stories" className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>Audience</FieldLabel>
          <Input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>Tone</FieldLabel>
          <Select value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="friendly">Friendly</SelectItem>
              <SelectItem value="professional">Professional</SelectItem>
              <SelectItem value="playful">Playful</SelectItem>
              <SelectItem value="inspirational">Inspirational</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <FieldLabel>Number of sections</FieldLabel>
          <Select value={String(form.sections)} onValueChange={(v) => setForm({ ...form, sections: Number(v) })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[2, 3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="md:col-span-2">
          <GenerateButton loading={loading} label="Generate Newsletter" onClick={run} />
        </div>
      </div>

      {result && !result.raw && (
        <div className="space-y-4">
          <ResultCard title="Subject & Preheader" color="text-violet-600">
            <div className="space-y-2">
              <div className="flex items-center gap-2 bg-neutral-50 rounded-xl p-3">
                <span className="text-[11px] text-neutral-500 font-medium uppercase">Subject</span>
                <span className="text-[14px] font-medium flex-1">{result.subject}</span>
                <button onClick={() => copyText(result.subject, toast)} className="text-neutral-500 hover:text-neutral-800"><Copy size={13} /></button>
              </div>
              <div className="flex items-center gap-2 bg-neutral-50 rounded-xl p-3">
                <span className="text-[11px] text-neutral-500 font-medium uppercase">Preheader</span>
                <span className="text-[13.5px] flex-1">{result.preheader}</span>
              </div>
            </div>
          </ResultCard>
          <ResultCard title="Newsletter body" color="text-violet-600">
            <p className="text-[14.5px] text-neutral-800 leading-relaxed mb-4">{result.intro}</p>
            {result.sections?.map((s, i) => (
              <div key={i} className="mt-4 pt-4 border-t border-neutral-100 first:border-0 first:mt-0 first:pt-0">
                <h3 className="text-[16px] font-semibold tracking-tight mb-1.5">{s.heading}</h3>
                <p className="text-[14px] text-neutral-700 leading-relaxed">{s.body}</p>
              </div>
            ))}
            {result.cta && (
              <div className="mt-5 p-4 rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[13px] font-semibold text-violet-800">{result.cta.text}</div>
                  {result.cta.url_suggestion && <div className="text-[12px] text-violet-600 mt-0.5">{result.cta.url_suggestion}</div>}
                </div>
                <Send size={16} className="text-violet-700" />
              </div>
            )}
            {result.ps && (
              <p className="mt-4 text-[13px] text-neutral-600 italic">P.S. {result.ps}</p>
            )}
          </ResultCard>
        </div>
      )}
      {result?.raw && <pre className="bg-white p-4 rounded-2xl border border-neutral-200 text-[13px] whitespace-pre-wrap">{result.raw}</pre>}
    </div>
  );
};

// ---------- Blog ----------
const BlogTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const [form, setForm] = useState({ topic: '', keywords: '', tone: 'professional', length: 'medium' });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!form.topic.trim()) return toast({ title: 'Topic required' });
    setLoading(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/ai/generate-content`, {
        topic: form.topic,
        keywords: form.keywords.split(',').map((k) => k.trim()).filter(Boolean),
        tone: form.tone,
        length: form.length,
      }, { withCredentials: true });
      setResult(r.data);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <FieldLabel>Article topic</FieldLabel>
          <Input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="How to choose a sustainable yoga mat" className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div className="md:col-span-2">
          <FieldLabel>Keywords (comma-separated)</FieldLabel>
          <Input value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="sustainable yoga, eco-friendly, natural rubber" className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>Tone</FieldLabel>
          <Select value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="professional">Professional</SelectItem>
              <SelectItem value="conversational">Conversational</SelectItem>
              <SelectItem value="authoritative">Authoritative</SelectItem>
              <SelectItem value="friendly">Friendly</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <FieldLabel>Length</FieldLabel>
          <Select value={form.length} onValueChange={(v) => setForm({ ...form, length: v })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="short">Short (~400 words)</SelectItem>
              <SelectItem value="medium">Medium (~800 words)</SelectItem>
              <SelectItem value="long">Long (~1500 words)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="md:col-span-2">
          <GenerateButton loading={loading} label="Generate Article" onClick={run} />
        </div>
      </div>

      {result && !result.raw && (
        <div className="space-y-4">
          <ResultCard title="Article" color="text-emerald-600">
            <h2 className="text-2xl md:text-3xl font-medium tracking-tight mb-2">{result.title}</h2>
            <div className="flex flex-wrap gap-2 mb-4 text-[12px] text-neutral-500">
              {result.estimated_read_minutes && <span className="inline-flex items-center gap-1"><Clock size={11} />{result.estimated_read_minutes} min read</span>}
              {result.slug && <span className="font-mono">/{result.slug}</span>}
            </div>
            {result.meta_description && (
              <p className="text-[13px] text-neutral-500 italic border-l-2 border-neutral-200 pl-3 mb-5">{result.meta_description}</p>
            )}
            <p className="text-[15px] text-neutral-800 leading-relaxed mb-5">{result.intro}</p>
            {result.sections?.map((s, i) => (
              <div key={i} className="mb-5">
                <h3 className="text-xl font-semibold tracking-tight mb-2">{s.heading}</h3>
                <p className="text-[14.5px] text-neutral-800 leading-relaxed whitespace-pre-line">{s.body}</p>
              </div>
            ))}
            {result.conclusion && (
              <div className="mt-6 pt-6 border-t border-neutral-200">
                <h3 className="text-xl font-semibold tracking-tight mb-2">Conclusion</h3>
                <p className="text-[14.5px] text-neutral-800 leading-relaxed">{result.conclusion}</p>
              </div>
            )}
            {result.tags?.length > 0 && (
              <div className="mt-6 flex flex-wrap gap-2">
                {result.tags.map((t, i) => (
                  <span key={i} className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-[12px] font-medium border border-emerald-100">#{t}</span>
                ))}
              </div>
            )}
          </ResultCard>
        </div>
      )}
      {result?.raw && <pre className="bg-white p-4 rounded-2xl border border-neutral-200 text-[13px] whitespace-pre-wrap">{result.raw}</pre>}
    </div>
  );
};

// ---------- Update ----------
const UpdateTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const [form, setForm] = useState({ product: '', changes: '', tone: 'friendly' });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!form.product.trim() || !form.changes.trim()) return toast({ title: 'Product and changes required' });
    setLoading(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/ai/generate-update`, form, { withCredentials: true });
      setResult(r.data);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 grid gap-4">
        <div>
          <FieldLabel>Product name</FieldLabel>
          <Input value={form.product} onChange={(e) => setForm({ ...form, product: e.target.value })} placeholder="Automatex v2.4" className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>What's new (paste raw notes / bullets)</FieldLabel>
          <Textarea value={form.changes} onChange={(e) => setForm({ ...form, changes: e.target.value })} rows={6} placeholder={`- Added new AI insights tab\n- Faster page loads\n- Fixed login bug`} className="rounded-xl border-neutral-300" />
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <FieldLabel>Tone</FieldLabel>
            <Select value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v })}>
              <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="friendly">Friendly</SelectItem>
                <SelectItem value="professional">Professional</SelectItem>
                <SelectItem value="exciting">Exciting</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <GenerateButton loading={loading} label="Generate Update" onClick={run} />
          </div>
        </div>
      </div>

      {result && !result.raw && (
        <div className="space-y-4">
          <ResultCard title="Announcement" color="text-amber-600">
            <h2 className="text-2xl md:text-3xl font-medium tracking-tight mb-2">{result.headline}</h2>
            <p className="text-[15px] text-neutral-600 mb-5">{result.subheadline}</p>
            <div className="grid md:grid-cols-2 gap-3">
              {result.highlights?.map((h, i) => (
                <div key={i} className="bg-amber-50 border border-amber-100 rounded-2xl p-4">
                  <div className="text-[14px] font-semibold text-amber-900 mb-1">{h.title}</div>
                  <p className="text-[13px] text-amber-800 leading-relaxed">{h.desc}</p>
                </div>
              ))}
            </div>
          </ResultCard>

          {result.social_post && (
            <ResultCard title="Social post" color="text-sky-600">
              <div className="flex items-start gap-3">
                <p className="text-[14.5px] text-neutral-800 whitespace-pre-line flex-1 leading-relaxed">{result.social_post}</p>
                <button onClick={() => copyText(result.social_post, toast)} className="text-neutral-500 hover:text-neutral-800"><Copy size={14} /></button>
              </div>
            </ResultCard>
          )}

          {(result.email_subject || result.email_body) && (
            <ResultCard title="Email announcement" color="text-violet-600">
              {result.email_subject && (
                <div className="mb-3 flex items-center gap-2 bg-neutral-50 rounded-xl p-3">
                  <span className="text-[11px] text-neutral-500 font-medium uppercase">Subject</span>
                  <span className="text-[14px] font-medium flex-1">{result.email_subject}</span>
                  <button onClick={() => copyText(result.email_subject, toast)} className="text-neutral-500"><Copy size={13} /></button>
                </div>
              )}
              <p className="text-[14px] text-neutral-800 leading-relaxed whitespace-pre-line">{result.email_body}</p>
            </ResultCard>
          )}
        </div>
      )}
      {result?.raw && <pre className="bg-white p-4 rounded-2xl border border-neutral-200 text-[13px] whitespace-pre-wrap">{result.raw}</pre>}
    </div>
  );
};

// ---------- Video Script ----------
const VideoTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const [form, setForm] = useState({ topic: '', platform: 'tiktok', duration_seconds: 30, tone: 'energetic' });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!form.topic.trim()) return toast({ title: 'Topic required' });
    setLoading(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/ai/execute`, {
        task_type: 'ad_script',
        user_goal: `Create a ${form.duration_seconds}-second ${form.platform} video ad about ${form.topic}.`,
        context: form,
      }, { withCredentials: true });
      setResult(r.data.result);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <FieldLabel>Video topic</FieldLabel>
          <Input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} placeholder="3 hidden features of our new product" className="h-11 rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>Platform</FieldLabel>
          <Select value={form.platform} onValueChange={(v) => setForm({ ...form, platform: v })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="tiktok">TikTok</SelectItem>
              <SelectItem value="reels">Instagram Reels</SelectItem>
              <SelectItem value="shorts">YouTube Shorts</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <FieldLabel>Duration</FieldLabel>
          <Select value={String(form.duration_seconds)} onValueChange={(v) => setForm({ ...form, duration_seconds: Number(v) })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="15">15 seconds</SelectItem>
              <SelectItem value="30">30 seconds</SelectItem>
              <SelectItem value="60">60 seconds</SelectItem>
              <SelectItem value="90">90 seconds</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <FieldLabel>Tone</FieldLabel>
          <Select value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v })}>
            <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="energetic">Energetic</SelectItem>
              <SelectItem value="informative">Informative</SelectItem>
              <SelectItem value="funny">Funny</SelectItem>
              <SelectItem value="emotional">Emotional</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end">
          <GenerateButton loading={loading} label="Generate Script" onClick={run} />
        </div>
      </div>

      {result && !result.raw && (
        <div className="space-y-4">
          <ResultCard title="Hook & Title" color="text-rose-600">
            <h2 className="text-xl md:text-2xl font-medium tracking-tight mb-2">{result.title}</h2>
            <div className="bg-rose-50 border border-rose-100 rounded-2xl p-4">
              <div className="text-[11px] uppercase tracking-wider text-rose-600 font-semibold mb-1">Opening hook</div>
              <p className="text-[15px] text-rose-900 font-medium">{result.hook}</p>
            </div>
          </ResultCard>

          <ResultCard title="Scene-by-scene script" color="text-rose-600">
            <div className="space-y-3">
              {result.scenes?.map((s, i) => (
                <div key={i} className="flex gap-3 p-3 rounded-2xl border border-neutral-200 hover:bg-neutral-50/50">
                  <div className="shrink-0 w-14 text-center">
                    <div className="text-[10px] uppercase tracking-wider text-neutral-400 font-medium">Scene</div>
                    <div className="text-lg font-medium text-neutral-800">{i + 1}</div>
                    <div className="text-[11px] text-neutral-500 mt-0.5">{s.timestamp}</div>
                  </div>
                  <div className="flex-1 space-y-1.5">
                    <div className="text-[12.5px]"><span className="text-neutral-500 font-medium">Visual:</span> <span className="text-neutral-800">{s.visual}</span></div>
                    <div className="text-[12.5px]"><span className="text-neutral-500 font-medium">VO:</span> <span className="text-neutral-800">{s.voiceover}</span></div>
                    {s.on_screen_text && <div className="text-[12.5px]"><span className="text-neutral-500 font-medium">Text:</span> <span className="text-neutral-800 font-medium">{s.on_screen_text}</span></div>}
                  </div>
                </div>
              ))}
            </div>
          </ResultCard>

          {(result.caption || result.hashtags?.length > 0 || result.music_vibe) && (
            <ResultCard title="Publishing kit" color="text-violet-600">
              {result.caption && (
                <div className="mb-3">
                  <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-medium mb-1">Caption</div>
                  <p className="text-[14px] text-neutral-800 whitespace-pre-line">{result.caption}</p>
                </div>
              )}
              {result.hashtags?.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {result.hashtags.map((h, i) => (
                    <span key={i} className="px-2.5 py-1 rounded-full bg-sky-50 text-sky-700 text-[12px] font-medium border border-sky-100">{h.startsWith('#') ? h : `#${h}`}</span>
                  ))}
                </div>
              )}
              {result.music_vibe && (
                <div className="text-[12.5px] text-neutral-600">🎵 Music vibe: <span className="font-medium text-neutral-800">{result.music_vibe}</span></div>
              )}
            </ResultCard>
          )}
        </div>
      )}
      {result?.raw && <pre className="bg-white p-4 rounded-2xl border border-neutral-200 text-[13px] whitespace-pre-wrap">{result.raw}</pre>}
    </div>
  );
};

// ---------- Multi-platform ----------
const PLATFORM_OPTIONS = [
  { id: 'instagram', label: 'Instagram', chars: 2200 },
  { id: 'tiktok', label: 'TikTok', chars: 2200 },
  { id: 'x', label: 'X (Twitter)', chars: 280 },
  { id: 'facebook', label: 'Facebook', chars: 63206 },
  { id: 'linkedin', label: 'LinkedIn', chars: 3000 },
  { id: 'youtube', label: 'YouTube', chars: 5000 },
  { id: 'pinterest', label: 'Pinterest', chars: 500 },
  { id: 'threads', label: 'Threads', chars: 500 },
  { id: 'reddit', label: 'Reddit', chars: 40000 },
  { id: 'substack', label: 'Substack', chars: 100000 },
  { id: 'blogger', label: 'Blogger', chars: 100000 },
];

const platformLimit = (p) => PLATFORM_OPTIONS.find((o) => o.id === p)?.chars || 2000;
const platformLabel = (p) => PLATFORM_OPTIONS.find((o) => o.id === p)?.label || p;

const MultiTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const navigate = useNavigate();
  const [form, setForm] = useState({ listing: '', tone: 'friendly' });
  const [platforms, setPlatforms] = useState({ instagram: true, x: true, linkedin: true });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const togglePlatform = (p) => setPlatforms({ ...platforms, [p]: !platforms[p] });

  const run = async () => {
    if (!form.listing.trim()) return toast({ title: 'Listing required' });
    const selected = Object.keys(platforms).filter((k) => platforms[k]);
    if (selected.length === 0) return toast({ title: 'Pick at least one platform' });
    setLoading(true);
    setResult(null);
    try {
      const r = await axios.post(`${API}/ai/multi-post`, { listing: form.listing, platforms: selected, tone: form.tone }, { withCredentials: true });
      setResult(r.data);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed' });
    } finally {
      setLoading(false);
    }
  };

  const sendToCompose = (p) => {
    const content = p.hashtags?.length
      ? `${p.content}\n\n${p.hashtags.map((h) => h.startsWith('#') ? h : `#${h}`).join(' ')}`
      : p.content;
    navigate('/dashboard/compose', { state: { draft: content, platform: p.platform } });
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70 grid gap-4">
        <div>
          <FieldLabel>New listing / news / item</FieldLabel>
          <Textarea value={form.listing} onChange={(e) => setForm({ ...form, listing: e.target.value })} rows={4} placeholder="New product: organic cotton tote bag, $29, available in 5 colors, made in Portugal..." className="rounded-xl border-neutral-300" />
        </div>
        <div>
          <FieldLabel>Platforms — AI will tailor copy & respect each platform's limit</FieldLabel>
          <div className="flex flex-wrap gap-2">
            {PLATFORM_OPTIONS.map((p) => (
              <button
                key={p.id}
                onClick={() => togglePlatform(p.id)}
                type="button"
                title={`${p.chars.toLocaleString()} char max`}
                className={`px-3.5 py-1.5 rounded-full text-[13px] font-medium border transition-all ${
                  platforms[p.id]
                    ? 'bg-[#1B7BFF] text-white border-[#1B7BFF]'
                    : 'bg-white text-neutral-700 border-neutral-300 hover:border-neutral-400'
                }`}
              >
                {p.label}
                <span className={`ml-1.5 text-[10.5px] ${platforms[p.id] ? 'text-blue-100' : 'text-neutral-400'}`}>
                  {p.chars >= 1000 ? `${(p.chars / 1000).toFixed(p.chars % 1000 === 0 ? 0 : 1)}k` : p.chars}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <FieldLabel>Tone</FieldLabel>
            <Select value={form.tone} onValueChange={(v) => setForm({ ...form, tone: v })}>
              <SelectTrigger className="h-11 rounded-xl border-neutral-300"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="friendly">Friendly</SelectItem>
                <SelectItem value="professional">Professional</SelectItem>
                <SelectItem value="playful">Playful</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <GenerateButton loading={loading} label="Generate All Posts" onClick={run} />
          </div>
        </div>
      </div>

      {result?.posts?.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          {result.posts.map((p, i) => {
            const limit = platformLimit(p.platform);
            const len = p.char_count || p.content?.length || 0;
            const overLimit = len > limit;
            return (
              <div key={i} className="bg-white rounded-3xl p-5 border border-neutral-200/70">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] uppercase tracking-wider px-2.5 py-1 rounded-full bg-[#1B7BFF]/10 text-[#1B7BFF] font-semibold">{platformLabel(p.platform)}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-[11px] font-medium ${overLimit ? 'text-rose-600' : 'text-neutral-500'}`}>
                      {len.toLocaleString()} / {limit.toLocaleString()}
                    </span>
                    <button onClick={() => copyText(p.content, toast)} className="text-neutral-500 hover:text-neutral-800"><Copy size={13} /></button>
                  </div>
                </div>
                <p className="text-[14px] text-neutral-800 whitespace-pre-line leading-relaxed mb-3">{p.content}</p>
                {p.hashtags?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {p.hashtags.map((h, j) => (
                      <span key={j} className="text-[11.5px] text-sky-700 bg-sky-50 px-2 py-0.5 rounded-full border border-sky-100">
                        <Hash size={9} className="inline" />{h.replace(/^#/, '')}
                      </span>
                    ))}
                  </div>
                )}
                <button onClick={() => sendToCompose(p)} className="w-full text-[12.5px] font-medium bg-neutral-50 hover:bg-neutral-100 text-neutral-700 border border-neutral-200 px-3 py-2 rounded-lg inline-flex items-center justify-center gap-1.5 transition-colors">
                  <Send size={12} /> Send to Compose
                </button>
              </div>
            );
          })}
        </div>
      )}
      {result?.raw && <pre className="bg-white p-4 rounded-2xl border border-neutral-200 text-[13px] whitespace-pre-wrap">{result.raw}</pre>}
    </div>
  );
};


// ---------- Trend Engine (gated to Growth+) ----------
const TrendsTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [source, setSource] = useState(null);
  const [cachedAt, setCachedAt] = useState(null);

  const load = async (force = false) => {
    if (force) setRefreshing(true); else setLoading(true);
    try {
      const url = force ? `${API}/ai/trends/refresh` : `${API}/ai/trends`;
      const r = force
        ? await axios.post(url, {}, { withCredentials: true })
        : await axios.get(url, { withCredentials: true });
      setTrends(r.data.trends || []);
      setCachedAt(r.data.cached_at);
      setSource(r.data.trends?.[0]?.source || null);
    } catch (e) {
      toast({ title: 'Could not load trends', description: e?.response?.data?.detail?.message || e.message });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
        <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
          <div>
            <h3 className="text-[18px] font-semibold text-neutral-900">Trend Engine</h3>
            <p className="text-[13px] text-neutral-600">
              Live viral-velocity feed across TikTok, Reels, and Shorts. Higher score = algorithm push.
              {source === 'fallback' && (
                <span className="ml-2 inline-block text-[10.5px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">
                  Curated baseline
                </span>
              )}
              {source === 'tiktok_creative_center' && (
                <span className="ml-2 inline-block text-[10.5px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                  Live feed
                </span>
              )}
              {cachedAt && (
                <span className="ml-2 text-[11.5px] text-neutral-500">
                  Updated {new Date(cachedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={() => { load(true); }}
            disabled={refreshing}
            className="cv-btn-secondary inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-[13px] font-semibold disabled:opacity-60"
            data-testid="trends-refresh"
          >
            {refreshing ? <><Loader2 size={13} className="animate-spin" /> Refreshing…</> : <><Sparkles size={13} /> Refresh feed</>}
          </button>
        </div>
      </div>

      {loading && (
        <div className="text-center py-10"><Loader2 size={20} className="animate-spin text-violet-600 mx-auto" /></div>
      )}

      {!loading && (
        <div className="grid md:grid-cols-2 gap-3" data-testid="trends-grid">
          {trends.map((t) => (
            <div key={t.hashtag} className="bg-white rounded-2xl p-5 border border-neutral-200/70 flex items-center gap-4">
              <div className={`text-3xl font-semibold tabular-nums w-12 text-center ${t.velocity >= 85 ? 'text-emerald-600' : t.velocity >= 70 ? 'text-violet-600' : 'text-amber-600'}`}>{t.velocity}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[14px] font-semibold text-neutral-900">{t.hashtag}</span>
                  <span className="text-[10.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-fuchsia-50 text-fuchsia-700 font-semibold">{t.platform}</span>
                </div>
                <p className="text-[13px] text-neutral-600 truncate" title={t.sample}>{t.sample}</p>
              </div>
              <button
                onClick={() => { navigator.clipboard?.writeText(t.sample); toast({ title: 'Hook copied' }); onGenerated?.(); }}
                className="text-neutral-500 hover:text-neutral-800"
                data-testid={`trend-copy-${t.hashtag.replace('#','')}`}
              >
                <Copy size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};


// ---------- A/B Hook Lab (gated to Growth+) ----------
const ABLabTab = ({ onGenerated }) => {
  const { toast } = useToast();
  const paywall = usePaywallHandler();
  const [seed, setSeed] = useState('');
  const [loading, setLoading] = useState(false);
  const [variants, setVariants] = useState([]);

  const run = async () => {
    if (!seed.trim()) return toast({ title: 'Hook idea required' });
    setLoading(true);
    try {
      const r = await axios.post(
        `${API}/ai/ab-variations`,
        { seed: seed.trim(), platform: 'tiktok', count: 5 },
        { withCredentials: true },
      );
      setVariants(r.data?.variants || []);
      onGenerated?.();
    } catch (e) {
      if (!paywall(e)) toast({ title: 'Generation failed', description: e?.response?.data?.detail || e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-3xl p-6 border border-neutral-200/70">
        <h3 className="text-[18px] font-semibold text-neutral-900 mb-1">A/B Hook Lab</h3>
        <p className="text-[13px] text-neutral-600 mb-4">Drop a hook idea. Get 5 scored variations to ship the highest-stopping version.</p>
        <div className="flex gap-2 flex-wrap">
          <Input
            placeholder="e.g. why most TikToks fail in the first 2 seconds"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            className="flex-1 min-w-[260px]"
            data-testid="ab-lab-seed"
          />
          <button
            onClick={run}
            disabled={loading}
            className="cv-btn-primary inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-[13px] font-semibold disabled:opacity-60"
            data-testid="ab-lab-run"
          >
            {loading ? <><Loader2 size={13} className="animate-spin" /> Generating…</> : <><FlaskConical size={13} /> Generate variants</>}
          </button>
        </div>
      </div>

      {variants.length > 0 && (
        <div className="space-y-2.5">
          {variants.map((v, i) => (
            <div key={i} className="bg-white rounded-2xl p-4 border border-neutral-200/70 flex items-start gap-4">
              <div className={`text-3xl font-semibold tabular-nums w-14 text-center pt-1 ${v.score >= 85 ? 'text-emerald-600' : v.score >= 70 ? 'text-amber-600' : 'text-neutral-500'}`}>
                {v.score}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[14px] text-neutral-800 leading-snug font-medium">{v.text}</p>
                {v.breakdown && (
                  <div className="mt-2 flex flex-wrap gap-1.5" data-testid={`ab-lab-breakdown-${i}`}>
                    {Object.entries(v.breakdown).map(([k, val]) => (
                      <span key={k} className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-neutral-100 text-neutral-600 border border-neutral-200">
                        <span className="font-semibold text-neutral-900">{val}</span>
                        <span>{k.replace(/_/g, ' ')}</span>
                      </span>
                    ))}
                  </div>
                )}
                {v.why && (
                  <p className="text-[12px] text-neutral-500 italic mt-2 leading-snug">{v.why}</p>
                )}
              </div>
              <button
                onClick={() => { navigator.clipboard?.writeText(v.text); toast({ title: 'Hook copied' }); }}
                className="text-neutral-500 hover:text-neutral-800 pt-1"
                data-testid={`ab-lab-copy-${i}`}
              >
                <Copy size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Studio;
