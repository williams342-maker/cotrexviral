import React, { useState } from 'react';
import Navbar from '../components/Navbar';
import Hero from '../components/Hero';
import LogoBar from '../components/LogoBar';
import HowWeWork from '../components/HowWeWork';
import Capabilities from '../components/Capabilities';
import WhyUs from '../components/WhyUs';
import Agents from '../components/Agents';
import Solutions from '../components/Solutions';
import Stats from '../components/Stats';
import Testimonials from '../components/Testimonials';
import CTAFooter from '../components/CTAFooter';
import Footer from '../components/Footer';
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
  const openAgentDirect = (a) => {
    setActiveAgent(a);
    setChatOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#F6F4ED] text-neutral-900 antialiased">
      <Navbar onGetStarted={openSelect} />
      <main>
        <Hero onGetStarted={openSelect} />
        <LogoBar />
        <HowWeWork />
        <Capabilities />
        <WhyUs />
        <Agents onSelect={openAgentDirect} />
        <Solutions />
        <Stats />
        <Testimonials />
        <CTAFooter onGetStarted={openSelect} />
      </main>
      <Footer />

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
