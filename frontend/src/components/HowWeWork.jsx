import React from 'react';
import { howWeWorkSteps, heroAgents } from '../data/mock';

const HowWeWork = () => {
  return (
    <section className="py-24">
      <div className="max-w-6xl mx-auto px-5">
        <div className="flex flex-col items-center text-center">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4">How we work</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.5rem)] leading-[1.05] tracking-tight text-neutral-900 font-medium max-w-3xl">
            We <span className="inline-flex items-center -space-x-3 align-middle mx-2">
              {heroAgents.slice(0, 3).map((a) => (
                <span key={a.id} className={`w-12 h-12 rounded-full ${a.bg} border-4 border-white inline-block overflow-hidden`}>
                  <img src={a.img} alt={a.name} className="w-full h-full object-cover" />
                </span>
              ))}
            </span> work
            <br />
            round-the-clock for you
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6 mt-16">
          {howWeWorkSteps.map((step, i) => (
            <div key={i} className="relative bg-white rounded-3xl p-8 border border-neutral-200/70 shadow-[0_2px_12px_rgba(0,0,0,0.03)] hover:shadow-[0_8px_28px_rgba(0,0,0,0.06)] transition-all hover:-translate-y-1">
              <div className="text-5xl font-display text-[#1B7BFF]/20 font-bold tracking-tight mb-2">{step.num}</div>
              <h3 className="text-xl font-semibold text-neutral-900 tracking-tight mb-3">{step.title}</h3>
              <p className="text-neutral-600 text-[15px] leading-relaxed">{step.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowWeWork;
