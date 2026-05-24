import React, { useState } from 'react';
import { useParams, Navigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Check, Sparkles } from 'lucide-react';
import CVNavbar from '../../components/cv/CVNavbar';
import CVBackdrop from '../../components/cv/CVBackdrop';
import CVFaq from '../../components/cv/CVFaq';
import CVFooter from '../../components/cv/CVFooter';
import CVSeo, { SOFTWARE_SCHEMA, buildFaqSchema } from '../../components/cv/CVSeo';
import { SelectAgentModal, AgentChatModal } from '../../components/Modals';
import { getCombo, ALL_COMBOS } from './data';

const buildFaqs = (tool, niche) => [
  {
    q: `Is the ${tool.label.toLowerCase()} really tailored for ${niche.label.toLowerCase()}?`,
    a: `Yes. CortexViral learns your voice and outputs ${tool.label.toLowerCase()} variants specifically for ${niche.audience}. Every generation reflects the pain points (${niche.pains.slice(0, 2).join(', ')}) and the ${niche.voice} tone that resonates in your niche.`,
  },
  {
    q: `Will the AI-generated posts actually sound like a real ${niche.label.toLowerCase().slice(0, -1)}?`,
    a: `Our model is trained on thousands of top-performing posts from ${niche.label.toLowerCase()}, so outputs match the cadence, hooks, and CTAs your audience already engages with. You can also feed your existing posts into the voice trainer for a perfect match.`,
  },
  {
    q: `Can I publish directly from CortexViral?`,
    a: `Yes — connect your channels once and CortexViral schedules + publishes automatically at each platform\'s peak window. ${niche.label} on the Pro plan typically save 5-8 hours per week.`,
  },
  {
    q: `Is there a free plan for ${niche.label.toLowerCase()}?`,
    a: `Absolutely — start with our Free plan (20 generations / month). Most ${niche.label.toLowerCase()} upgrade to Pro once they see the time savings — it usually pays for itself within the first week.`,
  },
];

const NicheToolPage = () => {
  const { slug } = useParams();
  const combo = getCombo(slug);
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);

  if (!combo) return <Navigate to="/" replace />;
  const { tool, niche } = combo;
  const faqs = buildFaqs(tool, niche);

  const title = `${tool.label} for ${niche.label} — AI-Powered & Free to Try`;
  const description = `${tool.label} built for ${niche.audience}. CortexViral writes ${niche.voice} ${tool.primaryKeyword} content in your voice — schedule, publish, and grow without burning out.`;

  // Related niches (same tool, other 3 niches) for internal linking
  const related = ALL_COMBOS
    .filter((c) => c.tool.slug === tool.slug && c.niche.slug !== niche.slug)
    .slice(0, 3);
  // Cross-sell: same niche, other tools
  const crossSell = ALL_COMBOS
    .filter((c) => c.niche.slug === niche.slug && c.tool.slug !== tool.slug)
    .slice(0, 3);

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title={title}
        description={description}
        path={`/tools/${slug}`}
        schema={[SOFTWARE_SCHEMA, buildFaqSchema(faqs.map((f) => ({ question: f.q, answer: f.a })))]}
      />
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      {/* HERO */}
      <section className="relative pt-32 pb-16 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="inline-flex items-center gap-2 px-3 h-7 rounded-full cv-glass text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-300 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 cv-pulse" />
            {tool.label} for {niche.label}
          </span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-4xl sm:text-5xl lg:text-6xl font-semibold text-white leading-[0.95]"
          >
            The AI {tool.label}{' '}
            <span className="cv-gradient-text">Built for {niche.label}.</span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="mt-6 max-w-2xl mx-auto text-[16px] text-zinc-400 leading-relaxed"
          >
            CortexViral generates {tool.primaryKeyword} content in a {niche.voice} voice tuned for {niche.audience}.
            Stop guessing what to post — let AI do the heavy lifting while you focus on {niche.pains[0]}.
          </motion.p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/dashboard"
              className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full"
              data-testid="niche-cta-primary"
            >
              Generate for free <ArrowRight size={15} />
            </Link>
            <button
              onClick={() => setSelectOpen(true)}
              className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full"
            >
              Chat with {tool.aiAgent}
            </button>
          </div>
        </div>
      </section>

      {/* PAIN POINTS */}
      <section className="relative cv-dark py-20">
        <CVBackdrop />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white text-center mb-12">
            Made for the way <span className="cv-gradient-text">{niche.label.toLowerCase()}</span> actually work
          </h2>
          <div className="grid md:grid-cols-3 gap-5">
            {niche.pains.map((p, i) => (
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
                <h3 className="cv-display text-[17px] font-semibold text-white capitalize">{p}</h3>
                <p className="text-[13px] text-zinc-400 mt-2 leading-relaxed">
                  CortexViral writes {tool.label.toLowerCase()} content engineered to address this exact pain point — using {niche.voice} language your audience trusts.
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* SAMPLE OUTPUT */}
      <section className="relative cv-dark py-20">
        <CVBackdrop />
        <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-10">
            <h2 className="cv-display text-3xl sm:text-4xl font-semibold text-white">
              See what CortexViral writes for <span className="cv-gradient-text">{niche.label.toLowerCase()}</span>
            </h2>
          </div>
          <div className="cv-glass-strong rounded-3xl p-7 cv-glow-soft">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-violet-400 font-semibold mb-4">
              <Sparkles size={11} /> Sample hook · {tool.label.toLowerCase()}
            </div>
            <div className="cv-display text-2xl sm:text-3xl text-white leading-snug">
              {niche.sampleHook}
            </div>
            <div className="mt-6 pt-5 border-t border-white/5 text-[13px] text-zinc-400 leading-relaxed">
              Generated for <strong className="text-zinc-200">{niche.audience}</strong> using a {niche.voice} tone.
              Pair with optimal-time scheduling and you have a viral system that runs while you work with clients.
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <CVFaq faqs={faqs} title={<>Common questions from <span className="cv-gradient-text">{niche.label.toLowerCase()}</span></>} />

      {/* INTERNAL LINKS */}
      <section className="relative cv-dark pb-20">
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 grid md:grid-cols-2 gap-10">
          <div>
            <h2 className="cv-display text-xl font-semibold text-white mb-4">More {tool.label.toLowerCase()} guides</h2>
            <div className="flex flex-wrap gap-2.5">
              {related.map((r) => (
                <Link key={r.slug} to={`/tools/${r.slug}`} className="cv-glass rounded-full px-4 py-2 text-[13px] text-zinc-300 hover:text-white hover:border-cyan-400/40 transition-colors">
                  For {r.niche.label} <ArrowRight size={11} className="inline ml-0.5" />
                </Link>
              ))}
            </div>
          </div>
          <div>
            <h2 className="cv-display text-xl font-semibold text-white mb-4">Other tools for {niche.label.toLowerCase()}</h2>
            <div className="flex flex-wrap gap-2.5">
              {crossSell.map((r) => (
                <Link key={r.slug} to={`/tools/${r.slug}`} className="cv-glass rounded-full px-4 py-2 text-[13px] text-zinc-300 hover:text-white hover:border-cyan-400/40 transition-colors">
                  {r.tool.label} <ArrowRight size={11} className="inline ml-0.5" />
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <CVFooter />

      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={(a) => { setActiveAgent(a); setSelectOpen(false); setTimeout(() => setChatOpen(true), 120); }} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export default NicheToolPage;
