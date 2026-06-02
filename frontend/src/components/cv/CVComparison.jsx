import React from 'react';
import { motion } from 'framer-motion';
import { Check, X, ArrowRight } from 'lucide-react';
import CVBackdrop from './CVBackdrop';

/**
 * Comparison table — addresses "vs ChatGPT, Buffer, Hootsuite, Jasper, Copy.ai"
 * positioning question that buyers ask during evaluation. Static, opinionated,
 * and honest about competitor strengths (saying "Buffer is bad at writing"
 * lands; saying "Buffer is bad at everything" doesn't).
 */

const ROWS = [
  { label: 'AI writes hook-tested posts',     cv: true,  chatgpt: 'partial', buffer: false, hootsuite: false, jasper: 'partial', copyai: 'partial' },
  { label: 'Studies real-time trends',        cv: true,  chatgpt: false,     buffer: false, hootsuite: false, jasper: false,     copyai: false },
  { label: 'Schedules posts at peak times',   cv: true,  chatgpt: false,     buffer: true,  hootsuite: true,  jasper: false,     copyai: false },
  { label: 'Publishes natively (no Zapier)',  cv: true,  chatgpt: false,     buffer: true,  hootsuite: true,  jasper: false,     copyai: false },
  { label: 'Learns from your post results',   cv: true,  chatgpt: false,     buffer: false, hootsuite: 'partial', jasper: false, copyai: false },
  { label: 'Multi-channel from one composer', cv: true,  chatgpt: false,     buffer: true,  hootsuite: true,  jasper: false,     copyai: false },
  { label: 'Generates short-form video scripts', cv: true, chatgpt: 'partial', buffer: false, hootsuite: false, jasper: 'partial', copyai: 'partial' },
  { label: 'Built-in analytics + attribution', cv: true, chatgpt: false,     buffer: true,  hootsuite: true,  jasper: false,     copyai: false },
];

const Cell = ({ v }) => {
  if (v === true)     return <Check size={14} className="text-emerald-400 mx-auto" />;
  if (v === false)    return <X     size={14} className="text-zinc-700  mx-auto" />;
  if (v === 'partial')return <span className="text-amber-400 text-[11px] font-semibold mx-auto inline-block">partial</span>;
  return null;
};

const ColHead = ({ label, highlight }) => (
  <th className={`px-3 py-3 text-center text-[11px] font-bold uppercase tracking-widest ${
    highlight
      ? 'text-violet-200 bg-violet-500/10 border-x border-violet-500/20'
      : 'text-zinc-500'
  }`}>
    {label}
  </th>
);

const CVComparison = ({ id = 'compare' }) => {
  return (
    <section id={id} className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-compare">
      <CVBackdrop />
      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">
            Why not just use…
          </span>
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="cv-display text-4xl sm:text-5xl font-semibold text-white mt-3 leading-tight"
          >
            CortexViral vs the{' '}
            <span className="cv-gradient-text">10 tools you'd stitch together.</span>
          </motion.h2>
          <p className="mt-4 text-zinc-400 max-w-2xl mx-auto text-[15px]">
            Most marketers run ChatGPT for ideas, Buffer or Hootsuite for scheduling, Jasper or Copy.ai for body copy, and a spreadsheet for everything else. CortexViral does the whole loop.
          </p>
        </div>

        <div className="overflow-x-auto cv-glass-strong rounded-2xl">
          <table className="min-w-full text-[13px]" data-testid="cv-compare-table">
            <thead>
              <tr className="border-b border-white/10">
                <th className="px-4 py-4 text-left text-[11px] font-bold uppercase tracking-widest text-zinc-500">
                  Capability
                </th>
                <ColHead label="CortexViral" highlight />
                <ColHead label="ChatGPT" />
                <ColHead label="Buffer" />
                <ColHead label="Hootsuite" />
                <ColHead label="Jasper" />
                <ColHead label="Copy.ai" />
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r, i) => (
                <tr key={r.label}
                     className={`border-b border-white/5 ${i % 2 === 0 ? 'bg-white/[0.01]' : ''}`}
                     data-testid={`cv-compare-row-${i}`}>
                  <td className="px-4 py-3 text-zinc-200 font-medium">{r.label}</td>
                  <td className="px-3 py-3 text-center bg-violet-500/[0.04] border-x border-violet-500/15">
                    <Cell v={r.cv} />
                  </td>
                  <td className="px-3 py-3 text-center"><Cell v={r.chatgpt} /></td>
                  <td className="px-3 py-3 text-center"><Cell v={r.buffer} /></td>
                  <td className="px-3 py-3 text-center"><Cell v={r.hootsuite} /></td>
                  <td className="px-3 py-3 text-center"><Cell v={r.jasper} /></td>
                  <td className="px-3 py-3 text-center"><Cell v={r.copyai} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-8 flex justify-center">
          <a href="/tools/viral-post-generator"
              data-testid="cv-compare-try-tool"
              className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-11 rounded-full">
            Try the free viral post generator <ArrowRight size={13} />
          </a>
        </div>
      </div>
    </section>
  );
};

export default CVComparison;
