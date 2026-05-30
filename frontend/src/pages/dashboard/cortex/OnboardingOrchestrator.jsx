import React, { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ArrowRight, X, Brain, ChevronRight } from 'lucide-react';
import { API } from '../../../context/AuthContext';
import useTypewriter from '../../../hooks/useTypewriter';
import OnboardingSpotlight from './OnboardingSpotlight';

/* OnboardingOrchestrator — AI-guided first-run mission.

   This is NOT a tour overlay. Cortex teaches through conversation:
   - Cortex's scripted messages appear in a top-right floating card
     with typewriter animation (so they coexist with the real chat).
   - Spotlights highlight the relevant UI region per step.
   - On `set_goal` step, the user types into the actual composer (the
     spotlight cues this); orchestrator listens for `onGoalSubmitted`.
   - On `sample_mission_proposal`, the orchestrator ticks the demo
     mission so the rail animates phases as Cortex narrates.

   Renders nothing if user is not in onboarding (eligible=false +
   no in-progress row).

   Public props:
     replayCounter: bumped by parent's "Show me around" button to
                    explicitly start a replay walkthrough.
     onCommandeerComposer: callback (text) — parent prefills the
                    composer for the user to send.
     goalSubmitted: bumped by parent when the user submits a message
                    while the orchestrator is on `set_goal` — that
                    message becomes the captured goal. */

const SPOTLIGHT_SELECTORS = {
  composer:        '[data-testid="cortex-composer"]',
  mission_rail:    '[data-testid="active-mission-rail"]',
  // Falls back through a few candidates so the spotlight has something
  // to land on even when the OptimizationStatus card isn't rendered yet.
  autonomy_chip:   '[data-testid="cortex-optimization-status"], [data-testid="active-mission-rail"]',
};

