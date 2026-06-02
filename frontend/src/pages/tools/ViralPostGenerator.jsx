import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import {
  Sparkles, Loader2, ArrowRight, Copy, Check,
  Lightbulb, Flame, BarChart3, Lock,
} from 'lucide-react';
import CVNavbar from '../../components/cv/CVNavbar';
import CVFooter from '../../components/cv/CVFooter';
import CVBackdrop from '../../components/cv/CVBackdrop';
import CVSeo, { buildBreadcrumbSchema } from '../../components/cv/CVSeo';
import CVBreadcrumbs from '../../components/cv/CVBreadcrumbs';
import AuthModal from '../../components/AuthModal';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PLATFORMS = [
  { v: 'tiktok',    label: 'TikTok'    },
  { v: 'instagram', label: 'Instagram' },
  { v: 'x',         label: 'X (Twitter)' },
  { v: 'linkedin',  label: 'LinkedIn'  },
  { v: 'youtube',   label: 'YouTube'   },
  { v: 'reddit',    label: 'Reddit'    },
  { v: 'facebook',  label: 'Facebook'  },
  { v: 'threads',   label: 'Threads'   },
];

const HOOK_META = {
  contrarian: { icon: Flame,      label: 'Contrarian take', tone: 'text-rose-300 border-rose-500/30 bg-rose-500/[0.04]' },
  curiosity:  { icon: Lightbulb,  label: 'Curiosity gap',   tone: 'text-amber-300 border-amber-500/30 bg-amber-500/[0.04]' },
  data_shock: { icon: BarChart3,  label: 'Data shock',      tone: 'text-cyan-300 border-cyan-500/30 bg-cyan-500/[0.04]' },
};

