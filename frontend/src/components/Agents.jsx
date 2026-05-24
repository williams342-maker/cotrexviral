import React from 'react';
import { ArrowRight } from 'lucide-react';
import { agentsList } from '../data/mock';

const Agents = ({ onSelect }) => {
  return (
    <section className="py-24">
      <div className="max-w-7xl mx-auto px-5">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="text-[12px] uppercase tracking-[0.18em] text-[#1B7BFF] font-semibold mb-4 block">AI agents</span>
          <h2 className="text-[clamp(2rem,4.5vw,3.25rem)] leading-[1.08] tracking-tight text-neutral-900 font-medium">
            Meet your new marketing team.
            <span className="text-neutral-500"> Ready when you are. Running while you sleep.</span>
          </h2>
          <p className="mt-5 text-neutral-600 text-[16px] leading-relaxed">
            Pick the specialists you need. They handle everything from posting to reporting — while you focus on what matters: growing your business.
          </p>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
          {agentsList.map((a) => (
            <button
              key={a.id}
              onClick={() => onSelect(a)}
              className={`group relative aspect-[3/4] rounded-3xl bg-gradient-to-br ${a.color} overflow-hidden text-left shadow-[0_4px_16px_rgba(0,0,0,0.04)] hover:shadow-[0_20px_40px_-12px_rgba(0,0,0,0.18)] transition-all duration-500 hover:-translate-y-2`}
            >
              <img
                src={a.img}
                alt={a.name}
                className="absolute inset-0 w-full h-full object-cover object-center"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/35 via-transparent to-transparent" />
              <div className="absolute bottom-0 left-0 right-0 p-5 text-white">
                <div className="text-[11px] uppercase tracking-wider opacity-90 mb-1">{a.role}</div>
                <div className="text-2xl font-semibold tracking-tight mb-3">{a.name}</div>
                <div className="inline-flex items-center gap-1.5 text-[13px] font-medium opacity-90 group-hover:opacity-100 group-hover:gap-2 transition-all">
                  Learn more <ArrowRight size={14} />
                </div>
              </div>
              <div className={`absolute top-4 right-4 w-2.5 h-2.5 rounded-full ${a.accent} ring-4 ring-white/60`} />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Agents;
