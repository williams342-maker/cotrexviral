import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';

/* OnboardingSpotlight — soft radial-gradient "halo" rendered through a
   portal over the targeted region. NOT a modal — it does not capture
   clicks. The rest of the UI stays interactive; the halo just draws
   the user's eye to a region while Cortex narrates.

   Target detection: `targetSelector` is queried on every animation
   frame so the spotlight follows the element as the layout shifts
   (resizable rail, mission cards animating in, etc.).

   No SVG masking — we use four absolutely-positioned dark panels
   that frame the target rectangle. This avoids the perf hit of
   continuously rebuilding an SVG clip-path. */
export default function OnboardingSpotlight({ targetSelector, padding = 12, dim = 0.35 }) {
  const [rect, setRect] = useState(null);

  useEffect(() => {
    if (!targetSelector) {
      setRect(null);
      return;
    }
    let raf = 0;
    const measure = () => {
      const el = document.querySelector(targetSelector);
      if (!el) {
        setRect(null);
      } else {
        const r = el.getBoundingClientRect();
        setRect({
          top:    r.top - padding,
          left:   r.left - padding,
          width:  r.width + padding * 2,
          height: r.height + padding * 2,
        });
      }
      raf = requestAnimationFrame(measure);
    };
    raf = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(raf);
  }, [targetSelector, padding]);

  if (typeof document === 'undefined') return null;
  if (!targetSelector) return null;

  return createPortal(
    <AnimatePresence>
      {rect && (
        <motion.div
          key="spotlight"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="pointer-events-none fixed inset-0 z-[60]"
          data-testid="onboarding-spotlight"
        >
          {/* 4 dark panels framing the target rectangle. pointer-events
              none so underlying UI stays interactive. */}
          <div className="absolute left-0 right-0 top-0 bg-black transition-all"
                style={{ height: rect.top, opacity: dim }} />
          <div className="absolute left-0 bg-black transition-all"
                style={{ top: rect.top, height: rect.height,
                          width: rect.left, opacity: dim }} />
          <div className="absolute right-0 bg-black transition-all"
                style={{ top: rect.top, height: rect.height,
                          left: rect.left + rect.width, opacity: dim }} />
          <div className="absolute left-0 right-0 bg-black transition-all"
                style={{ top: rect.top + rect.height,
                          bottom: 0, opacity: dim }} />
          {/* Soft violet halo around the spotlight target. */}
          <motion.div
            className="absolute rounded-2xl ring-2 ring-violet-400/60 shadow-[0_0_60px_12px_rgba(139,92,246,0.45)]"
            style={{ top: rect.top, left: rect.left,
                     width: rect.width, height: rect.height }}
            animate={{
              boxShadow: [
                '0 0 60px 12px rgba(139,92,246,0.35)',
                '0 0 80px 16px rgba(139,92,246,0.55)',
                '0 0 60px 12px rgba(139,92,246,0.35)',
              ],
            }}
            transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
          />
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
