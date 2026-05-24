import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { API } from '../../context/AuthContext';
import DashboardLayout from '../../components/DashboardLayout';
import {
  Loader2, Calendar as CalIcon, ChevronLeft, ChevronRight,
  Instagram, Twitter, Facebook, Linkedin, Youtube, Plus, X as XIcon,
  Sparkles, GripVertical, Zap, MousePointerSquareDashed, Trash2, ChevronsLeft, ChevronsRight,
} from 'lucide-react';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { useToast } from '../../hooks/use-toast';

const PLATFORM_ROWS = [
  { id: 'linkedin', label: 'LinkedIn', icon: Linkedin, color: 'text-sky-700 bg-sky-50' },
  { id: 'x', label: 'X', icon: Twitter, color: 'text-neutral-900 bg-neutral-100' },
  { id: 'instagram', label: 'Instagram', icon: Instagram, color: 'text-pink-600 bg-pink-50' },
  { id: 'pinterest', label: 'Pinterest', icon: () => <span className="text-[11px] font-bold">P</span>, color: 'text-red-600 bg-red-50' },
  { id: 'tiktok', label: 'TikTok', icon: () => <span className="text-[11px] font-bold">T</span>, color: 'text-neutral-900 bg-neutral-100' },
  { id: 'facebook', label: 'Facebook', icon: Facebook, color: 'text-blue-700 bg-blue-50' },
  { id: 'youtube', label: 'YouTube', icon: Youtube, color: 'text-red-700 bg-red-50' },
  { id: 'threads', label: 'Threads', icon: () => <span className="text-[11px] font-bold">@</span>, color: 'text-neutral-900 bg-neutral-100' },
];