export default function OnboardingOrchestrator({
  replayCounter = 0,
  onCommandeerComposer,
  goalSubmittedSignal = 0,
  lastUserMessage = '',
}) {
  const [state, setState] = useState(null);   // /onboarding/state response
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState(false);
  const tickRef = useRef(null);

  const loadState = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/onboarding/state`, { withCredentials: true });
      setState(r.data);
    } catch (_e) {
      setState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadState(); }, [loadState]);

  // Replay trigger from parent's "Show me around" button.
  useEffect(() => {
    if (replayCounter === 0) return;
    (async () => {
      try {
        await axios.post(`${API}/cortex/onboarding/start`,
                          { replay: true }, { withCredentials: true });
        setHidden(false);
        await loadState();
      } catch (_e) { /* */ }
    })();
  }, [replayCounter, loadState]);

  // First-time gate: if eligible and step is null, auto-start.
  useEffect(() => {
    if (loading || !state) return;
    if (state.step) return;  // already in-progress
    if (!state.eligible) return;
    (async () => {
      try {
        await axios.post(`${API}/cortex/onboarding/start`,
                          { replay: false }, { withCredentials: true });
        await loadState();
      } catch (_e) { /* */ }
    })();
  }, [loading, state, loadState]);

  const advance = useCallback(async (userInput = null) => {
    try {
      const r = await axios.post(
        `${API}/cortex/onboarding/advance`,
        { from_step: state?.step, user_input: userInput },
        { withCredentials: true });
      setState(r.data);
    } catch (_e) { /* */ }
  }, [state?.step]);

  const skip = useCallback(async () => {
    try {
      await axios.post(`${API}/cortex/onboarding/skip`, {},
                        { withCredentials: true });
    } catch (_e) { /* */ }
    setHidden(true);
    await loadState();
  }, [loadState]);

  // Composer prefill cue on `set_goal`.
  useEffect(() => {
    if (state?.step === 'set_goal' && onCommandeerComposer) {
      onCommandeerComposer('');   // just focus, don't prefill
    }
  }, [state?.step, onCommandeerComposer]);

  // When the user submits during `set_goal`, capture their message as
  // the goal and advance.
  useEffect(() => {
    if (goalSubmittedSignal === 0) return;
    if (state?.step !== 'set_goal') return;
    if (!lastUserMessage) return;
    advance(lastUserMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goalSubmittedSignal]);

  // Demo-mission ticker — fires during the rail-animation steps so the
  // demo mission advances phase-by-phase while Cortex narrates.
  useEffect(() => {
    const animatingSteps = new Set(['mission_lifecycle', 'autonomous_execution']);
    if (!state || !animatingSteps.has(state.step)) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        await axios.post(`${API}/cortex/onboarding/demo-tick`, {},
                          { withCredentials: true });
      } catch (_e) { /* */ }
      tickRef.current = setTimeout(tick, 2200);
    };
    tickRef.current = setTimeout(tick, 1000);
    return () => {
      cancelled = true;
      if (tickRef.current) clearTimeout(tickRef.current);
    };
  }, [state?.step]); // eslint-disable-line react-hooks/exhaustive-deps

  // Bail out: not eligible, no in-progress row, or terminal.
  if (loading) return null;
  if (hidden) return null;
  if (!state) return null;
  if (!state.step) return null;
  if (state.step === 'complete') return null;

  return (
    <>
      <OnboardingSpotlight targetSelector={SPOTLIGHT_SELECTORS[state.spotlight] || null} />
      <OnboardingCard
        state={state}
        onAdvance={() => advance()}
        onSkip={skip}
      />
    </>
  );
}


// ---------------------------------------------------------------- card
function OnboardingCard({ state, onAdvance, onSkip }) {
  const { displayed, done, skip: fastForward } = useTypewriter(
    state.message || '',
    { speed: 25, enabled: true },
  );
  // Reset typewriter when step changes (handled by useTypewriter key
  // via the text dependency).

  const stepIdx = ['welcome','set_goal','cc_intro','sample_mission_proposal',
                    'mission_lifecycle','autonomous_execution','autonomy_explain']
                    .indexOf(state.step);
  const totalSteps = 7;
  const pct = Math.min(100, Math.max(0,
    Math.round(((stepIdx + 1) / totalSteps) * 100)));

  return createCardPortal(
    <AnimatePresence>
      <motion.div
        key="onb-card"
        initial={{ opacity: 0, y: -16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
        data-testid="onboarding-card"
        className="fixed top-5 right-5 z-[70] w-[420px] max-w-[calc(100vw-32px)]
                    rounded-2xl border border-violet-400/30
                    bg-gradient-to-br from-zinc-950/95 to-violet-950/40
                    backdrop-blur-xl shadow-2xl shadow-violet-500/20 p-5"
      >
        {/* Header */}
        <div className="flex items-start gap-3 mb-3">
          <motion.span
            animate={{ rotate: [0, 8, -6, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/40"
          >
            <Brain size={16} className="text-white" />
          </motion.span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest font-semibold text-violet-300 flex items-center gap-1.5">
              <Sparkles size={10} /> Cortex Onboarding
            </div>
            <div className="text-[11px] text-zinc-500 mt-0.5">
              Step {Math.min(stepIdx + 1, totalSteps)} of {totalSteps}
            </div>
          </div>
          <button onClick={onSkip} data-testid="onboarding-skip-btn"
                  title="Skip onboarding"
                  className="shrink-0 w-7 h-7 rounded-md hover:bg-white/10 text-zinc-500 hover:text-zinc-200 transition flex items-center justify-center">
            <X size={13} />
          </button>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-white/5 rounded-full overflow-hidden mb-4">
          <motion.div
            className="h-full bg-gradient-to-r from-violet-400 to-fuchsia-400"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        </div>

        {/* Message — typewritered. Click to fast-forward. */}
        <div onClick={done ? undefined : fastForward}
              data-testid="onboarding-message"
              className={`text-[13.5px] text-zinc-100 leading-relaxed mb-4
                         ${done ? '' : 'cursor-pointer select-none'}`}>
          {displayed}
          {!done && (
            <span className="inline-block w-[2px] h-[14px] bg-violet-300 ml-1 align-middle animate-pulse" />
          )}
        </div>

        {/* CTA row */}
        <div className="flex items-center gap-2 text-[11px]">
          {state.expects_user_reply ? (
            <div data-testid="onboarding-await-input"
                  className="flex-1 text-zinc-400 italic flex items-center gap-1.5">
              <ChevronRight size={11} className="text-violet-300 animate-pulse" />
              Type your answer in the composer below…
            </div>
          ) : (
            <button onClick={onAdvance}
                    disabled={!done}
                    data-testid="onboarding-next-btn"
                    className="ml-auto flex items-center gap-1.5 px-3.5 py-2 rounded-lg
                              bg-violet-500 hover:bg-violet-400 text-white font-semibold
                              shadow-lg shadow-violet-500/30 transition
                              disabled:opacity-30 disabled:cursor-not-allowed">
              {state.step === 'autonomy_explain' ? 'Finish' : 'Continue'} <ArrowRight size={12} />
            </button>
          )}
        </div>
      </motion.div>
    </AnimatePresence>,
  );
}


/* Render the card straight into <body> via a portal so it sits above
   the dashboard z-index stack. We avoid importing react-dom up top to
   keep tree-shake friendly. */
function createCardPortal(children) {
  if (typeof document === 'undefined') return null;
  // eslint-disable-next-line global-require
  const { createPortal } = require('react-dom');
  return createPortal(children, document.body);
}
