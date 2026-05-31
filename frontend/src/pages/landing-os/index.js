import React from 'react';
import SeoLandingTemplate from './SeoLandingTemplate';

import marketingOs        from './content/marketing-os.json';
import sellerAcquisition  from './content/seller-acquisition.json';
import aiCampaignGenerator from './content/ai-campaign-generator.json';
import competitorAnalysis from './content/competitor-analysis.json';
import assetAnalysis      from './content/asset-analysis.json';

/*
  Static page exports. Each landing reads its long-form copy from a
  generated JSON file in /content. To regenerate, run:
    cd /app/backend && python -m scripts.generate_seo_landings
*/

export const MarketingOSLanding         = () => <SeoLandingTemplate content={marketingOs} />;
export const SellerAcquisitionLanding   = () => <SeoLandingTemplate content={sellerAcquisition} />;
export const AICampaignGeneratorLanding = () => <SeoLandingTemplate content={aiCampaignGenerator} />;
export const CompetitorAnalysisLanding  = () => <SeoLandingTemplate content={competitorAnalysis} />;
export const AssetAnalysisLanding       = () => <SeoLandingTemplate content={assetAnalysis} />;
