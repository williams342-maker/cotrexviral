import React, { useState, useEffect } from 'react';
import { Users, Star, MessageCircle, PenLine, Menu, X, LayoutDashboard } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const Navbar = ({ onGetStarted }) => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const { user, login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled ? 'py-3' : 'py-5'}`}>
      <div className="max-w-7xl mx-auto px-5 flex items-center justify-between">
        {/* Logo */}
        <a href="#" className="flex items-center gap-2 group">
          <div className="w-9 h-9 rounded-lg bg-[#0B2F66] text-white flex items-center justify-center font-bold text-sm tracking-tight">
            cv
          </div>
          <span className="font-semibold text-[15px] text-neutral-900 tracking-tight">CortexViral</span>
        </a>

        {/* Centered pill nav */}
        <nav className="hidden lg:flex items-center bg-white/90 backdrop-blur-md rounded-full shadow-[0_4px_24px_rgba(0,0,0,0.06)] border border-neutral-200/60 px-2 py-2 gap-1">
          <NavBtn icon={Users} label="Agents" active dot />
          <NavBtn icon={Star} label="Customers" />
          <NavBtn icon={MessageCircle} label="About us" />
          <NavBtn icon={PenLine} label="Blog" />
        </nav>

        {/* Right */}
        <div className="hidden lg:flex items-center gap-3">
          {user ? (
            <button onClick={() => navigate('/dashboard')} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white px-5 py-2 rounded-full text-sm font-medium transition-colors">
              <LayoutDashboard size={14} /> Dashboard
            </button>
          ) : (
            <button onClick={login} className="text-sm font-medium text-neutral-700 hover:text-neutral-900 px-4 py-2 rounded-full transition-colors">
              Login
            </button>
          )}
        </div>

        {/* Mobile */}
        <button className="lg:hidden p-2 rounded-lg hover:bg-neutral-100" onClick={() => setOpen(!open)}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {open && (
        <div className="lg:hidden absolute top-full left-0 right-0 mx-5 mt-2 bg-white rounded-2xl shadow-xl border border-neutral-200 p-4 flex flex-col gap-1">
          <MobileLink icon={Users} label="Agents" />
          <MobileLink icon={Star} label="Customers" />
          <MobileLink icon={MessageCircle} label="About us" />
          <MobileLink icon={PenLine} label="Blog" />
          {user ? (
            <button onClick={() => navigate('/dashboard')} className="mt-2 w-full bg-[#1B7BFF] text-white rounded-full py-2.5 text-sm font-medium">Dashboard</button>
          ) : (
            <button onClick={login} className="mt-2 w-full bg-neutral-100 text-neutral-900 rounded-full py-2.5 text-sm font-medium">Login</button>
          )}
          <button onClick={onGetStarted} className="mt-2 w-full bg-[#1B7BFF] text-white rounded-full py-2.5 text-sm font-medium">Get Started</button>
        </div>
      )}
    </header>
  );
};

const NavBtn = ({ icon: Icon, label, active, dot }) => (
  <button className={`relative flex flex-col items-center gap-0.5 px-4 py-1.5 rounded-full transition-colors ${active ? 'text-neutral-900' : 'text-neutral-500 hover:text-neutral-800'}`}>
    <Icon size={16} strokeWidth={active ? 2.4 : 2} />
    <span className="text-[11px] font-medium tracking-tight">{label}</span>
    {dot && <span className="absolute top-1 right-3 w-1.5 h-1.5 rounded-full bg-[#1B7BFF]" />}
  </button>
);

const MobileLink = ({ icon: Icon, label }) => (
  <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-neutral-50 text-sm font-medium text-neutral-800">
    <Icon size={18} /> {label}
  </a>
);

export default Navbar;