const PostCard = ({ p }) => {
  const [copied, setCopied] = useState(false);
  const meta = HOOK_META[p.hook_type] || HOOK_META.contrarian;
  const Icon = meta.icon;
  const handleCopy = async () => {
    try {
      const text = `${p.hook}\n\n${p.body}\n\n${p.cta}`;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (_e) { /* noop */ }
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      data-testid={`viral-post-card-${p.hook_type}`}
      className={`rounded-2xl border p-5 ${meta.tone}`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="w-7 h-7 rounded-md bg-white/[0.06] border border-white/10 flex items-center justify-center">
          <Icon size={13} />
        </span>
        <span className="text-[10.5px] uppercase tracking-widest font-bold">{meta.label}</span>
        <div className="flex-1" />
        <button onClick={handleCopy}
                data-testid={`viral-post-copy-${p.hook_type}`}
                className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-zinc-200 border border-white/10 inline-flex items-center gap-1 transition">
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div className="text-[15px] font-semibold text-white leading-snug mb-2">{p.hook}</div>
      <div className="text-[13.5px] text-zinc-300 leading-relaxed whitespace-pre-line mb-3">{p.body}</div>
      <div className="text-[12.5px] text-violet-200 font-medium mb-2">→ {p.cta}</div>
      <div className="text-[11px] text-zinc-500 italic">{p.why_it_works}</div>
    </motion.div>
  );
};

export default function ViralPostGenerator() {
  const navigate = useNavigate();
  const [niche, setNiche]       = useState('');
  const [platform, setPlatform] = useState('tiktok');
  const [busy, setBusy]         = useState(false);
  const [posts, setPosts]       = useState([]);
  const [error, setError]       = useState(null);
  const [authOpen, setAuthOpen] = useState(false);
  const resultsRef = useRef(null);

  const onSubmit = async (e) => {
    e?.preventDefault?.();
    if (busy) return;
    const n = niche.trim();
    if (n.length < 2) { setError('Tell us your niche so we can write good hooks.'); return; }
    setBusy(true);
    setError(null);
    setPosts([]);
    try {
      const r = await axios.post(`${API}/tools/viral-post`,
                                    { niche: n, platform });
      setPosts(r.data?.posts || []);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth' }), 80);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Generation failed';
      setError(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Free Viral Post Generator — AI Social Media Posts in Seconds | CortexViral"
        description="Free AI viral post generator. Enter your niche and platform — get 3 hook-tested social media posts in seconds. TikTok, Instagram, LinkedIn, X, and more. No signup required."
        path="/tools/viral-post-generator"
        schema={[
          buildBreadcrumbSchema([
            { label: 'Home', path: '/' },
            { label: 'Tools', path: '/tools' },
            { label: 'Viral Post Generator', path: '/tools/viral-post-generator' },
          ]),
          {
            '@context': 'https://schema.org',
            '@type': 'HowTo',
            name: 'Generate Viral Social Media Posts with AI',
            description: 'Use CortexViral\'s free AI tool to generate hook-tested social media posts for any niche and platform.',
            step: [
              { '@type': 'HowToStep', name: 'Enter your niche', text: 'Type the topic or audience you create content about.' },
              { '@type': 'HowToStep', name: 'Pick a platform',  text: 'Choose TikTok, Instagram, LinkedIn, X, or 4 more.' },
              { '@type': 'HowToStep', name: 'Generate',         text: 'Get 3 hook-tested posts using contrarian, curiosity, and data-shock frameworks.' },
            ],
          },
        ]}
      />
      <CVNavbar />
      <main className="relative pt-32 pb-24">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <CVBreadcrumbs items={[
            { label: 'Home', path: '/' },
            { label: 'Tools', path: '/tools' },
            { label: 'Viral Post Generator', path: '/tools/viral-post-generator' },
          ]} />

          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 px-3 h-7 rounded-full cv-glass text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-300 mb-5">
              <Sparkles size={11} /> Free · No signup
            </div>
            <h1 className="cv-display text-4xl sm:text-5xl lg:text-6xl font-semibold text-white leading-[1.05] tracking-tight">
              The Free <span className="cv-gradient-text">Viral Post Generator</span>
            </h1>
            <p className="mt-5 text-[16px] text-zinc-400 max-w-2xl mx-auto leading-relaxed">
              Enter your niche → pick a platform → get 3 hook-tested posts written by AI in seconds.
              No signup. No credit card. Just paste and ship.
            </p>
          </div>

          <form onSubmit={onSubmit}
                data-testid="viral-post-form"
                className="cv-glass-strong rounded-2xl p-5 sm:p-6 mb-8">
            <div className="grid sm:grid-cols-[1fr_auto_auto] gap-3 items-end">
              <div>
                <label className="text-[11px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5 block">
                  Your niche or audience
                </label>
                <input
                  type="text"
                  value={niche}
                  onChange={(e) => setNiche(e.target.value)}
                  placeholder="e.g. indie SaaS founders, plant-based recipes, woodworking shop owners"
                  data-testid="viral-post-niche-input"
                  className="w-full bg-white/[0.04] border border-white/10 rounded-lg px-3 h-11 text-[14px] text-white placeholder:text-zinc-600 focus:outline-none focus:border-violet-400/60 transition"
                  disabled={busy}
                  maxLength={200}
                />
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-widest text-zinc-500 font-semibold mb-1.5 block">
                  Platform
                </label>
                <select
                  value={platform}
                  onChange={(e) => setPlatform(e.target.value)}
                  data-testid="viral-post-platform-select"
                  disabled={busy}
                  className="bg-white/[0.04] border border-white/10 rounded-lg px-3 h-11 text-[14px] text-white focus:outline-none focus:border-violet-400/60 transition min-w-[140px]">
                  {PLATFORMS.map((p) => (
                    <option key={p.v} value={p.v} className="bg-zinc-900">{p.label}</option>
                  ))}
                </select>
              </div>
              <button type="submit"
                      disabled={busy}
                      data-testid="viral-post-generate-btn"
                      className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-11 rounded-lg disabled:opacity-60 disabled:cursor-not-allowed">
                {busy
                  ? <><Loader2 size={14} className="animate-spin" /> Generating…</>
                  : <>Generate <ArrowRight size={14} /></>}
              </button>
            </div>
            {error && (
              <div data-testid="viral-post-error"
                    className="mt-4 text-[12.5px] text-rose-300 bg-rose-500/10 border border-rose-500/25 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <div className="mt-3 text-[10.5px] uppercase tracking-widest text-zinc-600 font-medium">
              Powered by Claude Haiku · Generates in ~12s
            </div>
          </form>

          <AnimatePresence>
            {posts.length > 0 && (
              <motion.div
                ref={resultsRef}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                data-testid="viral-post-results">
                <div className="flex items-center gap-2 mb-4">
                  <div className="text-[11px] uppercase tracking-widest text-violet-300 font-semibold">
                    Generated posts
                  </div>
                  <div className="h-px flex-1 bg-white/10" />
                  <div className="text-[11px] text-zinc-500">3 hook frameworks</div>
                </div>
                <div className="grid md:grid-cols-3 gap-4">
                  {posts.map((p, i) => <PostCard key={i} p={p} />)}
                </div>

                {/* Lead-magnet conversion CTA */}
                <div data-testid="viral-post-upsell"
                     className="mt-8 cv-glass-strong rounded-2xl p-6 sm:p-7 border-violet-500/30">
                  <div className="flex items-start sm:items-center gap-4 flex-col sm:flex-row">
                    <div className="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center shrink-0">
                      <Lock size={16} className="text-violet-300" />
                    </div>
                    <div className="flex-1">
                      <div className="text-white font-semibold text-[15px]">
                        Want CortexViral to <span className="cv-gradient-text">schedule and post these</span> for you?
                      </div>
                      <div className="text-zinc-400 text-[13px] mt-1">
                        Free plan: connect one channel, schedule unlimited posts at peak times, see live analytics.
                      </div>
                    </div>
                    <button onClick={() => setAuthOpen(true)}
                            data-testid="viral-post-cta-signup"
                            className="cv-btn-primary inline-flex items-center gap-1.5 text-[13px] font-semibold px-5 h-10 rounded-full">
                      Start Free <ArrowRight size={13} />
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Why it works section */}
          <section className="mt-20 grid md:grid-cols-3 gap-4">
            {[
              { icon: Flame,      title: 'Contrarian hooks',  body: 'Challenge a widely-held belief in your niche. High engagement because they spark debate.' },
              { icon: Lightbulb,  title: 'Curiosity-gap hooks', body: 'Tease a payoff without giving it away. The brain hates loose ends — viewers stay to close them.' },
              { icon: BarChart3,  title: 'Data-shock hooks',  body: 'Lead with a specific, unexpected number. Specificity reads as credibility, the surprise stops the scroll.' },
            ].map((f) => (
              <div key={f.title} className="cv-glass rounded-xl p-5">
                <div className="w-9 h-9 rounded-md bg-white/[0.05] border border-white/10 flex items-center justify-center mb-3">
                  <f.icon size={15} className="text-violet-300" />
                </div>
                <div className="text-white font-semibold text-[14px] mb-1">{f.title}</div>
                <div className="text-zinc-400 text-[12.5px] leading-relaxed">{f.body}</div>
              </div>
            ))}
          </section>

          <section className="mt-20 text-center">
            <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white">
              Ready to put this on autopilot?
            </h2>
            <p className="text-zinc-400 mt-4 max-w-xl mx-auto">
              CortexViral generates posts like these every day for your niche, schedules them at peak times, and learns what works for your audience.
            </p>
            <div className="mt-6 flex flex-wrap gap-3 justify-center">
              <button onClick={() => setAuthOpen(true)}
                      data-testid="viral-post-bottom-cta"
                      className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full">
                Start Free <ArrowRight size={14} />
              </button>
              <button onClick={() => navigate('/pricing')}
                      className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full">
                See pricing
              </button>
            </div>
          </section>
        </div>
      </main>
      <CVFooter />
      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </div>
  );
}
