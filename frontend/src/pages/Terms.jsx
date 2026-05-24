import React from 'react';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { buildBreadcrumbSchema } from '../components/cv/CVSeo';
import CVBreadcrumbs from '../components/cv/CVBreadcrumbs';
import CVLegalLayout from '../components/cv/CVLegalLayout';

const SECTIONS = [
  {
    id: 'eligibility',
    title: '1. Eligibility',
    content: (
      <p>You must be at least 16 years old and able to form a binding contract in your jurisdiction. By using the Service you confirm you meet these requirements.</p>
    ),
  },
  {
    id: 'account',
    title: '2. Account & Security',
    content: (
      <p>You are responsible for keeping your login credentials and OAuth-connected accounts secure. Notify us immediately at <a href="mailto:support@cortexviral.com">support@cortexviral.com</a> if you suspect unauthorised access.</p>
    ),
  },
  {
    id: 'acceptable-use',
    title: '3. Acceptable Use',
    content: (
      <>
        <p>You agree not to use CortexViral to:</p>
        <ul>
          <li>Generate, post, or distribute content that is illegal, defamatory, hateful, or infringes third-party rights.</li>
          <li>Impersonate any person or entity, or misrepresent your affiliation.</li>
          <li>Send spam, scrape platforms, or violate the Terms of any connected social network (LinkedIn, TikTok, Instagram, etc.).</li>
          <li>Reverse-engineer, scrape, or otherwise abuse the Service or its APIs.</li>
        </ul>
        <p>Violations may result in suspension or termination of your account.</p>
      </>
    ),
  },
  {
    id: 'content',
    title: '4. Content Ownership',
    content: (
      <>
        <p>You retain ownership of all content you create using CortexViral. By using the Service you grant us a limited licence to process, store, and publish your content to platforms you have connected, solely to provide the Service.</p>
        <p>AI-generated drafts are provided "as is". You are responsible for reviewing them before publishing.</p>
      </>
    ),
  },
  {
    id: 'subscriptions',
    title: '5. Subscriptions & Payments',
    content: (
      <>
        <p>Paid plans are billed monthly or annually via Stripe. You can cancel any time; cancellation takes effect at the end of the current billing period.</p>
        <p>We offer a 14-day free trial on Pro and Scale plans. A 30-day refund window applies — see our <a href="/pricing">Pricing page</a> for details.</p>
      </>
    ),
  },
  {
    id: 'third-party',
    title: '6. Third-Party Platforms',
    content: (
      <p>When you connect a social platform we publish on your behalf using the OAuth scopes you have granted. We are not responsible for any action taken (or not taken) by those third-party platforms, including suspension of your account on those platforms.</p>
    ),
  },
  {
    id: 'availability',
    title: '7. Service Availability',
    content: (
      <p>We aim for high uptime but the Service is provided "as is" without uptime guarantees. Scheduled maintenance, third-party outages, or other factors may interrupt the Service.</p>
    ),
  },
  {
    id: 'liability',
    title: '8. Limitation of Liability',
    content: (
      <p>To the maximum extent permitted by law, CortexViral and its affiliates are not liable for any indirect, incidental, consequential, or punitive damages arising from your use of the Service. Our total liability is limited to the amount you paid us in the 12 months preceding the claim.</p>
    ),
  },
  {
    id: 'termination',
    title: '9. Termination',
    content: (
      <p>You can delete your account at any time from your dashboard. We can suspend or terminate access if we reasonably believe you have violated these Terms.</p>
    ),
  },
  {
    id: 'changes',
    title: '10. Changes to These Terms',
    content: (
      <p>We may update these Terms periodically. We will notify you via email or in-app banner of material changes. Continued use of the Service after changes means you accept the updated Terms.</p>
    ),
  },
  {
    id: 'law',
    title: '11. Governing Law',
    content: (
      <p>These Terms are governed by the laws of the United States (Delaware), without regard to conflict-of-laws principles.</p>
    ),
  },
  {
    id: 'contact',
    title: '12. Contact',
    content: (
      <p>Questions? Email <a href="mailto:support@cortexviral.com">support@cortexviral.com</a>.</p>
    ),
  },
];

const Terms = () => (
  <div className="min-h-screen cv-dark antialiased">
    <CVSeo
      title="Terms of Service"
      description="Terms governing your use of the CortexViral AI viral content platform."
      path="/terms"
      schema={buildBreadcrumbSchema([
        { label: 'Home', path: '/' },
        { label: 'Terms of Service', path: '/terms' },
      ])}
    />
    <CVNavbar />

    <section className="relative pt-32 pb-12 overflow-hidden">
      <CVBackdrop variant="hero" />
      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <CVBreadcrumbs items={[{ label: 'Legal', to: '/sitemap' }, { label: 'Terms of Service' }]} className="mb-5" />
        <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">Legal</span>
        <h1 className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[0.95]">
          Terms of <span className="cv-gradient-text">Service</span>
        </h1>
        <p className="mt-5 text-zinc-400 text-[15px]">Last updated: 25 February 2026</p>
      </div>
    </section>

    <section className="relative cv-dark pb-24">
      <CVLegalLayout
        intro={
          <>
            These Terms of Service ("Terms") govern your access to and use of CortexViral ("Service") at <strong>cortexviral.com</strong>.
            By using the Service you agree to be bound by these Terms. If you do not agree, do not use the Service.
          </>
        }
        sections={SECTIONS}
      />
    </section>

    <CVFooter />
  </div>
);

export default Terms;
