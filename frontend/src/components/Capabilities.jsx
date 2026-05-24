import React, { useState } from 'react';
import * as Icons from 'lucide-react';
import { capabilities } from '../data/mock';

const Capabilities = () => {
  return (
    <section className="py-24 bg-gradient-to-b from-transparent via-neutral-50/60 to-transparent">
      <div className="max-w-7xl mx-auto px-5">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4 block">Capabilities</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] tracking-tight text-neutral-900 font-medium">
            +50 core AI marketing workflows<br />
            <span className="text-neutral-500">thoughtfully crafted from human expertise</span>
          </h2>
          <p className="mt-5 text-neutral-600">Readily available for your execution support</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {capabilities.map((c, i) => {
            const Icon = Icons[c.icon] || Icons.Sparkles;
            const tints = ['bg-emerald-50 text-emerald-600', 'bg-amber-50 text-amber-600', 'bg-rose-50 text-rose-600', 'bg-violet-50 text-violet-600', 'bg-sky-50 text-sky-600', 'bg-teal-50 text-teal-600'];
            const tint = tints[i % tints.length];
            return (
              <div key={c.name} className="group bg-white rounded-2xl p-5 border border-neutral-200/70 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-default flex flex-col items-center text-center">
                <div className={`w-12 h-12 rounded-xl ${tint} flex items-center justify-center mb-3 group-hover:scale-110 transition-transform`}>
                  <Icon size={22} strokeWidth={2} />
                </div>
                <div className="text-[13px] font-medium text-neutral-800 leading-tight">
                  {c.name}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default Capabilities;
