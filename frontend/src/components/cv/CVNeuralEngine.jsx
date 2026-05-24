import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Activity, Radar, Sparkles } from 'lucide-react';
import CVBackdrop from './CVBackdrop';

const features = [
  { icon: Activity, title: 'Trend Detection', desc: 'Catches rising topics 24-48h before they peak so you ride the wave, not chase it.', color: 'from-violet-500/30 to-violet-500/0' },
  { icon: Brain, title: 'Audience Insights', desc: 'AI synthesises behaviour signals from every platform into one living persona.', color: 'from-blue-500/30 to-blue-500/0' },
  { icon: Sparkles, title: 'Content Amplification', desc: 'Generates hook-tested variants for X, Reels, LinkedIn and TikTok — in your voice.', color: 'from-cyan-500/30 to-cyan-500/0' },
  { icon: Radar, title: 'Smart Distribution', desc: 'Schedules each variant at each channel\'s peak window — automatically.', color: 'from-emerald-500/30 to-emerald-500/0' },
];

const CVNeuralEngine = () => {
  return (
    <section id="system" className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-engine">
      <CVBackdrop />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid lg:grid-cols-12 gap-12 items-center">
        {/* Copy */}
        <div className="lg:col-span-5">
          <span className="inline-block text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold mb-4">Our system</span>
          <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white leading-tight">
            AI Content Generation{' '}
            <span className="cv-gradient-text block sm:inline">for Social Media.</span>
          </h2>
          <p className="mt-5 text-[16px] text-zinc-400 leading-relaxed max-w-md">
            CortexViral's neural engine writes hook-tested, platform-tailored posts in your voice,
            then schedules them at each channel's peak window. The result: real engagement,
            real followers, and a content system that compounds month over month.
          </p>
          <button
            onClick={() => document.querySelector('#pipeline')?.scrollIntoView({ behavior: 'smooth' })}
            className="cv-btn-primary mt-7 inline-flex items-center gap-2 text-[13.5px] font-semibold px-5 h-11 rounded-full"
            data-testid="cv-engine-cta"
          >
            Explore Our Process
          </button>
        </div>

        {/* Visualisation card */}
        <div className="lg:col-span-7">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.7 }}
            className="cv-glass-strong rounded-3xl p-6 sm:p-8 cv-glow-soft"
          >
            <div className="flex items-center justify-between mb-5">
              <div>
                <div className="text-[13px] font-semibold text-white">Growth Overview</div>
                <div className="text-[11.5px] text-zinc-500">Live · all channels</div>
              </div>
              <div className="text-[11px] cv-glass rounded-full px-3 py-1 text-zinc-400">Last 30 days</div>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-6">
              <Stat label="Impressions" value="24.8M" delta="+245%" />
              <Stat label="Engagement" value="2.7M" delta="+186%" />
              <Stat label="Followers" value="142K" delta="+312%" />
            </div>

            {/* SVG chart */}
            <div className="relative">
              <svg viewBox="0 0 600 220" className="w-full h-44">
                <defs>
                  <linearGradient id="cvLine" x1="0" x2="1">
                    <stop offset="0%" stopColor="#7C3AED" />
                    <stop offset="50%" stopColor="#2563EB" />
                    <stop offset="100%" stopColor="#06B6D4" />
                  </linearGradient>
                  <linearGradient id="cvArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.45" />
                    <stop offset="100%" stopColor="#06B6D4" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[40, 90, 140, 190].map((y) => (
                  <line key={y} x1="0" x2="600" y1={y} y2={y} stroke="rgba(255,255,255,0.05)" />
                ))}
                <path
                  d="M0,180 L60,165 L120,170 L180,140 L240,125 L300,130 L360,90 L420,80 L480,55 L540,40 L600,20 L600,220 L0,220 Z"
                  fill="url(#cvArea)"
                />
                <path
                  d="M0,180 L60,165 L120,170 L180,140 L240,125 L300,130 L360,90 L420,80 L480,55 L540,40 L600,20"
                  fill="none"
                  stroke="url(#cvLine)"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                {/* Glow dot at end */}
                <circle cx="600" cy="20" r="6" fill="#06B6D4" />
                <circle cx="600" cy="20" r="12" fill="#06B6D4" opacity="0.25" className="cv-pulse" />
              </svg>
              {/* X labels */}
              <div className="flex justify-between text-[10.5px] text-zinc-500 mt-2 px-1">
                <span>May 1</span><span>May 8</span><span>May 15</span><span>May 22</span><span>May 30</span>
              </div>
            </div>
          </motion.div>

          {/* Feature mini-grid below visualisation */}
          <div className="mt-6 grid sm:grid-cols-2 gap-3">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 0.1 * i }}
                className="cv-glass rounded-2xl p-4 group hover:border-cyan-400/30 transition-colors relative overflow-hidden"
                data-testid={`cv-engine-feature-${i}`}
              >
                <div className={`absolute -top-12 -right-12 w-32 h-32 rounded-full bg-gradient-to-br ${f.color} blur-2xl opacity-70 group-hover:opacity-100 transition-opacity`} />
                <f.icon size={18} className="relative text-cyan-300 mb-2" />
                <div className="relative text-[13.5px] font-semibold text-white">{f.title}</div>
                <div className="relative text-[12px] text-zinc-400 mt-1 leading-relaxed">{f.desc}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

const Stat = ({ label, value, delta }) => (
  <div className="cv-glass rounded-2xl p-3">
    <div className="text-[10.5px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>
    <div className="cv-display text-[20px] font-semibold text-white mt-1">{value}</div>
    <div className="text-[10.5px] text-emerald-400 font-semibold mt-0.5">{delta}</div>
  </div>
);

export default CVNeuralEngine;
