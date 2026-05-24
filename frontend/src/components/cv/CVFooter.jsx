import React from 'react';
import { Twitter, Linkedin, Github } from 'lucide-react';
import CVLogo from './CVLogo';

const CVFooter = () => {
  return (
    <footer className="relative cv-dark border-t border-white/5 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex items-center gap-2.5">
          <CVLogo size="sm" />
          <span className="cv-display font-semibold text-[15px] text-white">
            Cortex<span className="cv-gradient-text">Viral</span>
          </span>
        </div>
        <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] text-zinc-400">
          <a href="#system" className="hover:text-white transition-colors">System</a>
          <a href="#pipeline" className="hover:text-white transition-colors">Pipeline</a>
          <a href="#results" className="hover:text-white transition-colors">Case Studies</a>
          <a href="/agents" className="hover:text-white transition-colors">Agents</a>
          <a href="/dashboard" className="hover:text-white transition-colors">Dashboard</a>
          <a href="#" className="hover:text-white transition-colors">Privacy</a>
          <a href="#" className="hover:text-white transition-colors">Terms</a>
        </nav>
        <div className="flex items-center gap-3">
          {[
            { Icon: Twitter, href: '#' },
            { Icon: Linkedin, href: '#' },
            { Icon: Github, href: '#' },
          ].map(({ Icon, href }, i) => (
            <a key={i} href={href} className="w-9 h-9 rounded-full cv-glass flex items-center justify-center text-zinc-400 hover:text-cyan-300 hover:border-cyan-400/30 transition-colors">
              <Icon size={14} />
            </a>
          ))}
        </div>
      </div>
      <div className="mt-8 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-[11.5px] text-zinc-600">
        © 2026 CortexViral · An AI-powered growth operating system for the modern internet.
      </div>
    </footer>
  );
};

export default CVFooter;
