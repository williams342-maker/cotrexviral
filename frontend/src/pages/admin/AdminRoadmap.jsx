import React from 'react';
import DashboardLayout from '../../components/DashboardLayout';
import { Link } from 'react-router-dom';
import {
  CheckCircle2, Wrench, Telescope, ExternalLink, Github,
  Cpu, Database, Boxes, ServerCog, GitBranch,
} from 'lucide-react';

/* /admin/roadmap — INTERNAL engineering roadmap. Verbatim, raw form.
   Read by founders, devs, contractors. Not exposed publicly. */

const PHASES = [
  {
    pill: 'MVP · shipped',
    pillTone: 'emerald',
    icon: CheckCircle2,
    title: 'Phase 1 — MVP',
    timeline: 'Live in production at cortexviral.com',
    stack: ['Next.js (react-snap prerender)', 'OpenAI API (via Emergent LLM key)', 'MongoDB (Motor async)', 'APScheduler', 'FastAPI'],
    items: [
      { name: 'ChatGPT-powered marketing assistant', status: 'shipped' },
      { name: 'Basic dashboard', status: 'shipped' },
      { name: 'Content generator (multi-format)', status: 'shipped' },
      { name: 'Pinterest automation (OAuth + publishing)', status: 'shipped' },
      { name: 'Instagram automation (OAuth scaffold)', status: 'partial' },
      { name: 'Facebook automation (OAuth scaffold)', status: 'partial' },
      { name: 'TikTok automation (OAuth + publishing)', status: 'shipped' },
      { name: 'LinkedIn automation (OAuth + publishing)', status: 'shipped' },
    ],
    notes: [
      'Originally scoped as 2–4 weeks. Actual: ~8 weeks including auth, billing, admin, OAuth scaffolding for 5 platforms.',
      'Instagram + Facebook publishing API calls still TODO — OAuth tokens are being persisted, just not dispatched in scheduler.py yet.',
    ],
  },
  {
    pill: 'Phase 2 · in build',
    pillTone: 'violet',
    icon: Wrench,
    title: 'Phase 2 — Agent features',
    timeline: 'Q2–Q3 2026',
    stack: ['n8n for workflow orchestration', 'Pinecone or Weaviate for AI memory', 'Snscrape / official APIs for listening', 'Mailtrap → Mailgun for email automation'],
    items: [
      { name: 'Scheduled posting (every platform)', status: 'partial', note: 'Pinterest live. FB/IG/TikTok dispatch logic needs wiring.' },
      { name: 'Automatic blog generation', status: 'todo', note: 'Reuses Studio /generate-content with new "publish-ready" template.' },
      { name: 'Analytics summaries (LLM digest)', status: 'todo', note: 'Cron: weekly per-user run reading posts.dispatch.* and channel-fetched insights.' },
      { name: 'Email automation', status: 'todo', note: 'Lifecycle templates exist. Need trigger graph (welcome, abandoned-cart, re-engagement).' },
      { name: 'AI memory (per-user persistent context)', status: 'todo', note: 'Embed posts + outcomes; surface to LLM via context block in routes/ai.py.' },
      { name: 'Social listening', status: 'todo', note: 'Reddit + X first. Tap into Trends Engine cache for stitching.' },
    ],
    notes: [
      'Order priority: scheduled posting → email automation → analytics summaries → blog gen → memory → listening.',
      'Phase 2 should NOT introduce a new infra dependency unless it pays back within 60 days.',
    ],
  },
  {
    pill: 'Phase 3 · vision',
    pillTone: 'cyan',
    icon: Telescope,
    title: 'Phase 3 — Autonomous marketing',
    timeline: 'Q4 2026 → 2027',
    stack: ['Meta + TikTok Ads APIs', 'Tournament-style A/B harness', 'Multi-agent message bus (Redis Streams)', 'Vector DB for competitor corpus'],
    items: [
      { name: 'Campaign execution (brief-in, full-stack-out)', status: 'todo' },
      { name: 'Automatic A/B testing with auto-scaling', status: 'todo' },
      { name: 'Competitor monitoring (corpus + diff)', status: 'todo' },
      { name: 'AI workflows (visual node editor)', status: 'todo' },
      { name: 'Ad optimisation (Meta/TikTok ROAS loops)', status: 'todo' },
      { name: 'Multi-agent system (Nova/Sam/Kai/Angela)', status: 'todo' },
    ],
    notes: [
      'This is the "AI marketing employees" positioning. Hard requirement: agents must show their work — every action audit-logged + reversible.',
      'Each multi-agent role should be its own LangGraph / DSPy program with explicit handoffs; no spaghetti shared memory.',
    ],
  },
];

