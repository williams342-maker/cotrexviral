import React from 'react';
import { teamLogos } from '../data/mock';

const LogoBar = () => {
  return (
    <section className="py-16 border-y border-neutral-200/70">
      <div className="max-w-7xl mx-auto px-5">
        <p className="text-center text-[12px] uppercase tracking-[0.18em] text-neutral-500 font-medium mb-8">
          Built by the team from
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-12 gap-y-6 opacity-80">
          {teamLogos.map((l) => (
            <div key={l.name} className="text-neutral-700 text-2xl font-semibold tracking-tight grayscale hover:grayscale-0 transition-all" style={{ fontFamily: l.name === 'Tesla' ? 'serif' : 'inherit' }}>
              {l.letter}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default LogoBar;
