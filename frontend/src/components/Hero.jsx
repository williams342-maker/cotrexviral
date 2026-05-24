import React from 'react';
import { ArrowRight } from 'lucide-react';
import { heroAgents, heroPills } from '../data/mock';

const Hero = ({ onGetStarted }) => {
  return (
    <section className="relative pt-32 pb-20 overflow-hidden">
      {/* soft radial bg */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[1100px] h-[700px] rounded-full opacity-60"
          style={{
            background: 'radial-gradient(ellipse at center, rgba(180,230,200,0.45) 0%, rgba(220,200,250,0.35) 35%, rgba(255,255,255,0) 70%)',
          }}
        />
      </div>

      <div className="max-w-7xl mx-auto px-5">
        <div className="text-center max-w-4xl mx-auto">
          <h1 className="font-display text-[clamp(2.5rem,6vw,5.25rem)] leading-[1.02] tracking-[-0.035em] text-neutral-900 font-medium">
            Meet <span className="text-[#1B7BFF] italic font-normal" style={{ fontFamily: 'Instrument Serif, serif' }}>Nova,</span>
            <br />
            your AI digital marketer
          </h1>
          <p className="mt-6 text-[17px] md:text-[19px] text-neutral-600 leading-relaxed max-w-2xl mx-auto">
            Assemble your team. More output. Zero overhead. Emails sent, conversations caught, competitors flagged, insights delivered — all from your inbox.
          </p>

          <div className="mt-9 flex items-center justify-center gap-3">
            <button
              onClick={onGetStarted}
              className="group inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white px-7 py-3.5 rounded-full text-[15px] font-medium shadow-[0_8px_28px_-6px_rgba(27,123,255,0.5)] transition-all duration-200 hover:translate-y-[-1px]"
            >
              Get Started
              <ArrowRight size={17} className="group-hover:translate-x-0.5 transition-transform" />
            </button>
          </div>
        </div>

        {/* Agent cards stage */}
        <div className="relative mt-16 lg:mt-20 h-[460px] md:h-[520px]">
          {/* floating pills */}
          {heroPills.map((p, i) => (
            <div
              key={i}
              className={`hidden md:flex absolute ${p.pos} ${p.color} rounded-full px-4 py-2 text-[13px] font-medium shadow-sm whitespace-nowrap animate-float`}
              style={{ animationDelay: `${i * 0.3}s` }}
            >
              {p.text}
            </div>
          ))}

          {/* cards */}
          <div className="absolute inset-0 flex items-center justify-center gap-4 md:gap-6">
            {heroAgents.map((a, i) => {
              const positions = [
                'translate-y-6 -rotate-[6deg] opacity-90 scale-90',
                'translate-y-2 -rotate-[2deg]',
                'translate-y-2 rotate-[2deg]',
                'translate-y-6 rotate-[6deg] opacity-90 scale-90',
              ];
              return (
                <div
                  key={a.id}
                  className={`relative w-[160px] md:w-[220px] lg:w-[260px] h-[300px] md:h-[400px] lg:h-[460px] rounded-[28px] ${a.bg} shadow-[0_20px_40px_-15px_rgba(0,0,0,0.15)] transition-transform duration-500 hover:!rotate-0 hover:!translate-y-0 hover:scale-105 ${positions[i]}`}
                >
                  <img
                    src={a.img}
                    alt={a.name}
                    className="absolute inset-0 w-full h-full object-cover object-center rounded-[28px]"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                  <div className="absolute bottom-4 left-0 right-0 text-center">
                    <div className="text-[11px] uppercase tracking-wider text-neutral-700 font-medium">{a.role}</div>
                    <div className="text-xl font-semibold text-neutral-900">{a.name}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
