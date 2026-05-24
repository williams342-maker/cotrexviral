import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Menu, X, ArrowUpRight, LayoutDashboard } from 'lucide-react';
import CVLogo from './CVLogo';
import { useAuth } from '../../context/AuthContext';

const links = [
  { label: 'System', href: '#system' },
  { label: 'Pipeline', href: '#pipeline' },
  { label: 'Results', href: '#results' },
  { label: 'Agents', href: '/agents', external: true },
  { label: 'Pricing', href: '/pricing', external: true },
];

const CVNavbar = ({ onGetStarted }) => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { user, login } = useAuth();

  // If parent didn't wire a real handler, fall back to auth-aware default:
  // logged-in users → /dashboard, logged-out → Emergent Google Auth.
  const handleCTA = () => {
    if (typeof onGetStarted === 'function') {
      onGetStarted();
      return;
    }
    if (user) navigate('/dashboard');
    else login();
  };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 14);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleNav = (e, link) => {
    if (link.external) {
      e.preventDefault();
      navigate(link.href);
      return;
    }
    // Smooth scroll for in-page anchors
    if (link.href.startsWith('#')) {
      e.preventDefault();
      const el = document.querySelector(link.href);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
        scrolled ? 'py-3' : 'py-5'
      }`}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <nav
          className={`flex items-center justify-between gap-4 rounded-2xl px-4 sm:px-6 h-14 transition-all duration-300 ${
            scrolled ? 'cv-glass-strong cv-glow-soft' : 'cv-glass'
          }`}
          data-testid="cv-navbar"
        >
          <button onClick={() => navigate('/')} className="flex items-center gap-2.5 group" data-testid="cv-nav-logo">
            <CVLogo size="sm" />
            <span className="cv-display font-semibold tracking-tight text-[15px] text-white">
              Cortex<span className="cv-gradient-text">Viral</span>
            </span>
          </button>

          <div className="hidden md:flex items-center gap-7">
            {links.map((l) => (
              <a
                key={l.label}
                href={l.href}
                onClick={(e) => handleNav(e, l)}
                className="text-[13.5px] font-medium text-zinc-400 hover:text-white transition-colors"
                data-testid={`cv-nav-${l.label.toLowerCase()}`}
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {user ? (
              <button
                onClick={() => navigate('/dashboard')}
                className="hidden sm:inline-flex items-center gap-1.5 text-[13px] font-medium text-zinc-300 hover:text-white px-3 h-9 rounded-lg transition-colors"
                data-testid="cv-nav-dashboard"
              >
                <LayoutDashboard size={13} /> Dashboard
              </button>
            ) : (
              <button
                onClick={login}
                className="hidden sm:inline-flex text-[13px] font-medium text-zinc-300 hover:text-white px-3 h-9 rounded-lg transition-colors"
                data-testid="cv-nav-login"
              >
                Login
              </button>
            )}
            <button
              onClick={handleCTA}
              className="cv-btn-primary inline-flex items-center gap-1.5 text-[13px] font-semibold px-4 h-9 rounded-full"
              data-testid="cv-nav-cta"
            >
              Start Growing <ArrowUpRight size={14} />
            </button>
            <button
              onClick={() => setOpen((o) => !o)}
              className="md:hidden inline-flex items-center justify-center w-9 h-9 rounded-lg cv-btn-secondary"
              aria-label="Toggle menu"
              data-testid="cv-nav-menu-toggle"
            >
              {open ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </nav>

        {/* Mobile menu */}
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-2 md:hidden cv-glass-strong rounded-2xl p-4 flex flex-col gap-1"
          >
            {links.map((l) => (
              <a
                key={l.label}
                href={l.href}
                onClick={(e) => { handleNav(e, l); setOpen(false); }}
                className="px-3 py-3 rounded-xl text-[14px] font-medium text-zinc-300 hover:bg-white/5 hover:text-white"
              >
                {l.label}
              </a>
            ))}
            <button
              onClick={() => { setOpen(false); user ? navigate('/dashboard') : login(); }}
              className="px-3 py-3 rounded-xl text-[14px] font-medium text-zinc-300 hover:bg-white/5 hover:text-white text-left"
            >
              {user ? 'Dashboard' : 'Login'}
            </button>
          </motion.div>
        )}
      </div>
    </motion.header>
  );
};

export default CVNavbar;
