import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Instagram, Twitter, Facebook, Linkedin, Youtube, Github,
  Loader2, Check, Globe, FileText, BarChart3, Megaphone,
  Mail, Briefcase, CreditCard, Users as UsersIcon,
} from 'lucide-react';
import { useToast } from '../../hooks/use-toast';

// Build a colored letter "logo" component for platforms without a lucide icon
const Letter = ({ ch, className = '' }) => (
  <span className={`text-base font-bold ${className}`}>{ch}</span>
);

const PLATFORM_META = {
  // Social
  instagram: { label: 'Instagram', color: 'from-pink-500 via-rose-500 to-amber-500', icon: Instagram },
  tiktok: { label: 'TikTok', color: 'from-neutral-900 to-neutral-700', icon: () => <Letter ch="T" /> },
  x: { label: 'X (Twitter)', color: 'from-neutral-900 to-neutral-700', icon: Twitter },
  facebook: { label: 'Facebook Pages', color: 'from-blue-600 to-blue-500', icon: Facebook },
  linkedin: { label: 'LinkedIn', color: 'from-sky-700 to-sky-600', icon: Linkedin },
  youtube: { label: 'YouTube', color: 'from-red-600 to-red-500', icon: Youtube },
  pinterest: { label: 'Pinterest', color: 'from-red-700 to-red-600', icon: () => <Letter ch="P" /> },
  threads: { label: 'Threads', color: 'from-neutral-900 to-neutral-800', icon: () => <Letter ch="@" /> },
  reddit: { label: 'Reddit', color: 'from-orange-600 to-orange-500', icon: () => <Letter ch="R" /> },
  // Publishing
  wordpress: { label: 'WordPress', color: 'from-sky-700 to-sky-500', icon: () => <Letter ch="W" /> },
  wordpress_selfhosted: { label: 'WordPress (Self-Hosted)', color: 'from-sky-800 to-sky-600', icon: () => <Letter ch="W" /> },
  substack: { label: 'Substack', color: 'from-orange-500 to-orange-400', icon: () => <Letter ch="S" /> },
  webflow: { label: 'Webflow', color: 'from-indigo-600 to-violet-500', icon: () => <Letter ch="w" /> },
  ghost: { label: 'Ghost', color: 'from-neutral-900 to-neutral-700', icon: () => <Letter ch="G" /> },
  framer: { label: 'Framer', color: 'from-blue-600 to-cyan-500', icon: () => <Letter ch="F" /> },
  blogger: { label: 'Blogger', color: 'from-orange-500 to-amber-500', icon: () => <Letter ch="B" /> },
  shopify: { label: 'Shopify', color: 'from-emerald-600 to-green-500', icon: () => <Letter ch="S" /> },
  // Analytics
  google_analytics: { label: 'Google Analytics', color: 'from-amber-500 to-orange-500', icon: BarChart3 },
  google_search_console: { label: 'Google Search Console', color: 'from-blue-600 to-sky-500', icon: Globe },
  omni_analytics: { label: 'Omni Analytics', color: 'from-orange-500 to-rose-500', icon: BarChart3 },
  posthog: { label: 'PostHog', color: 'from-amber-500 to-orange-600', icon: () => <Letter ch="P" /> },
  semrush: { label: 'Semrush', color: 'from-orange-600 to-amber-500', icon: () => <Letter ch="S" /> },
  // Ads
  google_ads: { label: 'Google Ads', color: 'from-blue-500 via-emerald-500 to-amber-500', icon: () => <Letter ch="G" /> },
  meta_ads: { label: 'Meta Ads', color: 'from-blue-600 to-violet-600', icon: () => <Letter ch="∞" /> },
  tiktok_ads: { label: 'TikTok Ads', color: 'from-neutral-900 to-neutral-700', icon: () => <Letter ch="T" /> },
  // Email / marketing
  klaviyo: { label: 'Klaviyo', color: 'from-neutral-900 to-neutral-700', icon: Mail },
  mailchimp: { label: 'Mailchimp', color: 'from-yellow-500 to-amber-500', icon: () => <Letter ch="M" /> },
  instantly: { label: 'Instantly', color: 'from-blue-600 to-blue-500', icon: () => <Letter ch="I" /> },
  brevo: { label: 'Brevo', color: 'from-emerald-700 to-emerald-500', icon: () => <Letter ch="B" /> },
  beehiiv: { label: 'beehiiv', color: 'from-violet-600 to-violet-500', icon: () => <Letter ch="b" /> },
  // Productivity
  google_docs: { label: 'Google Docs', color: 'from-blue-600 to-blue-500', icon: FileText },
  notion: { label: 'Notion', color: 'from-neutral-900 to-neutral-700', icon: () => <Letter ch="N" /> },
  airtable: { label: 'Airtable', color: 'from-rose-500 via-amber-500 to-blue-500', icon: () => <Letter ch="A" /> },
  github: { label: 'GitHub', color: 'from-neutral-900 to-neutral-800', icon: Github },
  // Payments
  stripe: { label: 'Stripe', color: 'from-violet-600 to-indigo-500', icon: CreditCard },
  revenuecat: { label: 'RevenueCat', color: 'from-rose-600 to-pink-500', icon: () => <Letter ch="RC" className="text-[11px]" /> },
  // CRM
  hubspot: { label: 'HubSpot', color: 'from-orange-600 to-orange-500', icon: () => <Letter ch="H" /> },
  zoho_crm: { label: 'Zoho CRM', color: 'from-blue-600 to-blue-500', icon: () => <Letter ch="Z" /> },
};