const TONES = {
  emerald: { pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', icon: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30' },
  violet:  { pill: 'bg-violet-500/15 text-violet-300 border-violet-500/30',  icon: 'text-violet-300 bg-violet-500/10 border-violet-500/30' },
  cyan:    { pill: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',       icon: 'text-cyan-300 bg-cyan-500/10 border-cyan-500/30' },
};

const STATUS = {
  shipped: { label: 'Shipped', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  partial: { label: 'Partial', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  todo:    { label: 'Todo',    cls: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/30' },
};

const AdminRoadmap = () => {
  return (
    <DashboardLayout
      title="Roadmap"
      subtitle="Internal engineering roadmap. Public version lives at /roadmap."
    >
      <div className="cv-dash-scope" data-testid="admin-roadmap">
        {/* External-link strip */}
        <div className="cv-glass rounded-2xl p-4 flex items-center gap-3 flex-wrap mb-6">
          <Link to="/roadmap" target="_blank" rel="noopener noreferrer"
            className="text-[12.5px] text-cyan-300 hover:text-cyan-200 inline-flex items-center gap-1.5"
            data-testid="admin-roadmap-public-link"
          >
            <ExternalLink size={12} /> View public /roadmap
          </Link>
          <span className="text-zinc-700">·</span>
          <span className="text-[12.5px] text-zinc-500 inline-flex items-center gap-1.5">
            <GitBranch size={12} /> Source of truth: <code className="text-zinc-300">/app/memory/PRD.md</code>
          </span>
        </div>

        {PHASES.map((phase) => {
          const tone = TONES[phase.pillTone];
          const Icon = phase.icon;
          return (
            <section
              key={phase.title}
              className="mb-8 cv-glass rounded-3xl overflow-hidden"
              data-testid={`admin-roadmap-${phase.pillTone}`}
            >
              {/* Header */}
              <div className="p-5 sm:p-6 border-b border-white/5 flex items-start gap-4">
                <div className={`shrink-0 w-12 h-12 rounded-xl border flex items-center justify-center ${tone.icon}`}>
                  <Icon size={20} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className={`text-[10.5px] uppercase tracking-[0.18em] font-semibold px-2.5 py-1 rounded-full border ${tone.pill}`}>
                      {phase.pill}
                    </span>
                    <span className="text-[11.5px] text-zinc-500 font-medium">{phase.timeline}</span>
                  </div>
                  <h2 className="text-[18px] font-semibold text-white">{phase.title}</h2>
                </div>
              </div>

              {/* Items */}
              <div className="px-5 sm:px-6 py-5">
                <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold mb-3 flex items-center gap-1.5">
                  <Boxes size={11} /> Features
                </div>
                <ul className="divide-y divide-white/5">
                  {phase.items.map((it) => {
                    const meta = STATUS[it.status];
                    return (
                      <li key={it.name} className="py-2.5 flex items-start gap-3 flex-wrap">
                        <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${meta.cls} shrink-0 mt-0.5`}>
                          {meta.label}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-[13.5px] text-white font-medium">{it.name}</div>
                          {it.note && (
                            <div className="text-[12px] text-zinc-500 mt-0.5 leading-relaxed font-mono">
                              {it.note}
                            </div>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Stack */}
              <div className="px-5 sm:px-6 py-5 border-t border-white/5 bg-white/[0.015]">
                <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold mb-3 flex items-center gap-1.5">
                  <Cpu size={11} /> Target stack
                </div>
                <div className="flex flex-wrap gap-2">
                  {phase.stack.map((s) => (
                    <span key={s} className="inline-flex items-center gap-1 text-[11.5px] font-mono text-zinc-300 bg-white/[0.04] border border-white/10 rounded px-2 py-1">
                      <Database size={10} className="text-zinc-500" /> {s}
                    </span>
                  ))}
                </div>
              </div>

              {/* Notes */}
              {phase.notes?.length > 0 && (
                <div className="px-5 sm:px-6 py-5 border-t border-white/5">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-semibold mb-3 flex items-center gap-1.5">
                    <ServerCog size={11} /> Internal notes
                  </div>
                  <ul className="space-y-2">
                    {phase.notes.map((n, i) => (
                      <li key={i} className="text-[12.5px] text-zinc-400 leading-relaxed pl-4 border-l border-violet-500/30">
                        {n}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          );
        })}

        <div className="text-center text-[11.5px] text-zinc-600 pt-4 pb-8 inline-flex items-center gap-1.5">
          <Github size={11} /> This page is admin-only. Edits → <code className="text-zinc-400">/app/frontend/src/pages/admin/AdminRoadmap.jsx</code>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default AdminRoadmap;
