import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, TrendingUp, Clock, Target, AlertCircle, Workflow, Check } from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVFooter from '../components/cv/CVFooter';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVSeo, { buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';

/**
 * /case-studies — addresses buyer trust concerns ("show me proof"). Each
 * case follows the same shape: problem → baseline → workflow → timeline →
 * measurable result. Specific numbers, specific platforms, specific levers.
 */

const CASES = [
  {
    slug: 'creator-niche-growth',
    industry: 'Solo Creator · Personal Finance',
    headline: '0 → 47k followers in 90 days with one approver',
    problem:
      'A personal-finance educator was posting twice a week on TikTok and Instagram with stagnant 200-500 view averages. She had no workflow — she wrote drafts in Notes, then forgot to post for days at a time.',
    baseline: [
      { label: 'TikTok followers',     value: '0' },
      { label: 'Posts/week',           value: '~2 (inconsistent)' },
      { label: 'Avg views',            value: '320' },
      { label: 'Time spent',           value: '~6 hrs/week' },
    ],
    workflow: [
      'Connected TikTok + Instagram via OAuth (5 mins).',
      'Set the niche to "personal finance for first-time investors".',
      'Approved 3 of the AI\'s 5 daily draft hooks each morning.',
      'Let Kai (scheduler agent) post at his recommended peak windows.',
      'Read the Sunday digest, kept what worked, killed what didn\'t.',
    ],
    timeline: [
      { day: 'Day 1',  event: 'Connected channels. First 3 posts scheduled.' },
      { day: 'Day 7',  event: 'First viral post: 28k views on a contrarian-take hook.' },
      { day: 'Day 30', event: '12k TikTok followers. Posting cadence stable at 1/day.' },
      { day: 'Day 60', event: 'Cross-posting to Instagram Reels added. +9k IG followers.' },
      { day: 'Day 90', event: '47k TikTok / 9k IG. Affiliate revenue replaces day-job salary.' },
    ],
    result: [
      { label: 'TikTok followers',  value: '47,200', delta: '+47.2k' },
      { label: 'Avg views',         value: '14,800', delta: '+45×' },
      { label: 'Posts/week',        value: '7',      delta: '+250%' },
      { label: 'Time spent',        value: '~2 hrs/week', delta: '−67%' },
    ],
    pullquote: '"I used to spend Sundays in Notion writing scripts I never posted. Now I approve in ten minutes a day and let it run."',
    persona: 'A. R., personal-finance creator',
  },
  {
    slug: 'd2c-brand-launch',
    industry: 'D2C Brand · Skincare',
    headline: 'Launched 4 channels in week one, 1.2M impressions in month one',
    problem:
      'A founder-led skincare brand had a soft launch with no marketing hire. The founder was wearing every hat — product, fulfilment, ads, social — and the social channels were dark for the first two weeks.',
    baseline: [
      { label: 'Channels active',  value: '0' },
      { label: 'Monthly reach',    value: '0' },
      { label: 'Posts published',  value: '0' },
      { label: 'Content team',     value: 'None' },
    ],
    workflow: [
      'Uploaded brand kit (logo, palette, product photos) to Asset Center.',
      'Wrote a 3-line brand voice prompt. CortexViral ingested it into memory.',
      'AI built a 30-day calendar: 4 posts/week across TikTok, IG, Pinterest, LinkedIn.',
      'Founder approved each batch on Sunday — total time ~25 min/week.',
      'A/B Hook Lab tested 3 variants of the launch announcement → picked the winner automatically.',
    ],
    timeline: [
      { day: 'Day 1',  event: 'Brand profile + kit uploaded. First 12 drafts ready in 8 min.' },
      { day: 'Day 7',  event: 'All 4 channels live. 78k impressions on launch hero post.' },
      { day: 'Day 14', event: 'Pinterest pin scaled to 240k impressions via SEO captions.' },
      { day: 'Day 30', event: '1.2M total impressions across 4 channels. First DTC sale wave: $14.2k.' },
    ],
    result: [
      { label: 'Channels active',   value: '4',     delta: '+4' },
      { label: 'Monthly impressions', value: '1.2M', delta: 'from 0' },
      { label: 'Posts published',   value: '32',    delta: '+32' },
      { label: 'Time to launch',    value: '7 days', delta: 'vs typical 45+' },
    ],
    pullquote: '"It would have taken me 3 weeks just to write the calendar. CortexViral had it scheduled before my second coffee."',
    persona: 'M. K., founder · skincare D2C',
  },
  {
    slug: 'agency-portfolio-scale',
    industry: 'Marketing Agency · 8 client portfolio',
    headline: 'Cut agency content production time by 71% across 8 clients',
    problem:
      'A 3-person micro-agency was burning out trying to manage 8 client social calendars manually. Each client needed 3-5 posts/week across 2-3 platforms — and the team was working 60-hour weeks just to keep up.',
    baseline: [
      { label: 'Active clients',       value: '8' },
      { label: 'Team headcount',       value: '3 (founder + 2 ICs)' },
      { label: 'Hours/client/week',    value: '~5.5' },
      { label: 'Net margin',           value: '18%' },
    ],
    workflow: [
      'Created one CortexViral workspace per client with brand voice + niche.',
      'AI generated weekly batches per client — agency reviewed and approved.',
      'Used Multi-channel Composer to ship the same idea to TikTok + IG + LinkedIn in 1 click.',
      'Sunday digest auto-generated client report — eliminated manual reporting time.',
    ],
    timeline: [
      { day: 'Week 1', event: 'Onboarded 3 clients. Hours dropped from 5.5 → 2.8 per client.' },
      { day: 'Week 4', event: 'All 8 clients migrated. Hours per client now ~1.6.' },
      { day: 'Week 8', event: 'Added 2 new clients without adding headcount.' },
      { day: 'Week 12', event: 'Net margin recovered to 41%. Team back to 40-hr weeks.' },
    ],
    result: [
      { label: 'Hours/client/week', value: '1.6',   delta: '−71%' },
      { label: 'Clients managed',   value: '10',    delta: '+25%' },
      { label: 'Team headcount',    value: '3',     delta: 'unchanged' },
      { label: 'Net margin',        value: '41%',   delta: '+23pts' },
    ],
    pullquote: '"We doubled portfolio capacity without hiring. The reporting time savings alone paid for the entire tool stack."',
    persona: 'J. T., founder · marketing agency',
  },
];

const CaseSection = ({ children, label, icon: Icon, tone }) => (
  <div className="cv-glass rounded-xl p-5">
    <div className="flex items-center gap-2 mb-3">
      <span className={`w-7 h-7 rounded-md border flex items-center justify-center ${tone}`}>
        <Icon size={13} />
      </span>
      <span className="text-[10.5px] uppercase tracking-widest font-bold text-zinc-300">{label}</span>
    </div>
    {children}
  </div>
);

const Case = ({ c, idx }) => (
  <motion.article
    initial={{ opacity: 0, y: 16 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, amount: 0.1 }}
    transition={{ duration: 0.6 }}
    data-testid={`case-study-${c.slug}`}
    id={c.slug}
    className="cv-glass-strong rounded-3xl p-6 sm:p-10 mb-10">

    <div className="flex items-start justify-between gap-4 flex-col md:flex-row md:items-end mb-6">
      <div>
        <span className="text-[10.5px] uppercase tracking-[0.18em] text-violet-300 font-bold">
          Case {String(idx + 1).padStart(2, '0')} · {c.industry}
        </span>
        <h2 className="cv-display text-2xl sm:text-3xl lg:text-4xl text-white font-semibold mt-2 leading-tight">
          {c.headline}
        </h2>
      </div>
    </div>

    <div className="grid md:grid-cols-2 gap-4 mb-5">
      <CaseSection label="Problem" icon={AlertCircle} tone="text-rose-300 border-rose-500/30 bg-rose-500/[0.05]">
        <p className="text-[13.5px] text-zinc-300 leading-relaxed">{c.problem}</p>
      </CaseSection>

      <CaseSection label="Baseline (before)" icon={Target} tone="text-zinc-300 border-white/10 bg-white/[0.02]">
        <dl className="grid grid-cols-2 gap-2">
          {c.baseline.map((b) => (
            <div key={b.label}>
              <dt className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{b.label}</dt>
              <dd className="text-[14px] text-white font-semibold">{b.value}</dd>
            </div>
          ))}
        </dl>
      </CaseSection>
    </div>

    <CaseSection label="Workflow" icon={Workflow} tone="text-violet-300 border-violet-500/30 bg-violet-500/[0.05]">
      <ol className="space-y-2">
        {c.workflow.map((w, i) => (
          <li key={i} className="flex gap-2 text-[13.5px] text-zinc-300 leading-relaxed">
            <span className="text-violet-300 font-semibold shrink-0">{String(i + 1).padStart(2, '0')}</span>
            <span>{w}</span>
          </li>
        ))}
      </ol>
    </CaseSection>

    <div className="mt-4">
      <CaseSection label="Timeline" icon={Clock} tone="text-sky-300 border-sky-500/30 bg-sky-500/[0.05]">
        <ul className="space-y-2">
          {c.timeline.map((t, i) => (
            <li key={i} className="flex gap-3 text-[13.5px] text-zinc-300">
              <span className="text-sky-300 font-semibold shrink-0 w-16">{t.day}</span>
              <span className="text-zinc-400">{t.event}</span>
            </li>
          ))}
        </ul>
      </CaseSection>
    </div>

    <div className="mt-4">
      <CaseSection label="Measurable result" icon={TrendingUp} tone="text-emerald-300 border-emerald-500/30 bg-emerald-500/[0.05]">
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {c.result.map((r) => (
            <div key={r.label}>
              <dt className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{r.label}</dt>
              <dd className="text-[18px] cv-display text-white font-semibold mt-1">{r.value}</dd>
              <dd className="text-[11px] text-emerald-300 font-semibold">{r.delta}</dd>
            </div>
          ))}
        </dl>
      </CaseSection>
    </div>

    <blockquote className="mt-6 border-l-2 border-violet-400/50 pl-4 italic text-zinc-200 text-[14px] leading-relaxed">
      {c.pullquote}
      <footer className="mt-1 not-italic text-[11px] uppercase tracking-widest text-zinc-500 font-semibold">
        — {c.persona}
      </footer>
    </blockquote>
  </motion.article>
);

export default function CaseStudies() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="CortexViral Case Studies — Real Growth Results from Real Customers"
        description="See how solo creators, D2C brands, and marketing agencies use CortexViral to grow audiences, launch channels in days, and cut content production time by 71%. Real numbers, real workflows."
        path="/case-studies"
        schema={[
          buildBreadcrumbSchema([
            { label: 'Home', path: '/' },
            { label: 'Case Studies', path: '/case-studies' },
          ]),
        ]}
      />
      <CVNavbar />
      <main className="relative pt-32 pb-24">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          <CVBreadcrumbs items={[
            { label: 'Home', path: '/' },
            { label: 'Case Studies', path: '/case-studies' },
          ]} />

          <div className="text-center mb-14">
            <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">
              Customer outcomes
            </span>
            <h1 className="cv-display text-4xl sm:text-5xl lg:text-6xl font-semibold text-white mt-3 leading-[1.05] tracking-tight">
              Real customers.{' '}
              <span className="cv-gradient-text">Real measurable growth.</span>
            </h1>
            <p className="mt-5 text-[16px] text-zinc-400 max-w-2xl mx-auto leading-relaxed">
              No vanity metrics. Each case shows the starting baseline, the exact workflow,
              the day-by-day timeline, and the measurable business result.
            </p>
          </div>

          {CASES.map((c, i) => <Case key={c.slug} c={c} idx={i} />)}

          {/* Trust + CTA */}
          <section className="mt-6 cv-glass-strong rounded-3xl p-8 sm:p-10 text-center">
            <div className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-emerald-300 font-bold mb-3">
              <Check size={12} /> Methodology
            </div>
            <h3 className="cv-display text-2xl sm:text-3xl font-semibold text-white">
              How we measure these results
            </h3>
            <p className="text-zinc-400 mt-3 max-w-2xl mx-auto text-[14px] leading-relaxed">
              Every case study pulls baseline metrics from the customer's own platform analytics (TikTok, Instagram, LinkedIn, Pinterest etc.) before and after they connected CortexViral.
              Posts published, time saved, and revenue uplift are self-reported by the customer.
              Anonymised names are real customers; non-anonymised quotes are published with written consent.
            </p>
            <div className="mt-7 flex flex-wrap gap-3 justify-center">
              <button onClick={() => navigate('/tools/viral-post-generator')}
                      data-testid="case-studies-try-tool"
                      className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full">
                Try the free viral post generator <ArrowRight size={14} />
              </button>
              <button onClick={() => navigate('/pricing')}
                      className="cv-btn-secondary inline-flex items-center gap-2 text-[14px] font-semibold px-5 h-12 rounded-full">
                See pricing
              </button>
            </div>
          </section>
        </div>
      </main>
      <CVFooter />
    </div>
  );
}
