import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Plus, MessageCircle, Loader2, Search,
} from 'lucide-react';
import { API } from '../../../context/AuthContext';

/* ConversationHistory — ChatGPT-style left panel of past chats.

   Sits between the main app sidebar and the chat thread. Shows:
     · "+ New conversation" button
     · Grouped list of past conversations (Today / Yesterday / Older)
     · Active conversation highlighted */

const fmtDateBucket = (iso) => {
  if (!iso) return 'Older';
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return 'Today';
    const yest = new Date(now); yest.setDate(yest.getDate() - 1);
    if (d.toDateString() === yest.toDateString()) return 'Yesterday';
    const diffDays = (now - d) / (1000 * 60 * 60 * 24);
    if (diffDays < 7)  return 'This week';
    if (diffDays < 30) return 'This month';
    return 'Older';
  } catch { return 'Older'; }
};

const BUCKET_ORDER = ['Today', 'Yesterday', 'This week', 'This month', 'Older'];

export const ConversationHistory = ({ activeId, onSelect, onNew, refreshKey }) => {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(true);
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/cortex/console/conversations?limit=50`,
                                  { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_e) { setItems([]); }
    finally { setBusy(false); }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  const handleNew = async () => {
    try {
      const r = await axios.post(`${API}/cortex/console/conversations/new`, {},
                                   { withCredentials: true });
      const cid = r.data?.conversation_id;
      if (cid) {
        onNew?.(cid);
        // Don't reload until first message lands — empty threads don't show up.
      }
    } catch (_e) { /* */ }
  };

  // Group items by date bucket.
  const filtered = filter
    ? items.filter((c) => (c.title || '').toLowerCase().includes(filter.toLowerCase()))
    : items;
  const grouped = {};
  for (const it of filtered) {
    const b = fmtDateBucket(it.updated_at);
    (grouped[b] ||= []).push(it);
  }

  return (
    <aside data-testid="cortex-conversation-history"
           className="flex flex-col h-full min-h-0 w-[240px] shrink-0 border-r border-white/5 bg-white/[0.01] backdrop-blur-md">
      {/* Header — New + search */}
      <div className="p-3 border-b border-white/5 space-y-2">
        <button onClick={handleNew} data-testid="conversation-new-btn"
                className="w-full text-[12px] font-semibold px-3 py-2 rounded-lg bg-violet-500 hover:bg-violet-400 text-white transition flex items-center gap-1.5 shadow-lg shadow-violet-500/20">
          <Plus size={13} /> New conversation
        </button>
        <div className="relative">
          <Search size={11} className="absolute left-2 top-2 text-zinc-600" />
          <input value={filter} onChange={(e) => setFilter(e.target.value)}
                  placeholder="Search history"
                  data-testid="conversation-history-search"
                  className="w-full text-[11.5px] bg-white/[0.02] border border-white/5 rounded-md pl-7 pr-2 py-1.5 text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-violet-500/40" />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2 px-1">
        {busy && (
          <div className="px-3 py-4 flex items-center gap-2 text-[11px] text-zinc-500">
            <Loader2 size={11} className="animate-spin" /> Loading…
          </div>
        )}
        {!busy && filtered.length === 0 && (
          <div className="px-3 py-4 text-[11px] text-zinc-500 italic">
            {filter ? 'No matches.' : 'No conversations yet — start one!'}
          </div>
        )}

        {!busy && BUCKET_ORDER.filter((b) => grouped[b]).map((bucket) => (
          <div key={bucket} className="mb-3">
            <div className="px-2 text-[9px] uppercase tracking-widest text-zinc-600 font-bold mb-1">
              {bucket}
            </div>
            <div className="space-y-0.5">
              {grouped[bucket].map((c) => {
                const active = c.id === activeId;
                return (
                  <button key={c.id} onClick={() => onSelect?.(c)}
                          data-testid={`conversation-item-${c.id}`}
                          className={`w-full text-left px-2.5 py-2 rounded-md transition group ${
                            active
                              ? 'bg-violet-500/15 border border-violet-500/30'
                              : 'hover:bg-white/[0.04] border border-transparent'
                          }`}>
                    <div className="flex items-start gap-1.5">
                      <MessageCircle size={10} className={
                        active ? 'text-violet-300 mt-0.5 shrink-0' : 'text-zinc-600 mt-0.5 shrink-0'
                      } />
                      <div className="flex-1 min-w-0">
                        <div className={`text-[12px] leading-tight truncate ${
                          active ? 'text-white font-medium' : 'text-zinc-300'
                        }`}>
                          {c.title}
                        </div>
                        <div className="text-[10px] text-zinc-500 mt-0.5 flex items-center gap-1">
                          <span>{c.message_count} msg</span>
                          {c.last_message && (
                            <span className="text-zinc-600 truncate">· {c.last_message.slice(0, 40)}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
};

export default ConversationHistory;