const MarketingCalendar = () => {
  const { toast } = useToast();
  const [view, setView] = useState('week');
  const [cursor, setCursor] = useState(new Date());
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(null);
  const [optimalSlots, setOptimalSlots] = useState({}); // {platform: [{datetime, hour}]}
  const [showOptimal, setShowOptimal] = useState(false);
  const [loadingOptimal, setLoadingOptimal] = useState(false);
  const [rationale, setRationale] = useState('');
  const [niche, setNiche] = useState('');
  const [dropTarget, setDropTarget] = useState(null);
  const [dragging, setDragging] = useState(null);

  // Lasso / multi-select state
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [lasso, setLasso] = useState(null); // {x0,y0,x1,y1} in grid-local coords
  const gridRef = React.useRef(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  const range = useMemo(() => {
    const start = new Date(cursor);
    if (view === 'week') {
      start.setDate(start.getDate() - start.getDay());
      start.setHours(0, 0, 0, 0);
      const end = new Date(start);
      end.setDate(end.getDate() + 7);
      return { start, end, days: 7 };
    }
    start.setDate(1);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setMonth(end.getMonth() + 1);
    return { start, end, days: Math.round((end - start) / (1000 * 60 * 60 * 24)) };
  }, [cursor, view]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/posts/scheduled?start=${range.start.toISOString()}&end=${range.end.toISOString()}`,
        { withCredentials: true }
      );
      setPosts(r.data);
    } catch (e) {}
    setLoading(false);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [cursor, view]);

  const fetchOptimal = async () => {
    setLoadingOptimal(true);
    try {
      const r = await axios.post(
        `${API}/ai/optimal-times`,
        { platforms: PLATFORM_ROWS.map((p) => p.id), niche: niche || undefined },
        { withCredentials: true }
      );
      setOptimalSlots(r.data.slots || {});
      setRationale(r.data.rationale || '');
      setShowOptimal(true);
    } catch (e) {
      toast({ title: 'Could not load AI times' });
    } finally {
      setLoadingOptimal(false);
    }
  };

  const days = useMemo(() => {
    const arr = [];
    for (let i = 0; i < range.days; i++) {
      const d = new Date(range.start);
      d.setDate(d.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [range]);

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const cellKey = (platform, date) => `${platform}-${date.toISOString().slice(0, 10)}`;
  const postsByCell = useMemo(() => {
    const map = {};
    posts.forEach((p) => {
      const d = new Date(p.scheduled_at);
      const dKey = d.toISOString().slice(0, 10);
      p.platforms.forEach((pl) => {
        const k = `${pl}-${dKey}`;
        if (!map[k]) map[k] = [];
        map[k].push(p);
      });
    });
    return map;
  }, [posts]);

  // optimal slots indexed by platform-yyyy-mm-dd
  const optimalByCell = useMemo(() => {
    const map = {};
    Object.entries(optimalSlots).forEach(([platform, slots]) => {
      slots.forEach((s) => {
        const d = new Date(s.datetime);
        const k = `${platform}-${d.toISOString().slice(0, 10)}`;
        if (!map[k]) map[k] = [];
        map[k].push({ hour: s.hour, score: s.score, datetime: s.datetime });
      });
    });
    return map;
  }, [optimalSlots]);

  const navigate = (dir) => {
    const d = new Date(cursor);
    if (view === 'week') d.setDate(d.getDate() + dir * 7);
    else d.setMonth(d.getMonth() + dir);
    setCursor(d);
  };

  const cancelPost = async (id) => {
    try {
      await axios.delete(`${API}/posts/scheduled/${id}`, { withCredentials: true });
      toast({ title: 'Scheduled post cancelled' });
      load();
    } catch (e) {}
  };

  // --- Lasso multi-select handlers (active only in selectMode) ---
  const toggleSelectMode = () => {
    setSelectMode((m) => !m);
    setSelectedIds(new Set());
    setLasso(null);
  };

  const togglePostSelection = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onGridMouseDown = (e) => {
    if (!selectMode) return;
    // ignore if click started on a post chip
    if (e.target.closest('[data-post-chip]')) return;
    const rect = gridRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + gridRef.current.scrollLeft;
    const y = e.clientY - rect.top + gridRef.current.scrollTop;
    setLasso({ x0: x, y0: y, x1: x, y1: y });
    if (!e.shiftKey) setSelectedIds(new Set());
  };

  const onGridMouseMove = (e) => {
    if (!selectMode || !lasso) return;
    const rect = gridRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left + gridRef.current.scrollLeft;
    const y = e.clientY - rect.top + gridRef.current.scrollTop;
    const newLasso = { ...lasso, x1: x, y1: y };
    setLasso(newLasso);

    // compute selection
    const minX = Math.min(newLasso.x0, x);
    const maxX = Math.max(newLasso.x0, x);
    const minY = Math.min(newLasso.y0, y);
    const maxY = Math.max(newLasso.y0, y);
    const gridRect = gridRef.current.getBoundingClientRect();
    const chips = gridRef.current.querySelectorAll('[data-post-chip]');
    const hits = new Set(selectedIds);
    chips.forEach((el) => {
      const r = el.getBoundingClientRect();
      const elX0 = r.left - gridRect.left + gridRef.current.scrollLeft;
      const elY0 = r.top - gridRect.top + gridRef.current.scrollTop;
      const elX1 = elX0 + r.width;
      const elY1 = elY0 + r.height;
      const intersects = elX0 < maxX && elX1 > minX && elY0 < maxY && elY1 > minY;
      const id = el.getAttribute('data-post-id');
      if (intersects) hits.add(id);
    });
    setSelectedIds(hits);
  };

  const onGridMouseUp = () => {
    if (!selectMode) return;
    setLasso(null);
  };

  const shiftSelected = async (deltaDays) => {
    if (selectedIds.size === 0) return;
    setBulkBusy(true);
    const ids = Array.from(selectedIds);
    const updates = ids.map((id) => {
      const p = posts.find((x) => x.id === id);
      if (!p) return null;
      const newAt = new Date(p.scheduled_at);
      newAt.setDate(newAt.getDate() + deltaDays);
      if (newAt < today) return null;
      return axios.patch(
        `${API}/posts/scheduled/${id}`,
        { scheduled_at: newAt.toISOString() },
        { withCredentials: true }
      ).catch(() => null);
    }).filter(Boolean);
    const results = await Promise.all(updates);
    const ok = results.filter((r) => r && r.status === 200).length;
    toast({ title: `Shifted ${ok} post${ok === 1 ? '' : 's'} by ${deltaDays > 0 ? '+' : ''}${deltaDays} day${Math.abs(deltaDays) === 1 ? '' : 's'}` });
    setSelectedIds(new Set());
    setBulkBusy(false);
    load();
  };

  const cancelSelected = async () => {
    if (selectedIds.size === 0) return;
    setBulkBusy(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.all(
      ids.map((id) =>
        axios.delete(`${API}/posts/scheduled/${id}`, { withCredentials: true }).catch(() => null)
      )
    );
    const ok = results.filter((r) => r && r.status === 200).length;
    toast({ title: `Cancelled ${ok} post${ok === 1 ? '' : 's'}` });
    setSelectedIds(new Set());
    setBulkBusy(false);
    load();
  };

  const onDragStart = (post, fromPlatform) => (e) => {
    setDragging({ post, fromPlatform });
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', post.id);
  };

  const onDragOver = (platform, date) => (e) => {
    if (date < today) return;
    e.preventDefault();
    setDropTarget(`${platform}-${date.toISOString().slice(0, 10)}`);
  };

  const onDragLeave = () => setDropTarget(null);

  const onDrop = (platform, date) => async (e) => {
    e.preventDefault();
    setDropTarget(null);
    if (!dragging) return;
    const { post, fromPlatform } = dragging;
    setDragging(null);
    if (date < today) {
      toast({ title: "Can't reschedule into the past" });
      return;
    }

    const newAt = new Date(post.scheduled_at);
    newAt.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());

    // swap platforms: replace fromPlatform with platform; keep any others intact
    const newPlatforms = post.platforms.map((p) => (p === fromPlatform ? platform : p));

    try {
      await axios.patch(
        `${API}/posts/scheduled/${post.id}`,
        { scheduled_at: newAt.toISOString(), platforms: newPlatforms },
        { withCredentials: true }
      );
      toast({ title: 'Rescheduled', description: `Moved to ${platform} on ${date.toLocaleDateString()}` });
      load();
    } catch (e) {
      toast({ title: 'Could not move post' });
    }
  };

  return (
    <DashboardLayout title="Marketing Calendar" subtitle="Drag posts to reschedule, or let AI suggest the best slots.">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(-1)} className="w-9 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 flex items-center justify-center"><ChevronLeft size={16} /></button>
          <button onClick={() => setCursor(new Date())} className="px-4 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 text-[13px] font-medium inline-flex items-center gap-1.5">
            <CalIcon size={13} /> Today
          </button>
          <button onClick={() => navigate(1)} className="w-9 h-9 rounded-lg bg-white border border-neutral-200 hover:bg-neutral-50 flex items-center justify-center"><ChevronRight size={16} /></button>
          <div className="ml-3 text-[15px] font-semibold">
            {view === 'week'
              ? `${range.start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${new Date(range.end - 1).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`
              : range.start.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
            }
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="Your niche (optional, helps AI)" className="h-9 w-56 rounded-lg border-neutral-300 text-[13px]" />
          <button
            onClick={toggleSelectMode}
            data-testid="calendar-select-mode-btn"
            className={`inline-flex items-center gap-1.5 px-3 h-9 rounded-lg text-[13px] font-medium border transition-colors ${
              selectMode ? 'bg-amber-500 text-white border-amber-500' : 'bg-white text-amber-700 border-amber-200 hover:bg-amber-50'
            }`}
            title="Lasso-select multiple posts for bulk actions"
          >
            <MousePointerSquareDashed size={13} />
            {selectMode ? 'Done selecting' : 'Bulk select'}
          </button>
          <button
            onClick={showOptimal ? () => setShowOptimal(false) : fetchOptimal}
            disabled={loadingOptimal}
            className={`inline-flex items-center gap-1.5 px-4 h-9 rounded-lg text-[13px] font-medium border transition-colors ${
              showOptimal ? 'bg-violet-600 text-white border-violet-600' : 'bg-white text-violet-700 border-violet-200 hover:bg-violet-50'
            }`}
          >
            {loadingOptimal ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            {showOptimal ? 'Hide AI times' : 'AI optimal times'}
          </button>
          <div className="inline-flex bg-white border border-neutral-200 rounded-lg p-1">
            <button onClick={() => setView('month')} className={`px-3 h-7 rounded-md text-[13px] font-medium transition-colors ${view === 'month' ? 'bg-neutral-900 text-white' : 'text-neutral-600 hover:bg-neutral-50'}`}>Month</button>
            <button onClick={() => setView('week')} className={`px-3 h-7 rounded-md text-[13px] font-medium transition-colors ${view === 'week' ? 'bg-[#1B7BFF] text-white' : 'text-neutral-600 hover:bg-neutral-50'}`}>Week</button>
          </div>
        </div>
      </div>

      {showOptimal && rationale && (
        <div className="mb-4 p-3 rounded-2xl bg-violet-50 border border-violet-100 text-[13px] text-violet-900 flex items-start gap-2">
          <Zap size={14} className="text-violet-600 mt-0.5 shrink-0" />
          <p className="leading-relaxed">{rationale}</p>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12"><Loader2 className="animate-spin text-[#1B7BFF] mx-auto" /></div>
      ) : (
        <div className="bg-white rounded-3xl border border-neutral-200/70 overflow-x-auto relative" ref={gridRef} onMouseDown={onGridMouseDown} onMouseMove={onGridMouseMove} onMouseUp={onGridMouseUp} onMouseLeave={onGridMouseUp} style={{ userSelect: selectMode ? 'none' : 'auto', cursor: selectMode ? 'crosshair' : 'default' }}>
          {lasso && (
            <div
              data-testid="calendar-lasso-rect"
              className="absolute bg-amber-200/30 border-2 border-dashed border-amber-500 pointer-events-none z-10 rounded"
              style={{
                left: Math.min(lasso.x0, lasso.x1),
                top: Math.min(lasso.y0, lasso.y1),
                width: Math.abs(lasso.x1 - lasso.x0),
                height: Math.abs(lasso.y1 - lasso.y0),
              }}
            />
          )}
          <div className="min-w-[900px]">
            {/* Header row */}
            <div className="grid border-b border-neutral-200/70" style={{ gridTemplateColumns: `120px repeat(${days.length}, minmax(0, 1fr))` }}>
              <div className="p-3 text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">Channel</div>
              {days.map((d) => {
                const isToday = d.getTime() === today.getTime();
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <div key={d.toISOString()} className={`p-3 text-center ${isToday ? 'bg-emerald-50/50' : isWeekend ? 'bg-rose-50/20' : ''}`}>
                    <div className={`text-2xl font-medium tracking-tight ${isToday ? 'text-emerald-700' : isWeekend && d.getDay() === 0 ? 'text-rose-500' : 'text-neutral-900'}`}>{d.getDate()}</div>
                    <div className={`text-[10.5px] uppercase tracking-wider mt-0.5 ${isToday ? 'text-emerald-700 font-semibold' : 'text-neutral-500'}`}>{d.toLocaleDateString(undefined, { weekday: 'short' })}</div>
                  </div>
                );
              })}
            </div>

            {/* Platform rows */}
            {PLATFORM_ROWS.map((p) => {
              const PIcon = p.icon;
              return (
                <div key={p.id} className="grid border-b border-neutral-100 last:border-0" style={{ gridTemplateColumns: `120px repeat(${days.length}, minmax(0, 1fr))` }}>
                  <div className="p-3 flex items-center gap-2 border-r border-neutral-100">
                    <div className={`w-7 h-7 rounded-lg ${p.color} flex items-center justify-center`}>
                      <PIcon size={13} />
                    </div>
                    <span className="text-[13px] font-medium">{p.label}</span>
                  </div>
                  {days.map((d) => {
                    const isToday = d.getTime() === today.getTime();
                    const cellPosts = postsByCell[cellKey(p.id, d)] || [];
                    const optimalsHere = showOptimal ? (optimalByCell[cellKey(p.id, d)] || []) : [];
                    const isPast = d < today;
                    const k = cellKey(p.id, d);
                    const isDropTarget = dropTarget === k;
                    return (
                      <div
                        key={d.toISOString()}
                        onDragOver={onDragOver(p.id, d)}
                        onDragLeave={onDragLeave}
                        onDrop={onDrop(p.id, d)}
                        className={`p-2 border-r border-neutral-100 last:border-0 min-h-[90px] group relative transition-colors ${
                          isToday ? 'bg-emerald-50/30' : isPast ? 'bg-neutral-50/40' : ''
                        } ${isDropTarget ? 'bg-blue-100/60 ring-2 ring-inset ring-[#1B7BFF]' : ''}`}
                      >
                        {/* AI optimal marker */}
                        {optimalsHere.length > 0 && cellPosts.length === 0 && (
                          <button
                            onClick={() => {
                              const slot = optimalsHere[0];
                              const d2 = new Date(d);
                              d2.setHours(slot.hour, 0, 0, 0);
                              setComposing({ platform: p.id, date: d2, suggestedTime: `${String(slot.hour).padStart(2, '0')}:00` });
                            }}
                            className="absolute top-1.5 right-1.5 inline-flex items-center gap-0.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-violet-100 text-violet-700 border border-violet-200 hover:bg-violet-200 transition-colors"
                            title={`AI suggests ${optimalsHere.map((s) => s.hour + ':00').join(', ')}`}
                          >
                            <Sparkles size={9} /> {optimalsHere[0].hour}h
                          </button>
                        )}

                        {cellPosts.map((post) => {
                          const isSelected = selectedIds.has(post.id);
                          return (
                          <div
                            key={post.id}
                            data-post-chip
                            data-post-id={post.id}
                            draggable={!selectMode}
                            onDragStart={selectMode ? undefined : onDragStart(post, p.id)}
                            onDragEnd={() => { setDragging(null); setDropTarget(null); }}
                            onClick={selectMode ? (e) => { e.stopPropagation(); togglePostSelection(post.id); } : undefined}
                            className={`mb-1 px-2 py-1.5 rounded-md border text-[11px] group/post transition-colors ${
                              isSelected
                                ? 'bg-amber-100 border-amber-400 ring-2 ring-amber-300 cursor-pointer'
                                : selectMode
                                  ? 'bg-[#1B7BFF]/10 border-[#1B7BFF]/20 hover:bg-amber-50 hover:border-amber-300 cursor-pointer'
                                  : 'bg-[#1B7BFF]/10 border-[#1B7BFF]/20 cursor-move hover:bg-[#1B7BFF]/15'
                            }`}
                            title={selectMode ? 'Click to (de)select' : 'Drag to reschedule'}
                          >
                            <div className="flex items-start gap-1">
                              {!selectMode && <GripVertical size={10} className="text-[#1B7BFF]/50 mt-0.5 shrink-0" />}
                              {selectMode && (
                                <input
                                  type="checkbox"
                                  readOnly
                                  checked={isSelected}
                                  className="mt-0.5 w-3 h-3 accent-amber-500 shrink-0 pointer-events-none"
                                />
                              )}
                              <span className={`line-clamp-2 flex-1 font-medium ${isSelected ? 'text-amber-900' : 'text-[#1B7BFF]'}`}>{post.content.slice(0, 40)}</span>
                              {!selectMode && (
                                <button onClick={(e) => { e.stopPropagation(); cancelPost(post.id); }} className="opacity-0 group-hover/post:opacity-100 text-rose-500"><XIcon size={10} /></button>
                              )}
                            </div>
                            <span className={`inline-block mt-0.5 text-[9px] uppercase tracking-wider font-semibold ${isSelected ? 'text-amber-700' : 'text-[#1B7BFF]/70'}`}>
                              {new Date(post.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          );
                        })}

                        {!isPast && cellPosts.length === 0 && (
                          <button
                            onClick={() => setComposing({ platform: p.id, date: d })}
                            className="opacity-0 group-hover:opacity-100 absolute inset-0 m-1 rounded-md border-2 border-dashed border-[#1B7BFF]/40 text-[#1B7BFF] flex items-center justify-center transition-opacity"
                            title="Schedule a post"
                          >
                            <Plus size={14} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-4 text-[12px] text-neutral-500">
        <div className="flex items-center gap-1.5"><GripVertical size={12} /> Drag a post to a new day or channel to reschedule</div>
        <div className="flex items-center gap-1.5"><MousePointerSquareDashed size={12} className="text-amber-600" /> Toggle "Bulk select" then lasso-drag to pick multiple posts for shift/cancel</div>
        {showOptimal && <div className="flex items-center gap-1.5"><Sparkles size={12} className="text-violet-600" /> Violet badges show AI-recommended posting hours</div>}
      </div>

      {composing && (
        <ScheduleModal
          platform={composing.platform}
          date={composing.date}
          suggestedTime={composing.suggestedTime}
          onClose={() => setComposing(null)}
          onCreated={() => { setComposing(null); load(); }}
        />
      )}

      {selectMode && selectedIds.size > 0 && (
        <div
          data-testid="calendar-bulk-action-bar"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 bg-neutral-900 text-white rounded-2xl shadow-2xl px-4 py-3 flex items-center gap-3 border border-neutral-700"
        >
          <span className="text-[13px] font-semibold pr-2 border-r border-neutral-700">
            {selectedIds.size} selected
          </span>
          <button
            onClick={() => shiftSelected(-7)}
            disabled={bulkBusy}
            data-testid="bulk-shift-minus-week"
            className="inline-flex items-center gap-1 text-[12px] font-medium px-2.5 h-8 rounded-lg hover:bg-neutral-800 disabled:opacity-50"
            title="Shift selected −7 days"
          >
            <ChevronsLeft size={12} /> −1w
          </button>
          <button
            onClick={() => shiftSelected(-1)}
            disabled={bulkBusy}
            data-testid="bulk-shift-minus-day"
            className="inline-flex items-center gap-1 text-[12px] font-medium px-2.5 h-8 rounded-lg hover:bg-neutral-800 disabled:opacity-50"
          >
            <ChevronLeft size={12} /> −1d
          </button>
          <button
            onClick={() => shiftSelected(1)}
            disabled={bulkBusy}
            data-testid="bulk-shift-plus-day"
            className="inline-flex items-center gap-1 text-[12px] font-medium px-2.5 h-8 rounded-lg hover:bg-neutral-800 disabled:opacity-50"
          >
            +1d <ChevronRight size={12} />
          </button>
          <button
            onClick={() => shiftSelected(7)}
            disabled={bulkBusy}
            data-testid="bulk-shift-plus-week"
            className="inline-flex items-center gap-1 text-[12px] font-medium px-2.5 h-8 rounded-lg hover:bg-neutral-800 disabled:opacity-50"
          >
            +1w <ChevronsRight size={12} />
          </button>
          <div className="w-px h-5 bg-neutral-700" />
          <button
            onClick={cancelSelected}
            disabled={bulkBusy}
            data-testid="bulk-cancel-btn"
            className="inline-flex items-center gap-1 text-[12px] font-medium px-2.5 h-8 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-50"
          >
            {bulkBusy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />} Cancel
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            disabled={bulkBusy}
            data-testid="bulk-clear-btn"
            className="text-[12px] font-medium px-2.5 h-8 rounded-lg hover:bg-neutral-800 text-neutral-400"
          >
            Clear
          </button>
        </div>
      )}
    </DashboardLayout>
  );
};

const ScheduleModal = ({ platform, date, suggestedTime, onClose, onCreated }) => {
  const { toast } = useToast();
  const [content, setContent] = useState('');
  const [time, setTime] = useState(suggestedTime || '10:00');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const [hh, mm] = time.split(':');
      const at = new Date(date);
      at.setHours(parseInt(hh, 10), parseInt(mm, 10), 0, 0);
      await axios.post(`${API}/channels/publish`, {
        content,
        platforms: [platform],
        scheduled_at: at.toISOString(),
      }, { withCredentials: true });
      toast({ title: 'Post scheduled', description: `${platform} • ${at.toLocaleString()}` });
      onCreated();
    } catch (e) {
      toast({ title: 'Failed to schedule' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-xl font-semibold tracking-tight mb-1">Schedule a post</h3>
        <p className="text-[13px] text-neutral-500 mb-4">For <span className="font-medium capitalize text-neutral-700">{platform}</span> on {date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
        <form onSubmit={submit} className="space-y-3">
          <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={5} placeholder="Write your post…" required className="rounded-xl border-neutral-300" />
          <div>
            <label className="text-[12px] font-medium text-neutral-600 mb-1.5 block">
              Time {suggestedTime && <span className="ml-1 text-violet-600 text-[11px]">✨ AI suggests {suggestedTime}</span>}
            </label>
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="h-11 rounded-xl border-neutral-300 w-40" required />
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100">Cancel</button>
            <button type="submit" disabled={busy} className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] disabled:opacity-60 text-white text-[13px] font-medium px-5 h-10 rounded-xl">
              {busy ? <Loader2 size={14} className="animate-spin" /> : 'Schedule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default MarketingCalendar;
