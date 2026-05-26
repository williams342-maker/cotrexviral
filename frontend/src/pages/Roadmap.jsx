import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowRight, CheckCircle2, Sparkles, Wrench, Rocket, Telescope,
  Zap, Calendar, FileText, BarChart3, Mail, Brain, Ear,
  Target, FlaskConical, Eye, Workflow, MousePointerClick, Network,
} from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { ORG_SCHEMA, buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';

/* /roadmap — public-facing product roadmap. Three phases:
   1. Today (shipped MVP — features users can use right now)
   2. Coming soon (Phase 2 — agentic features)
   3. The long-term vision (Phase 3 — full autonomous marketing) */

const PHASES = [
  {
    id: 'today',
    pill: 'Live now',
    pillTone: 'emerald',
    icon: CheckCircle2,
    accent: 'emerald',
    title: 'What you get today',
    subtitle: 'A working AI marketing assistant. Not a demo. Not a promise.',
    timeline: 'Shipping now · v1',
    items: [
      {
        icon: Brain,
        title: 'ChatGPT-class marketing assistant',
        body: 'GPT-class reasoning trained on your niche, brand voice, and challenge — every output already sounds like you.',
      },
      {
        icon: BarChart3,
        title: 'Creator-first dashboard',
        body: 'Overview, performance, AI insights, calendar, and content studio in one neural-glass interface.',
      },
      {
        icon: Sparkles,
        title: 'Multi-format content generator',
        body: 'Newsletters, blog posts, multi-platform social posts, video scripts, product updates — all in one studio.',
      },
      {
        icon: Workflow,
        title: 'Pinterest + Instagram + 4 more',
        body: 'Live OAuth for TikTok, LinkedIn, Pinterest, Facebook, Instagram + scheduled publishing with drag-and-drop calendar.',
      },
    ],
  },
  {
    id: 'soon',
    pill: 'In build',
    pillTone: 'violet',
    icon: Wrench,
    accent: 'violet',
    title: 'Coming soon — Agent mode',
    subtitle: 'CortexViral stops being a tool. It starts being a teammate.',
    timeline: 'Next 2 quarters',
    items: [
      {
        icon: Calendar,
        title: 'Scheduled posting at peak velocity',
        body: 'Already live for Pinterest. Rolling out to every connected channel with platform-specific peak-window scheduling.',
      },
      {
        icon: FileText,
        title: 'Automatic blog generation',
        body: 'Drop a keyword — get a publish-ready, SEO-optimised long-form post with internal links and meta tags.',
      },
      {
        icon: BarChart3,
        title: 'Analytics summaries (English, not dashboards)',
        body: 'Weekly digest: "Here is what worked, why it worked, and what to ship next." Written by your AI strategist.',
      },
      {
        icon: Mail,
        title: 'Email automation',
        body: 'Lifecycle, welcome, abandoned-cart, and re-engagement flows generated from your brand profile.',
      },
      {
        icon: Brain,
        title: 'AI memory',
        body: 'Persistent recall of every post, every result, every reply — so your assistant gets sharper every week.',
      },
      {
        icon: Ear,
        title: 'Social listening',
        body: 'Real-time monitoring across Reddit, X, TikTok, LinkedIn — surfaced as actionable hooks the moment they trend.',
      },
    ],
  },
  {
    id: 'vision',
    pill: 'The vision',
    pillTone: 'cyan',
    icon: Telescope,
    accent: 'cyan',
    title: 'The endgame — autonomous marketing',
    subtitle: 'Hire AI marketing employees. They never sleep, never miss a trend, never miss a follow-up.',
    timeline: 'The full platform',
    items: [
      {
        icon: Target,
        title: 'Campaign execution',
        body: 'Brief in, multi-channel campaign out — landing pages, ads, posts, emails, and follow-up sequences shipped end-to-end.',
      },
      {
        icon: FlaskConical,
        title: 'Automatic A/B testing',
        body: 'Every post auto-spawns hook variants. Winners get scaled, losers get killed — all without human intervention.',
      },
      {
        icon: Eye,
        title: 'Competitor monitoring',
        body: 'Track your competitors\' winning hooks, posting cadence, and growth velocity in real time.',
      },
      {
        icon: Workflow,
        title: 'AI workflows',
        body: 'Visual node-based automations: "if engagement drops 20%, generate 5 new hooks and ship the top performer."',
      },
      {
        icon: MousePointerClick,
        title: 'Ad optimisation',
        body: 'Auto-bid, auto-pause, and creative refresh on Meta + TikTok Ads. Continuous ROAS optimisation.',
      },
      {
        icon: Network,
        title: 'Multi-agent system',
        body: 'Nova (strategy) · Sam (copy) · Kai (analytics) · Angela (community) — four specialists collaborating on every campaign.',
      },
    ],
  },
];

const TONES = {
  emerald: { dot: 'bg-emerald-400', pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', icon: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30', line: 'from-emerald-400/60 via-violet-400/30 to-violet-400/0' },
  violet: { dot: 'bg-violet-400', pill: 'bg-violet-500/15 text-violet-300 border-violet-500/30', icon: 'text-violet-300 bg-violet-500/10 border-violet-500/30', line: 'from-violet-400/60 via-cyan-400/30 to-cyan-400/0' },
  cyan: { dot: 'bg-cyan-400', pill: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30', icon: 'text-cyan-300 bg-cyan-500/10 border-cyan-500/30', line: 'from-cyan-400/60 via-cyan-400/0 to-transparent' },
};

const Roadmap = () => {
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const navigate = useNavigate();

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Roadmap — Where CortexViral is Going"
        description="The CortexViral product roadmap: what is shipping now, what is in build for agent mode, and the long-term vision of fully autonomous AI marketing employees."
        path="/roadmap"
        schema={[ORG_SCHEMA, buildBreadcrumbSchema([
          { label: 'Home', path: '/' },
          { label: 'Roadmap', path: '/roadmap' },
        ])]}
      />
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      {/* HERO */}
      <section className="relative pt-32 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <CVBreadcrumbs items={[{ label: 'Roadmap' }]} className="justify-center mb-5" />
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Product roadmap</span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]"
            data-testid="roadmap-hero-title"
          >
            From assistant to{' '}
            <span className="cv-gradient-text">autonomous marketing team.</span>
          </motion.h1>
          <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">
            CortexViral ships in three deliberate phases: a working AI marketing assistant today, a full agent mode in the coming quarters, and ultimately a multi-agent system that runs your marketing department for you.
          </p>
          <div className="mt-7 flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => navigate('/dashboard')}
              className="cv-btn-primary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="roadmap-cta-start"
            >
              Use what is live today <ArrowRight size={14} />
            </button>
            <button
              onClick={() => document.getElementById('phases')?.scrollIntoView({ behavior: 'smooth' })}
              className="cv-btn-secondary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="roadmap-cta-explore"
            >
              See the roadmap
            </button>
          </div>
          <div className="mt-4 text-[12.5px] text-zinc-500">
            Built on Next.js · OpenAI · Supabase · n8n · APScheduler
          </div>
        </div>
      </section>

      {/* PHASES TIMELINE */}
      <section id="phases" className="relative cv-dark py-20 scroll-mt-24">
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="relative">
            {/* vertical timeline line */}
            <div className="hidden md:block absolute left-9 top-2 bottom-2 w-px bg-gradient-to-b from-emerald-400/40 via-violet-400/40 to-cyan-400/0" aria-hidden />

            {PHASES.map((phase, idx) => {
              const tone = TONES[phase.accent];
              const PhaseIcon = phase.icon;
              return (
                <motion.div
                  key={phase.id}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-80px' }}
                  transition={{ duration: 0.55, delay: idx * 0.05 }}
                  className="relative mb-16 last:mb-0"
                  data-testid={`roadmap-phase-${phase.id}`}
                >
                  <div className="flex flex-col md:flex-row gap-6 md:gap-8">
                    {/* Phase marker */}
                    <div className="shrink-0 flex md:flex-col items-center md:items-start gap-3 md:w-20">
                      <div className={`relative w-[72px] h-[72px] rounded-2xl border ${tone.icon} flex items-center justify-center`}>
                        <PhaseIcon size={26} />
                        <span className={`absolute -top-1 -right-1 w-3 h-3 rounded-full ${tone.dot} cv-pulse`} />
                      </div>
                    </div>

                    {/* Phase content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 flex-wrap mb-2.5">
                        <span className={`text-[10.5px] uppercase tracking-[0.18em] font-semibold px-2.5 py-1 rounded-full border ${tone.pill}`}>
                          {phase.pill}
                        </span>
                        <span className="text-[11.5px] text-zinc-500 font-medium">{phase.timeline}</span>
                      </div>
                      <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white leading-tight">{phase.title}</h2>
                      <p className="text-zinc-400 text-[15px] mt-2 max-w-2xl leading-relaxed">{phase.subtitle}</p>

                      <div className="grid sm:grid-cols-2 gap-3 mt-7">
                        {phase.items.map((it) => {
                          const ItemIcon = it.icon;
                          return (
                            <div key={it.title} className="cv-glass rounded-2xl p-4 hover:border-white/10 transition-colors">
                              <div className="flex items-start gap-3">
                                <div className={`shrink-0 w-9 h-9 rounded-lg border flex items-center justify-center ${tone.icon}`}>
                                  <ItemIcon size={15} />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="text-[14px] font-semibold text-white">{it.title}</div>
                                  <div className="text-[12.5px] text-zinc-400 mt-1 leading-relaxed">{it.body}</div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* STACK STRIP */}
      <section className="relative cv-dark pb-12">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="cv-glass-strong rounded-3xl p-7 sm:p-9">
            <div className="flex items-start gap-4 mb-5">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/30 to-cyan-500/30 border border-violet-500/30 flex items-center justify-center">
                <Zap size={18} className="text-violet-200" />
              </div>
              <div>
                <h2 className="cv-display text-2xl font-semibold text-white">What it is built on</h2>
                <p className="text-zinc-400 text-[14px] mt-1.5">An honest look at the stack so you know we are not duct-taping prompts together.</p>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
              {[
                { label: 'Next.js + React 18', sub: 'Static-prerendered SPA · CWV-tuned' },
                { label: 'FastAPI + Motor', sub: 'Async backend over MongoDB' },
                { label: 'OpenAI GPT-class', sub: 'Routed via Emergent LLM key' },
                { label: 'APScheduler', sub: 'Reliable publish queue with retries' },
                { label: 'Stripe billing', sub: 'Test mode + webhook idempotency' },
                { label: 'Mailtrap + Mailgun', sub: 'Provider chain with fallback' },
              ].map((s) => (
                <div key={s.label} className="rounded-xl border border-white/5 p-3.5 bg-white/[0.02]">
                  <div className="text-[13.5px] font-semibold text-white">{s.label}</div>
                  <div className="text-[11.5px] text-zinc-500 mt-0.5">{s.sub}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative cv-dark py-20">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <Rocket size={28} className="text-violet-300 mx-auto" />
          <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white mt-4">
            Get a head start before the agents arrive.
          </h2>
          <p className="text-zinc-400 text-[15px] mt-3 max-w-xl mx-auto leading-relaxed">
            Every account today gets the assistant. Every feature shipped in Phase 2 and Phase 3 rolls out for free to existing users. Lock in your early-creator price now.
          </p>
          <div className="mt-7 flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => navigate('/dashboard')}
              className="cv-btn-primary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="roadmap-cta-start-free"
            >
              Start Free <ArrowRight size={14} />
            </button>
            <button
              onClick={() => navigate('/pricing')}
              className="cv-btn-secondary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="roadmap-cta-pricing"
            >
              See pricing
            </button>
          </div>
        </div>
      </section>

      <CVFooter />
      <SelectAgentModal
        open={selectOpen}
        onClose={() => setSelectOpen(false)}
        onSelect={(a) => { setActiveAgent(a); setSelectOpen(false); setTimeout(() => setChatOpen(true), 120); }}
      />
      <AgentChatModal
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        agent={activeAgent}
        onBack={() => { setChatOpen(false); setSelectOpen(true); }}
      />
    </div>
  );
};

export default Roadmap;
