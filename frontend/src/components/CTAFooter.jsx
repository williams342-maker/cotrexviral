import React from 'react';
import { ArrowRight } from 'lucide-react';

const CTAFooter = ({ onGetStarted }) => {
  return (
    <section className="py-24">
      <div className="max-w-5xl mx-auto px-5">
        <div className="relative rounded-[40px] bg-gradient-to-br from-[#E8F1FF] via-white to-[#FFF4E0] p-12 md:p-20 text-center border border-neutral-200/70 overflow-hidden">
          {/* decorative orbs */}
          <div className="absolute -top-20 -left-20 w-72 h-72 rounded-full bg-emerald-200/30 blur-3xl" />
          <div className="absolute -bottom-20 -right-20 w-72 h-72 rounded-full bg-violet-200/30 blur-3xl" />

          <div className="relative">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#0B2F66] text-white font-bold text-base mb-6">
              e/
            </div>
            <h2 className="text-[clamp(2rem,4.5vw,3.5rem)] leading-[1.05] tracking-tight text-neutral-900 font-medium">
              Hire your marketing team.
              <br />
              <span className="text-neutral-500">Starting today.</span>
            </h2>
            <p className="mt-6 text-neutral-600 text-[16.5px] leading-relaxed max-w-xl mx-auto">
              Pick the specialists you need. Brief them once. They handle 250+ hours of work while you focus on strategy.
            </p>
            <div className="mt-9">
              <button
                onClick={onGetStarted}
                className="group inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white px-7 py-3.5 rounded-full text-[15px] font-medium shadow-[0_8px_28px_-6px_rgba(27,123,255,0.5)] transition-all duration-200 hover:translate-y-[-1px]"
              >
                Get Started
                <ArrowRight size={17} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
              <p className="mt-4 text-[13px] text-neutral-500">3-day free trial • Cancel anytime</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default CTAFooter;
