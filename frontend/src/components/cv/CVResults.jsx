import React from 'react';
import { motion } from 'framer-motion';
import CVBackdrop from './CVBackdrop';

const cases = [
  {
    badge: 'E-COMMERCE',
    badgeColor: 'text-pink-400 bg-pink-400/10 border-pink-400/20',
    name: 'GlowSkin',
    tag: 'Skincare Brand',
    primary: '+312%',
    primaryLabel: 'Revenue Increase',
    primaryColor: 'cv-gradient-text',
    sub: [
      { label: 'New Visitors', value: '2.4M' },
      { label: 'Revenue Generated', value: '$1.2M' },
    ],
    stroke: '#EC4899',
  },
  {
    badge: 'CREATOR',
    badgeColor: 'text-cyan-300 bg-cyan-400/10 border-cyan-400/20',
    name: 'Liam Carter',
    tag: 'Lifestyle Creator',
    primary: '+245K',
    primaryLabel: 'New Followers',
    primaryColor: 'text-cyan-300',
    sub: [
      { label: 'Video Views', value: '47M' },
      { label: 'Engagement Rate', value: '8.9%' },
    ],
    stroke: '#06B6D4',
  },
  {
    badge: 'SAAS',
    badgeColor: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/20',
    name: 'Taskly',
    tag: 'SaaS Platform',
    primary: '+182%',
    primaryLabel: 'User Growth',
    primaryColor: 'text-emerald-300',
    sub: [
      { label: 'New Signups', value: '18K' },
      { label: 'MRR Growth', value: '$580K' },
    ],
    stroke: '#10B981',
  },
];

const CaseCard = ({ c, i }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: '-80px' }}
    transition={{ duration: 0.5, delay: i * 0.1 }}
    className="cv-glass-strong rounded-3xl p-6 group hover:border-violet-400/30 transition-colors relative overflow-hidden"
    data-testid={`cv-case-${i}`}
  >
    <span className={`inline-block text-[10px] uppercase tracking-[0.2em] font-semibold px-2.5 py-1 rounded-full border ${c.badgeColor}`}>
      {c.badge}
    </span>
    <div className="mt-5">
      <div className="cv-display text-[20px] font-semibold text-white">{c.name}</div>
      <div className="text-[12px] text-zinc-500">{c.tag}</div>
    </div>
    <div className="mt-6">
      <div className={`cv-display text-5xl font-semibold ${c.primaryColor}`}>{c.primary}</div>
      <div className="text-[12px] text-zinc-400 mt-1">{c.primaryLabel}</div>
    </div>

    {/* Mini sparkline */}
    <svg viewBox="0 0 240 60" className="mt-5 w-full h-14">
      <defs>
        <linearGradient id={`grad-${i}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c.stroke} stopOpacity="0.45" />
          <stop offset="100%" stopColor={c.stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0,50 L30,46 L60,42 L90,36 L120,30 L150,22 L180,18 L210,10 L240,4 L240,60 L0,60 Z"
        fill={`url(#grad-${i})`}
      />
      <path
        d="M0,50 L30,46 L60,42 L90,36 L120,30 L150,22 L180,18 L210,10 L240,4"
        fill="none"
        stroke={c.stroke}
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>

    <div className="mt-6 grid grid-cols-2 gap-3 pt-5 border-t border-white/5">
      {c.sub.map((s) => (
        <div key={s.label}>
          <div className="cv-display text-[16px] font-semibold text-white">{s.value}</div>
          <div className="text-[10.5px] uppercase tracking-wider text-zinc-500 mt-0.5">{s.label}</div>
        </div>
      ))}
    </div>
  </motion.div>
);

const CVResults = () => {
  return (
    <section id="results" className="relative cv-dark py-28 overflow-hidden" data-testid="cv-section-results">
      <CVBackdrop />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Proven results</span>
          <h2 className="cv-display text-4xl sm:text-5xl font-semibold text-white mt-3 leading-tight">
            Grow Faster With{' '}
            <span className="cv-gradient-text">AI Content Systems.</span>
          </h2>
          <p className="mt-4 text-zinc-400">Three brands. Three industries. One AI engine driving viral growth.</p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {cases.map((c, i) => <CaseCard key={c.name} c={c} i={i} />)}
        </div>
      </div>
    </section>
  );
};

export default CVResults;
