import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Check } from 'lucide-react';
import CVNavbar from './CVNavbar';
import CVBackdrop from './CVBackdrop';
import CVFaq from './CVFaq';
import CVFooter from './CVFooter';
import CVSeo, { SOFTWARE_SCHEMA, buildFaqSchema, buildBreadcrumbSchema } from './CVSeo';
import CVBreadcrumbs from './CVBreadcrumbs';
import { SelectAgentModal, AgentChatModal } from '../Modals';
import { NICHES } from '../../pages/programmatic/data';

// Map landing-page paths → matching programmatic tool slug for niche cross-linking
const PATH_TO_PROG_TOOL = {
  '/ai-tiktok-post-generator': 'tiktok-script-generator',
  '/viral-content-ideas-generator': 'viral-content-ideas',
  '/instagram-caption-ai-generator': 'instagram-caption-generator',
  '/short-form-video-ideas-ai': 'tiktok-script-generator',
  '/content-automation-tool': 'viral-content-ideas',
};

/**
 * Reusable SEO landing page template — used by /ai-tiktok-post-generator,
 * /viral-content-ideas-generator, etc.  Each instance imports this and passes
 * its own copy + FAQ + related-links so the URL targets a single keyword intent.
 *
 * Props:
 *   seo:        { title, description, path }
 *   hero:       { kicker, h1, sub, primaryCta, secondaryCta }
 *   benefits:   [{ title, body }] (3-6 cards)
 *   how:        { h2, steps: [{ n, title, body }] }
 *   useCases:   [{ title, body }] (3 cards)
 *   faqs:       [{ q, a }]
 *   related:    [{ label, href }]
 */
const CVLandingPage = ({ seo, hero, benefits, how, useCases, faqs, related }) => {
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const navigate = useNavigate();

  const handleSelectAgent = (a) => {
    setActiveAgent(a);
    setSelectOpen(false);
    setTimeout(() => setChatOpen(true), 120);
  };

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title={seo.title}
        description={seo.description}
        path={seo.path}
        schema={[
          SOFTWARE_SCHEMA,
          buildFaqSchema(faqs.map((f) => ({ question: f.q, answer: f.a }))),
          buildBreadcrumbSchema([
            { label: 'Home', path: '/' },
            { label: hero.kicker, path: seo.path },
          ]),
        ]}
      />
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      {/* HERO */}
      <section className="relative pt-32 pb-20 overflow-hidden" data-testid="cv-landing-hero">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <CVBreadcrumbs
            items={[{ label: hero.kicker }]}
            className="justify-center mb-6"
          />
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-3 h-7 rounded-full cv-glass text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-300 mb-6"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 cv-pulse" />
            {hero.kicker}
          </motion.span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white leading-[0.95]"
          >
            {hero.h1}
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="mt-6 text-[17px] leading-relaxed text-zinc-400 max-w-2xl mx-auto"
          >
            {hero.sub}
          </motion.p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full"
              data-testid="cv-landing-cta-primary"
            >
              {hero.primaryCta || 'Start Free'} <ArrowRight size={15} />
            </button>
            <button
              onClick={() => setSelectOpen(true)}
              className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full"
            >
              {hero.secondaryCta || 'Talk to an AI Agent'}
            </button>
          </div>
        </div>
      </section>

      {/* BENEFITS */}
      <section className="relative cv-dark py-20">
        <CVBackdrop />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-5">
            {benefits.map((b, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="cv-glass-strong rounded-3xl p-6"
              >
                <div className="w-10 h-10 rounded-xl cv-glass flex items-center justify-center mb-4 text-cyan-300">
                  <Check size={18} />
                </div>
                <h3 className="cv-display text-[18px] font-semibold text-white">{b.title}</h3>
                <p className="text-[13.5px] text-zinc-400 mt-2 leading-relaxed">{b.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW */}
      <section className="relative cv-dark py-24">
        <CVBackdrop />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white leading-tight">{how.h2}</h2>
          </div>
          <div className="grid md:grid-cols-2 gap-5">
            {how.steps.map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="cv-glass rounded-3xl p-6 flex gap-4"
              >
                <span className="cv-display shrink-0 w-12 h-12 rounded-full cv-glass-strong flex items-center justify-center text-cyan-300 text-[18px] font-semibold">
                  {s.n}
                </span>
                <div>
                  <h3 className="cv-display text-[17px] font-semibold text-white">{s.title}</h3>
                  <p className="text-[13.5px] text-zinc-400 mt-1.5 leading-relaxed">{s.body}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* USE CASES */}
      {useCases?.length > 0 && (
        <section className="relative cv-dark py-20">
          <CVBackdrop />
          <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white text-center mb-12">
              Made for <span className="cv-gradient-text">every creator</span>
            </h2>
            <div className="grid md:grid-cols-3 gap-5">
              {useCases.map((u, i) => (
                <div key={i} className="cv-glass-strong rounded-3xl p-6">
                  <h3 className="cv-display text-[18px] font-semibold text-white">{u.title}</h3>
                  <p className="text-[13.5px] text-zinc-400 mt-2 leading-relaxed">{u.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      <CVFaq faqs={faqs} />

      {/* RELATED — internal links for SEO */}
      {related?.length > 0 && (
        <section className="relative cv-dark pb-12">
          <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 className="cv-display text-2xl font-semibold text-white mb-6 text-center">Related guides &amp; tools</h2>
            <div className="flex flex-wrap justify-center gap-2.5" data-testid="cv-landing-related">
              {related.map((r) => (
                <Link key={r.href} to={r.href} className="cv-glass rounded-full px-4 py-2 text-[13px] text-zinc-300 hover:text-white hover:border-cyan-400/40 transition-colors">
                  {r.label} <ArrowRight size={12} className="inline ml-0.5" />
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* BY NICHE — programmatic cross-links for long-tail SEO */}
      {PATH_TO_PROG_TOOL[seo.path] && (
        <section className="relative cv-dark pb-20" data-testid="cv-landing-by-niche">
          <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 className="cv-display text-2xl font-semibold text-white mb-2 text-center">
              Try it for your <span className="cv-gradient-text">niche</span>
            </h2>
            <p className="text-center text-[13px] text-zinc-500 mb-6 max-w-xl mx-auto">
              Pre-tuned variants of this tool, optimised for the voice and pain points of specific industries.
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2.5 max-w-4xl mx-auto">
              {NICHES.map((n) => (
                <Link
                  key={n.slug}
                  to={`/tools/${PATH_TO_PROG_TOOL[seo.path]}-for-${n.slug}`}
                  className="cv-glass rounded-xl px-3.5 py-2.5 text-[12.5px] text-zinc-300 hover:text-white hover:border-cyan-400/30 transition-colors text-left"
                >
                  For {n.label} <ArrowRight size={11} className="inline ml-0.5 opacity-60" />
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <CVFooter />

      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={handleSelectAgent} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export default CVLandingPage;
