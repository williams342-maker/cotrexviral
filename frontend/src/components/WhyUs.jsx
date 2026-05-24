import React from 'react';
import { Check, X, Minus, Bot, Briefcase, User } from 'lucide-react';
import { comparisonRows } from '../data/mock';

const WhyUs = () => {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-5">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4 block">Why us?</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] tracking-tight text-neutral-900 font-medium">
            Scale your marketing at a fraction of the cost.
            <span className="text-neutral-500"> Always on, always shipping.</span>
          </h2>
          <p className="mt-6 text-neutral-600 text-[17px] leading-relaxed">
            AI marketers cost 90% less than contractors. And they never ask for time off. Get expert-level execution across every channel — without the overhead of building a full in-house team.
          </p>
        </div>

        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.04)]">
          {/* Header */}
          <div className="grid grid-cols-4 bg-neutral-50/50 border-b border-neutral-200/70">
            <div className="p-5 text-[13px] text-neutral-500 font-medium">Compare</div>
            <ColHeader icon={Bot} label="AI Marketers" highlight />
            <ColHeader icon={Briefcase} label="Agencies" />
            <ColHeader icon={User} label="Human Contractors" />
          </div>

          {comparisonRows.map((row, i) => (
            <div key={i} className={`grid grid-cols-4 border-b border-neutral-100 last:border-0 ${i % 2 === 0 ? 'bg-white' : 'bg-neutral-50/30'}`}>
              <div className="p-4 md:p-5 text-[14px] text-neutral-700 font-medium">{row.feature}</div>
              <Cell value={row.ai} type="good" highlight />
              <Cell value={row.agency} type="neutral" />
              <Cell value={row.human} type="bad" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

const ColHeader = ({ icon: Icon, label, highlight }) => (
  <div className={`p-5 flex items-center justify-center gap-2 ${highlight ? 'bg-[#1B7BFF]/5 border-l border-r border-[#1B7BFF]/15' : ''}`}>
    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${highlight ? 'bg-[#1B7BFF] text-white' : 'bg-neutral-200 text-neutral-700'}`}>
      <Icon size={16} />
    </div>
    <span className={`text-[14px] font-semibold ${highlight ? 'text-[#1B7BFF]' : 'text-neutral-700'}`}>{label}</span>
  </div>
);

const Cell = ({ value, type, highlight }) => {
  const tone = type === 'good' ? 'text-emerald-700' : type === 'bad' ? 'text-rose-700' : 'text-neutral-600';
  const Ic = type === 'good' ? Check : type === 'bad' ? X : Minus;
  return (
    <div className={`p-4 md:p-5 flex items-center justify-center gap-2 text-center ${highlight ? 'bg-[#1B7BFF]/5 border-l border-r border-[#1B7BFF]/15' : ''}`}>
      <Ic size={14} className={tone} strokeWidth={2.5} />
      <span className={`text-[13.5px] font-medium ${highlight ? 'text-neutral-900' : 'text-neutral-700'}`}>{value}</span>
    </div>
  );
};

export default WhyUs;
