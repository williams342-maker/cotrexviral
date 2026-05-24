/**
 * Programmatic SEO content templates.
 *
 * URL pattern: /tools/:slug
 *   where slug = `${tool.slug}-for-${niche.slug}`
 *
 * Example URLs (auto-listed in sitemap):
 *   /tools/instagram-caption-generator-for-fitness-coaches
 *   /tools/tiktok-script-generator-for-real-estate
 *   /tools/viral-content-ideas-for-saas-founders
 *
 * Adding niches or tools below multiplies pages instantly — no JSX edits.
 */

export const TOOLS = [
  {
    slug: 'instagram-caption-generator',
    label: 'Instagram Caption Generator',
    primaryKeyword: 'Instagram caption AI',
    intent: 'caption',
    aiAgent: 'Nova',
  },
  {
    slug: 'tiktok-script-generator',
    label: 'TikTok Script Generator',
    primaryKeyword: 'AI TikTok script',
    intent: 'short-form',
    aiAgent: 'Nova',
  },
  {
    slug: 'viral-content-ideas',
    label: 'Viral Content Ideas',
    primaryKeyword: 'viral content ideas',
    intent: 'ideation',
    aiAgent: 'Kai',
  },
  {
    slug: 'linkedin-post-generator',
    label: 'LinkedIn Post Generator',
    primaryKeyword: 'AI LinkedIn post',
    intent: 'longform',
    aiAgent: 'Nova',
  },
];

export const NICHES = [
  {
    slug: 'fitness-coaches',
    label: 'Fitness Coaches',
    audience: 'fitness coaches and personal trainers',
    pains: ['booking clients consistently', 'standing out from other coaches', 'showing transformation proof'],
    voice: 'motivational, no-fluff',
    sampleHook: '"3 mistakes 90% of personal trainers make on Instagram"',
  },
  {
    slug: 'real-estate',
    label: 'Real Estate Agents',
    audience: 'real estate agents and brokers',
    pains: ['generating qualified leads', 'differentiating from competitors', 'showing market expertise'],
    voice: 'authoritative yet warm',
    sampleHook: '"Why this $1.2M listing sold in 4 days (with photos)"',
  },
  {
    slug: 'saas-founders',
    label: 'SaaS Founders',
    audience: 'SaaS founders and indie hackers',
    pains: ['building in public credibility', 'driving demo signups', 'launching new features'],
    voice: 'direct, data-led',
    sampleHook: '"We just hit $10K MRR in 90 days. Here\'s the post that did it."',
  },
  {
    slug: 'e-commerce-brands',
    label: 'E-commerce Brands',
    audience: 'DTC and e-commerce brands',
    pains: ['ad costs rising', 'finding organic UGC angles', 'launching new SKUs'],
    voice: 'product-storytelling, snappy',
    sampleHook: '"Watch what happens when you add this $9 product to a routine."',
  },
  {
    slug: 'restaurants',
    label: 'Restaurants',
    audience: 'restaurant owners and operators',
    pains: ['filling weeknight covers', 'showcasing new menu items', 'building local buzz'],
    voice: 'mouth-watering, hyper-local',
    sampleHook: '"The brunch that breaks Instagram every Sunday."',
  },
  {
    slug: 'beauty-creators',
    label: 'Beauty Creators',
    audience: 'beauty and skincare creators',
    pains: ['standing out in a crowded niche', 'product launches', 'tutorial fatigue'],
    voice: 'aspirational, visual-first',
    sampleHook: '"The 30-second routine that fixed my skin barrier."',
  },
  {
    slug: 'consultants',
    label: 'Consultants',
    audience: 'consultants and B2B service providers',
    pains: ['demonstrating expertise', 'inbound lead flow', 'thought-leadership'],
    voice: 'expert, contrarian where useful',
    sampleHook: '"3 things I tell every founder before they hire a fractional CMO."',
  },
  {
    slug: 'agencies',
    label: 'Marketing Agencies',
    audience: 'marketing and creative agencies',
    pains: ['scaling client output', 'showcasing case studies', 'recruiting talent'],
    voice: 'punchy, results-led',
    sampleHook: '"We grew a client from 0 to 100K followers in 90 days. Here\'s the playbook."',
  },
];

export const getCombo = (slug) => {
  // slug = "tiktok-script-generator-for-fitness-coaches" → split at "-for-"
  const sep = '-for-';
  const idx = slug.indexOf(sep);
  if (idx === -1) return null;
  const toolSlug = slug.slice(0, idx);
  const nicheSlug = slug.slice(idx + sep.length);
  const tool = TOOLS.find((t) => t.slug === toolSlug);
  const niche = NICHES.find((n) => n.slug === nicheSlug);
  if (!tool || !niche) return null;
  return { tool, niche };
};

export const ALL_COMBOS = TOOLS.flatMap((tool) =>
  NICHES.map((niche) => ({ tool, niche, slug: `${tool.slug}-for-${niche.slug}` }))
);
