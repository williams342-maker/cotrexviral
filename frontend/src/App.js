import React from 'react';
import './App.css';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import Marketing from './pages/Marketing';
import Agents from './pages/Agents';
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
import Main from './pages/dashboard/Main';
import Performance from './pages/dashboard/Performance';
import MarketingCalendar from './pages/dashboard/MarketingCalendar';
import AdminOverview from './pages/admin/AdminOverview';
import AdminUsers from './pages/admin/AdminUsers';
import AdminTickets from './pages/admin/AdminTickets';
import AdminAudit from './pages/admin/AdminAudit';
import AdminBroadcasts from './pages/admin/AdminBroadcasts';
import { Toaster } from './components/ui/toaster';
import { AuthProvider } from './context/AuthContext';

function AppRouter() {
  const location = useLocation();
  // CRITICAL: Detect session_id during render (synchronous) before ProtectedRoute checks.
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/" element={<Marketing />} />
      <Route path="/marketing" element={<Marketing />} />
      <Route path="/agents" element={<Agents />} />
      <Route path="/dashboard" element={<ProtectedRoute><Overview /></ProtectedRoute>} />
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
      <Route path="/admin" element={<ProtectedRoute admin><AdminOverview /></ProtectedRoute>} />
      <Route path="/admin/users" element={<ProtectedRoute admin><AdminUsers /></ProtectedRoute>} />
      <Route path="/admin/tickets" element={<ProtectedRoute admin><AdminTickets /></ProtectedRoute>} />
      <Route path="/admin/audit-log" element={<ProtectedRoute admin><AdminAudit /></ProtectedRoute>} />
      <Route path="/admin/broadcasts" element={<ProtectedRoute admin><AdminBroadcasts /></ProtectedRoute>} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
