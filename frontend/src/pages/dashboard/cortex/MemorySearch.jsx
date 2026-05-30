import React, { useState } from 'react';
import axios from 'axios';
import { Search, Loader2 } from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* MemorySearch — modal for semantic recall across all past
   conversations. Opens via Cmd/Ctrl+K. Extracted from CommandCenter.jsx. */

export const MemorySearch = ({ open, onClose }) => {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState([]);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/cortex/memory/recall`,
                                  { query: q, k: 8 },
                                  { withCredentials: true });
      setHits(r.data?.hits || []);
    } finally { setBusy(false); }
  };

  if (!open) return null;
  return (
    <div data-testid="cortex-memory-search-modal"
         className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center pt-24 px-4"
         onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
           className="w-full max-w-2xl rounded-2xl border border-white/10 bg-zinc-950 shadow-2xl">
        <div className="p-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Search size={14} className="text-violet-300" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && run()}
                    data-testid="memory-search-input"
                    placeholder="Search past conversations: e.g. 'Etsy sellers', 'Father's Day'"
                    className="flex-1 bg-transparent text-[14px] text-white placeholder:text-zinc-500 focus:outline-none" />
            {busy && <Loader2 size={13} className="animate-spin text-zinc-500" />}
            <button onClick={onClose} className="text-zinc-500 hover:text-white text-[11px]">
              Esc
            </button>
          </div>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-4 space-y-2">
          {hits.length === 0 && !busy && q && (
            <div className="text-[12px] text-zinc-500 italic">
              No relevant past messages found.
            </div>
          )}
          {hits.map((h, i) => (
            <div key={i} data-testid={`memory-hit-${i}`}
                  className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
              <div className="flex items-center gap-2 text-[10px] text-zinc-500 mb-1 uppercase tracking-wider">
                <span>{h.role}</span>
                <span>· {(h.created_at || '').slice(0, 10)}</span>
                <span className="ml-auto">score {Math.round(h.score * 100) / 100}</span>
              </div>
              <div className="text-[13px] text-zinc-200 leading-relaxed">{h.text}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default MemorySearch;
