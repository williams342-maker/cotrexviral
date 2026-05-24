import React from 'react';
import { Twitter, Linkedin, Instagram, Mail } from 'lucide-react';

const Footer = () => {
  return (
    <footer className="border-t border-neutral-200/70 py-12 bg-white/40">
      <div className="max-w-7xl mx-auto px-5">
        <div className="grid md:grid-cols-4 gap-10">
          <div>
            <a href="#" className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-[#0B2F66] text-white flex items-center justify-center font-bold text-sm">
                ax
              </div>
              <span className="font-semibold text-[15px] text-neutral-900">Automatex</span>
            </a>
            <p className="mt-4 text-[14px] text-neutral-600 leading-relaxed">
              AI marketing agents that execute your entire strategy 24/7.
            </p>
            <div className="mt-5 flex gap-3">
              {[Twitter, Linkedin, Instagram, Mail].map((I, i) => (
                <a key={i} href="#" className="w-9 h-9 rounded-full bg-neutral-100 hover:bg-[#1B7BFF] hover:text-white text-neutral-600 flex items-center justify-center transition-colors">
                  <I size={15} />
                </a>
              ))}
            </div>
          </div>

          <FooterCol title="Agents" links={['Nova', 'Sam', 'Kai', 'Angela']} />
          <FooterCol title="Company" links={['About', 'Customers', 'Blog', 'Careers']} />
          <FooterCol title="Resources" links={['Pricing', 'Help center', 'Terms', 'Privacy']} />
        </div>

        <div className="mt-12 pt-6 border-t border-neutral-200/70 flex flex-col md:flex-row justify-between items-center gap-3">
          <p className="text-[13px] text-neutral-500">© {new Date().getFullYear()} Automatex. All rights reserved.</p>
          <p className="text-[13px] text-neutral-500">Made with care</p>
        </div>
      </div>
    </footer>
  );
};

const FooterCol = ({ title, links }) => (
  <div>
    <h4 className="text-[12px] uppercase tracking-[0.16em] text-neutral-500 font-semibold mb-4">{title}</h4>
    <ul className="space-y-2.5">
      {links.map((l) => (
        <li key={l}><a href="#" className="text-[14px] text-neutral-700 hover:text-[#1B7BFF] transition-colors">{l}</a></li>
      ))}
    </ul>
  </div>
);

export default Footer;
