import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import CVBackdrop from './CVBackdrop';

const DEFAULT_FAQS = [
  {
    q: 'How does CortexViral generate viral social posts?',
    a: 'Tell CortexViral your niche and target audience, and our AI studies what is currently going viral in that vertical (hooks, formats, posting times). It then writes platform-tailored drafts — TikTok scripts, Instagram captions, LinkedIn long-form, Twitter threads — each variant tested against proven hook patterns. You approve in one tap and it ships.',
  },
  {
    q: 'Which social platforms can CortexViral post to?',
    a: 'CortexViral publishes directly to TikTok, Instagram, X (Twitter), LinkedIn, Facebook, YouTube, Pinterest, Reddit and Threads. You connect each channel once with OAuth — no copy-pasting between tabs.',
  },
  {
    q: 'How is this different from ChatGPT, Buffer, Jasper or Hootsuite?',
    a: 'ChatGPT writes general text — it doesn\'t schedule, doesn\'t learn what works for your audience, and can\'t publish anywhere. Buffer and Hootsuite schedule but make you write everything yourself. Jasper and Copy.ai generate copy but have no analytics or publishing. CortexViral closes the entire loop: trend research → draft → approve → schedule at peak time → measure → learn — in one product. See the full breakdown on our /agents page.',
  },
  {
    q: 'Can it really replace a social media manager?',
    a: 'For most solo founders, creators and small marketing teams — yes. CortexViral handles the four jobs an SMM does daily: ideation (Nova), content writing (Sam), distribution timing (Kai), and reply / community work (Angela). You keep human oversight: every post lands in your approval queue before it goes live.',
  },
  {
    q: 'Is there a free plan? How does pricing work?',
    a: 'Yes — start free with limited AI generations and one connected channel, no credit card. Paid tiers (Creator and Agency) unlock unlimited posts, more channels, scheduling, analytics, team seats and direct publishing. Full breakdown on the /pricing page.',
  },
  {
    q: 'How fast can I get my first post out?',
    a: 'About three minutes. Connect one channel, type your niche, hit generate. CortexViral returns five hook-tested drafts in ~20 seconds; pick one, approve, and it schedules to your next peak window automatically.',
  },
  {
    q: 'Do you have case studies and real results?',
    a: 'Yes — our insights blog covers marketplace growth playbooks, seller acquisition wins, and the campaign frameworks our customers use to grow 3-5x in 60 days. Start with /insights/marketplace-growth-strategies or /insights/seller-acquisition-playbook.',
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
