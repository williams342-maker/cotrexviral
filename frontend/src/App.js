import React from 'react';
import './App.css';
import { HelmetProvider } from 'react-helmet-async';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
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
import Main from './pages/dashboard/Main';
import Performance from './pages/dashboard/Performance';
import MarketingCalendar from './pages/dashboard/MarketingCalendar';
import AdminOverview from './pages/admin/AdminOverview';
import AdminUsers from './pages/admin/AdminUsers';
import AdminTickets from './pages/admin/AdminTickets';
import AdminAudit from './pages/admin/AdminAudit';
import AdminBroadcasts from './pages/admin/AdminBroadcasts';
import AdminWebhookEvents from './pages/admin/AdminWebhookEvents';
import AdminSettings from './pages/admin/AdminSettings';
import AdminRoadmap from './pages/admin/AdminRoadmap';
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
      <Route path="/dashboard" element={<ProtectedRoute><Overview /></ProtectedRoute>} />
      <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
      <Route path="/auth/claim" element={<AuthClaim />} />
      <Route path="/dashboard/main" element={<ProtectedRoute><Main /></ProtectedRoute>} />
      <Route path="/dashboard/performance" element={<ProtectedRoute><Performance /></ProtectedRoute>} />
      <Route path="/dashboard/calendar" element={<ProtectedRoute><MarketingCalendar /></ProtectedRoute>} />
      <Route path="/dashboard/insights" element={<ProtectedRoute><Insights /></ProtectedRoute>} />
      <Route path="/dashboard/seo" element={<ProtectedRoute><SeoReview /></ProtectedRoute>} />
      <Route path="/dashboard/scan" element={<ProtectedRoute><SiteScan /></ProtectedRoute>} />
      <Route path="/dashboard/channels" element={<ProtectedRoute><Channels /></ProtectedRoute>} />
      <Route path="/dashboard/compose" element={<ProtectedRoute><Compose /></ProtectedRoute>} />
      <Route path="/dashboard/studio" element={<ProtectedRoute><Studio /></ProtectedRoute>} />
      <Route path="/dashboard/posts" element={<ProtectedRoute><Posts /></ProtectedRoute>} />
      <Route path="/dashboard/leads" element={<ProtectedRoute><Leads /></ProtectedRoute>} />
      <Route path="/dashboard/help" element={<ProtectedRoute><Help /></ProtectedRoute>} />
      <Route path="/dashboard/settings/account" element={<ProtectedRoute><AccountSettings /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute admin><AdminOverview /></ProtectedRoute>} />
      <Route path="/admin/users" element={<ProtectedRoute admin><AdminUsers /></ProtectedRoute>} />
      <Route path="/admin/tickets" element={<ProtectedRoute admin><AdminTickets /></ProtectedRoute>} />
      <Route path="/admin/audit-log" element={<ProtectedRoute admin><AdminAudit /></ProtectedRoute>} />
      <Route path="/admin/broadcasts" element={<ProtectedRoute admin><AdminBroadcasts /></ProtectedRoute>} />
      <Route path="/admin/webhook-events" element={<ProtectedRoute admin><AdminWebhookEvents /></ProtectedRoute>} />
      <Route path="/admin/settings" element={<ProtectedRoute admin><AdminSettings /></ProtectedRoute>} />
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
