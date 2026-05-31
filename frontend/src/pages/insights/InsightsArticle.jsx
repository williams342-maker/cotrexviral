import React from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowRight, Calendar, Clock, BookOpen, Quote, Sparkles, Compass,
} from 'lucide-react';
import CVNavbar from '../../components/cv/CVNavbar';
import CVBackdrop from '../../components/cv/CVBackdrop';
import CVFooter from '../../components/cv/CVFooter';
import CVFaq from '../../components/cv/CVFaq';
import CVBreadcrumbs from '../../components/cv/CVBreadcrumbs';
import CVSeo, {
  ORG_SCHEMA, SITE, buildBreadcrumbSchema, buildFaqSchema,
} from '../../components/cv/CVSeo';
import { POSTS } from './posts';

const LANDING_TITLES = {
  'marketing-os':          'AI Marketing Operating System',
  'seller-acquisition':    'AI Seller Acquisition Engine',
  'ai-campaign-generator': 'AI Campaign Generator',
  'competitor-analysis':   'AI Competitor Analysis',
  'asset-analysis':        'AI Marketing Asset Analysis',
  'instagram-marketing-ai': 'Instagram Marketing AI',
  'facebook-marketing-ai':  'Facebook Marketing AI',
  'linkedin-marketing-ai':  'LinkedIn Marketing AI',
  'reddit-marketing-ai':    'Reddit Marketing AI',
  'youtube-marketing-ai':   'YouTube Marketing AI',
  'tiktok-marketing-ai':    'TikTok Marketing AI',
};

const fmt = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'long', day: 'numeric', year: 'numeric',
    });
  } catch { return ''; }
};