const CATEGORY_ICON = {
  'Social': UsersIcon,
  'Publishing & CMS': FileText,
  'Analytics': BarChart3,
  'Ads': Megaphone,
  'Email & Marketing': Mail,
  'Productivity': Briefcase,
  'Payments': CreditCard,
  'CRM': Briefcase,
};

const Channels = () => {
  const [catalog, setCatalog] = useState({});
  const [statusMap, setStatusMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [linkedInOAuth, setLinkedInOAuth] = useState({ configured: false, connected: false });
  const { toast } = useToast();

  const load = async () => {
    setLoading(true);
    try {
      const [cat, list, li] = await Promise.all([
        axios.get(`${API}/channels/catalog`, { withCredentials: true }),
        axios.get(`${API}/channels`, { withCredentials: true }),
        axios.get(`${API}/oauth/linkedin/status`, { withCredentials: true }).catch(() => ({ data: { configured: false, connected: false } })),
      ]);
      setCatalog(cat.data);
      const map = {};
      list.data.forEach((c) => { map[c.platform] = c; });
      setStatusMap(map);
      setLinkedInOAuth(li.data);
    } catch (e) {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  // Show a toast based on the ?linkedin=connected|denied query the OAuth callback redirects with.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const v = params.get('linkedin');
    if (v === 'connected') toast({ title: 'LinkedIn connected!', description: 'Future posts to LinkedIn will publish live.' });
    if (v === 'denied') toast({ title: 'LinkedIn connection cancelled' });
    if (v) {
      const url = new URL(window.location.href);
      url.searchParams.delete('linkedin');
      window.history.replaceState({}, '', url.toString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = async (platform) => {
    const meta = PLATFORM_META[platform];
    const ch = statusMap[platform];
    setBusy(platform);
    try {
      // Real OAuth path for LinkedIn (when credentials are configured server-side)
      if (platform === 'linkedin' && linkedInOAuth.configured) {
        if (linkedInOAuth.connected) {
          await axios.delete(`${API}/oauth/linkedin`, { withCredentials: true });
          toast({ title: 'Disconnected LinkedIn' });
          await load();
        } else {
          const r = await axios.get(`${API}/oauth/linkedin/start`, { withCredentials: true });
          window.location.href = r.data.authorize_url;
          return; // navigation in progress — don't reset busy
        }
      } else if (ch?.connected) {
        await axios.post(`${API}/channels/disconnect`, { platform }, { withCredentials: true });
        toast({ title: `Disconnected from ${meta?.label || platform}` });
      } else {
        await axios.post(`${API}/channels/connect`, { platform }, { withCredentials: true });
        toast({
          title: `Connected to ${meta?.label || platform}`,
          description: platform === 'linkedin'
            ? 'MOCKED — admin: set LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET in .env to enable real OAuth.'
            : 'MOCKED — no real OAuth in this demo.',
        });
      }
      await load();
    } catch (e) {
      toast({ title: 'Action failed' });
    } finally {
      setBusy(null);
    }
  };

  const connectedCount = Object.values(statusMap).filter((c) => c.connected).length;

  return (
    <DashboardLayout
      title="Integrations"
      subtitle={`Connect ${Object.keys(PLATFORM_META).length}+ platforms to publish, analyze, and grow.${linkedInOAuth.configured ? ' LinkedIn is live OAuth — other platforms are still mocked.' : ' All platforms are currently mocked.'}`}
    >
      <div className="flex items-center gap-3 mb-7 flex-wrap">
        <div className="px-4 py-2 rounded-full bg-emerald-50 border border-emerald-100 text-emerald-700 text-[13px] font-medium">
          {connectedCount} connected
        </div>
        <div className="px-4 py-2 rounded-full bg-neutral-50 border border-neutral-200 text-neutral-700 text-[13px] font-medium">
          {Object.keys(PLATFORM_META).length - connectedCount} available
        </div>
        {linkedInOAuth.configured && (
          <div className="px-4 py-2 rounded-full bg-sky-50 border border-sky-200 text-sky-700 text-[13px] font-medium inline-flex items-center gap-1.5" data-testid="linkedin-live-oauth-badge">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500 cv-pulse" /> LinkedIn live OAuth
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <div className="space-y-10">
          {Object.entries(catalog).map(([category, platforms]) => {
            const CatIcon = CATEGORY_ICON[category] || Globe;
            return (
              <section key={category}>
                <div className="flex items-center gap-2 mb-4">
                  <CatIcon size={15} className="text-neutral-500" />
                  <h2 className="text-[12px] uppercase tracking-wider text-neutral-500 font-semibold">{category}</h2>
                  <span className="text-[12px] text-neutral-400">({platforms.length})</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {platforms.map((p) => (
                    <PlatformCard
                      key={p}
                      platform={p}
                      meta={PLATFORM_META[p]}
                      status={statusMap[p]}
                      busy={busy === p}
                      onToggle={() => toggle(p)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </DashboardLayout>
  );
};

const PlatformCard = ({ platform, meta, status, busy, onToggle }) => {
  if (!meta) return null;
  const Icon = meta.icon;
  const connected = status?.connected;
  return (
    <div className="bg-white rounded-2xl p-4 border border-neutral-200/70 hover:shadow-md transition-all">
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${meta.color} text-white flex items-center justify-center shrink-0`}>
          <Icon size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[14px] font-semibold truncate">{meta.label}</div>
          <div className="flex items-center gap-1.5 text-[11.5px] mt-0.5">
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-neutral-300'}`} />
            <span className={connected ? 'text-emerald-700' : 'text-neutral-500'}>
              {connected ? (status.handle || 'Connected') : 'Not connected'}
            </span>
          </div>
        </div>
      </div>
      <button
        onClick={onToggle}
        disabled={busy}
        className={`w-full h-9 rounded-lg text-[12.5px] font-medium inline-flex items-center justify-center gap-1.5 transition-colors ${
          connected
            ? 'bg-neutral-50 text-neutral-700 hover:bg-neutral-100 border border-neutral-200'
            : 'bg-[#1B7BFF] hover:bg-[#1668e0] text-white'
        }`}
      >
        {busy ? <Loader2 size={13} className="animate-spin" /> : connected ? <><Check size={13} /> Disconnect</> : 'Connect'}
      </button>
    </div>
  );
};

export default Channels;
