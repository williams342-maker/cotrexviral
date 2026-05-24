import React from 'react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import CVLegalLayout from '../components/cv/CVLegalLayout';

const SECTIONS = [
  {
    id: 'collect',
    title: '1. Information We Collect',
    content: (
      <>
        <p><strong>Account data</strong> — email address, name, and profile picture provided by your Google or LinkedIn login.</p>
        <p><strong>Connected-channel data</strong> — when you connect a social platform (e.g. LinkedIn, TikTok, Instagram), we receive an OAuth access token, your platform user ID, and basic profile info (display name, picture). We never receive or store your platform password.</p>
        <p><strong>Content you create</strong> — posts, drafts, scheduled-publishing data, and prompts you submit to our AI features.</p>
        <p><strong>Usage data</strong> — pages viewed, features used, error logs. Used to improve the product.</p>
        <p><strong>Cookies</strong> — a single session cookie (<code>session_token</code>) keeps you logged in. No third-party tracking cookies.</p>
      </>
    ),
  },
  {
    id: 'use',
    title: '2. How We Use Your Information',
    content: (
      <ul>
        <li>To authenticate you and keep your account secure.</li>
        <li>To generate AI content using your prompts (processed by our LLM providers; see Section 5).</li>
        <li>To publish content to platforms you have explicitly connected, on your behalf.</li>
        <li>To send transactional emails (account, billing, security). We do not send marketing emails without opt-in.</li>
        <li>To debug, monitor, and improve the service.</li>
      </ul>
    ),
  },
  {
    id: 'oauth',
    title: '3. Social Media Permissions (OAuth)',
    content: (
      <>
        <p>When you connect a social account via OAuth, we request the minimum scopes required to perform the actions you have asked us to perform — typically <strong>profile/email</strong> and <strong>post-on-your-behalf</strong>. We never request scopes for reading your DMs, contacts, or unrelated data.</p>
        <p>You can disconnect any platform at any time from the <strong>Integrations</strong> page; this revokes our stored token immediately.</p>
      </>
    ),
  },
  {
    id: 'security',
    title: '4. Data Storage & Security',
    content: (
      <p>All data is stored encrypted at rest in MongoDB. Access tokens are stored encrypted and accessible only to our backend service when publishing on your behalf. We use HTTPS everywhere and follow standard SaaS-security practices.</p>
    ),
  },
  {
    id: 'sharing',
    title: '5. Third Parties We Share Data With',
    content: (
      <>
        <p><strong>AI providers</strong> — your prompts and content drafts are sent to large-language-model providers (OpenAI, Anthropic, Google) via the Emergent LLM proxy. Providers process prompts to generate responses and do not retain them for training.</p>
        <p><strong>Social platforms</strong> — when you publish a post, the post content is sent to the destination platform's API (e.g. LinkedIn, TikTok, Instagram).</p>
        <p><strong>Payment processor</strong> — billing is handled by Stripe. We never see or store your full payment-card details.</p>
        <p>We do not sell, rent, or trade your personal data to any third party.</p>
      </>
    ),
  },
  {
    id: 'retention',
    title: '6. Data Retention',
    content: (
      <p>We keep your data for as long as your account is active. If you delete your account, we permanently remove your personal data (including OAuth tokens) within 30 days, except where law requires retention (billing records, etc.).</p>
    ),
  },
  {
    id: 'rights',
    title: '7. Your Rights',
    content: (
      <>
        <p>You can request: a copy of your data, correction of inaccurate data, or deletion of your account. Email <a href="mailto:privacy@cortexviral.com">privacy@cortexviral.com</a> and we will respond within 30 days.</p>
        <p>If you are located in the EEA / UK, you have rights under GDPR including the right to lodge a complaint with your local data protection authority.</p>
      </>
    ),
  },
  {
    id: 'children',
    title: '8. Children',
    content: (
      <p>CortexViral is not directed at children under 16. If you believe a child has provided us personal data, contact us at <a href="mailto:privacy@cortexviral.com">privacy@cortexviral.com</a> and we will remove it.</p>
    ),
  },
  {
    id: 'changes',
    title: '9. Changes to This Policy',
    content: (
      <p>We will update this page when our practices change. If changes are material we will notify you via email or an in-app banner before they take effect.</p>
    ),
  },
  {
    id: 'contact',
    title: '10. Contact',
    content: (
      <p>Questions? Email <a href="mailto:privacy@cortexviral.com">privacy@cortexviral.com</a> or <a href="mailto:support@cortexviral.com">support@cortexviral.com</a>.</p>
    ),
  },
];

const Privacy = () => (
  <div className="min-h-screen cv-dark antialiased">
    <CVSeo
      title="Privacy Policy"
      description="How CortexViral collects, uses, stores, and protects your data — including OAuth tokens from connected social platforms."
      path="/privacy"
      schema={buildBreadcrumbSchema([
        { label: 'Home', path: '/' },
        { label: 'Privacy Policy', path: '/privacy' },
      ])}
    />
    <CVNavbar onGetStarted={() => {}} />

    <section className="relative pt-32 pb-12 overflow-hidden">
      <CVBackdrop variant="hero" />
      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <CVBreadcrumbs items={[{ label: 'Legal', to: '/sitemap' }, { label: 'Privacy Policy' }]} className="mb-5" />
        <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Legal</span>
        <h1 className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]">
          Privacy <span className="cv-gradient-text">Policy</span>
        </h1>
        <p className="mt-5 text-zinc-400 text-[15px]">Last updated: 25 February 2026</p>
      </div>
    </section>

    <section className="relative cv-dark pb-24">
      <CVLegalLayout
        intro={
          <>
            CortexViral ("we", "us", "our") provides an AI-powered social-media content platform at <strong>cortexviral.com</strong>.
            This Privacy Policy explains what data we collect, why we collect it, and how we handle it. By using CortexViral you agree to the terms below.
          </>
        }
        sections={SECTIONS}
      />
    </section>

    <CVFooter />
  </div>
);

export default Privacy;
