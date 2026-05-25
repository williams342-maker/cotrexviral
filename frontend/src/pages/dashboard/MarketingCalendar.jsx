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
  const [altMode, setAltMode] = useState(false); // tracks if Alt key is held during drag
  const [monthDayDetail, setMonthDayDetail] = useState(null); // {date, posts}
  const [recurrenceConfirm, setRecurrenceConfirm] = useState(null); // {post, intent: 'cancel'|'shift', ...}
  const [seriesPrompt, setSeriesPrompt] = useState(null); // After Shift+drag: ask whether to shift series

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
    // Month view: pad to full weeks so the grid is always 7×N (typically 7×5
    // or 7×6). Start of month, then back up to the previous Sunday.
    start.setDate(1);
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() - start.getDay()); // back up to Sunday
    const monthEnd = new Date(cursor);
    monthEnd.setMonth(monthEnd.getMonth() + 1, 0); // last day of current month
    const end = new Date(monthEnd);
    end.setDate(end.getDate() + (6 - end.getDay()) + 1); // forward to next Saturday +1
    end.setHours(0, 0, 0, 0);
    const days = Math.round((end - start) / (1000 * 60 * 60 * 24));
    return { start, end, days };
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

  // Month view groups posts by day (regardless of platform), so we can show
  // a single row-per-day with stacked platform dots.
  const postsByDay = useMemo(() => {
    const map = {};
    posts.forEach((p) => {
      const d = new Date(p.scheduled_at);
      const dKey = d.toISOString().slice(0, 10);
      if (!map[dKey]) map[dKey] = [];
      map[dKey].push(p);
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

  const cancelPost = async (id, scope = 'only') => {
    try {
      await axios.delete(`${API}/posts/scheduled/${id}?scope=${scope}`, { withCredentials: true });
      toast({ title: scope === 'only' ? 'Scheduled post cancelled' : scope === 'future' ? 'This + future occurrences cancelled' : 'Series cancelled' });
      load();
    } catch (e) {}
  };

  // Series-aware cancel: if the post belongs to a recurrence, open a confirm modal.
  const requestCancel = (post) => {
    if (post.recurrence_group_id) {
      setRecurrenceConfirm({ post, intent: 'cancel' });
    } else {
      cancelPost(post.id);
    }
  };

  const shiftSeries = async (groupId, anchorPostId, deltaDays) => {
    try {
      const r = await axios.patch(
        `${API}/posts/series/${groupId}`,
        { delta_days: deltaDays, anchor_post_id: anchorPostId },
        { withCredentials: true },
      );
      toast({
        title: `Series shifted by ${deltaDays > 0 ? '+' : ''}${deltaDays} day${Math.abs(deltaDays) === 1 ? '' : 's'}`,
        description: `${r.data.updated} post${r.data.updated === 1 ? '' : 's'} updated`,
      });
      load();
    } catch (e) {
      toast({ title: 'Could not shift series', description: e.response?.data?.detail });
    }
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
    // altKey at drag-start is when most browsers reliably expose it on dataTransfer
    e.dataTransfer.effectAllowed = e.altKey ? 'copy' : 'move';
    e.dataTransfer.setData('text/plain', post.id);
  };

  const onDragOver = (platform, date) => (e) => {
    if (date < today) return;
    e.preventDefault();
    setAltMode(e.altKey);
    e.dataTransfer.dropEffect = e.altKey ? 'copy' : 'move';
    setDropTarget(`${platform}-${date.toISOString().slice(0, 10)}`);
  };

  const onDragLeave = () => setDropTarget(null);

  const onDrop = (platform, date) => async (e) => {
    e.preventDefault();
    setDropTarget(null);
    const isDuplicate = e.altKey;
    const wantsSeriesShift = e.shiftKey && !selectMode;
    setAltMode(false);
    if (!dragging) return;
    const { post, fromPlatform } = dragging;
    setDragging(null);
    if (date < today) {
      toast({ title: "Can't reschedule into the past" });
      return;
    }

    // Shift+drag on a recurring post → prompt to shift the entire series by
    // the date delta (matching what the user dragged). The single-instance
    // move is the implicit "no" answer.
    if (wantsSeriesShift && post.recurrence_group_id) {
      const origDate = new Date(post.scheduled_at);
      origDate.setHours(0, 0, 0, 0);
      const dropDate = new Date(date);
      dropDate.setHours(0, 0, 0, 0);
      const delta = Math.round((dropDate - origDate) / (1000 * 60 * 60 * 24));
      if (delta !== 0) {
        setSeriesPrompt({ post, delta });
        return;
      }
    }

    const newAt = new Date(post.scheduled_at);
    newAt.setFullYear(date.getFullYear(), date.getMonth(), date.getDate());

    // swap platforms: replace fromPlatform with platform; keep any others intact
    const newPlatforms = post.platforms.map((p) => (p === fromPlatform ? platform : p));

    try {
      if (isDuplicate) {
        await axios.post(
          `${API}/channels/publish`,
          { content: post.content, platforms: newPlatforms, media_url: post.media_url, scheduled_at: newAt.toISOString() },
          { withCredentials: true },
        );
        toast({ title: 'Duplicated', description: `New copy on ${platform} · ${date.toLocaleDateString()}` });
      } else {
        await axios.patch(
          `${API}/posts/scheduled/${post.id}`,
          { scheduled_at: newAt.toISOString(), platforms: newPlatforms },
          { withCredentials: true },
        );
        toast({ title: 'Rescheduled', description: `Moved to ${platform} on ${date.toLocaleDateString()}` });
      }
      load();
    } catch (e) {
      toast({ title: isDuplicate ? 'Could not duplicate post' : 'Could not move post' });
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
            {view === 'week' ? (
              <>
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
                                <button onClick={(e) => { e.stopPropagation(); requestCancel(post); }} className="opacity-0 group-hover/post:opacity-100 text-rose-500"><XIcon size={10} /></button>
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
              </>
            ) : (
              <MonthGrid
                days={days}
                cursor={cursor}
                today={today}
                postsByDay={postsByDay}
                onDayClick={(d) => setMonthDayDetail({ date: d, posts: postsByDay[d.toISOString().slice(0, 10)] || [] })}
                dragging={dragging}
                onDragOver={(d) => (e) => { if (d < today) return; e.preventDefault(); setAltMode(e.altKey); e.dataTransfer.dropEffect = e.altKey ? 'copy' : 'move'; setDropTarget(`day-${d.toISOString().slice(0, 10)}`); }}
                onDragLeave={() => setDropTarget(null)}
                onDrop={(d) => async (e) => {
                  e.preventDefault();
                  setDropTarget(null);
                  const isDup = e.altKey;
                  if (!dragging) return;
                  const { post } = dragging;
                  setDragging(null);
                  if (d < today) { toast({ title: "Can't reschedule into the past" }); return; }
                  const newAt = new Date(post.scheduled_at);
                  newAt.setFullYear(d.getFullYear(), d.getMonth(), d.getDate());
                  try {
                    if (isDup) {
                      await axios.post(`${API}/channels/publish`,
                        { content: post.content, platforms: post.platforms, media_url: post.media_url, scheduled_at: newAt.toISOString() },
                        { withCredentials: true });
                      toast({ title: 'Duplicated', description: d.toLocaleDateString() });
                    } else {
                      await axios.patch(`${API}/posts/scheduled/${post.id}`,
                        { scheduled_at: newAt.toISOString() }, { withCredentials: true });
                      toast({ title: 'Rescheduled', description: d.toLocaleDateString() });
                    }
                    load();
                  } catch (err) {
                    toast({ title: isDup ? 'Could not duplicate' : 'Could not move' });
                  }
                }}
                onDragStart={(post) => (e) => {
                  setDragging({ post, fromPlatform: post.platforms[0] });
                  e.dataTransfer.effectAllowed = 'copyMove';
                  e.dataTransfer.setData('text/plain', post.id);
                }}
                onAddClick={(d) => setComposing({ platform: 'instagram', date: d })}
                dropTarget={dropTarget}
                cursorMonth={cursor.getMonth()}
              />
            )}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-4 text-[12px] text-neutral-500">
        <div className="flex items-center gap-1.5"><GripVertical size={12} /> Drag a post to a new day or channel to reschedule</div>
        <div className="flex items-center gap-1.5"><span className="font-mono text-[10px] px-1 bg-neutral-100 rounded">Alt</span>+drag to duplicate · <span className="font-mono text-[10px] px-1 bg-violet-100 text-violet-700 rounded">Shift</span>+drag a 🔁 weekly post to shift the series</div>
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
      {monthDayDetail && (
        <DayDetailDrawer
          date={monthDayDetail.date}
          posts={monthDayDetail.posts}
          onClose={() => setMonthDayDetail(null)}
          onCancel={(post) => { requestCancel(post); }}
        />
      )}

      {recurrenceConfirm && (
        <RecurrenceCancelModal
          post={recurrenceConfirm.post}
          onClose={() => setRecurrenceConfirm(null)}
          onConfirm={async (scope) => {
            await cancelPost(recurrenceConfirm.post.id, scope);
            setRecurrenceConfirm(null);
            setMonthDayDetail(null);
          }}
        />
      )}

      {seriesPrompt && (
        <SeriesShiftPromptModal
          post={seriesPrompt.post}
          delta={seriesPrompt.delta}
          onClose={() => setSeriesPrompt(null)}
          onMoveOne={async () => {
            const { post, delta } = seriesPrompt;
            const newAt = new Date(post.scheduled_at);
            newAt.setDate(newAt.getDate() + delta);
            try {
              await axios.patch(
                `${API}/posts/scheduled/${post.id}`,
                { scheduled_at: newAt.toISOString() },
                { withCredentials: true },
              );
              toast({ title: 'Moved this instance only' });
              load();
            } catch (e) {
              toast({ title: 'Could not move post' });
            }
            setSeriesPrompt(null);
          }}
          onShiftFuture={async () => {
            const { post, delta } = seriesPrompt;
            await shiftSeries(post.recurrence_group_id, post.id, delta);
            setSeriesPrompt(null);
          }}
          onShiftAll={async () => {
            const { post, delta } = seriesPrompt;
            await shiftSeries(post.recurrence_group_id, null, delta);
            setSeriesPrompt(null);
          }}
        />
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

// -----------------------------------------------------------------------------
// MonthGrid — 7×N day cells. Each cell shows date + up to 3 platform dots +
// "+N more" overflow. Click a day to open the side drawer with all posts.
// -----------------------------------------------------------------------------
const PLATFORM_DOT_COLOR = {
  instagram: 'bg-pink-500',
  tiktok: 'bg-neutral-900',
  x: 'bg-neutral-700',
  facebook: 'bg-blue-600',
  linkedin: 'bg-sky-700',
  youtube: 'bg-red-600',
  pinterest: 'bg-red-500',
  threads: 'bg-neutral-800',
  reddit: 'bg-orange-600',
};
const MAX_DOTS = 3;

const MonthGrid = ({
  days, today, postsByDay, onDayClick, dropTarget, cursorMonth,
  onDragOver, onDragLeave, onDrop, onDragStart,
}) => {
  return (
    <div data-testid="calendar-month-grid">
      <div className="grid grid-cols-7 border-b border-neutral-200/70">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((dow) => (
          <div key={dow} className="p-2.5 text-center text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">
            {dow}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((d) => {
          const dKey = d.toISOString().slice(0, 10);
          const dayPosts = postsByDay[dKey] || [];
          const isToday = d.getTime() === today.getTime();
          const isPast = d < today;
          const isCurrentMonth = d.getMonth() === cursorMonth;
          // Build a unique platform set in stable order so dots are consistent.
          const platformsSet = Array.from(new Set(dayPosts.flatMap((p) => p.platforms || [])));
          const shownPlatforms = platformsSet.slice(0, MAX_DOTS);
          const extraCount = Math.max(0, platformsSet.length - MAX_DOTS);
          const isDropTarget = dropTarget === `day-${dKey}`;
          return (
            <button
              key={dKey}
              type="button"
              data-testid={`month-cell-${dKey}`}
              onClick={() => onDayClick(d)}
              onDragOver={onDragOver(d)}
              onDragLeave={onDragLeave}
              onDrop={onDrop(d)}
              className={`min-h-[110px] p-2 border-r border-b border-neutral-100 last:border-r-0 text-left transition-colors relative group ${
                isCurrentMonth ? 'bg-white' : 'bg-neutral-50/50'
              } ${isToday ? 'ring-2 ring-inset ring-emerald-300' : ''} ${
                isDropTarget ? 'bg-blue-100/70 ring-2 ring-inset ring-[#1B7BFF]' : ''
              } hover:bg-violet-50/40`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className={`text-[13px] font-semibold ${
                  isToday ? 'text-emerald-700'
                    : !isCurrentMonth ? 'text-neutral-300'
                    : isPast ? 'text-neutral-400'
                    : 'text-neutral-800'
                }`}>
                  {d.getDate()}
                </span>
                {dayPosts.length > 0 && (
                  <span className="text-[10px] font-semibold text-neutral-500 bg-neutral-100 rounded-full px-1.5 py-0.5" data-testid={`month-cell-count-${dKey}`}>
                    {dayPosts.length}
                  </span>
                )}
              </div>
              {dayPosts.length > 0 && (
                <div className="space-y-1">
                  {dayPosts.slice(0, 2).map((post) => (
                    <div
                      key={post.id}
                      data-post-chip
                      data-post-id={post.id}
                      draggable
                      onDragStart={onDragStart(post)}
                      onClick={(e) => e.stopPropagation()}
                      className="px-1.5 py-1 rounded-md bg-[#1B7BFF]/10 border border-[#1B7BFF]/20 text-[10.5px] text-[#1B7BFF] font-medium truncate cursor-move hover:bg-[#1B7BFF]/15"
                      title={post.content}
                    >
                      {new Date(post.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {post.content.slice(0, 22)}
                    </div>
                  ))}
                  <div className="flex items-center gap-1 flex-wrap">
                    {shownPlatforms.map((pl) => (
                      <span
                        key={pl}
                        className={`w-2 h-2 rounded-full ${PLATFORM_DOT_COLOR[pl] || 'bg-neutral-500'}`}
                        title={pl}
                      />
                    ))}
                    {extraCount > 0 && (
                      <span className="text-[9.5px] font-semibold text-neutral-500">+{extraCount}</span>
                    )}
                    {dayPosts.length > 2 && (
                      <span className="text-[9.5px] text-neutral-500 ml-1">+{dayPosts.length - 2} more</span>
                    )}
                  </div>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

const DayDetailDrawer = ({ date, posts, onClose, onCancel }) => (
  <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose} data-testid="month-day-drawer">
    <div className="bg-black/40 flex-1" />
    <div
      className="w-[420px] max-w-full bg-white h-full overflow-y-auto p-6 shadow-2xl"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between mb-1">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-neutral-500 font-semibold">
            {date.toLocaleDateString(undefined, { weekday: 'long' })}
          </div>
          <h3 className="text-2xl font-semibold tracking-tight">
            {date.toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}
          </h3>
        </div>
        <button onClick={onClose} className="w-9 h-9 rounded-lg hover:bg-neutral-100 flex items-center justify-center" data-testid="month-day-drawer-close">
          <XIcon size={16} />
        </button>
      </div>
      <p className="text-[13px] text-neutral-500 mb-5">
        {posts.length === 0 ? 'Nothing scheduled.' : `${posts.length} scheduled post${posts.length === 1 ? '' : 's'}`}
      </p>
      <div className="space-y-3">
        {posts.map((post) => (
          <div key={post.id} className="border border-neutral-200 rounded-2xl p-3 bg-white">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[12px] font-semibold text-neutral-600">
                {new Date(post.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
              <button
                onClick={() => onCancel(post)}
                className="text-rose-500 hover:text-rose-700 text-[11px] font-medium inline-flex items-center gap-1"
                data-testid={`drawer-cancel-${post.id}`}
              >
                <Trash2 size={11} /> Cancel
              </button>
            </div>
            <p className="text-[13px] text-neutral-800 leading-snug line-clamp-3">{post.content}</p>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {post.platforms.map((pl) => (
                <span key={pl} className="inline-flex items-center gap-1 text-[10.5px] capitalize text-neutral-700 bg-neutral-100 rounded-full px-2 py-0.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${PLATFORM_DOT_COLOR[pl] || 'bg-neutral-500'}`} />
                  {pl}
                </span>
              ))}
              {post.recurrence_group_id && (
                <span className="inline-flex items-center gap-1 text-[10.5px] text-violet-700 bg-violet-50 border border-violet-100 rounded-full px-2 py-0.5">
                  🔁 weekly {post.recurrence_index != null ? `(${post.recurrence_index + 1}/${post.recurrence_total})` : ''}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  </div>
);

// -----------------------------------------------------------------------------
// RecurrenceCancelModal — asked when a user cancels a chip belonging to a
// recurrence series. Three scopes: only / future / all (+ "never mind").
// -----------------------------------------------------------------------------
const RecurrenceCancelModal = ({ post, onClose, onConfirm }) => {
  const total = post.recurrence_total || '?';
  const idx = post.recurrence_index != null ? post.recurrence_index + 1 : '?';
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="recurrence-cancel-modal">
      <div className="bg-white rounded-3xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-violet-600 mb-1">
          <span className="text-lg">🔁</span>
          <h3 className="text-lg font-semibold text-neutral-900">Cancel which posts?</h3>
        </div>
        <p className="text-[13px] text-neutral-500 mb-5 leading-relaxed">
          This is post <strong>{idx} of {total}</strong> in a weekly series. Pick what to cancel:
        </p>
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => onConfirm('only')}
            data-testid="recurrence-scope-only"
            className="w-full text-left p-3 rounded-2xl border border-neutral-200 hover:border-rose-300 hover:bg-rose-50/40 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-neutral-800 group-hover:text-rose-700">Just this one</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">Keeps every other instance in the series.</div>
          </button>
          <button
            type="button"
            onClick={() => onConfirm('future')}
            data-testid="recurrence-scope-future"
            className="w-full text-left p-3 rounded-2xl border border-neutral-200 hover:border-rose-300 hover:bg-rose-50/40 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-neutral-800 group-hover:text-rose-700">This + all upcoming</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">Keeps any past instances, cancels everything from this one onward.</div>
          </button>
          <button
            type="button"
            onClick={() => onConfirm('all')}
            data-testid="recurrence-scope-all"
            className="w-full text-left p-3 rounded-2xl border border-rose-200 bg-rose-50/40 hover:bg-rose-50 hover:border-rose-400 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-rose-700">The entire series</div>
            <div className="text-[12px] text-rose-600/80 mt-0.5">All {total} instances, including past unsent ones.</div>
          </button>
        </div>
        <div className="flex justify-end mt-4">
          <button
            type="button"
            onClick={onClose}
            data-testid="recurrence-cancel-dismiss"
            className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100"
          >
            Never mind
          </button>
        </div>
      </div>
    </div>
  );
};

// -----------------------------------------------------------------------------
// SeriesShiftPromptModal — opens after Shift+drag on a recurrence chip. Asks
// whether to move just the instance, the rest of the series, or the entire
// series by the date delta the user just dragged.
// -----------------------------------------------------------------------------
const SeriesShiftPromptModal = ({ post, delta, onClose, onMoveOne, onShiftFuture, onShiftAll }) => {
  const sign = delta > 0 ? '+' : '';
  const label = `${sign}${delta} day${Math.abs(delta) === 1 ? '' : 's'}`;
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="series-shift-modal">
      <div className="bg-white rounded-3xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-violet-600 mb-1">
          <span className="text-lg">🔁</span>
          <h3 className="text-lg font-semibold text-neutral-900">Shift the series?</h3>
        </div>
        <p className="text-[13px] text-neutral-500 mb-5 leading-relaxed">
          You moved a recurring post by <strong>{label}</strong>. Apply this shift to:
        </p>
        <div className="space-y-2">
          <button
            type="button"
            onClick={onMoveOne}
            data-testid="series-move-one"
            className="w-full text-left p-3 rounded-2xl border border-neutral-200 hover:border-[#1B7BFF]/40 hover:bg-blue-50/40 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-neutral-800 group-hover:text-[#1668e0]">Just this instance</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">Move only the post you dragged.</div>
          </button>
          <button
            type="button"
            onClick={onShiftFuture}
            data-testid="series-shift-future"
            className="w-full text-left p-3 rounded-2xl border border-violet-200 bg-violet-50/40 hover:bg-violet-50 hover:border-violet-400 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-violet-700">This + all upcoming</div>
            <div className="text-[12px] text-violet-600/80 mt-0.5">Shift this post and every still-scheduled future instance by {label}.</div>
          </button>
          <button
            type="button"
            onClick={onShiftAll}
            data-testid="series-shift-all"
            className="w-full text-left p-3 rounded-2xl border border-neutral-200 hover:border-violet-300 hover:bg-violet-50/40 transition-colors group"
          >
            <div className="text-[13.5px] font-semibold text-neutral-800 group-hover:text-violet-700">Entire series</div>
            <div className="text-[12px] text-neutral-500 mt-0.5">All {post.recurrence_total || ''} instances, past and future, shifted by {label}.</div>
          </button>
        </div>
        <div className="flex justify-end mt-4">
          <button
            type="button"
            onClick={onClose}
            data-testid="series-shift-dismiss"
            className="text-[13px] font-medium text-neutral-600 px-4 h-10 rounded-xl hover:bg-neutral-100"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
