import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import CVBackdrop from './CVBackdrop';

const DEFAULT_FAQS = [
  {
    q: 'What is an AI viral content generator?',
    a: 'An AI viral content generator like CortexViral uses large language models to draft hook-tested, platform-tailored social media posts in seconds — including hooks, captions, hashtags, and CTAs. It analyses what is currently trending in your niche, then writes content matched to each channel\'s peak posting window.',
  },
  {
    q: 'Can CortexViral really help me grow on TikTok and Instagram?',
    a: 'Yes. Our AI generates short-form video scripts with timed scenes, voiceover, on-screen text, and Instagram-ready captions. Combined with optimal-time scheduling and multi-variant testing, brands typically see 3–5× more reach within the first 60 days.',
  },
  {
    q: 'Which social platforms does CortexViral support?',
    a: 'CortexViral supports TikTok, Instagram, X (Twitter), LinkedIn, YouTube, Facebook, Pinterest, Threads, Reddit, and 30+ more channels. You publish once and CortexViral tailors the post for every connected channel.',
  },
  {
    q: 'How is this different from ChatGPT or other AI writers?',
    a: 'ChatGPT writes general text. CortexViral is a viral marketing automation tool: it studies real-time trends, generates platform-specific variants, schedules them at peak windows, tracks performance, and learns what works for your niche. It is a closed-loop growth system, not just a writer.',
  },
  {
    q: 'Do I need to hire a social media manager if I use CortexViral?',
    a: 'No. CortexViral replaces or augments your social-media manager. Four specialist AI agents (Nova, Sam, Kai, Angela) handle content, SEO, social listening, and email — all reporting into your inbox 24/7.',
  },
  {
    q: 'Is there a free plan?',
    a: 'Yes. Start free with limited AI generations, then upgrade to Pro for unlimited posts, real-time scheduling, premium analytics, and live publishing to connected channels.',
  },
];

const CVFaq = ({ faqs = DEFAULT_FAQS, title, kicker = 'Frequently asked', id = 'faq' }) => {
  const [open, setOpen] = useState(0);
  return (
    <section id={id} className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-faq">
      <CVBackdrop />
      <div className="relative max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">{kicker}</span>
          <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white mt-3 leading-tight">
            {title || (
              <>
                Questions about <span className="cv-gradient-text">AI viral content</span>?
              </>
            )}
          </h2>
        </div>

        <div className="space-y-3">
          {faqs.map((f, i) => (
            <div
              key={i}
              className={`cv-glass-strong rounded-2xl transition-colors ${
                open === i ? 'border-violet-400/30' : ''
              }`}
            >
              <button
                onClick={() => setOpen(open === i ? -1 : i)}
                className="w-full flex items-center justify-between text-left px-5 py-4"
                data-testid={`cv-faq-q-${i}`}
                aria-expanded={open === i}
                aria-controls={`cv-faq-a-${i}`}
              >
                <span className="cv-display text-[16px] font-semibold text-white pr-4">{f.q}</span>
                <ChevronDown
                  size={18}
                  className={`text-violet-300 shrink-0 transition-transform ${open === i ? 'rotate-180' : ''}`}
                />
              </button>
              <AnimatePresence initial={false}>
                {open === i && (
                  <motion.div
                    key="content"
                    id={`cv-faq-a-${i}`}
                    role="region"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden"
                  >
                    <div className="px-5 pb-5 text-[14px] text-zinc-400 leading-relaxed">{f.a}</div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export { DEFAULT_FAQS };
export default CVFaq;
