import React from 'react';
import { Helmet } from 'react-helmet-async';

/**
 * Per-route SEO head manager.
 * Wraps react-helmet-async with sensible CortexViral defaults + JSON-LD support.
 *
 * Usage:
 *   <CVSeo title="..." description="..." path="/foo" schema={{...}} />
 */
const SITE = 'https://social-sync-ai-1.emergent.host';
const DEFAULT_OG = `${SITE}/cortex-logo.png`;

const CVSeo = ({
  title,
  description,
  path = '/',
  ogImage = DEFAULT_OG,
  noindex = false,
  schema = null,
}) => {
  const url = `${SITE}${path}`;
  const fullTitle = title.includes('CortexViral') ? title : `${title} | CortexViral`;

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={url} />
      {noindex && <meta name="robots" content="noindex, nofollow" />}

      {/* Open Graph */}
      <meta property="og:type" content="website" />
      <meta property="og:url" content={url} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:image" content={ogImage} />
      <meta property="og:site_name" content="CortexViral" />

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={ogImage} />

      {schema && (
        <script type="application/ld+json">{JSON.stringify(schema)}</script>
      )}
    </Helmet>
  );
};

export const ORG_SCHEMA = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'CortexViral',
  url: SITE,
  logo: DEFAULT_OG,
  description:
    'AI viral content generator and growth automation platform for creators, startups, and brands.',
  sameAs: [
    'https://twitter.com/cortexviral',
    'https://www.linkedin.com/company/cortexviral',
  ],
};

export const SOFTWARE_SCHEMA = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'CortexViral',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  url: SITE,
  description:
    'AI viral content generator — create, schedule, and grow across TikTok, Instagram, X, LinkedIn, YouTube and more from one inbox.',
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
  },
  aggregateRating: {
    '@type': 'AggregateRating',
    ratingValue: '4.8',
    reviewCount: '142',
  },
};

export const buildFaqSchema = (items) => ({
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: items.map((q) => ({
    '@type': 'Question',
    name: q.question,
    acceptedAnswer: { '@type': 'Answer', text: q.answer },
  })),
});

export const buildArticleSchema = ({ title, description, slug, date, author = 'CortexViral' }) => ({
  '@context': 'https://schema.org',
  '@type': 'Article',
  headline: title,
  description,
  author: { '@type': 'Organization', name: author },
  publisher: ORG_SCHEMA,
  datePublished: date,
  dateModified: date,
  mainEntityOfPage: `${SITE}/blog/${slug}`,
});

export default CVSeo;
