import React, { useState } from 'react';
import CVNavbar from '../components/cv/CVNavbar';
import CVHero from '../components/cv/CVHero';
import CVNeuralEngine from '../components/cv/CVNeuralEngine';
import CVPipeline from '../components/cv/CVPipeline';
import CVResults from '../components/cv/CVResults';
import CVCTAFooter from '../components/cv/CVCTAFooter';
import CVFooter from '../components/cv/CVFooter';
import { SelectAgentModal, AgentChatModal } from '../components/Modals';

const Marketing = () => {
  const [selectOpen, setSelectOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);

  const openSelect = () => {
    setChatOpen(false);
    setSelectOpen(true);
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
      <CVNavbar onGetStarted={openSelect} />
      <main>
        <CVHero onGetStarted={openSelect} />
        <CVNeuralEngine />
        <CVPipeline />
        <CVResults />
        <CVCTAFooter onGetStarted={openSelect} />
      </main>
      <CVFooter />

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
