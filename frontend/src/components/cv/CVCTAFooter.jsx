import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import CVLogo from './CVLogo';

const CVCTAFooter = ({ onGetStarted }) => {
  return (
    <section className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-cta">
      {/* Vortex backdrop */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="cv-aurora cv-aurora-violet" style={{ top: '-20%', left: '50%', transform: 'translateX(-50%)', width: '70rem', height: '70rem' }} />
        <div className="absolute inset-0 cv-grid-bg opacity-50" />
      </div>

      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-12 gap-10 items-center">
        <div className="lg:col-span-7">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Ready to build your growth engine?</span>
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="cv-display text-4xl sm:text-5xl lg:text-6xl font-semibold text-white mt-3 leading-[1.05]"
          >
            Let's Build a Brand{' '}
            <span className="cv-gradient-text">People Can't Ignore.</span>
          </motion.h2>
          <p className="mt-5 text-zinc-400 max-w-xl text-[16px]">
            Partner with CortexViral and turn your brand into a viral growth machine —
            powered by AI agents that publish, optimise, and learn 24/7.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              onClick={onGetStarted}
              className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full"
              data-testid="cv-cta-launch"
            >
              Launch Your Growth System <ArrowRight size={15} />
            </button>
            <a
              href="/dashboard"
              className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full"
            >
              See Dashboard
            </a>
          </div>
        </div>

        {/* Orbiting logo visual */}
        <div className="lg:col-span-5 relative">
          <div className="relative aspect-square max-w-[420px] mx-auto cv-float">
            <div className="absolute inset-0 rounded-full" style={{
              background: 'radial-gradient(circle, rgba(124,58,237,.4), rgba(6,182,212,.2) 50%, transparent 75%)',
              filter: 'blur(50px)',
            }} />
            <CVLogo size={320} className="absolute inset-0 flex items-center justify-center" />

            {/* Orbiting avatars */}
            {[
              { top: '10%', left: '0%', label: 'Content Strategy' },
              { top: '80%', left: '10%', label: 'Performance Ads' },
              { top: '40%', right: '0%', label: 'Growth Analytics' },
            ].map((o, i) => (
              <div
                key={i}
                className="absolute cv-glass-strong rounded-full pl-2 pr-3 py-1.5 flex items-center gap-2 shadow-lg"
                style={{ top: o.top, left: o.left, right: o.right }}
              >
                <span className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-400 to-cyan-400" />
                <span className="text-[11px] text-white font-medium whitespace-nowrap">{o.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default CVCTAFooter;
