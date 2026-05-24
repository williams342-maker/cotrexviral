import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { stats } from '../data/mock';

const Stats = () => {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const obs = new IntersectionObserver(
      ([e]) => e.isIntersecting && setVisible(true),
      { threshold: 0.3 }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <section ref={ref} className="py-24">
      <div className="max-w-7xl mx-auto px-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          {stats.map((s, i) => (
            <div key={i} className="bg-white rounded-3xl p-7 border border-neutral-200/70 shadow-[0_2px_12px_rgba(0,0,0,0.03)] hover:shadow-md transition-all">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center mb-5 ${s.dir === 'up' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                {s.dir === 'up' ? <ArrowUp size={16} strokeWidth={2.5} /> : <ArrowDown size={16} strokeWidth={2.5} />}
              </div>
              <div className={`text-[44px] md:text-[56px] font-medium tracking-tight text-neutral-900 leading-none transition-all duration-1000 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3'}`} style={{ transitionDelay: `${i * 100}ms` }}>
                {s.value}
              </div>
              <div className="mt-3 text-[14px] text-neutral-600 leading-snug">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Stats;
