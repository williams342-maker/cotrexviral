import React from 'react';
import { ArrowUpRight } from 'lucide-react';

/* "Built by Makers. Powered by Innovation." — the sibling-brand strip
   that sits right above the global footer on the marketing homepage.

   Three brand cards link out to the maker properties:
     - Williams CNC      → williamscnc.com   (copper-on-carbon wordmark)
     - Crafters Market   → craftersmarket.org (industrial orange wordmark)
     - CortexViral       → /                  (violet gradient wordmark)

   Neither external brand exposes a clean standalone logo SVG/PNG, so
   each card uses a *typographic* logo treatment that matches the
   brand's actual identity:
     • Williams CNC      = font-display copper text on a carbon plate
     • Crafters Market   = stacked "CRAFTERS / MARKET" outline-orange
     • CortexViral       = "CortexViral" wordmark + the violet "C" mark

   The cards are external links with `rel="noopener noreferrer"` and
   an `ArrowUpRight` affordance so the user knows they leave the site. */
const CARDS = [
  {
    key:   'williams',
    title: 'Williams CNC',
    tagline: 'Precision-cut art for makers who refuse compromise.',
    href:  'https://williamscnc.com',
    external: true,
    // Carbon plate + copper headline, mirrors williamscnc.com's actual palette.
    plateClass: 'bg-[#0e0c09] border-[#b87333]/30 hover:border-[#b87333]',
    logo: (
      <div className="flex flex-col">
        <span className="font-mono text-[10px] uppercase tracking-[0.32em] text-[#b87333]/80 mb-3">
          Williams CNC Art
        </span>
        <span className="block font-black text-[44px] leading-[0.88] tracking-tight"
              style={{ fontFamily: 'ui-serif, Georgia, serif' }}>
          <span className="block text-white">WILLIAMS</span>
          <span className="block text-[#b87333]">CNC</span>
        </span>
      </div>
    ),
  },
  {
    key:   'crafters',
    title: 'Crafters Market',
    tagline: 'The marketplace for CNC, plasma & custom fabrication.',
    href:  'https://craftersmarket.org',
    external: true,
    // Industrial steel + ember orange, mirrors craftersmarket.org.
    plateClass: 'bg-[#0a0a0a] border-[#ff4500]/30 hover:border-[#ff4500]',
    logo: (
      <div className="flex flex-col">
        <span className="font-mono text-[10px] uppercase tracking-[0.32em] text-[#ff4500] mb-3">
          ◆ Artisan Marketplace
        </span>
        <span className="block font-black text-[44px] leading-[0.88] tracking-tighter"
              style={{ fontFamily: 'ui-serif, Georgia, serif' }}>
          <span className="block text-white">CRAFTERS</span>
          <span className="block text-[#ff4500]">MARKET</span>
        </span>
      </div>
    ),
  },
  {
    key:   'cortex',
    title: 'CortexViral',
    tagline: 'AI marketing OS — your growth team, working 24/7.',
    href:  '/',
    external: false,
    plateClass:
      'bg-gradient-to-br from-violet-950/40 via-zinc-950 to-cyan-950/20 border-violet-500/30 hover:border-violet-400',
    logo: (
      <div className="flex flex-col">
        <span className="font-mono text-[10px] uppercase tracking-[0.32em] text-violet-300 mb-3">
          AI Marketing OS
        </span>
        <span className="flex items-baseline gap-3">
          <span
            aria-hidden="true"
            className="inline-flex items-center justify-center w-12 h-12 rounded-xl border border-violet-500/40 bg-violet-500/15 text-violet-300 font-black text-2xl"
            style={{ fontFamily: 'ui-serif, Georgia, serif' }}
          >
            C
          </span>
          <span className="font-black text-[40px] leading-none tracking-tight">
            <span className="text-white">Cortex</span>
            <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-cyan-400 bg-clip-text text-transparent">
              Viral
            </span>
          </span>
        </span>
      </div>
    ),
  },
];

const CVBuiltByMakers = () => {
  return (
    <section
      data-testid="built-by-makers"
      className="relative border-t border-white/10 bg-zinc-950 py-20 md:py-28"
    >
      <div className="max-w-[1400px] mx-auto px-4 md:px-8">
        <div className="text-center mb-12 md:mb-16">
          <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.32em] text-violet-300 mb-4">
            <span className="inline-block w-8 h-px bg-violet-400/60" />
            Our sibling brands
            <span className="inline-block w-8 h-px bg-violet-400/60" />
          </span>
          <h2 className="font-black text-4xl sm:text-5xl lg:text-6xl text-white tracking-tight leading-[1.05]">
            Built by Makers.{' '}
            <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-cyan-400 bg-clip-text text-transparent">
              Powered by Innovation.
            </span>
          </h2>
          <p className="text-zinc-400 text-sm md:text-base max-w-2xl mx-auto mt-5 leading-relaxed">
            We don't just build software — we build with the people who make things.
            CortexViral grows out of the same shop floor as Williams CNC and Crafters Market.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6">
          {CARDS.map((c) => (
            <a
              key={c.key}
              href={c.href}
              target={c.external ? '_blank' : undefined}
              rel={c.external ? 'noopener noreferrer' : undefined}
              data-testid={`built-by-makers-card-${c.key}`}
              className={`group relative flex flex-col justify-between rounded-2xl border ${c.plateClass} p-7 md:p-8 min-h-[260px] transition-colors duration-300`}
            >
              <ArrowUpRight
                size={18}
                className="absolute top-6 right-6 text-zinc-500 group-hover:text-white group-hover:-translate-y-0.5 group-hover:translate-x-0.5 transition-all"
                aria-hidden="true"
              />
              {c.logo}
              <p className="mt-6 text-sm text-zinc-400 leading-relaxed max-w-[28ch]">
                {c.tagline}
              </p>
              <span className="mt-5 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.28em] text-zinc-300 group-hover:text-white">
                Visit{c.external ? ' →' : ''}
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CVBuiltByMakers;
