import React, { useEffect, useRef } from 'react';
import { Quote } from 'lucide-react';
import { testimonials } from '../data/mock';

const Testimonials = () => {
  const trackRef = useRef(null);

  // duplicate for infinite marquee
  const items = [...testimonials, ...testimonials];

  return (
    <section className="py-24 overflow-hidden">
      <div className="max-w-7xl mx-auto px-5">
        <div className="text-center max-w-3xl mx-auto mb-14">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4 block">Customers</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] tracking-tight text-neutral-900 font-medium">
            Don't take our word for it
          </h2>
          <p className="mt-5 text-neutral-600 text-[16px]">
            Here's what our customers think about our AI agents.
          </p>
        </div>
      </div>

      <div className="relative">
        <div className="absolute left-0 top-0 bottom-0 w-32 z-10 bg-gradient-to-r from-[#F6F4ED] to-transparent pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-32 z-10 bg-gradient-to-l from-[#F6F4ED] to-transparent pointer-events-none" />

        <div ref={trackRef} className="flex gap-5 animate-marquee group-hover:[animation-play-state:paused]" style={{ width: 'max-content' }}>
          {items.map((t, i) => (
            <div key={i} className="w-[380px] md:w-[440px] shrink-0 bg-white rounded-3xl p-7 border border-neutral-200/70 shadow-[0_2px_12px_rgba(0,0,0,0.03)]">
              <Quote size={22} className="text-[#1B7BFF]/60 mb-4" />
              <p className="text-[15.5px] text-neutral-800 leading-relaxed line-clamp-6">{t.quote}</p>
              <div className="mt-6 pt-5 border-t border-neutral-100 flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full ${t.color} flex items-center justify-center text-white font-semibold`}>
                  {t.initial}
                </div>
                <div>
                  <div className="text-[14px] font-semibold text-neutral-900">{t.company}</div>
                  <div className="text-[12px] text-neutral-500">{t.location}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Testimonials;
