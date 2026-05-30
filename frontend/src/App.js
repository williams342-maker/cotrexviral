import React from 'react';
import './App.css';
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import Marketing from './pages/Marketing';
import Agents from './pages/Agents';
import Pricing from './pages/Pricing';
import Roadmap from './pages/Roadmap';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import SitemapPage from './pages/Sitemap';
import DataDeletion from './pages/DataDeletion';
import NicheToolPage from './pages/programmatic/NicheToolPage';
import { TikTokGenerator, ViralIdeas, InstagramCaption, ShortFormVideo, ContentAutomation } from './pages/landing';
import { BlogIndex, BlogPost } from './pages/blog/Blog';
import AuthCallback from './pages/AuthCallback';
import ProtectedRoute from './components/ProtectedRoute';
import Overview from './pages/dashboard/Overview';
import SeoReview from './pages/dashboard/SeoReview';
import SiteScan from './pages/dashboard/SiteScan';
import Insights from './pages/dashboard/Insights';
import Channels from './pages/dashboard/Channels';
import Compose from './pages/dashboard/Compose';
import Posts from './pages/dashboard/Posts';
import Leads from './pages/dashboard/Leads';
import Studio from './pages/dashboard/Studio';
import Help from './pages/dashboard/Help';
import AccountSettings from './pages/dashboard/AccountSettings';
import AgentWorkspace from './pages/dashboard/AgentWorkspace';
import AITeam from './pages/dashboard/AITeam';
import CommandCenter from './pages/dashboard/CommandCenter';
import LegacyCommandCenter from './pages/dashboard/LegacyCommandCenter';
import CampaignDetail from './pages/dashboard/CampaignDetail';
import ActiveCampaigns from './pages/dashboard/ActiveCampaigns';
import Missions from './pages/dashboard/Missions';
import Reports from './pages/dashboard/Reports';
import CortexWorkspace from './pages/dashboard/CortexWorkspace';
import TeamDetail from './pages/dashboard/TeamDetail';
import AutonomyControl from './pages/dashboard/AutonomyControl';
import SellerMissionControl from './pages/dashboard/seller/SellerMissionControl';
import SellerDiscovery from './pages/dashboard/seller/SellerDiscovery';
import QualifiedSellers from './pages/dashboard/seller/QualifiedSellers';
import SellerConversations from './pages/dashboard/seller/Conversations';
import SellerOnboarding from './pages/dashboard/seller/Onboarding';
import SellerRetention from './pages/dashboard/seller/Retention';
import SellerAnalytics from './pages/dashboard/seller/Analytics';
import Memory from './pages/dashboard/Memory';
import Approvals from './pages/dashboard/Approvals';
import Trends from './pages/dashboard/Trends';
import Main from './pages/dashboard/Main';
import Performance from './pages/dashboard/Performance';
import MarketingCalendar from './pages/dashboard/MarketingCalendar';
import Team from './pages/dashboard/Team';
import Standups from './pages/dashboard/Standups';
import Listening from './pages/dashboard/Listening';
import Goals from './pages/dashboard/Goals';
import Experiments from './pages/dashboard/Experiments';
import Briefs from './pages/dashboard/Briefs';
import Autonomy from './pages/dashboard/Autonomy';
import Chatter from './pages/dashboard/Chatter';
import TeamPerformance from './pages/dashboard/TeamPerformance';
import AdminOverview from './pages/admin/AdminOverview';
import AdminUsers from './pages/admin/AdminUsers';
import AdminTickets from './pages/admin/AdminTickets';
import AdminAudit from './pages/admin/AdminAudit';
import AdminBroadcasts from './pages/admin/AdminBroadcasts';
import AdminWebhookEvents from './pages/admin/AdminWebhookEvents';
import AdminSettings from './pages/admin/AdminSettings';
import AdminIntegrations from './pages/admin/AdminIntegrations';
import AdminRoadmap from './pages/admin/AdminRoadmap';
import AdminSellerOS from './pages/admin/AdminSellerOS';
import AdminEmailLog from './pages/admin/AdminEmailLog';
import Onboarding from './pages/Onboarding';
import AuthClaim from './pages/AuthClaim';
import { Toaster } from './components/ui/toaster';
import { AuthProvider } from './context/AuthContext';
import VisitTracker from './components/VisitTracker';

