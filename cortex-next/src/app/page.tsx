import Link from 'next/link';
import { ArrowRight, Sparkles, Zap, TrendingUp, Wand2 } from 'lucide-react';

/**
 * Homepage — Server-rendered marketing page.
 *
 * This is a Server Component: zero client JS shipped for the structural
 * markup (Lucide icons are tree-shaken). Crawlers see the fully-rendered
 * HTML on the first byte.
 */
export default function HomePage() {
  return (
    <main className="min-h-screen bg-cortex-bg text-zinc-100 antialiased relative overflow-hidden">
      {/* Backdrop glow */}
      <div className="pointer-events-none absolute inset-0 z-0">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[900px] h-[900px] rounded-full bg-violet-500/15 blur-[160px]" />
        <div className="absolute top-1/2 right-0 w-[600px] h-[600px] rounded-full bg-cyan-500/10 blur-[140px]" />
      </div>

      {/* NAV */}
      <header className="relative z-10 max-w-6xl mx-auto px-6 py-5 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 text-white font-semibold tracking-tight">
          <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-cyan-400 flex items-center justify-center">
            <Sparkles size={13} className="text-white" />
          </span>
          <span className="font-display text-[17px]">CortexViral</span>
        </Link>
        <nav className="hidden sm:flex items-center gap-7 text-[13px] text-zinc-400">
          <Link href="/pricing" className="hover:text-white">Pricing</Link>
          <Link href="/blog" className="hover:text-white">Blog</Link>
          <Link href="/sitemap" className="hover:text-white">All tools</Link>
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/dashboard"
            className="text-[13px] font-medium text-zinc-300 hover:text-white px-3 h-9 rounded-lg inline-flex items-center transition-colors"
          >
            Login
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-[13px] font-semibold px-4 h-9 rounded-full bg-white text-zinc-900 hover:bg-zinc-200 transition-colors"
          >
            Start Free <ArrowRight size={14} />
          </Link>
        </div>
      </header>

      {/* HERO */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 pt-20 pb-24 text-center">
        <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">
          AI Viral Content Engine
        </span>
        <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl font-semibold mt-3 leading-[0.95] tracking-tight text-white">
          Create Viral Content That{' '}
          <span className="cv-gradient-text">Actually Grows Your Audience.</span>
        </h1>
        <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">
          CortexViral helps you generate hooks, scripts, and short-form content engineered for TikTok, Instagram Reels, and YouTube Shorts.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-[14px] font-semibold px-6 h-12 rounded-full bg-white text-zinc-900 hover:bg-zinc-200 transition-colors"
          >
            Start Free <ArrowRight size={15} />
          </Link>
          <Link
            href="/pricing"
            className="cv-glass inline-flex items-center gap-1.5 text-[14px] font-semibold px-6 h-12 rounded-full text-zinc-100 hover:bg-white/5 transition-colors"
          >
            View Plans
          </Link>
        </div>
        <p className="mt-4 text-[12.5px] text-zinc-500">
          No credit card required · Upgrade anytime · Built for creators &amp; brands
        </p>
      </section>

      {/* VALUE STRIP */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 pb-24">
        <div className="cv-glass rounded-3xl p-8">
          <h2 className="text-[15px] uppercase tracking-[0.22em] text-violet-300 font-semibold text-center mb-6">
            Why creators switch to CortexViral
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {[
              { icon: Zap,         text: 'Built for virality, not generic AI writing' },
              { icon: Sparkles,    text: 'Hook-first content generation system' },
              { icon: TrendingUp,  text: 'Optimized for TikTok, Reels &amp; Shorts algorithms' },
              { icon: Wand2,       text: 'Create content 10x faster with structured workflows' },
            ].map((v) => (
              <div key={v.text} className="flex items-start gap-3 text-[14px] text-zinc-300">
                <v.icon size={17} className="text-cyan-300 mt-0.5 shrink-0" />
                <span dangerouslySetInnerHTML={{ __html: v.text }} />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 max-w-4xl mx-auto px-6 pb-24 text-center">
        <h2 className="font-display text-4xl sm:text-5xl font-semibold text-white leading-tight">
          Turn ideas into viral content in <span className="cv-gradient-text">minutes.</span>
        </h2>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 mt-8 text-[14px] font-semibold px-6 h-12 rounded-full bg-white text-zinc-900 hover:bg-zinc-200 transition-colors"
        >
          Start Free Today <ArrowRight size={15} />
        </Link>
      </section>

      {/* Footer */}
      <footer className="relative z-10 max-w-6xl mx-auto px-6 py-10 text-[12.5px] text-zinc-500 border-t border-white/5 flex flex-wrap items-center justify-between gap-3">
        <span>© {new Date().getFullYear()} CortexViral. All rights reserved.</span>
        <nav className="flex items-center gap-5">
          <Link href="/privacy" className="hover:text-zinc-300">Privacy</Link>
          <Link href="/terms"   className="hover:text-zinc-300">Terms</Link>
          <Link href="/sitemap" className="hover:text-zinc-300">Sitemap</Link>
        </nav>
      </footer>
    </main>
  );
}
