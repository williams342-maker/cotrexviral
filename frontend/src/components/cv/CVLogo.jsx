import React from 'react';

/**
 * CortexViral logo: combines the uploaded artwork as an image with optional pulse glow.
 * Use size="sm" (28px), "md" (40px), "lg" (64px), or pass a custom className.
 */
const sizeMap = { sm: 28, md: 40, lg: 64, xl: 96 };

const CVLogo = ({ size = 'md', withWordmark = false, className = '', wordmarkClass = '' }) => {
  const px = sizeMap[size] || size;
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span
        className="relative inline-block rounded-full"
        style={{ width: px, height: px }}
      >
        <span
          className="absolute inset-0 rounded-full cv-pulse"
          style={{
            background: 'radial-gradient(circle, rgba(124,58,237,.45), rgba(6,182,212,.25) 60%, transparent 75%)',
            filter: 'blur(8px)',
          }}
        />
        <img
          src="/cortex-logo.png"
          alt="CortexViral"
          className="relative w-full h-full object-contain"
          draggable={false}
        />
      </span>
      {withWordmark && (
        <span className={`cv-display font-semibold tracking-tight ${wordmarkClass}`}>
          Cortex<span className="cv-gradient-text">Viral</span>
        </span>
      )}
    </span>
  );
};

export default CVLogo;
