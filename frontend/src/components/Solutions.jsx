import React from 'react';
import * as Icons from 'lucide-react';
import { bentoTiles } from '../data/mock';

const Solutions = () => {
  return (
    <section className="py-24 bg-gradient-to-b from-transparent via-neutral-50/60 to-transparent">
      <div className="max-w-7xl mx-auto px-5">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4 block">Solutions</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] tracking-tight text-neutral-900 font-medium">
            For startups, global enterprises,
            <span className="text-neutral-500"> and everyone in between</span>
          </h2>
          <p className="mt-5 text-neutral-600 text-[16px] leading-relaxed">
            Simple defaults, direct integrations, and advanced customization means our specialists will scale with you.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          {bentoTiles.map((t, i) => {
            const Icon = Icons[t.icon] || Icons.Sparkles;
            return (
              <div key={i} className={`relative overflow-hidden rounded-3xl bg-gradient-to-br ${t.accent} p-8 md:p-10 border border-neutral-200/50 hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.12)] transition-all duration-500 group`}>
                <div className="w-12 h-12 rounded-xl bg-white shadow-sm flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Icon size={22} className="text-neutral-800" />
                </div>
                <h3 className="text-[26px] md:text-[30px] font-medium tracking-tight text-neutral-900 mb-3 leading-tight">
                  {t.title}
                </h3>
                <p className="text-neutral-700 text-[15px] leading-relaxed max-w-md">{t.desc}</p>
                {/* decorative blob */}
                <div className="absolute -bottom-10 -right-10 w-40 h-40 rounded-full bg-white/40 blur-2xl pointer-events-none" />
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default Solutions;