function AppRouter() {
  const location = useLocation();
  // CRITICAL: Detect session_id during render (synchronous) before ProtectedRoute checks.
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  return (
    <>
      <VisitTracker />
      <Routes>
      <Route path="/" element={<Marketing />} />
      <Route path="/marketing" element={<Marketing />} />
      <Route path="/agents" element={<Agents />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/roadmap" element={<Roadmap />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/sitemap" element={<SitemapPage />} />
      <Route path="/data-deletion" element={<DataDeletion />} />
      <Route path="/ai-tiktok-post-generator" element={<TikTokGenerator />} />
      <Route path="/viral-content-ideas-generator" element={<ViralIdeas />} />
      <Route path="/instagram-caption-ai-generator" element={<InstagramCaption />} />
      <Route path="/short-form-video-ideas-ai" element={<ShortFormVideo />} />
      <Route path="/content-automation-tool" element={<ContentAutomation />} />
      <Route path="/tools/:slug" element={<NicheToolPage />} />
      <Route path="/blog" element={<BlogIndex />} />
      <Route path="/blog/:slug" element={<BlogPost />} />
      <Route path="/dashboard" element={<ProtectedRoute><CommandCenter /></ProtectedRoute>} />
      <Route path="/dashboard/command-center" element={<ProtectedRoute><CommandCenter /></ProtectedRoute>} />
      <Route path="/dashboard/legacy" element={<ProtectedRoute><LegacyCommandCenter /></ProtectedRoute>} />
      <Route path="/dashboard/missions" element={<ProtectedRoute><Missions /></ProtectedRoute>} />
      <Route path="/dashboard/cortex" element={<ProtectedRoute><Missions /></ProtectedRoute>} />
      <Route path="/dashboard/cortex/:id" element={<ProtectedRoute><CortexWorkspace /></ProtectedRoute>} />
      <Route path="/dashboard/reports" element={<ProtectedRoute><Reports /></ProtectedRoute>} />
      <Route path="/dashboard/teams/:teamId" element={<ProtectedRoute><TeamDetail /></ProtectedRoute>} />
      <Route path="/dashboard/campaigns/active" element={<ProtectedRoute><ActiveCampaigns /></ProtectedRoute>} />
      <Route path="/dashboard/campaigns/:id" element={<ProtectedRoute><CampaignDetail /></ProtectedRoute>} />
      <Route path="/dashboard/overview" element={<ProtectedRoute><Overview /></ProtectedRoute>} />
      <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
      <Route path="/auth/claim" element={<AuthClaim />} />
      <Route path="/dashboard/main" element={<ProtectedRoute><Main /></ProtectedRoute>} />
      <Route path="/dashboard/performance" element={<ProtectedRoute><Performance /></ProtectedRoute>} />
      <Route path="/dashboard/calendar" element={<ProtectedRoute><MarketingCalendar /></ProtectedRoute>} />
      <Route path="/dashboard/growth-team" element={<ProtectedRoute><Team /></ProtectedRoute>} />
      <Route path="/dashboard/standups" element={<ProtectedRoute><Standups /></ProtectedRoute>} />
      <Route path="/dashboard/listening" element={<ProtectedRoute><Listening /></ProtectedRoute>} />
      <Route path="/dashboard/goals" element={<ProtectedRoute><Goals /></ProtectedRoute>} />
      <Route path="/dashboard/experiments" element={<ProtectedRoute><Experiments /></ProtectedRoute>} />
      <Route path="/dashboard/briefs" element={<ProtectedRoute><Briefs /></ProtectedRoute>} />
      <Route path="/dashboard/autonomy" element={<ProtectedRoute><Autonomy /></ProtectedRoute>} />
      <Route path="/dashboard/autonomy-control" element={<ProtectedRoute><AutonomyControl /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os" element={<ProtectedRoute><SellerMissionControl /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/discovery" element={<ProtectedRoute><SellerDiscovery /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/qualified" element={<ProtectedRoute><QualifiedSellers /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/conversations" element={<ProtectedRoute><SellerConversations /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/onboarding" element={<ProtectedRoute><SellerOnboarding /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/retention" element={<ProtectedRoute><SellerRetention /></ProtectedRoute>} />
      <Route path="/dashboard/seller-os/analytics" element={<ProtectedRoute><SellerAnalytics /></ProtectedRoute>} />
      <Route path="/dashboard/chatter" element={<ProtectedRoute><Chatter /></ProtectedRoute>} />
      <Route path="/dashboard/team-performance" element={<ProtectedRoute><TeamPerformance /></ProtectedRoute>} />
      <Route path="/dashboard/insights" element={<ProtectedRoute><Insights /></ProtectedRoute>} />
      <Route path="/dashboard/seo" element={<ProtectedRoute><SeoReview /></ProtectedRoute>} />
      <Route path="/dashboard/scan" element={<ProtectedRoute><SiteScan /></ProtectedRoute>} />
      <Route path="/dashboard/channels" element={<ProtectedRoute><Channels /></ProtectedRoute>} />
      <Route path="/dashboard/compose" element={<ProtectedRoute><Compose /></ProtectedRoute>} />
      <Route path="/dashboard/studio" element={<ProtectedRoute><Studio /></ProtectedRoute>} />
      <Route path="/dashboard/posts" element={<ProtectedRoute><Posts /></ProtectedRoute>} />
      <Route path="/dashboard/leads" element={<ProtectedRoute><Leads /></ProtectedRoute>} />
      <Route path="/dashboard/help" element={<ProtectedRoute><Help /></ProtectedRoute>} />
      <Route path="/dashboard/agent" element={<ProtectedRoute><AgentWorkspace /></ProtectedRoute>} />
      <Route path="/dashboard/agent/:agentId" element={<ProtectedRoute><AgentWorkspace /></ProtectedRoute>} />
      <Route path="/dashboard/team" element={<ProtectedRoute><AITeam /></ProtectedRoute>} />
      <Route path="/dashboard/memory" element={<ProtectedRoute><Memory /></ProtectedRoute>} />
      <Route path="/dashboard/approvals" element={<ProtectedRoute><Approvals /></ProtectedRoute>} />
      <Route path="/dashboard/trends" element={<ProtectedRoute><Trends /></ProtectedRoute>} />
      <Route path="/dashboard/settings/account" element={<ProtectedRoute><AccountSettings /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute admin><AdminOverview /></ProtectedRoute>} />
      <Route path="/admin/users" element={<ProtectedRoute admin><AdminUsers /></ProtectedRoute>} />
      <Route path="/admin/tickets" element={<ProtectedRoute admin><AdminTickets /></ProtectedRoute>} />
      <Route path="/admin/audit-log" element={<ProtectedRoute admin><AdminAudit /></ProtectedRoute>} />
      <Route path="/admin/broadcasts" element={<ProtectedRoute admin><AdminBroadcasts /></ProtectedRoute>} />
      <Route path="/admin/webhook-events" element={<ProtectedRoute admin><AdminWebhookEvents /></ProtectedRoute>} />
      <Route path="/admin/settings" element={<ProtectedRoute admin><AdminSettings /></ProtectedRoute>} />
      <Route path="/admin/integrations" element={<ProtectedRoute admin><AdminIntegrations /></ProtectedRoute>} />
      <Route path="/admin/seller-os" element={<ProtectedRoute admin><AdminSellerOS /></ProtectedRoute>} />
      <Route path="/admin/email-log" element={<ProtectedRoute admin><AdminEmailLog /></ProtectedRoute>} />
      <Route path="/admin/roadmap" element={<ProtectedRoute admin><AdminRoadmap /></ProtectedRoute>} />
    </Routes>
    </>
  );
}

function App() {
  return (
    <div className="App">
      <HelmetProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRouter />
            <Toaster />
          </AuthProvider>
        </BrowserRouter>
      </HelmetProvider>
    </div>
  );
}

export default App;
