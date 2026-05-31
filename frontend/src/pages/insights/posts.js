/**
 * Insights index — static index of all blog posts.
 *
 * Each entry mirrors the __meta__ block in the generated JSON so the
 * index page can be rendered without lazy-loading every article body.
 * Add new entries here when you ship a new article.
 *
 * Generating the bodies:
 *   cd /app/backend && python -m scripts.generate_insights
 */

import howToRecruitEtsy        from './content/how-to-recruit-etsy-sellers.json';
import aiMarketingOsExplained  from './content/ai-marketing-operating-systems-explained.json';
import redditAutomation        from './content/reddit-marketing-automation.json';
import marketplaceGrowth       from './content/marketplace-growth-strategies.json';
import campaignFrameworks      from './content/campaign-planning-frameworks.json';
import aiCompetitiveIntel      from './content/ai-competitive-intelligence.json';
import socialAutomationGuide   from './content/social-media-automation-guide.json';
import assetAnalysis           from './content/asset-analysis-for-marketers.json';
import multiChannelMgmt        from './content/multi-channel-campaign-management.json';
import sellerPlaybook          from './content/seller-acquisition-playbook.json';

export const POSTS = {
  'how-to-recruit-etsy-sellers':              howToRecruitEtsy,
  'ai-marketing-operating-systems-explained': aiMarketingOsExplained,
  'reddit-marketing-automation':              redditAutomation,
  'marketplace-growth-strategies':            marketplaceGrowth,
  'campaign-planning-frameworks':             campaignFrameworks,
  'ai-competitive-intelligence':              aiCompetitiveIntel,
  'social-media-automation-guide':            socialAutomationGuide,
  'asset-analysis-for-marketers':             assetAnalysis,
  'multi-channel-campaign-management':        multiChannelMgmt,
  'seller-acquisition-playbook':              sellerPlaybook,
};

// Sorted newest-first by published_at; falls back to insertion order.
export const POST_LIST = Object.values(POSTS).sort((a, b) => {
  const da = a.__meta__?.published_at || '';
  const db = b.__meta__?.published_at || '';
  return db.localeCompare(da);
});

export const CATEGORIES = [
  { value: 'all',          label: 'All insights' },
  { value: 'playbooks',    label: 'Playbooks' },
  { value: 'strategy',     label: 'Strategy' },
  { value: 'operations',   label: 'Operations' },
  { value: 'automation',   label: 'Automation' },
  { value: 'intelligence', label: 'Intelligence' },
];

export const POSTS_PER_PAGE = 6;
