import React, { useState } from 'react';
import CVNavbar from '../components/cv/CVNavbar';
import CVHero from '../components/cv/CVHero';
import CVNeuralEngine from '../components/cv/CVNeuralEngine';
import CVPipeline from '../components/cv/CVPipeline';
import CVResults from '../components/cv/CVResults';
import CVComparison from '../components/cv/CVComparison';
import CVFaq, { DEFAULT_FAQS } from '../components/cv/CVFaq';
import CVCTAFooter from '../components/cv/CVCTAFooter';
import CVBuiltByMakers from '../components/cv/CVBuiltByMakers';
import CVFooter from '../components/cv/CVFooter';
import CVSeo, { ORG_SCHEMA, SOFTWARE_SCHEMA, buildFaqSchema } from '../components/cv/CVSeo';
import { useAuth } from '../context/AuthContext';
import AuthModal from '../components/AuthModal';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';

const Marketing = () => {
  // "Start Free" CTAs across the marketing page must trigger the real
  // login flow — not the old "Choose Your Specialist" picker which is
  // only useful AFTER signup. The agent picker stays available via the
  // existing chat-with-agent UI for already-authenticated users.
  const { user, login } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);

  const openStartFree = () => {
    // If already authed, jump straight into the agent picker (legacy flow
    // for warm users). Otherwise open the Auth modal which redirects to
    // auth.emergentagent.com — the real signup path.
    if (user) {
      setChatOpen(false);
      setSelectOpen(true);
    } else {
      setAuthOpen(true);
    }
  };
  const handleSelectAgent = (a) => {
    setActiveAgent(a);
    setSelectOpen(false);
    setTimeout(() => setChatOpen(true), 120);
  };
  const handleBack = () => {
    setChatOpen(false);
    setTimeout(() => setSelectOpen(true), 120);
  };

  return (
    <div className="min-h-screen cv-dark antialiased">
      <CVSeo
        title="Create, Schedule & Optimize Social Posts Automatically | CortexViral"
        description="CortexViral is the AI social marketing autopilot: pick your niche, AI writes hook-tested posts, you approve in one tap, it schedules at peak times and measures results. Replace a 5-person social team — start free."
        path="/"
        schema={[ORG_SCHEMA, SOFTWARE_SCHEMA, buildFaqSchema(DEFAULT_FAQS.map((f) => ({ question: f.q, answer: f.a })))]}
      />
      <CVNavbar onGetStarted={openStartFree} />
      <main>
        <CVHero onGetStarted={openStartFree} />
        <CVNeuralEngine />
        <CVPipeline />
        <CVResults />
        <CVComparison />
        <CVFaq />
        <CVCTAFooter onGetStarted={openStartFree} />
      </main>
      <CVBuiltByMakers />
      <CVFooter />

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />

      <SelectAgentModal
        open={selectOpen}
        onClose={() => setSelectOpen(false)}
        onSelect={handleSelectAgent}
      />
      <AgentChatModal
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        agent={activeAgent}
        onBack={handleBack}
      />
    </div>
  );
};

export default Marketing;
