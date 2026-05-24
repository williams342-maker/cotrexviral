import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import axios from 'axios';
import {
  Check, X, ArrowRight, Sparkles, Loader2, Zap, TrendingUp,
  Layers, Wand2, Building2, Rocket,
} from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFaq from '../components/cv/CVFaq';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { SOFTWARE_SCHEMA, buildFaqSchema, buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import { useToast } from '../hooks/use-toast';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Tier catalogue — annual price = 12 monthly − 2 months free.
const TIERS = [
  {
    name: 'Free',
    plan: null,
    icon: Sparkles,
    monthly: 0,
    annual: 0,
    blurb: 'For testing viral content ideas',
    cta: 'Start Free',
    micro: 'Perfect for trying viral content ideas before upgrading',
    features: [
      '5 viral hook generations / week',
      'Basic caption generator',
      'Limited TikTok content ideas',
      'Single-platform output (TikTok only)',
      'Standard AI response mode',
    ],
    excluded: ['No trend engine', 'No A/B hook variations', 'No batch generation'],
    highlighted: false,
  },
  {
    name: 'Starter',
    plan: 'starter',
    icon: Zap,
    monthly: 15,
    annual: 150,
    blurb: 'For new creators building consistency',
    cta: 'Get Started',
    micro: 'Best for creators posting a few times per week',
    features: [
      'Everything in Free, plus:',
      '30+ content generations / month',
      'TikTok + Instagram Reels support',
      'Improved hook quality engine',
      'Caption + hashtag generator',
      'Content idea expansion tools',
    ],
    highlighted: false,
  },
  {
    name: 'Growth',
    plan: 'growth',
    icon: TrendingUp,
    monthly: 39,
    annual: 390,
    blurb: 'For serious creators growing audiences fast',
    cta: 'Go Viral Faster',
    micro: 'Best for creators posting daily and scaling reach',
    badge: '🔥 Most Popular',
    features: [
      'Everything in Starter, plus:',
      'Unlimited viral hook generation',
      'Full TikTok / Reels / Shorts script engine',
      'Trend-based content suggestions',
      'A/B hook variations',
      'Engagement-optimized captions',
      'Viral content scoring system',
      'Priority AI processing',
    ],
    highlighted: true,
  },
  {
    name: 'Agency',
    plan: 'agency',
    icon: Building2,
    monthly: 99,
    annual: 990,
    blurb: 'For agencies, brands & power users',
    cta: 'Scale Content Production',
    micro: 'Built for agencies managing multiple clients or brands',
    features: [
      'Everything in Growth, plus:',
      'Multi-brand workspaces',
      'Client folders & organization tools',
      'Bulk content generation',
      'Content batching system',
      'Team collaboration access',
      'API / automation access (optional)',
      'Early feature access',
    ],
    highlighted: false,
  },
];

// Feature comparison matrix
const COMPARISON = [
  { feature: 'Hook Generator',       free: '✓', starter: '✓',       growth: '✓',         agency: '✓' },
  { feature: 'Caption Generator',    free: 'Limited', starter: '✓', growth: '✓',         agency: '✓' },
  { feature: 'TikTok Scripts',       free: '—', starter: 'Basic',   growth: 'Advanced',  agency: 'Advanced' },
  { feature: 'Instagram Reels',      free: '—', starter: '✓',       growth: '✓',         agency: '✓' },
  { feature: 'YouTube Shorts',       free: '—', starter: '—',       growth: '✓',         agency: '✓' },
  { feature: 'Trend Engine',         free: '—', starter: '—',       growth: '✓',         agency: '✓' },
  { feature: 'A/B Hook Variations',  free: '—', starter: '—',       growth: '✓',         agency: '✓' },
  { feature: 'Batch Generation',     free: '—', starter: '—',       growth: '—',         agency: '✓' },
  { feature: 'Multi-Brand Workspaces', free: '—', starter: '—',     growth: '—',         agency: '✓' },
  { feature: 'API Access',           free: '—', starter: '—',       growth: '—',         agency: 'Optional' },
  { feature: 'Priority AI Processing', free: '—', starter: '—',     growth: '✓',         agency: '✓' },
];

const VALUE_PROPS = [
  'Built for virality, not generic AI writing',
  'Hook-first content generation system',
  'Optimized for TikTok, Reels & Shorts algorithms',
  'Create content 10x faster with structured AI workflows',
];

const PRICING_FAQS = [
  { q: 'Is CortexViral really free?', a: 'Yes — you can generate limited viral hooks and content ideas without paying. No credit card, no time limit. The Free tier is built so you can test the engine before committing.' },
  { q: 'What happens when I hit my free limit?', a: "You'll be prompted to upgrade to continue generating content and unlock advanced features like the trend engine and A/B hook variations." },
  { q: 'Can I cancel anytime?', a: 'Yes — no contracts, no commitments. Cancel from the dashboard in two clicks. We never auto-renew without warning you first.' },
  { q: 'Does CortexViral guarantee virality?', a: 'No tool can guarantee virality — but CortexViral dramatically increases your chances by using proven engagement structures, scroll-stopping hook frameworks, and real-time trend data.' },
  { q: 'Who is this for?', a: 'Creators, marketers, brands, and agencies producing short-form content for TikTok, Instagram Reels, and YouTube Shorts. Especially anyone who feels stuck staring at a blank script.' },
  { q: 'How does annual billing work?', a: 'Pay yearly and get 2 months free on every paid plan. Toggle the billing switch above to see annual pricing.' },
  { q: 'Is there a free trial on paid plans?', a: 'Yes — all paid plans include a 14-day free trial. We only charge on day 15, and you can cancel anytime during the trial without paying a cent.' },
];

const Pricing = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [annual, setAnnual] = useState(false);
  const [loadingPlan, setLoadingPlan] = useState(null);

  const priceFor = (t) => {
    if (t.monthly === 0) return { value: '$0', period: 'forever' };
    if (annual) {
      const perMonth = Math.round(t.annual / 12);
      return { value: `$${perMonth}`, period: '/mo billed annually' };
    }
    return { value: `$${t.monthly}`, period: '/month' };
  };

  const onCta = async (t) => {
    if (!t.plan) {
      navigate('/dashboard');
      return;
    }
    setLoadingPlan(t.plan);
    try {
      const { data } = await axios.post(
        `${API}/billing/checkout-session`,
        { plan: t.plan, interval: annual ? 'year' : 'month', origin_url: window.location.origin },
        { withCredentials: true },
      );
      window.location.assign(data.url);
    } catch (e) {
      if (e?.response?.status === 401) {
        toast({ title: 'Please sign in first', description: 'Redirecting to login…' });
        setTimeout(() => navigate('/dashboard'), 800);
      } else {
        toast({
          title: 'Could not start checkout',
          description: e?.response?.data?.detail || e.message || 'Try again in a moment.',
        });
      }
      setLoadingPlan(null);
    }
  };

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Pricing — Plans for Creators, Brands & Agencies"
        description="Simple pricing for CortexViral. Start free. Upgrade to Starter ($15), Growth ($39), or Agency ($99) for unlimited viral content, trend engine, A/B hooks, and batch generation. 14-day free trial on all paid plans."
        path="/pricing"
        schema={[
          SOFTWARE_SCHEMA,
          buildFaqSchema(PRICING_FAQS.map((f) => ({ question: f.q, answer: f.a }))),
          buildBreadcrumbSchema([
            { label: 'Home', path: '/' },
            { label: 'Pricing', path: '/pricing' },
          ]),
        ]}
      />
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      {/* HERO */}
      <section className="relative pt-32 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <CVBreadcrumbs items={[{ label: 'Pricing' }]} className="justify-center mb-5" />
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Pricing</span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]"
          >
            Create Viral Content That{' '}
            <span className="cv-gradient-text">Actually Grows Your Audience.</span>
          </motion.h1>
          <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">
            CortexViral helps you generate hooks, scripts, and short-form content engineered for TikTok, Instagram Reels, and YouTube Shorts.
          </p>

          <div className="mt-7 flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => navigate('/dashboard')}
              className="cv-btn-primary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="hero-start-free"
            >
              Start Free <ArrowRight size={14} />
            </button>
            <button
              onClick={() => document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth' })}
              className="cv-btn-secondary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13.5px] font-semibold"
              data-testid="hero-view-plans"
            >
              View Plans
            </button>
          </div>
          <div className="mt-4 text-[12.5px] text-zinc-500">
            No credit card required · Upgrade anytime · Built for creators &amp; brands
          </div>

          {/* Billing toggle */}
          <div className="mt-10 inline-flex items-center gap-2 cv-glass rounded-full p-1.5" data-testid="pricing-billing-toggle">
            <button
              onClick={() => setAnnual(false)}
              className={`px-4 h-9 rounded-full text-[13px] font-semibold transition-all ${!annual ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-white'}`}
              data-testid="toggle-monthly"
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`px-4 h-9 rounded-full text-[13px] font-semibold transition-all inline-flex items-center gap-1.5 ${annual ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-white'}`}
              data-testid="toggle-annual"
            >
              Annual
              <span className="text-[9.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-semibold">
                2 mo free
              </span>
            </button>
          </div>
        </div>
      </section>

      {/* VALUE STRIP */}
      <section className="relative cv-dark py-10" data-testid="pricing-value-strip">
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="cv-glass rounded-3xl p-6 sm:p-8">
            <h2 className="cv-display text-[15px] uppercase tracking-[0.22em] text-violet-300 font-semibold text-center mb-5">
              Why creators switch to CortexViral
            </h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {VALUE_PROPS.map((v) => (
                <div key={v} className="flex items-start gap-2.5 text-[13.5px] text-zinc-300">
                  <Check size={15} className="text-cyan-300 mt-0.5 shrink-0" />
                  <span>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* PRICING TABLE — 4 tiers */}
      <section id="plans" className="relative cv-dark pt-6 pb-16 scroll-mt-24">
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid md:grid-cols-2 xl:grid-cols-4 gap-5">
          {TIERS.map((t, i) => {
            const Icon = t.icon;
            const price = priceFor(t);
            const isLoading = t.plan && loadingPlan === t.plan;
            return (
              <motion.div
                key={t.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className={`relative cv-glass-strong rounded-3xl p-7 flex flex-col ${t.highlighted ? 'border-violet-400/50 cv-glow-violet' : ''}`}
                data-testid={`pricing-tier-${t.name.toLowerCase()}`}
              >
                {t.highlighted && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 bg-gradient-to-r from-violet-500 to-blue-500 text-white text-[11px] font-semibold uppercase tracking-wider px-3 py-1 rounded-full shadow-lg whitespace-nowrap">
                    {t.badge}
                  </span>
                )}
                <div className="flex items-center gap-2.5 mb-1">
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${t.highlighted ? 'bg-violet-500/15 text-violet-300' : 'bg-white/5 text-zinc-300'}`}>
                    <Icon size={17} />
                  </div>
                  <h2 className="cv-display text-2xl font-semibold text-white">{t.name}</h2>
                </div>
                <p className="text-[13px] text-zinc-400 mt-1.5 min-h-[40px]">{t.blurb}</p>

                <div className="mt-5 flex items-baseline gap-1.5">
                  <span className="cv-display text-5xl font-semibold text-white">{price.value}</span>
                  <span className="text-[13px] text-zinc-500">{price.period}</span>
                </div>

                <button
                  onClick={() => onCta(t)}
                  disabled={isLoading}
                  className={`mt-6 inline-flex items-center justify-center gap-1.5 h-11 rounded-full text-[13.5px] font-semibold transition-all ${t.highlighted ? 'cv-btn-primary' : 'cv-btn-secondary'} ${isLoading ? 'opacity-70 cursor-wait' : ''}`}
                  data-testid={`pricing-cta-${t.name.toLowerCase()}`}
                >
                  {isLoading ? (
                    <><Loader2 size={14} className="animate-spin" /> Loading…</>
                  ) : (
                    <>{t.cta} <ArrowRight size={14} /></>
                  )}
                </button>
                <p className="text-[11.5px] text-zinc-500 mt-2 text-center">{t.micro}</p>

                <ul className="mt-6 space-y-2.5 flex-1">
                  {t.features.map((f, idx) => (
                    <li key={`${t.name}-f-${idx}`} className={`flex items-start gap-2.5 text-[13px] ${idx === 0 && t.name !== 'Free' ? 'text-zinc-400 italic' : 'text-zinc-300'}`}>
                      {idx === 0 && t.name !== 'Free' ? (
                        <span className="w-3.5 mt-0.5 shrink-0" />
                      ) : (
                        <Check size={14} className="text-cyan-300 mt-0.5 shrink-0" />
                      )}
                      <span>{f}</span>
                    </li>
                  ))}
                  {t.excluded?.map((f) => (
                    <li key={`${t.name}-x-${f}`} className="flex items-start gap-2.5 text-[12.5px] text-zinc-500 line-through">
                      <X size={13} className="text-zinc-600 mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </motion.div>
            );
          })}
        </div>

        <p className="mt-12 text-center text-[12.5px] text-zinc-500">
          All prices in USD. Taxes calculated at checkout. 14-day free trial on all paid plans.
        </p>
      </section>

      {/* FEATURE COMPARISON TABLE */}
      <section className="relative cv-dark py-16" data-testid="pricing-comparison-table">
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-10">
            <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Compare</span>
            <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white mt-2">
              Feature <span className="cv-gradient-text">comparison</span>
            </h2>
          </div>
          <div className="cv-glass rounded-3xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px]">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left p-4 text-[12px] uppercase tracking-wider text-zinc-500 font-semibold">Feature</th>
                    <th className="p-4 text-[12px] uppercase tracking-wider text-zinc-500 font-semibold text-center">Free</th>
                    <th className="p-4 text-[12px] uppercase tracking-wider text-zinc-500 font-semibold text-center">Starter</th>
                    <th className="p-4 text-[12px] uppercase tracking-wider text-violet-300 font-semibold text-center">Growth</th>
                    <th className="p-4 text-[12px] uppercase tracking-wider text-zinc-500 font-semibold text-center">Agency</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map((row, idx) => (
                    <tr key={row.feature} className={`border-b border-white/5 last:border-0 ${idx % 2 === 0 ? 'bg-white/[0.015]' : ''}`}>
                      <td className="p-4 text-[13.5px] text-zinc-300">{row.feature}</td>
                      {['free', 'starter', 'growth', 'agency'].map((col) => (
                        <td key={col} className={`p-4 text-center text-[13.5px] ${row[col] === '✓' ? 'text-cyan-300' : row[col] === '—' ? 'text-zinc-600' : 'text-zinc-400'} ${col === 'growth' ? 'bg-violet-500/[0.04]' : ''}`}>
                          {row[col] === '✓' ? <Check size={15} className="inline" /> : row[col] === '—' ? <X size={13} className="inline opacity-40" /> : row[col]}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      {/* WHY FREE ISN'T ENOUGH */}
      <section className="relative cv-dark py-16" data-testid="pricing-why-free">
        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="cv-glass-strong rounded-3xl p-8 sm:p-10 text-center">
            <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Reality check</span>
            <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white mt-2 mb-5">
              Why Free Isn't Enough to <span className="cv-gradient-text">Grow Your Audience</span>
            </h2>
            <p className="text-zinc-400 text-[15px] max-w-xl mx-auto">
              Free users can test ideas — but viral growth requires:
            </p>
            <div className="mt-6 grid sm:grid-cols-2 gap-3 max-w-xl mx-auto text-left">
              {[
                'Consistent content output',
                'Trend adaptation',
                'Hook optimization',
                'Structured scripting',
              ].map((req) => (
                <div key={req} className="flex items-start gap-2.5">
                  <Rocket size={15} className="text-violet-300 mt-0.5 shrink-0" />
                  <span className="text-[14px] text-zinc-200">{req}</span>
                </div>
              ))}
            </div>
            <p className="text-[13px] text-zinc-500 mt-7">These are unlocked in paid plans starting at <strong className="text-zinc-300">$15/mo</strong>.</p>
          </div>
        </div>
      </section>

      {/* CONVERSION SECTION */}
      <section className="relative cv-dark py-16" data-testid="pricing-conversion">
        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <Wand2 size={28} className="text-violet-300 mx-auto mb-4" />
          <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white">
            Turn Ideas Into Viral Content in <span className="cv-gradient-text">Minutes.</span>
          </h2>
          <p className="mt-4 text-zinc-400 text-[16px] max-w-xl mx-auto">
            Join creators using CortexViral to generate high-performing short-form content that actually gets views.
          </p>
          <button
            onClick={() => navigate('/dashboard')}
            className="cv-btn-primary inline-flex items-center gap-1.5 px-6 h-12 rounded-full text-[14px] font-semibold mt-7"
            data-testid="conversion-cta"
          >
            Start Free Today <ArrowRight size={15} />
          </button>
        </div>
      </section>

      {/* FAQ */}
      <CVFaq faqs={PRICING_FAQS} title={<>Pricing <span className="cv-gradient-text">questions</span>?</>} />

      {/* FINAL CTA */}
      <section className="relative cv-dark py-20" data-testid="pricing-final-cta">
        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white leading-[0.95]">
            Start Creating <span className="cv-gradient-text">Viral Content</span> Today.
          </h2>
          <p className="mt-5 text-zinc-400 text-[15px] max-w-xl mx-auto">
            Free users can start immediately. Upgrade anytime to unlock full viral content systems.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
            <button
              onClick={() => navigate('/dashboard')}
              className="cv-btn-primary inline-flex items-center gap-1.5 px-6 h-12 rounded-full text-[14px] font-semibold"
            >
              Start Free <ArrowRight size={15} />
            </button>
            <button
              onClick={() => document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth' })}
              className="cv-btn-secondary inline-flex items-center gap-1.5 px-6 h-12 rounded-full text-[14px] font-semibold"
            >
              View Plans
            </button>
          </div>
        </div>
      </section>

      <CVFooter />

      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={(a) => { setActiveAgent(a); setSelectOpen(false); setTimeout(() => setChatOpen(true), 120); }} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export default Pricing;
