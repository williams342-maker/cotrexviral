import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Check, ArrowRight, Sparkles } from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFaq from '../components/cv/CVFaq';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { SOFTWARE_SCHEMA, buildFaqSchema } from '../components/cv/CVSeo';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: 'forever',
    blurb: 'For creators just getting started.',
    cta: 'Start free',
    href: '/dashboard',
    features: [
      '20 AI generations / month',
      '2 connected social channels',
      'Manual publishing',
      'Basic analytics (last 7 days)',
      'Community support',
    ],
    highlighted: false,
  },
  {
    name: 'Pro',
    price: '$29',
    period: 'per month',
    blurb: 'For creators and small teams shipping daily content.',
    cta: 'Start 14-day free trial',
    href: '/dashboard',
    features: [
      'Unlimited AI generations',
      '10 connected social channels',
      'AI optimal-time scheduling',
      'Auto-publish queue (24/7 scheduler)',
      'Full analytics + per-post metrics',
      'Email support',
      'AI image generation',
      'Custom voice training',
    ],
    highlighted: true,
    badge: 'Most popular',
  },
  {
    name: 'Scale',
    price: '$99',
    period: 'per month',
    blurb: 'For brands and agencies running multiple accounts.',
    cta: 'Talk to sales',
    href: '#contact',
    features: [
      'Everything in Pro',
      'Unlimited connected channels',
      'Up to 5 workspaces',
      'Multi-seat collaboration',
      'API access + Zapier integration',
      'Priority human support',
      'White-label option',
      'Custom AI agent training',
    ],
    highlighted: false,
  },
];

const PRICING_FAQS = [
  { q: 'Is there really a free plan?', a: 'Yes — Free is free forever, no credit card required. You get 20 AI generations a month and 2 connected channels. Most solo creators stay on Free for their first few weeks.' },
  { q: 'What payment methods do you accept?', a: 'All major credit cards (Visa, Mastercard, Amex), Apple Pay, Google Pay, and Stripe-supported regional payment methods. Annual plans support invoicing.' },
  { q: 'Can I switch plans anytime?', a: 'Yes. Upgrade instantly with prorated billing, or downgrade at the end of your current cycle — no questions asked.' },
  { q: 'What happens to my content if I cancel?', a: 'Everything you generated, scheduled, or published stays in your account. You can export it as JSON or CSV anytime. Cancelled accounts are not deleted.' },
  { q: 'Do you offer annual discounts?', a: 'Yes — pay annually and get 2 months free on Pro and Scale plans. Toggle the billing switch above to see annual pricing.' },
  { q: 'Is there a money-back guarantee?', a: 'Pro and Scale come with a 14-day free trial — no charge until day 15. If you cancel within the first 30 days of paid billing, we will refund in full, no questions asked.' },
];

