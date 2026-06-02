import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Play } from 'lucide-react';
import CVBackdrop from './CVBackdrop';
import CVLogo from './CVLogo';

const KPI = ({ label, value, accent }) => (
  <div className="flex flex-col">
    <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-medium">{label}</span>
    <span className={`cv-display text-[22px] font-semibold mt-0.5 ${accent}`}>{value}</span>
  </div>
);

const CVHero = ({ onGetStarted }) => {
  return (
    <section className="relative cv-dark overflow-hidden pt-32 pb-24 lg:pt-40 lg:pb-32" data-testid="cv-hero">
      <CVBackdrop variant="hero" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-12 gap-10 items-center">
        {/* Left: copy */}
        <div className="lg:col-span-7">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 px-3 h-7 rounded-full cv-glass text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-300 mb-6"
            data-testid="cv-hero-badge"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 cv-pulse" />
            AI social marketing autopilot
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05 }}
            className="cv-display text-5xl sm:text-6xl lg:text-7xl font-semibold text-white leading-[0.95]"
          >
            Create, schedule, and optimize{' '}
            <span className="cv-gradient-text">short-form social posts</span>
            <span className="text-zinc-400 text-[0.7em] font-normal"> — automatically.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.15 }}
            className="mt-6 max-w-2xl text-[17px] leading-relaxed text-zinc-400"
          >
            <strong className="text-zinc-200">
              Pick your niche → AI writes hook-tested posts → you approve in one tap → CortexViral schedules at peak times → it measures results and learns.
            </strong>{' '}
            Replace the work of a 5-person social team — without the overhead, the agency retainer, or stitching together ten tools.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25 }}
            className="mt-9 flex flex-wrap items-center gap-3"
          >
            <button
              onClick={onGetStarted}
              className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full"
              data-testid="cv-hero-cta-primary"
            >
              Start Free <ArrowRight size={15} />
            </button>
            <a
              href="/tools/viral-post-generator"
              className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full"
              data-testid="cv-hero-cta-secondary"
            >
              <Play size={13} /> Try the free tool
            </a>
          </motion.div>

          {/* Concrete-workflow strip — replaces vague "viral growth" claim with the 4 steps users will actually do. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-14"
            data-testid="cv-hero-workflow"
          >
            <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-600 font-medium mb-4">
              How CortexViral works
            </div>
            <ol className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12.5px]">
              {[
                { n: '01', t: 'Pick a niche',         d: 'Enter your topic + audience.' },
                { n: '02', t: 'AI generates hooks',   d: 'Hook-tested posts per platform.' },
                { n: '03', t: 'Approve in one tap',   d: 'Edit or accept the AI draft.' },
                { n: '04', t: 'It schedules + learns', d: 'Posts at peak times, tracks ROI.' },
              ].map((step) => (
                <li key={step.n} className="cv-glass rounded-xl p-3" data-testid={`cv-hero-step-${step.n}`}>
                  <div className="cv-display text-[13px] font-semibold cv-gradient-text">{step.n}</div>
                  <div className="text-white font-semibold mt-1">{step.t}</div>
                  <div className="text-zinc-500 mt-0.5 text-[11.5px] leading-snug">{step.d}</div>
                </li>
              ))}
            </ol>
          </motion.div>
        </div>

        {/* Right: hero visual — neural orb + floating dashboard */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, delay: 0.2, ease: 'easeOut' }}
          className="lg:col-span-5 relative"
        >
          <div className="relative aspect-square max-w-[520px] mx-auto cv-float">
            {/* Glow ring */}
            <div className="absolute inset-0 rounded-full" style={{
              background: 'radial-gradient(circle, rgba(124,58,237,.35), rgba(6,182,212,.18) 50%, transparent 70%)',
              filter: 'blur(40px)',
            }} />
            <CVLogo size={420} priority className="absolute inset-0 flex items-center justify-center" />
          </div>

          {/* Floating mini-dashboard card */}
          <motion.div
            initial={{ opacity: 0, x: -20, y: 20 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            className="absolute -bottom-4 -left-6 sm:left-0 cv-glass-strong rounded-2xl p-4 w-[230px] shadow-2xl"
            data-testid="cv-hero-floating-card"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Growth</span>
              <span className="text-[10.5px] text-emerald-400 font-semibold bg-emerald-400/10 px-1.5 py-0.5 rounded-full">+312%</span>
            </div>
            <div className="cv-display text-2xl font-semibold text-white">142K</div>
            <div className="text-[11px] text-zinc-500 mt-0.5">Followers · last 30 days</div>
            {/* Sparkline */}
            <svg viewBox="0 0 200 50" className="mt-3 w-full h-10">
              <defs>
                <linearGradient id="cvSpark" x1="0" x2="1">
                  <stop offset="0%" stopColor="#7C3AED" />
                  <stop offset="100%" stopColor="#06B6D4" />
                </linearGradient>
              </defs>
              <polyline
                fill="none"
                stroke="url(#cvSpark)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points="0,38 20,32 40,34 60,28 80,22 100,24 120,18 140,14 160,16 180,8 200,4"
              />
            </svg>
          </motion.div>

          {/* Floating top-right pill */}
          <motion.div
            initial={{ opacity: 0, x: 20, y: -10 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            transition={{ duration: 0.8, delay: 0.75 }}
            className="absolute top-2 right-0 cv-glass-strong rounded-full px-4 h-10 flex items-center gap-2 shadow-2xl"
          >
            <span className="w-2 h-2 rounded-full bg-violet-400 cv-pulse" />
            <span className="text-[12px] text-white font-medium">AI generating · 4.8M reach</span>
          </motion.div>
        </motion.div>
      </div>

      {/* KPI strip */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.7 }}
        className="relative mt-20 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8"
      >
        <div className="cv-glass-strong rounded-3xl px-8 py-6 grid grid-cols-2 sm:grid-cols-4 gap-6">
          <KPI label="Engagement" value="+320%" accent="text-white" />
          <KPI label="Reach" value="4.8M" accent="cv-gradient-text" />
          <KPI label="New followers" value="240K" accent="text-cyan-300" />
          <KPI label="Average ROI" value="18×" accent="text-violet-300" />
        </div>
      </motion.div>
    </section>
  );
};

export default CVHero;
