import React, { useEffect, useRef } from 'react';
import { ArrowUp, Loader2, Command } from 'lucide-react';

/* Composer — auto-resizing textarea + send button.
   Pulled from CommandCenter.jsx. */

export const Composer = ({ value, onChange, onSubmit, sending }) => {
  const ref = useRef(null);
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 144) + 'px';
  }, [value]);

  return (
    <div data-testid="cortex-composer"
         className="rounded-2xl border border-white/10 bg-white/[0.03] focus-within:border-violet-500/40 backdrop-blur-md transition">
      <div className="flex items-end gap-2 p-2">
        <textarea ref={ref} rows={1}
          data-testid="cortex-composer-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Message Cortex — try: 'recruit 50 woodworking sellers' or 'what should I focus on this week?'"
          className="flex-1 resize-none bg-transparent px-2 py-2 text-[13.5px] text-white placeholder:text-zinc-500 focus:outline-none leading-relaxed"
          disabled={sending} />
        <button onClick={onSubmit} disabled={sending || !value.trim()}
                data-testid="cortex-composer-send"
                className="shrink-0 w-9 h-9 rounded-lg bg-violet-500 hover:bg-violet-400 disabled:bg-white/5 disabled:cursor-not-allowed text-white flex items-center justify-center transition shadow-lg shadow-violet-500/20 disabled:shadow-none">
          {sending ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}
        </button>
      </div>
      <div className="px-3 pb-2 pt-0.5 text-[10px] text-zinc-500 flex items-center gap-2">
        <Command size={10} /> Press Enter to send, Shift+Enter for newline
      </div>
    </div>
  );
};

export default Composer;