const Pricing = () => {
  const navigate = useNavigate();
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const [annual, setAnnual] = useState(false);

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Pricing — Plans for Creators, Teams, and Agencies"
        description="Simple, transparent pricing for CortexViral. Start free with 20 AI generations/month. Upgrade to Pro ($29/mo) for unlimited generations and live auto-publishing across 38+ channels."
        path="/pricing"
        schema={[SOFTWARE_SCHEMA, buildFaqSchema(PRICING_FAQS.map((f) => ({ question: f.q, answer: f.a })))]}
      />
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      {/* HERO */}
      <section className="relative pt-32 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Pricing</span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]"
          >
            Pricing That Scales{' '}
            <span className="cv-gradient-text">With Your Growth.</span>
          </motion.h1>
          <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">
            Start free. Upgrade when AI is doing so much of the work it pays for itself. Cancel anytime.
          </p>

          {/* Billing toggle */}
          <div className="mt-8 inline-flex items-center gap-3 cv-glass rounded-full p-1.5" data-testid="pricing-billing-toggle">
            <button
              onClick={() => setAnnual(false)}
              className={`px-4 h-9 rounded-full text-[13px] font-semibold transition-all ${!annual ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-white'}`}
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`px-4 h-9 rounded-full text-[13px] font-semibold transition-all inline-flex items-center gap-1.5 ${annual ? 'bg-white text-zinc-900' : 'text-zinc-400 hover:text-white'}`}
            >
              Annual
              <span className="text-[9.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-semibold">
                2 mo free
              </span>
            </button>
          </div>
        </div>
      </section>

      {/* TIERS */}
      <section className="relative cv-dark pb-20">
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-3 gap-5">
          {tiers.map((t, i) => {
            const numericPrice = t.price === '$0' ? '$0' : `$${Math.round(parseInt(t.price.replace('$',''), 10) * (annual ? 10/12 : 1))}`;
            return (
              <motion.div
                key={t.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className={`relative cv-glass-strong rounded-3xl p-7 flex flex-col ${
                  t.highlighted ? 'border-violet-400/50 cv-glow-violet' : ''
                }`}
                data-testid={`pricing-tier-${t.name.toLowerCase()}`}
              >
                {t.highlighted && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 bg-gradient-to-r from-violet-500 to-blue-500 text-white text-[11px] font-semibold uppercase tracking-wider px-3 py-1 rounded-full shadow-lg">
                    <Sparkles size={11} /> {t.badge}
                  </span>
                )}
                <h2 className="cv-display text-2xl font-semibold text-white">{t.name}</h2>
                <p className="text-[13px] text-zinc-400 mt-1.5 h-10">{t.blurb}</p>
                <div className="mt-5 flex items-baseline gap-1.5">
                  <span className="cv-display text-5xl font-semibold text-white">{numericPrice}</span>
                  <span className="text-[13px] text-zinc-500">
                    {t.price === '$0' ? t.period : (annual ? '/mo billed annually' : t.period)}
                  </span>
                </div>
                <button
                  onClick={() => t.href.startsWith('/') ? navigate(t.href) : window.location.assign(t.href)}
                  className={`mt-6 inline-flex items-center justify-center gap-1.5 h-11 rounded-full text-[13.5px] font-semibold transition-all ${
                    t.highlighted
                      ? 'cv-btn-primary'
                      : 'cv-btn-secondary'
                  }`}
                  data-testid={`pricing-cta-${t.name.toLowerCase()}`}
                >
                  {t.cta} <ArrowRight size={14} />
                </button>
                <ul className="mt-7 space-y-2.5 flex-1">
                  {t.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-[13px] text-zinc-300">
                      <Check size={14} className="text-cyan-300 mt-0.5 shrink-0" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
              </motion.div>
            );
          })}
        </div>

        <p className="mt-12 text-center text-[12.5px] text-zinc-500">
          All prices in USD. Taxes calculated at checkout. Need a custom plan? <a href="#contact" className="text-cyan-300 hover:text-cyan-200">Talk to us →</a>
        </p>
      </section>

      {/* COMPARISON FEATURE STRIP */}
      <section className="relative cv-dark py-16">
        <CVBackdrop />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white">
            Every plan ships with the <span className="cv-gradient-text">CortexViral core</span>
          </h2>
          <div className="mt-10 grid sm:grid-cols-3 gap-5">
            {[
              { title: '38+ social channels', body: 'TikTok, Instagram, X, LinkedIn, YouTube, Facebook, Pinterest, Threads, Reddit, and more.' },
              { title: '4 AI specialist agents', body: 'Nova (content), Sam (SEO), Kai (social listening), Angela (email).' },
              { title: 'Always-on scheduler', body: 'Background worker pushes scheduled posts at the exact peak window.' },
            ].map((b) => (
              <div key={b.title} className="cv-glass rounded-2xl p-5 text-left">
                <h3 className="cv-display text-[16px] font-semibold text-white">{b.title}</h3>
                <p className="text-[13px] text-zinc-400 mt-1.5 leading-relaxed">{b.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <CVFaq faqs={PRICING_FAQS} title={<>Pricing <span className="cv-gradient-text">questions</span>?</>} />

      <CVFooter />

      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={(a) => { setActiveAgent(a); setSelectOpen(false); setTimeout(() => setChatOpen(true), 120); }} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export default Pricing;