const InsightsArticle = () => {
  const { slug } = useParams();
  const post = POSTS[slug];

  if (!post) return <Navigate to="/insights" replace />;

  const m = post.__meta__ || {};
  const author = m.author || {};
  const breadcrumbs = [
    { label: 'Home', path: '/' },
    { label: 'Insights', path: '/insights' },
    { label: m.title, path: `/insights/${m.slug}` },
  ];

  // schema.org/Article + author Person sub-resource
  const articleSchema = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: m.title,
    description: m.dek,
    datePublished: m.published_at,
    dateModified: m.published_at,
    author: {
      '@type': 'Person',
      name: author.name,
      jobTitle: author.jobTitle,
      url: author.url,
    },
    publisher: {
      '@type': 'Organization',
      name: 'CortexViral',
      logo: { '@type': 'ImageObject', url: `${SITE}/cortex-logo.png` },
    },
    mainEntityOfPage: { '@type': 'WebPage', '@id': `${SITE}/insights/${m.slug}` },
    keywords: m.primary_kw,
  };

  return (
    <div className="min-h-screen cv-dark antialiased" data-testid={`insights-article-${m.slug}`}>
      <CVSeo
        title={`${m.title} | CortexViral Insights`}
        description={m.dek}
        path={`/insights/${m.slug}`}
        schema={[
          ORG_SCHEMA,
          articleSchema,
          buildBreadcrumbSchema(breadcrumbs),
          buildFaqSchema((post.faq || []).map((f) => ({ question: f.q, answer: f.a }))),
        ]}
      />
      <CVNavbar />

      {/* Hero */}
      <section className="relative pt-28 pb-12 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <CVBreadcrumbs items={[
            { label: 'Insights', path: '/insights' },
            { label: m.category_label || m.category },
          ]} className="mb-5" />

          <div className="flex items-center gap-2 mb-5">
            <span className="text-[10.5px] uppercase tracking-[0.2em] font-semibold text-violet-300">
              {m.category_label || m.category}
            </span>
            <span className="w-1 h-1 rounded-full bg-zinc-700" />
            <span className="text-[11px] text-zinc-500 inline-flex items-center gap-1">
              <Clock size={10} /> {m.read_minutes || 5} min read
            </span>
          </div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="cv-display text-4xl sm:text-5xl lg:text-[52px] font-semibold text-white leading-[1.05]"
            data-testid="article-h1"
          >
            {m.title}
          </motion.h1>
          <p className="mt-5 text-[17px] text-zinc-400 leading-relaxed">
            {m.dek}
          </p>

          <div className="mt-7 flex items-center gap-3 pb-2 border-b border-white/5">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-white font-semibold text-[13px]">
              {(author.name || 'C')[0]}
            </div>
            <div>
              <div className="text-[13px] font-semibold text-white" data-testid="article-author">
                {author.name}
              </div>
              <div className="text-[11.5px] text-zinc-500 flex items-center gap-2">
                {author.jobTitle}
                {m.published_at && (
                  <>
                    <span className="w-1 h-1 rounded-full bg-zinc-700" />
                    <span className="inline-flex items-center gap-1"><Calendar size={10} /> {fmt(m.published_at)}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Key takeaways */}
      {Array.isArray(post.key_takeaways) && post.key_takeaways.length > 0 && (
        <section className="relative cv-dark py-6">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="cv-glass-strong rounded-2xl p-6 sm:p-7">
              <div className="flex items-center gap-2 mb-3 text-[11px] uppercase tracking-[0.2em] text-cyan-300 font-semibold">
                <BookOpen size={12} /> Key takeaways
              </div>
              <ul className="space-y-2.5">
                {post.key_takeaways.map((t, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[14px] text-zinc-200">
                    <Sparkles size={13} className="text-cyan-300 mt-1 shrink-0" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* Lede */}
      {post.lede && (
        <section className="relative cv-dark py-2">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <p className="text-[18px] text-zinc-200 leading-relaxed font-medium">
              {post.lede}
            </p>
          </div>
        </section>
      )}

      {/* Body sections */}
      <section className="relative cv-dark py-6" data-testid="article-sections">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-10">
          {(post.sections || []).map((s, idx) => (
            <article key={idx} className="" data-testid={`article-section-${idx}`}>
              <h2 className="cv-display text-2xl sm:text-[28px] font-semibold text-white leading-tight mt-2">
                {s.heading}
              </h2>
              <p className="mt-3 text-[15.5px] leading-[1.7] text-zinc-300 whitespace-pre-line">
                {s.body}
              </p>
              {Array.isArray(s.bullets) && s.bullets.length > 0 && (
                <ul className="mt-4 space-y-2.5">
                  {s.bullets.map((b, bi) => (
                    <li key={bi} className="flex items-start gap-2.5 text-[14px] text-zinc-300">
                      <Sparkles size={13} className="text-violet-300 mt-1 shrink-0" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      </section>

      {/* Pull quote */}
      {post.pull_quote && (
        <section className="relative cv-dark py-10">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <blockquote className="border-l-2 border-violet-400 pl-6 italic text-[20px] sm:text-[22px] leading-relaxed text-zinc-100 cv-display">
              <Quote size={18} className="text-violet-300 mb-2" />
              {post.pull_quote}
            </blockquote>
          </div>
        </section>
      )}

      {/* Related landing-page CTA */}
      {m.related_landing && post.related_landing_blurb && (
        <section className="relative cv-dark py-10" data-testid="article-related-landing">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="cv-glass-strong rounded-2xl p-6 sm:p-7 flex flex-col sm:flex-row sm:items-center gap-5">
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-[0.2em] font-semibold text-violet-300 mb-1">From the platform</div>
                <div className="text-[16px] font-semibold text-white mb-2">
                  {LANDING_TITLES[m.related_landing] || 'Explore the platform'}
                </div>
                <p className="text-[13.5px] text-zinc-400 leading-relaxed">{post.related_landing_blurb}</p>
              </div>
              <Link
                to={`/${m.related_landing}`}
                data-testid="article-related-landing-cta"
                className="cv-btn-primary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13px] font-semibold shrink-0"
              >
                See it in action <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* Related articles */}
      {Array.isArray(post.related_articles) && post.related_articles.length > 0 && (
        <section className="relative cv-dark py-12" data-testid="article-related">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center mb-8">
              <span className="text-[11px] uppercase tracking-[0.22em] text-violet-300 font-semibold">Keep reading</span>
              <h2 className="cv-display text-3xl font-semibold text-white mt-2">More from <span className="cv-gradient-text">Insights</span></h2>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              {post.related_articles.map((r) => (
                <Link
                  key={r.slug}
                  to={`/insights/${r.slug}`}
                  data-testid={`article-related-${r.slug}`}
                  className="group cv-glass rounded-2xl p-5 hover:border-violet-400/40 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Compass size={13} className="text-cyan-300" />
                    <span className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">Related</span>
                  </div>
                  <div className="text-[14.5px] font-semibold text-white group-hover:text-cyan-300 transition-colors leading-tight">
                    {r.title}
                  </div>
                  <div className="text-[12.5px] text-zinc-400 mt-2 leading-relaxed">{r.blurb}</div>
                  <div className="mt-3 inline-flex items-center gap-1 text-[12px] font-semibold text-violet-300 group-hover:gap-2 transition-all">
                    Read article <ArrowRight size={12} />
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ */}
      <div id="article-faq" data-testid="article-faq">
        <CVFaq
          faqs={post.faq || []}
          title={<>Frequently asked</>}
        />
      </div>

      {/* Final takeaway */}
      {post.final_takeaway && (
        <section className="relative cv-dark py-14" data-testid="article-final">
          <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
            <p className="text-[16px] leading-[1.8] text-zinc-300">{post.final_takeaway}</p>
            <div className="mt-7 flex items-center gap-3">
              <Link
                to="/dashboard"
                className="cv-btn-primary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13px] font-semibold"
                data-testid="article-cta-primary"
              >
                Start Your First Mission <ArrowRight size={13} />
              </Link>
              <Link
                to="/insights"
                className="cv-btn-secondary inline-flex items-center gap-1.5 px-5 h-11 rounded-full text-[13px] font-semibold"
              >
                Back to Insights
              </Link>
            </div>
          </div>
        </section>
      )}

      <CVFooter />
    </div>
  );
};

export default InsightsArticle;
