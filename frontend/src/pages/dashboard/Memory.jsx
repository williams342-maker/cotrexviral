import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Brain, Trash2, RefreshCw, Search, Loader2, Sparkles, ShieldAlert,
  X as XIcon, Plus, Tag as TagIcon, Calendar as CalendarIcon,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';
import { useToast } from '../../hooks/use-toast';

/* /dashboard/memory — the "memory viewer" your agents pull context from.
   Three sections:
     1. Search bar — semantic search across all memories
     2. Stats strip — total count + breakdown by kind
     3. Memory list — Notion-style cards, deletable */

const KIND_TONES = {
  brand_profile: { label: 'Brand profile', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
  post:          { label: 'Post',          cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  hook:          { label: 'Hook',          cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  agent_summary: { label: 'Agent context', cls: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30' },
  manual:        { label: 'Manual',        cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
};

const Memory = () => {
  const { toast } = useToast();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const load = () =>
    axios.get(`${API}/memory/list?limit=200`, { withCredentials: true })
      .then((r) => setMemories(r.data.memories || []))
      .catch(() => setMemories([]));

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const runSearch = async (e) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const r = await axios.post(`${API}/memory/search`, { query: q, k: 10 }, { withCredentials: true });
      setSearchResults(r.data.results || []);
    } catch (err) {
      toast({ title: 'Search failed', description: err.response?.data?.detail || err.message });
    }
    setSearching(false);
  };

  const reindex = async () => {
    if (reindexing) return;
    setReindexing(true);
    try {
      const r = await axios.post(`${API}/memory/reindex`, {}, { withCredentials: true });
      toast({
        title: `Reindexed ${r.data.indexed} memory entr${r.data.indexed === 1 ? 'y' : 'ies'}`,
        description: 'Brand profile + recent posts are now searchable.',
      });
      await load();
    } catch (err) {
      toast({ title: 'Reindex failed', description: err.response?.data?.detail || err.message });
    }
    setReindexing(false);
  };

  const remove = async (id) => {
    if (!window.confirm('Forget this memory? Agents will no longer use it.')) return;
    try {
      await axios.delete(`${API}/memory/${id}`, { withCredentials: true });
      setMemories((ms) => ms.filter((m) => m.id !== id));
      setSearchResults((rs) => rs ? rs.filter((m) => m.id !== id) : rs);
    } catch (err) {
      toast({ title: 'Could not delete', description: err.response?.data?.detail || err.message });
    }
  };

  const counts = memories.reduce((acc, m) => {
    acc[m.kind] = (acc[m.kind] || 0) + 1;
    return acc;
  }, {});

  const display = searchResults !== null ? searchResults : memories;

  return (
    <DashboardLayout
      title="Memory"
      subtitle="What your AI team remembers about you. Every agent reads from this before they reply."
      headerExtra={
        <div className="flex gap-2">
          <button
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 border border-violet-500/30 px-3.5 h-9 rounded-lg"
            data-testid="memory-add-btn"
          >
            <Plus size={12} /> Add memory
          </button>
          <button
            onClick={reindex}
            disabled={reindexing}
            data-testid="memory-reindex-btn"
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium bg-white/[0.04] hover:bg-white/10 border border-white/10 text-zinc-200 px-3.5 h-9 rounded-lg disabled:opacity-40"
          >
            {reindexing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Reindex
          </button>
        </div>
      }
    >
      <div className="cv-dash-scope" data-testid="memory-page">

        {/* Search bar */}
        <form onSubmit={runSearch} className="cv-glass rounded-2xl p-3 flex items-center gap-2 mb-6">
          <Search size={16} className="text-zinc-500 ml-2 shrink-0" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!e.target.value) setSearchResults(null);
            }}
            placeholder="Ask your memory anything (semantic search)…"
            data-testid="memory-search-input"
            className="flex-1 bg-transparent outline-none text-[14px] text-zinc-100 placeholder-zinc-500 px-1"
          />
          {query && (
            <button
              type="button"
              onClick={() => { setQuery(''); setSearchResults(null); }}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-white/5"
              data-testid="memory-search-clear"
            >
              <XIcon size={14} />
            </button>
          )}
          <button
            type="submit"
            disabled={searching || !query.trim()}
            data-testid="memory-search-btn"
            className="inline-flex items-center gap-1.5 text-[12px] font-semibold bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white px-3.5 h-8 rounded-lg"
          >
            {searching ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            Search
          </button>
        </form>

        {/* Stats strip */}
        <div className="flex flex-wrap gap-2 mb-5" data-testid="memory-stats">
          <span className="inline-flex items-center gap-1.5 text-[12px] text-zinc-300 bg-white/[0.04] border border-white/10 rounded-full px-3 py-1">
            <Brain size={12} className="text-violet-400" /> <strong className="text-white">{memories.length}</strong> total
          </span>
          {Object.entries(counts).map(([kind, n]) => {
            const tone = KIND_TONES[kind] || { label: kind, cls: 'bg-white/[0.04] text-zinc-300 border-white/10' };
            return (
              <span key={kind} className={`inline-flex items-center gap-1.5 text-[11.5px] font-medium rounded-full px-3 py-1 border ${tone.cls}`}>
                <TagIcon size={10} /> {tone.label} · {n}
              </span>
            );
          })}
        </div>

        {/* List */}
        {loading ? (
          <div className="text-center py-12 text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
        ) : display.length === 0 ? (
          <div className="cv-glass rounded-2xl p-10 text-center">
            <Brain size={28} className="text-zinc-500 mx-auto mb-3" />
            <p className="text-white font-semibold">
              {searchResults !== null ? 'No matches in memory yet' : 'Memory is empty'}
            </p>
            <p className="text-[13px] text-zinc-400 mt-1.5 max-w-md mx-auto leading-relaxed">
              {searchResults !== null
                ? 'Try a different phrasing, or click Reindex to backfill from your brand profile and recent posts.'
                : 'Click Reindex to seed memory from your onboarding profile + recent posts. Every published post and agent conversation will then be remembered automatically.'}
            </p>
            <button
              onClick={reindex}
              disabled={reindexing}
              className="mt-5 inline-flex items-center gap-1.5 text-[12.5px] font-semibold bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white px-4 h-10 rounded-lg"
              data-testid="memory-empty-reindex"
            >
              {reindexing ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              Seed memory now
            </button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3" data-testid="memory-list">
            {display.map((m) => {
              const tone = KIND_TONES[m.kind] || { label: m.kind, cls: 'bg-white/[0.04] text-zinc-300 border-white/10' };
              return (
                <div key={m.id} className="cv-glass rounded-2xl p-4 hover:border-white/10 transition-colors" data-testid={`memory-card-${m.id}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className={`text-[10.5px] uppercase tracking-[0.18em] font-bold rounded-full px-2 py-0.5 border ${tone.cls}`}>
                      {tone.label}
                    </span>
                    <div className="flex items-center gap-2 text-[10.5px] text-zinc-500">
                      {m.score !== undefined && (
                        <span title="Relevance score" className="text-violet-300 font-semibold">
                          {(m.score * 100).toFixed(0)}%
                        </span>
                      )}
                      <CalendarIcon size={9} />
                      {new Date(m.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <p className="text-[13px] text-zinc-200 leading-relaxed" style={{ whiteSpace: 'pre-wrap' }}>
                    {m.text.length > 280 ? m.text.slice(0, 280) + '…' : m.text}
                  </p>
                  {m.meta && Object.keys(m.meta).length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {Object.entries(m.meta).slice(0, 4).map(([k, v]) => (
                        <span key={k} className="text-[10.5px] text-zinc-500 bg-white/[0.02] border border-white/5 rounded px-2 py-0.5 font-mono">
                          {k}: {String(v).slice(0, 32)}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between gap-2">
                    <span className="text-[10.5px] text-zinc-500 font-mono truncate">{m.id.slice(0, 8)}</span>
                    <button
                      onClick={() => remove(m.id)}
                      data-testid={`memory-delete-${m.id}`}
                      className="text-[11px] text-zinc-500 hover:text-rose-300 inline-flex items-center gap-1"
                    >
                      <Trash2 size={11} /> Forget
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Privacy note */}
        <div className="mt-6 cv-glass rounded-2xl p-4 flex items-start gap-3" data-testid="memory-privacy-note">
          <ShieldAlert size={16} className="text-zinc-500 shrink-0 mt-0.5" />
          <p className="text-[12.5px] text-zinc-400 leading-relaxed">
            Memory is per-account and never shared between users. Embeddings are computed locally on the CortexViral server (no third-party vector database). Click <strong className="text-white">Forget</strong> on any card to remove it instantly.
          </p>
        </div>
      </div>

      {showAdd && (
        <AddMemoryModal
          onClose={() => setShowAdd(false)}
          onSaved={async () => { setShowAdd(false); await load(); toast({ title: 'Memory saved' }); }}
        />
      )}
    </DashboardLayout>
  );
};

const AddMemoryModal = ({ onClose, onSaved }) => {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const { toast } = useToast();

  const save = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/memory/remember`, { text, kind: 'manual' }, { withCredentials: true });
      onSaved();
    } catch (err) {
      toast({ title: 'Could not save', description: err.response?.data?.detail || err.message });
    }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => !busy && onClose()} data-testid="memory-add-modal">
      <div className="bg-zinc-950 border border-violet-500/30 rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-1.5">
          <Brain size={18} className="text-violet-300" />
          <h3 className="text-lg font-semibold text-white">Add a memory</h3>
        </div>
        <p className="text-[13px] text-zinc-400 leading-relaxed mt-2">
          Anything you want every agent to remember — a winning hook, your founder story, audience pain points, a tone you love or hate. Just write it like a note.
        </p>
        <form onSubmit={save} className="mt-4">
          <textarea
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            placeholder="e.g. 'Our audience hates aggressive sales language — keep tone playful and educational.'"
            data-testid="memory-add-text"
            className="w-full rounded-xl bg-zinc-900 border border-zinc-800 focus:border-violet-500/50 text-zinc-100 px-3.5 py-3 text-[13.5px] outline-none resize-none"
          />
          <div className="flex justify-end gap-2 mt-4">
            <button type="button" onClick={onClose} disabled={busy} className="text-[13px] font-medium text-zinc-300 px-4 h-10 rounded-xl hover:bg-zinc-800/80">Cancel</button>
            <button type="submit" disabled={busy || !text.trim()} data-testid="memory-add-submit" className="cv-btn-primary inline-flex items-center gap-2 text-[13px] font-semibold px-5 h-10 rounded-xl disabled:opacity-40">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              {busy ? 'Saving…' : 'Save memory'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Memory;
