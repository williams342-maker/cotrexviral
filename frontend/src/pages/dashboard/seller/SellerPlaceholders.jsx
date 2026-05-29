import React from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../../../components/DashboardLayout';
import { MessageSquare, TrendingUp, ShieldCheck, BarChart3, Sparkles, ArrowRight } from 'lucide-react';

/* Phase 2/3 placeholder pages — the routes need to exist (sidebar links
   resolve to a real page) but the heavy logic ships in the next session.
   Each card honestly tells the operator what phase will deliver it. */

export const SellerConversations = () => (
  <SellerPlaceholder
    title="Seller OS · Conversations"
    icon={MessageSquare}
    phase="Phase 2"
    headline="Cortex will run every outreach conversation here."
    bullets={[
      'Per-seller threads (email + Instagram DM + Facebook + LinkedIn)',
      'Sent · Delivered · Opened · Replied · Interested events',
      'Seller Success AI with auto-escalation when confidence is low',
    ]}
  />
);

export const SellerOnboarding = () => (
  <SellerPlaceholder
    title="Seller OS · Onboarding"
    icon={TrendingUp}
    phase="Phase 3"
    headline="Sub-10-minute autonomous onboarding."
    bullets={[
      'Auto-create account + storefront',
      'Import products + generate descriptions + SEO metadata',
      'Send welcome sequence (drips through email + social DMs)',
    ]}
  />
);

export const SellerRetention = () => (
  <SellerPlaceholder
    title="Seller OS · Retention"
    icon={ShieldCheck}
    phase="Phase 3"
    headline="Detect churn before it happens."
    bullets={[
      'Monitor active listings, sales, traffic, engagement',
      'Surface inactivity + declining-performance signals',
      'Auto-launch retention workflows (offer + nudge sequence)',
    ]}
  />
);

export const SellerAnalytics = () => (
  <SellerPlaceholder
    title="Seller OS · Analytics"
    icon={BarChart3}
    phase="Phase 3"
    headline="The unified seller funnel report."
    bullets={[
      'Cohort-level conversion rates per source / niche / offer',
      'Cortex's ROI per dollar of LLM spend',
      'Compare mission velocity across niches',
    ]}
  />
);

const SellerPlaceholder = ({ title, icon: Icon, phase, headline, bullets }) => {
  const navigate = useNavigate();
  return (
    <DashboardLayout title={title} subtitle={headline}>
      <div className="space-y-5" data-testid={`seller-placeholder-${phase.toLowerCase().replace(' ', '-')}`}>
        <div className="rounded-2xl border border-white/5 bg-gradient-to-br from-violet-500/10 via-blue-500/5 to-zinc-900 p-8 flex items-start gap-5">
          <div className="w-14 h-14 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center">
            <Icon size={22} className="text-violet-300" />
          </div>
          <div className="flex-1">
            <div className="text-[11px] uppercase tracking-wider text-violet-300 font-semibold mb-1">
              {phase} · coming next
            </div>
            <div className="text-xl font-semibold text-white cv-display mb-3">{headline}</div>
            <ul className="space-y-1.5 text-[13px] text-zinc-400">
              {bullets.map((b) => (
                <li key={b} className="flex items-start gap-2"><Sparkles size={11} className="mt-1 text-violet-300" /> {b}</li>
              ))}
            </ul>
            <button onClick={() => navigate('/dashboard/seller-os')}
                    data-testid="seller-placeholder-back"
                    className="mt-5 text-[12px] font-semibold px-3.5 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-white transition inline-flex items-center gap-1.5">
              Back to Mission Control <ArrowRight size={11} />
            </button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};
