import React from 'react';
import { Link } from 'react-router-dom';
import { Twitter, Linkedin, Github } from 'lucide-react';
import CVLogo from './CVLogo';

const platformLinks = [
  { label: 'Marketing OS',         to: '/marketing-os' },
  { label: 'Seller Acquisition',   to: '/seller-acquisition' },
  { label: 'AI Campaign Generator', to: '/ai-campaign-generator' },
  { label: 'Competitor Analysis',  to: '/competitor-analysis' },
  { label: 'Asset Analysis',       to: '/asset-analysis' },
];

const productLinks = [
  { label: 'AI TikTok Generator', to: '/ai-tiktok-post-generator' },
  { label: 'Viral Content Ideas', to: '/viral-content-ideas-generator' },
  { label: 'Instagram Captions', to: '/instagram-caption-ai-generator' },
  { label: 'Short-Form Video AI', to: '/short-form-video-ideas-ai' },
  { label: 'Content Automation', to: '/content-automation-tool' },
];

const companyLinks = [
  { label: 'Agents', to: '/agents' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Roadmap', to: '/roadmap' },
  { label: 'Blog', to: '/blog' },
  { label: 'Dashboard', to: '/dashboard' },
];

const CVFooter = () => {
  return (
    <footer className="relative cv-dark border-t border-white/5 pt-16 pb-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid md:grid-cols-12 gap-10">
          {/* Brand */}
          <div className="md:col-span-3">
            <div className="flex items-center gap-2.5">
              <CVLogo size="sm" />
              <span className="cv-display font-semibold text-[15px] text-white">
                Cortex<span className="cv-gradient-text">Viral</span>
              </span>
            </div>
            <p className="text-[13px] text-zinc-400 mt-4 max-w-xs leading-relaxed">
              The AI Marketing Operating System — plan campaigns, generate content, recruit sellers, and analyze competitors from one command center.
            </p>
            <div className="flex items-center gap-3 mt-5">
              {[
                { Icon: Twitter, href: 'https://twitter.com/cortexviral' },
                { Icon: Linkedin, href: 'https://linkedin.com/company/cortexviral' },
                { Icon: Github, href: '#' },
              ].map(({ Icon, href }, i) => (
                <a key={i} href={href} className="w-9 h-9 rounded-full cv-glass flex items-center justify-center text-zinc-400 hover:text-cyan-300 hover:border-cyan-400/30 transition-colors">
                  <Icon size={14} />
                </a>
              ))}
            </div>
          </div>

          {/* Platform — Phase 6: footer-wide SEO internal linking */}
          <div className="md:col-span-3" data-testid="footer-platform-links">
            <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500 font-semibold mb-4">Platform</div>
            <ul className="space-y-2.5">
              {platformLinks.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-[13.5px] text-zinc-400 hover:text-white transition-colors" data-testid={`footer-link-${l.to.replace('/','')}`}>{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Product */}
          <div className="md:col-span-2">
            <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500 font-semibold mb-4">AI tools</div>
            <ul className="space-y-2.5">
              {productLinks.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company */}
          <div className="md:col-span-2">
            <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500 font-semibold mb-4">Company</div>
            <ul className="space-y-2.5">
              {companyLinks.map((l) => (
                <li key={l.to}>
                  <Link to={l.to} className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal */}
          <div className="md:col-span-2">
            <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500 font-semibold mb-4">Legal</div>
            <ul className="space-y-2.5">
              <li><Link to="/privacy" className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">Privacy</Link></li>
              <li><Link to="/terms" className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">Terms</Link></li>
              <li><Link to="/data-deletion" className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">Data Deletion</Link></li>
              <li><Link to="/sitemap" className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">Sitemap</Link></li>
              <li><a href="mailto:support@cortexviral.com" className="text-[13.5px] text-zinc-400 hover:text-white transition-colors">Contact</a></li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-white/5 text-[11.5px] text-zinc-600 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span>© 2026 CortexViral — An AI-powered growth operating system for the modern internet.</span>
          <span>Made for creators, founders, and brands that want to compound.</span>
        </div>
      </div>
    </footer>
  );
};

export default CVFooter;
