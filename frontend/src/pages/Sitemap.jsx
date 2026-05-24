import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, FileText, Tag, Layers, Hash } from 'lucide-react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import { POSTS } from './blog/posts';
import { ALL_COMBOS, TOOLS, NICHES } from './programmatic/data';

const Group = ({ icon: Icon, title, count, children }) => (
  <section className="mb-12">
    <div className="flex items-center gap-3 mb-5">
      <span className="w-10 h-10 rounded-xl cv-glass flex items-center justify-center text-cyan-300">
        <Icon size={18} />
      </span>
      <h2 className="cv-display text-2xl font-semibold text-white">
        {title} <span className="text-zinc-500 text-[15px] ml-1.5 font-normal">({count})</span>
      </h2>
    </div>
    {children}
  </section>
);

const LinkPill = ({ to, label }) => (
  <Link
    to={to}
    className="block cv-glass rounded-xl px-4 py-3 hover:border-cyan-400/30 hover:text-white transition-colors text-[13.5px] text-zinc-300"
  >
    {label}
    <span className="text-[11px] text-zinc-500 block mt-0.5 truncate">{to}</span>
  </Link>
);

const CORE = [
  { to: '/', label: 'Home — AI Viral Content Generator' },
  { to: '/pricing', label: 'Pricing — Plans for creators, teams, agencies' },
  { to: '/agents', label: 'AI Agents — Nova, Sam, Kai, Angela' },
  { to: '/dashboard', label: 'Dashboard (login required)' },
];

const TOOL_PAGES = [
  { to: '/ai-tiktok-post-generator', label: 'AI TikTok Post Generator' },
  { to: '/viral-content-ideas-generator', label: 'Viral Content Ideas Generator' },
  { to: '/instagram-caption-ai-generator', label: 'Instagram Caption AI Generator' },
  { to: '/short-form-video-ideas-ai', label: 'Short-Form Video Ideas AI' },
  { to: '/content-automation-tool', label: 'Content Automation Tool' },
];

const LEGAL = [
  { to: '/privacy', label: 'Privacy Policy' },
  { to: '/terms', label: 'Terms of Service' },
];

const SitemapPage = () => {
  // Group programmatic combos by tool for readability
  const grouped = TOOLS.map((tool) => ({
    tool,
    combos: ALL_COMBOS.filter((c) => c.tool.slug === tool.slug),
  }));
  const total = CORE.length + TOOL_PAGES.length + LEGAL.length + POSTS.length + ALL_COMBOS.length;

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Sitemap — All CortexViral Pages"
        description="Browse every page on CortexViral: AI tools, niche generators, blog articles, and legal pages — organised in one human-readable index."
        path="/sitemap"
        schema={buildBreadcrumbSchema([
          { label: 'Home', path: '/' },
          { label: 'Sitemap', path: '/sitemap' },
        ])}
      />
      <CVNavbar onGetStarted={() => {}} />

      <section className="relative pt-32 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <CVBreadcrumbs items={[{ label: 'Sitemap' }]} className="justify-center mb-5" />
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Site map</span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]"
          >
            Every page on{' '}
            <span className="cv-gradient-text">CortexViral.</span>
          </motion.h1>
          <p className="mt-6 max-w-2xl mx-auto text-zinc-400 text-[16px]">
            A human-readable index of all <strong className="text-zinc-200">{total}</strong> public pages.
            For the machine-readable version, see <a href="/api/seo/sitemap.xml" className="text-cyan-300 hover:text-cyan-200">sitemap.xml</a>.
          </p>
        </div>
      </section>

      <section className="relative cv-dark pb-24">
        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">

          <Group icon={Layers} title="Core" count={CORE.length}>
            <div className="grid sm:grid-cols-2 gap-3">
              {CORE.map((l) => <LinkPill key={l.to} {...l} />)}
            </div>
          </Group>

          <Group icon={Tag} title="AI Tools (keyword landing pages)" count={TOOL_PAGES.length}>
            <div className="grid sm:grid-cols-2 gap-3">
              {TOOL_PAGES.map((l) => <LinkPill key={l.to} {...l} />)}
            </div>
          </Group>

          <Group icon={Hash} title={`Niche Tool Pages (${TOOLS.length} tools × ${NICHES.length} niches)`} count={ALL_COMBOS.length}>
            {grouped.map(({ tool, combos }) => (
              <div key={tool.slug} className="mb-6">
                <h3 className="cv-display text-[15px] font-semibold text-violet-300 mb-3">{tool.label}</h3>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {combos.map((c) => (
                    <Link
                      key={c.slug}
                      to={`/tools/${c.slug}`}
                      className="block cv-glass rounded-lg px-3 py-2 text-[12.5px] text-zinc-300 hover:text-white hover:border-cyan-400/30 transition-colors"
                    >
                      For {c.niche.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </Group>

          <Group icon={FileText} title="Blog Articles" count={POSTS.length}>
            <div className="grid sm:grid-cols-2 gap-3">
              {POSTS.map((p) => (
                <Link
                  key={p.slug}
                  to={`/blog/${p.slug}`}
                  className="block cv-glass rounded-xl px-4 py-3 hover:border-cyan-400/30 transition-colors"
                >
                  <span className="inline-block text-[9.5px] uppercase tracking-[0.16em] font-semibold px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300 border border-violet-500/20">{p.cluster}</span>
                  <div className="text-[13.5px] text-zinc-200 mt-1.5 font-medium">{p.title}</div>
                  <div className="text-[11px] text-zinc-500 mt-1">/blog/{p.slug}</div>
                </Link>
              ))}
            </div>
          </Group>

          <Group icon={Layers} title="Legal" count={LEGAL.length}>
            <div className="grid sm:grid-cols-2 gap-3">
              {LEGAL.map((l) => <LinkPill key={l.to} {...l} />)}
            </div>
          </Group>

          <div className="text-center mt-16 cv-glass-strong rounded-3xl p-8">
            <p className="text-[14px] text-zinc-400">
              Looking for something specific?{' '}
              <Link to="/" className="text-cyan-300 hover:text-cyan-200 font-semibold">Start at the home page</Link>
              {' '}or <a href="mailto:support@cortexviral.com" className="text-cyan-300 hover:text-cyan-200 font-semibold">email support</a>.
            </p>
          </div>
        </div>
      </section>

      <CVFooter />
    </div>
  );
};

export default SitemapPage;
