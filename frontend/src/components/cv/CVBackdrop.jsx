import React from 'react';

/**
 * Reusable backdrop for dark-themed CortexViral sections:
 *   <CVBackdrop variant="hero" /> — animated auroras + grid + particles
 *   <CVBackdrop variant="subtle" /> — grid only
 */
const CVBackdrop = ({ variant = 'subtle', className = '' }) => {
  if (variant === 'hero') {
    return (
      <div className={`absolute inset-0 overflow-hidden pointer-events-none ${className}`} aria-hidden>
        <div className="absolute inset-0 cv-grid-bg" />
        <div className="cv-aurora cv-aurora-violet" style={{ top: '-20%', left: '-15%' }} />
        <div className="cv-aurora cv-aurora-cyan" style={{ bottom: '-30%', right: '-20%' }} />
        <div className="absolute inset-0 cv-particles" />
        <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#09090B] to-transparent" />
      </div>
    );
  }
  return (
    <div className={`absolute inset-0 overflow-hidden pointer-events-none ${className}`} aria-hidden>
      <div className="absolute inset-0 cv-grid-bg opacity-60" />
      <div className="cv-aurora cv-aurora-violet" style={{ top: '20%', left: '-30%', width: '40rem', height: '40rem' }} />
    </div>
  );
};

export default CVBackdrop;
