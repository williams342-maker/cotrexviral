import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API, useAuth } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import { useToast } from '../../hooks/use-toast';
import { Send, Search, Radar, Share2, Sparkles, ArrowRight, FileText, Inbox, BarChart3, Wand2, CreditCard, CheckCircle2, Gift } from 'lucide-react';
import UsageMeter from '../../components/UsageMeter';

const Overview = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ posts: 0, reports: 0, channels: 0, leads: 0 });
  const [billing, setBilling] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    axios.get(`${API}/dashboard/stats`, { withCredentials: true })
      .then((r) => setStats(r.data))
      .catch(() => {});
    axios.get(`${API}/billing/me`, { withCredentials: true })
      .then((r) => setBilling(r.data))
      .catch(() => {});
  }, []);

  // Handle post-Stripe-checkout redirect
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const status = params.get('billing');
    const sessionId = params.get('session_id');
    if (status === 'success' && sessionId) {
      toast({ title: 'Payment received', description: 'Confirming with Stripe…' });
      // Poll until paid
      let attempts = 0;
      const poll = async () => {
        try {
          const r = await axios.get(`${API}/billing/checkout/status/${sessionId}`, { withCredentials: true });
          if (r.data.payment_status === 'paid') {
            const me = await axios.get(`${API}/billing/me`, { withCredentials: true });
            setBilling(me.data);
            toast({ title: `Welcome to ${me.data.plan === 'pro' ? 'Pro' : 'Scale'}!`, description: 'Your 14-day trial has started.' });
            navigate('/dashboard', { replace: true });
            return;
          }
        } catch {}
        if (++attempts < 8) setTimeout(poll, 1500);
        else {
          toast({ title: "Still confirming…", description: "We'll email you when it's done." });
          navigate('/dashboard', { replace: true });
        }
      };
      poll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openPortal = async () => {
    setPortalLoading(true);
    try {
      const { data } = await axios.post(
        `${API}/billing/portal-session`,
        { origin_url: window.location.origin },
        { withCredentials: true },
      );
      window.location.assign(data.url);
    } catch (e) {
      toast({ title: 'Could not open billing portal', description: e?.response?.data?.detail || e.message });
      setPortalLoading(false);
    }
  };

  const tiles = [
    { label: 'Posts published', value: stats.posts, icon: FileText, color: 'bg-emerald-50 text-emerald-700' },
    { label: 'AI reports', value: stats.reports, icon: BarChart3, color: 'bg-violet-50 text-violet-700' },
    { label: 'Channels connected', value: stats.channels, icon: Share2, color: 'bg-amber-50 text-amber-700' },
    { label: 'Leads collected', value: stats.leads, icon: Inbox, color: 'bg-rose-50 text-rose-700' },
  ];

  const quickActions = [
    { to: '/dashboard/studio', icon: Wand2, title: 'Open Content Studio', desc: 'Newsletters, blog posts, video scripts, multi-platform.', color: 'from-rose-100 to-rose-50' },
    { to: '/dashboard/seo', icon: Search, title: 'Run an SEO review', desc: 'Audit any URL with AI — score, issues, fixes.', color: 'from-blue-100 to-blue-50' },
    { to: '/dashboard/scan', icon: Radar, title: 'Scan your website', desc: 'Detect new listings & generate post ideas.', color: 'from-emerald-100 to-emerald-50' },
    { to: '/dashboard/compose', icon: Send, title: 'Compose & publish', desc: 'Push new posts across all your channels.', color: 'from-violet-100 to-violet-50' },
    { to: '/dashboard/insights', icon: Sparkles, title: 'Get AI insights', desc: 'Tailored marketing advice for your business.', color: 'from-amber-100 to-amber-50' },
  ];

  return (
    <DashboardLayout>
      <div className="mb-9">
        <div className="text-[13px] text-neutral-500 mb-1">Welcome back</div>
        <h1 className="text-3xl md:text-4xl font-medium tracking-tight">
          Hi {user?.name?.split(' ')[0] || 'there'} 👋
        </h1>
        <p className="text-neutral-600 mt-1">Here's what's running across your marketing today.</p>
      </div>

      {/* Billing strip */}
      <div className="mb-7 flex items-center justify-between gap-4 flex-wrap rounded-2xl border border-neutral-200/70 bg-white px-5 py-4" data-testid="dashboard-billing-strip">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${billing?.usage?.comped ? 'bg-emerald-50 text-emerald-700' : billing?.plan && billing.plan !== 'free' ? 'bg-violet-50 text-violet-700' : 'bg-neutral-100 text-neutral-600'}`}>
            {billing?.usage?.comped ? <Gift size={16} /> : billing?.plan && billing.plan !== 'free' ? <CheckCircle2 size={16} /> : <CreditCard size={16} />}
          </div>
          <div>
            <div className="text-[14px] font-semibold text-neutral-900 flex items-center flex-wrap gap-2">
              <span>{billing?.usage?.plan_label || 'Free plan'} plan</span>
              {billing?.usage?.comped && (
                <span
                  className="inline-flex items-center gap-1 text-[10.5px] uppercase tracking-wider bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full font-semibold"
                  data-testid="comped-ribbon"
                  title="Your account was gifted premium access by the CortexViral team. No billing required."
                >
                  <Gift size={9} /> Comped by CortexViral
                </span>
              )}
              {!billing?.usage?.comped && billing?.subscription_status === 'trialing' && <span className="text-[11px] uppercase tracking-wider bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-semibold">Trial</span>}
              {!billing?.usage?.comped && billing?.subscription_status === 'past_due' && <span className="text-[11px] uppercase tracking-wider bg-rose-50 text-rose-700 px-2 py-0.5 rounded-full font-semibold">Past due</span>}
            </div>
            <div className="text-[12.5px] text-neutral-500">
              {billing?.usage?.comped
                ? 'Gifted by the CortexViral team — enjoy! No card on file, no renewal.'
                : !billing?.plan || billing.plan === 'free'
                ? 'Free forever — 5 viral hooks / week, TikTok only.'
                : `Billed ${billing.billing_interval === 'year' ? 'annually' : 'monthly'}.${billing.current_period_end ? ` Renews ${new Date(billing.current_period_end).toLocaleDateString()}` : ''}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {billing?.usage?.comped ? (
            <span className="text-[12px] text-emerald-700 font-medium">No action needed ✨</span>
          ) : (!billing?.plan || billing.plan === 'free') ? (
            <Link to="/pricing" className="cv-btn-primary inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-[13px] font-semibold" data-testid="upgrade-btn">
              Upgrade <ArrowRight size={13} />
            </Link>
          ) : (
            <button
              onClick={openPortal}
              disabled={portalLoading}
              className="cv-btn-secondary inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-[13px] font-semibold disabled:opacity-60"
              data-testid="manage-billing-btn"
            >
              {portalLoading ? 'Opening…' : 'Manage billing'}
            </button>
          )}
        </div>
      </div>

      {/* Annual upsell — only shown to monthly subscribers (P2) */}
      {!billing?.usage?.comped && billing?.plan && billing.plan !== 'free' && billing.billing_interval === 'month' && billing.subscription_status !== 'past_due' && (() => {
        // Annual savings = 12 × monthly − annual (2 months free).
        const savings = { starter: 30, growth: 78, agency: 198, pro: 58, scale: 198 };
        const perMonthAnnual = { starter: 13, growth: 33, agency: 83, pro: 24, scale: 83 };
        const save = savings[billing.plan] || 0;
        const annualMo = perMonthAnnual[billing.plan] || 0;
        return (
          <div
            className="mb-7 rounded-2xl border border-violet-200 bg-gradient-to-r from-violet-50 via-indigo-50 to-violet-50 px-5 py-4 flex items-center justify-between gap-4 flex-wrap"
            data-testid="annual-upsell-banner"
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-white shadow-sm flex items-center justify-center text-violet-700">
                <Sparkles size={16} />
              </div>
              <div>
                <div className="text-[14px] font-semibold text-neutral-900">
                  Switch to annual billing &amp; save ${save} per year
                </div>
                <div className="text-[12.5px] text-neutral-600">
                  2 months free — get the same {billing.usage?.plan_label || 'paid'} features at ${annualMo}/mo billed annually.
                </div>
              </div>
            </div>
            <button
              onClick={openPortal}
              disabled={portalLoading}
              className="cv-btn-primary inline-flex items-center gap-1.5 px-4 h-9 rounded-full text-[13px] font-semibold disabled:opacity-60"
              data-testid="annual-upsell-cta"
            >
              {portalLoading ? 'Opening…' : 'Switch to annual'} <ArrowRight size={13} />
            </button>
          </div>
        );
      })()}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {tiles.map((t) => (
          <div key={t.label} className="bg-white rounded-2xl p-5 border border-neutral-200/70">
            <div className={`w-9 h-9 rounded-lg ${t.color} flex items-center justify-center mb-3`}>
              <t.icon size={17} />
            </div>
            <div className="text-3xl font-medium tracking-tight">{t.value}</div>
            <div className="text-[13px] text-neutral-600 mt-1">{t.label}</div>
          </div>
        ))}
      </div>

      <div className="mb-10">
        <UsageMeter />
      </div>

      <h2 className="text-xl font-semibold tracking-tight mb-4">Quick actions</h2>
      <div className="grid md:grid-cols-2 gap-4">
        {quickActions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className={`group relative overflow-hidden rounded-3xl bg-gradient-to-br ${a.color} p-7 border border-neutral-200/50 hover:shadow-lg transition-all hover:-translate-y-0.5`}
          >
            <div className="w-12 h-12 rounded-xl bg-white flex items-center justify-center mb-4 shadow-sm">
              <a.icon size={20} className="text-neutral-800" />
            </div>
            <div className="text-lg font-semibold tracking-tight mb-1">{a.title}</div>
            <div className="text-[14px] text-neutral-700">{a.desc}</div>
            <div className="mt-5 inline-flex items-center gap-1.5 text-[13px] font-medium text-[#1B7BFF] group-hover:gap-2 transition-all">
              Open <ArrowRight size={14} />
            </div>
          </Link>
        ))}
      </div>
    </DashboardLayout>
  );
};

export default Overview;
