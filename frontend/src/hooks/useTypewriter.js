import { useEffect, useState, useRef } from 'react';

/* useTypewriter — progressively reveals a string one character at a
   time. Returns [displayed, done]. Resets if the source text changes.
   Defaults to 25ms/char (user-chosen "lively" pace).

   Implementation notes:
   - Uses requestAnimationFrame batching via setTimeout for low CPU.
   - Skips animation entirely when prefers-reduced-motion is set.
   - Caller can force-complete via `done` flag to allow click-to-skip. */
export default function useTypewriter(text, { speed = 25, enabled = true } = {}) {
  const [displayed, setDisplayed] = useState(enabled ? '' : text);
  const [done, setDone] = useState(!enabled);
  const idxRef = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      setDone(true);
      return;
    }
    // Respect users who've asked for reduced motion.
    const reduce = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setDisplayed(text);
      setDone(true);
      return;
    }
    setDisplayed('');
    setDone(false);
    idxRef.current = 0;

    const tick = () => {
      idxRef.current += 1;
      if (idxRef.current >= text.length) {
        setDisplayed(text);
        setDone(true);
        timerRef.current = null;
        return;
      }
      setDisplayed(text.slice(0, idxRef.current));
      timerRef.current = setTimeout(tick, speed);
    };
    timerRef.current = setTimeout(tick, speed);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [text, speed, enabled]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setDisplayed(text);
    setDone(true);
  };

  return { displayed, done, skip };
}
