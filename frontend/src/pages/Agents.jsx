import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import CVNavbar from '../components/cv/CVNavbar';
import CVBackdrop from '../components/cv/CVBackdrop';
import CVFooter from '../components/cv/CVFooter';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';
import { ArrowRight } from 'lucide-react';

const agents = [
  {
    id: 'nova',
    name: 'Nova',
    role: 'AI Digital Marketer',
    color: 'from-violet-500/40 to-violet-500/0',
    accent: 'text-violet-300',
    avatar: '',
    blurb: 'Crafts viral hooks, multi-platform copy, and CTA-tested variants in your voice.',
    skills: ['Hook engineering', 'Multi-platform copy', 'Headline A/B'],
  },
  {
    id: 'sam',
    name: 'Sam',
    role: 'AI SEO / GEO Manager',
    color: 'from-cyan-500/40 to-cyan-500/0',
    accent: 'text-cyan-300',
    avatar: '',
    blurb: 'Audits your site, ranks competitors, and ships SEO-perfect briefs for every page.',
    skills: ['Technical audits', 'Competitor gap analysis', 'Schema & meta'],
  },
  {
    id: 'kai',
    name: 'Kai',
    role: 'AI Social Listener',
    color: 'from-blue-500/40 to-blue-500/0',
    accent: 'text-blue-300',
    avatar: '',
    blurb: 'Listens across X, Reddit, TikTok & Threads to surface trending angles before they peak.',
    skills: ['Trend detection', 'Sentiment analysis', 'Optimal posting times'],
  },
  {
    id: 'angela',
    name: 'Angela',
    role: 'AI Email Marketer',
    color: 'from-emerald-500/40 to-emerald-500/0',
    accent: 'text-emerald-300',
    avatar: '',
    blurb: 'Writes newsletters, drip sequences, and lifecycle flows that convert subscribers.',
    skills: ['Newsletter drafts', 'Drip sequences', 'Lifecycle automation'],
  },
];

const AgentsPage = () => {
  const navigate = useNavigate();
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);

  const handleSelectAgent = (a) => {
    setActiveAgent(a);
    setSelectOpen(false);
    setTimeout(() => setChatOpen(true), 120);
  };
  const openDirect = (a) => {
    setActiveAgent(a);
    setChatOpen(true);
  };

  return (
    <div className="min-h-screen cv-dark">
      <CVNavbar onGetStarted={() => setSelectOpen(true)} />

      <section className="relative pt-32 pb-20 overflow-hidden">
        <CVBackdrop variant="hero" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <span className="text-[11px] uppercase tracking-[0.22em] text-violet-400 font-semibold">The AI Team</span>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="cv-display text-5xl sm:text-6xl font-semibold text-white mt-3 leading-[1.05]"
          >
            Meet your <span className="cv-gradient-text">always-on</span> growth team.
          </motion.h1>
          <p className="mt-5 text-zinc-400 max-w-2xl mx-auto text-[16px]">
            Four specialist AI agents that publish, optimise, and report — directly into your inbox.
            Pick one and start a conversation right now.
          </p>
        </div>
      </section>

      <section className="relative cv-dark pb-28">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {agents.map((a, i) => (
            <motion.button
              key={a.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              onClick={() => openDirect(a)}
              className="text-left cv-glass-strong rounded-3xl p-6 group hover:border-violet-400/30 transition-colors relative overflow-hidden"
              data-testid={`cv-agent-card-${a.id}`}
            >
              <div className={`absolute -top-20 -right-20 w-60 h-60 rounded-full bg-gradient-to-br ${a.color} blur-3xl opacity-80 group-hover:opacity-100 transition-opacity`} />
              <div className="relative">
                <div className="w-20 h-20 rounded-2xl cv-glass flex items-center justify-center mb-4 overflow-hidden">
                  {a.avatar ? (
                    <img src={a.avatar} alt={a.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className={`cv-display text-3xl font-semibold ${a.accent}`}>{a.name[0]}</span>
                  )}
                </div>
                <div className="cv-display text-2xl font-semibold text-white">{a.name}</div>
                <div className={`text-[12px] uppercase tracking-wider font-semibold mt-1 ${a.accent}`}>{a.role}</div>
                <p className="text-[13.5px] text-zinc-400 mt-3 leading-relaxed">{a.blurb}</p>
                <div className="flex flex-wrap gap-1.5 mt-4">
                  {a.skills.map((s) => (
                    <span key={s} className="text-[10.5px] cv-glass px-2 py-1 rounded-full text-zinc-300">{s}</span>
                  ))}
                </div>
                <div className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-white group-hover:text-cyan-300 transition-colors">
                  Chat with {a.name} <ArrowRight size={13} />
                </div>
              </div>
            </motion.button>
          ))}
        </div>

        <div className="mt-12 text-center">
          <button
            onClick={() => navigate('/dashboard')}
            className="cv-btn-primary inline-flex items-center gap-2 text-[14px] font-semibold px-6 h-12 rounded-full"
            data-testid="cv-agents-dashboard-cta"
          >
            Open your dashboard <ArrowRight size={15} />
          </button>
        </div>
      </section>

      <CVFooter />

      <SelectAgentModal open={selectOpen} onClose={() => setSelectOpen(false)} onSelect={handleSelectAgent} />
      <AgentChatModal open={chatOpen} onClose={() => setChatOpen(false)} agent={activeAgent} onBack={() => { setChatOpen(false); setSelectOpen(true); }} />
    </div>
  );
};

export default AgentsPage;
