import React from 'react';
import { motion } from 'framer-motion';
import { Target, PenLine, Share2, TrendingUp, Rocket } from 'lucide-react';
import CVBackdrop from './CVBackdrop';

const steps = [
  { num: '01', icon: Target, color: 'text-violet-400', label: 'Strategy', desc: 'Data-driven insights and growth strategy customised for your niche.' },
  { num: '02', icon: PenLine, color: 'text-blue-400', label: 'Content', desc: 'Viral content engineered to capture attention in the first 3 seconds.' },
  { num: '03', icon: Share2, color: 'text-cyan-400', label: 'Distribution', desc: 'Multi-platform pushes that maximise reach at each channel\'s peak window.' },
  { num: '04', icon: TrendingUp, color: 'text-cyan-300', label: 'Conversion', desc: 'Optimised funnels and CTAs that turn attention into revenue.' },
  { num: '05', icon: Rocket, color: 'text-emerald-400', label: 'Scale', desc: 'AI-optimised scaling systems for unstoppable, compounding growth.' },
];

const CVPipeline = () => {
  return (
    <section id="pipeline" className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-pipeline">
      <CVBackdrop />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">How we drive growth</span>
          <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white mt-3 leading-tight">
            A Data-Backed{' '}
            <span className="cv-gradient-text">Growth Pipeline.</span>
          </h2>
          <p className="mt-4 text-zinc-400 max-w-xl mx-auto">Proven system. Predictable results. Sustainable scale.</p>
        </div>

        <div className="relative">
          {/* Connecting line — desktop only */}
          <div className="hidden lg:block absolute top-12 left-[8%] right-[8%] h-px" aria-hidden>
            <div className="h-full w-full bg-gradient-to-r from-violet-500/0 via-violet-500/60 via-blue-500/60 via-cyan-500/60 to-emerald-500/0" />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-5 gap-6 lg:gap-4">
            {steps.map((s, i) => (
              <motion.div
                key={s.num}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ duration: 0.5, delay: i * 0.08 }}
                className="text-center group"
                data-testid={`cv-pipeline-step-${i}`}
              >
                <div className="relative inline-flex items-center justify-center w-20 h-20 rounded-full cv-glass mb-4 group-hover:scale-110 transition-transform">
                  <div className="absolute inset-0 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ background: 'radial-gradient(circle, rgba(124,58,237,.35), transparent 60%)', filter: 'blur(15px)' }}
                  />
                  <s.icon size={26} className={`relative ${s.color}`} />
                </div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500 font-semibold mb-1">{s.num}</div>
                <div className="cv-display text-[20px] font-semibold text-white">{s.label}</div>
                <div className="text-[12.5px] text-zinc-400 mt-2 leading-relaxed max-w-[200px] mx-auto">{s.desc}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default CVPipeline;
