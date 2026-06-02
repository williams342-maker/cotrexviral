import React, { useEffect, useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import {
  FileText, Globe, Search, BarChart3, Users, Lightbulb,
  ChevronRight, ExternalLink, ArrowLeft, X, CheckSquare, Square, Trash2, AlertTriangle, RotateCw,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import { API } from '../../context/AuthContext';

/* Reports — lists every analysis report the user has on file (SEO scans,
 * site scans, competitor audits, content audits). Supports `?id=<report_id>`
 * deep-link from the analysis_complete chat card / Active Work rail /
 * Recommendation Bridge "View Findings" CTA.
 */

const TYPE_META = {
  seo_scan:         { icon: Globe,     label: 'SEO Scan',         tone: 'text-emerald-300 border-emerald-500/25 bg-emerald-500/[0.04]' },
  site_scan:        { icon: Search,    label: 'Site Scan',        tone: 'text-sky-300 border-sky-500/25 bg-sky-500/[0.04]' },
  competitor_audit: { icon: BarChart3, label: 'Competitor Audit', tone: 'text-amber-300 border-amber-500/25 bg-amber-500/[0.04]' },
  content_audit:    { icon: FileText,  label: 'Content Audit',    tone: 'text-fuchsia-300 border-fuchsia-500/25 bg-fuchsia-500/[0.04]' },
  seller_discovery: { icon: Users,     label: 'Seller Discovery', tone: 'text-violet-300 border-violet-500/25 bg-violet-500/[0.04]' },
};

// Heuristic: detect reports that failed to scan / produced no useful
// content. The data model has no explicit `status` field — failures are
// recognizable only via the LLM-written summary text or by an empty
// findings body.
function isFailedReport(r) {
  const body = r?.report || {};
  const summary = String(body.summary || '').trim().toLowerCase();
  if (!summary) {
    const empty = !(body.improvements?.length || body.issues?.length
                     || body.recommendations?.length || body.post_ideas?.length
                     || body.notable_items?.length);
    if (empty) return true;
  }
  if (/^(could not|scan could not|failed to|unable to|scan failed)/.test(summary)) return true;
  if (/lacked (an? )?(http|valid) protocol/.test(summary)) return true;
  return false;
}


export default function Reports() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get('id');

  // ---- bulk selection state ----
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [retryBusyIds, setRetryBusyIds] = useState(() => new Set());

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/reports`, { withCredentials: true });
        setReports(Array.isArray(r.data) ? r.data : []);
      } catch (_e) { setReports([]); }
      finally { setLoading(false); }
    })();
  }, []);

  const handleDelete = async (reportId) => {
    if (!window.confirm('Delete this report? This cannot be undone.')) return;
    try {
      await axios.delete(`${API}/reports/${reportId}`, { withCredentials: true });
      setReports((prev) => prev.filter((r) => r.id !== reportId));
      setSelectedIds((prev) => {
        if (!prev.has(reportId)) return prev;
        const next = new Set(prev); next.delete(reportId); return next;
      });
      // If the currently-open detail view was just deleted, fall back to list.
      if (activeId === reportId) setSearchParams({});
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Failed to delete report';
      window.alert(detail);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectMode(false);
  };

  const selectAllFailed = () => {
    const failedIds = reports.filter(isFailedReport).map((r) => r.id);
    if (failedIds.length === 0) {
      window.alert('No failed scans detected.');
      return;
    }
    setSelectMode(true);
    setSelectedIds(new Set(failedIds));
  };

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!window.confirm(`Delete ${ids.length} report${ids.length > 1 ? 's' : ''}? This cannot be undone.`)) return;
    setBulkBusy(true);
    try {
      const r = await axios.post(`${API}/reports/bulk-delete`,
                                  { ids }, { withCredentials: true });
      const deleted = r.data?.deleted ?? ids.length;
      setReports((prev) => prev.filter((x) => !selectedIds.has(x.id)));
      if (activeId && selectedIds.has(activeId)) setSearchParams({});
      clearSelection();
      // Lightweight toast via alert — keeps the page free of toast deps churn.
      if (deleted !== ids.length) {
        window.alert(`Deleted ${deleted} of ${ids.length} reports.`);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Bulk delete failed';
      window.alert(detail);
    } finally {
      setBulkBusy(false);
    }
  };

  const retryOne = async (reportId) => {
    setRetryBusyIds((prev) => { const n = new Set(prev); n.add(reportId); return n; });
    try {
      const r = await axios.post(`${API}/reports/${reportId}/retry`, {},
                                    { withCredentials: true });
      const newReport = r.data?.report;
      if (!newReport) throw new Error('Retry returned no new report.');
      // Swap the failed row out, drop the new one in newest-first.
      setReports((prev) => [newReport, ...prev.filter((x) => x.id !== reportId)]);
      if (activeId === reportId) setSearchParams({ id: newReport.id });
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Retry failed';
      window.alert(detail);
    } finally {
      setRetryBusyIds((prev) => { const n = new Set(prev); n.delete(reportId); return n; });
    }
  };

  const bulkRetryFailed = async () => {
    const failed = reports.filter(isFailedReport);
    if (failed.length === 0) {
      window.alert('No failed scans to retry.');
      return;
    }
    if (!window.confirm(
      `Retry ${failed.length} failed scan${failed.length > 1 ? 's' : ''}? ` +
      `Cortex will fix the URL where possible (e.g. add the missing https://) and re-run each scan.`)) return;
    setBulkBusy(true);
    setRetryBusyIds(new Set(failed.map((r) => r.id)));
    try {
      const r = await axios.post(`${API}/reports/bulk-retry`,
                                  { ids: failed.map((x) => x.id) },
                                  { withCredentials: true });
      // Refresh from server so we get fresh new rows + skip data in one shot.
      try {
        const r2 = await axios.get(`${API}/reports`, { withCredentials: true });
        setReports(Array.isArray(r2.data) ? r2.data : []);
      } catch (_e) { /* keep optimistic state */ }
      const { retried, skipped } = r.data || {};
      window.alert(
        `Retried ${retried || 0} of ${failed.length}.` +
        (skipped ? ` Skipped: ${skipped}.` : ''));
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Bulk retry failed';
      window.alert(detail);
    } finally {
      setBulkBusy(false);
      setRetryBusyIds(new Set());
    }
  };

  const active = useMemo(() =>
    reports.find((r) => r.id === activeId), [reports, activeId]);

  // ---- filter state (only applies on the list view) ----
  const [q, setQ] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [range, setRange] = useState('all');    // all | 7d | 30d | 90d
  const [sort, setSort] = useState('newest');   // newest | oldest

  const filtered = useMemo(() => {
    const now = Date.now();
    const rangeMs = { '7d': 7, '30d': 30, '90d': 90 }[range];
    const cutoff = rangeMs ? now - rangeMs * 24 * 60 * 60 * 1000 : null;
    const query = q.trim().toLowerCase();
    const out = reports.filter((r) => {
      if (typeFilter !== 'all' && (r.type || 'site_scan') !== typeFilter) return false;
      if (cutoff) {
        const t = new Date(r.created_at || 0).getTime();
        if (!t || t < cutoff) return false;
      }
      if (query) {
        const hay = `${r.url || ''} ${r.target || ''} ${r.report?.summary || ''}`.toLowerCase();
        if (!hay.includes(query)) return false;
      }
      return true;
    });
    out.sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return sort === 'newest' ? tb - ta : ta - tb;
    });
    return out;
  }, [reports, q, typeFilter, range, sort]);

  // Available type chips (only show types that exist in the data so we
  // don't render a Competitor chip for a user with zero competitor scans).
  const availableTypes = useMemo(() => {
    const set = new Set(reports.map((r) => r.type || 'site_scan'));
    return ['all', ...['seo_scan', 'site_scan', 'competitor_audit', 'content_audit', 'seller_discovery'].filter((t) => set.has(t))];
  }, [reports]);

  const failedCount = useMemo(() => reports.filter(isFailedReport).length, [reports]);

  return (
    <DashboardLayout>
      <div data-testid="reports-page" className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-white tracking-tight">Analysis Reports</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Every scan and audit Cortex has run, with structured findings + recommendations.
            </p>
          </div>
        </div>

        {loading ? (
          <div data-testid="reports-loading" className="text-zinc-500 text-sm">Loading reports…</div>
        ) : reports.length === 0 ? (
          <EmptyState />
        ) : active ? (
          <ReportDetail report={active} onBack={() => setSearchParams({})} />
        ) : (
          <>
            <FilterBar
              q={q} onQ={setQ}
              typeFilter={typeFilter} onType={setTypeFilter}
              availableTypes={availableTypes}
              range={range} onRange={setRange}
              sort={sort} onSort={setSort}
              total={reports.length} filtered={filtered.length}
              selectMode={selectMode}
              onToggleSelectMode={() => {
                setSelectMode((v) => !v);
                if (selectMode) setSelectedIds(new Set());
              }}
              failedCount={failedCount}
              onSelectFailed={selectAllFailed}
              onRetryAllFailed={bulkRetryFailed}
              bulkBusy={bulkBusy}
            />

            {selectedIds.size > 0 && (
              <SelectionBar
                count={selectedIds.size}
                total={filtered.length}
                busy={bulkBusy}
                onSelectAllVisible={() =>
                  setSelectedIds(new Set(filtered.map((r) => r.id)))}
                onClear={clearSelection}
                onDelete={bulkDelete}
              />
            )}

            {filtered.length === 0 ? (
              <FilteredEmpty onClear={() => { setQ(''); setTypeFilter('all'); setRange('all'); }} />
            ) : (
              <ReportList reports={filtered}
                            onOpen={(id) => setSearchParams({ id })}
                            onDelete={handleDelete}
                            onRetry={retryOne}
                            retryBusyIds={retryBusyIds}
                            selectMode={selectMode || selectedIds.size > 0}
                            selectedIds={selectedIds}
                            onToggleSelect={toggleSelect} />
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}


function FilterBar({ q, onQ, typeFilter, onType, availableTypes,
                       range, onRange, sort, onSort, total, filtered,
                       selectMode, onToggleSelectMode, failedCount, onSelectFailed,
                       onRetryAllFailed, bulkBusy }) {
  const hasFilter = q || typeFilter !== 'all' || range !== 'all' || sort !== 'newest';
  return (
    <div data-testid="reports-filter-bar"
          className="rounded-xl border border-white/5 bg-white/[0.02] p-3 space-y-3">
      {/* Row 1 — free-text search + result counter */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input value={q} onChange={(e) => onQ(e.target.value)}
                  placeholder="Search by URL or finding…"
                  data-testid="reports-search-input"
                  className="w-full text-[13px] text-zinc-100 bg-white/[0.03] border border-white/10 rounded-md pl-8 pr-8 py-1.5 focus:outline-none focus:border-violet-500/40" />
          {q && (
            <button onClick={() => onQ('')}
                    data-testid="reports-search-clear"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white transition">
              <X size={12} />
            </button>
          )}
        </div>
        <span className="text-[11px] text-zinc-500 tabular-nums shrink-0"
                data-testid="reports-result-count">
          {filtered === total ? `${total} reports` : `${filtered} of ${total}`}
        </span>
      </div>

      {/* Row 2 — type chips + date range + sort */}
      <div className="flex flex-wrap items-center gap-1.5">
        {availableTypes.map((t) => (
          <button key={t}
                  onClick={() => onType(t)}
                  data-testid={`reports-type-${t}`}
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-md border transition ${
                    typeFilter === t
                      ? 'bg-violet-500/20 text-violet-200 border-violet-500/40'
                      : 'bg-white/[0.02] text-zinc-400 border-white/10 hover:bg-white/[0.05]'}`}>
            {t === 'all' ? 'All types' : (TYPE_META[t]?.label || t)}
          </button>
        ))}
        <div className="w-px h-4 bg-white/10 mx-1" />
        {[
          ['all', 'Any time'],
          ['7d',  '7 days'],
          ['30d', '30 days'],
          ['90d', '90 days'],
        ].map(([k, label]) => (
          <button key={k}
                  onClick={() => onRange(k)}
                  data-testid={`reports-range-${k}`}
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-md border transition ${
                    range === k
                      ? 'bg-cyan-500/15 text-cyan-200 border-cyan-500/30'
                      : 'bg-white/[0.02] text-zinc-400 border-white/10 hover:bg-white/[0.05]'}`}>
            {label}
          </button>
        ))}
        <div className="flex-1 hidden md:block" />
        <select value={sort} onChange={(e) => onSort(e.target.value)}
                data-testid="reports-sort"
                className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/[0.02] border border-white/10 text-zinc-300 hover:bg-white/[0.05] focus:outline-none focus:border-violet-500/40">
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
        {hasFilter && (
          <button onClick={() => { onQ(''); onType('all'); onRange('all'); onSort('newest'); }}
                  data-testid="reports-clear-all"
                  className="text-[10.5px] font-semibold px-2 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-white/5 transition flex items-center gap-1">
            <X size={10} /> Clear
          </button>
        )}
        <div className="w-px h-4 bg-white/10 mx-1" />
        {failedCount > 0 && (
          <>
            <button onClick={onRetryAllFailed}
                    data-testid="reports-retry-failed"
                    disabled={bulkBusy}
                    title={`Re-run all ${failedCount} failed scan${failedCount > 1 ? 's' : ''} with repaired URLs`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 border border-emerald-500/30 transition flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed">
              <RotateCw size={10} className={bulkBusy ? 'animate-spin' : ''} /> Retry all failed ({failedCount})
            </button>
            <button onClick={onSelectFailed}
                    data-testid="reports-select-failed"
                    title={`Select all ${failedCount} failed scan${failedCount > 1 ? 's' : ''}`}
                    className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-200 border border-rose-500/25 transition flex items-center gap-1">
              <AlertTriangle size={10} /> Clear failed scans ({failedCount})
            </button>
          </>
        )}
        <button onClick={onToggleSelectMode}
                data-testid="reports-toggle-select-mode"
                title={selectMode ? 'Exit selection mode' : 'Select multiple reports'}
                className={`text-[10.5px] font-semibold px-2 py-1 rounded-md border transition flex items-center gap-1 ${
                  selectMode
                    ? 'bg-violet-500/20 text-violet-100 border-violet-500/40'
                    : 'bg-white/[0.02] text-zinc-300 border-white/10 hover:bg-white/[0.05]'}`}>
          {selectMode ? <CheckSquare size={10} /> : <Square size={10} />}
          {selectMode ? 'Selecting' : 'Select'}
        </button>
      </div>
    </div>
  );
}


function FilteredEmpty({ onClear }) {
  return (
    <div data-testid="reports-filtered-empty"
          className="rounded-xl border border-white/5 bg-white/[0.02] p-8 text-center">
      <Search size={22} className="text-zinc-500 mx-auto mb-2" />
      <div className="text-sm text-zinc-300 mb-3">No reports match your filters.</div>
      <button onClick={onClear}
              data-testid="reports-filtered-empty-clear"
              className="text-[12px] font-semibold px-3 py-1.5 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition">
        Clear filters
      </button>
    </div>
  );
}


function SelectionBar({ count, total, busy, onSelectAllVisible, onClear, onDelete }) {
  return (
    <div data-testid="reports-selection-bar"
         className="sticky top-2 z-20 rounded-xl border border-violet-500/30 bg-violet-500/[0.08] backdrop-blur-md px-3 py-2 flex items-center gap-3">
      <div className="flex items-center gap-1.5 text-[12px] text-violet-100 font-semibold">
        <CheckSquare size={13} />
        <span data-testid="reports-selection-count">
          {count} selected
        </span>
        <span className="text-violet-300/70 font-normal">· of {total} visible</span>
      </div>
      <button onClick={onSelectAllVisible}
              data-testid="reports-selection-select-all"
              disabled={busy || count >= total}
              className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-zinc-200 border border-white/10 transition disabled:opacity-40 disabled:cursor-not-allowed">
        Select all visible
      </button>
      <div className="flex-1" />
      <button onClick={onClear}
              data-testid="reports-selection-cancel"
              disabled={busy}
              className="text-[11px] font-semibold px-2 py-1 rounded-md text-zinc-300 hover:text-white hover:bg-white/[0.06] transition flex items-center gap-1">
        <X size={11} /> Cancel
      </button>
      <button onClick={onDelete}
              data-testid="reports-selection-delete"
              disabled={busy}
              className="text-[11.5px] font-semibold px-3 py-1.5 rounded-md bg-rose-500 hover:bg-rose-400 text-white transition flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-rose-500/20">
        <Trash2 size={12} />
        {busy ? 'Deleting…' : `Delete ${count}`}
      </button>
    </div>
  );
}


function EmptyState() {
  return (
    <div data-testid="reports-empty"
          className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
      <Lightbulb size={28} className="text-violet-300 mx-auto mb-3" />
      <div className="text-white font-semibold mb-1">No reports yet</div>
      <div className="text-sm text-zinc-400 mb-4">
        Ask Cortex to scan a URL — for example, <code className="text-violet-300">scan craftersmarket.org</code> —
        and the report lands here automatically.
      </div>
      <a href="/dashboard"
          data-testid="reports-empty-cta"
          className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition">
        Open Command Center <ChevronRight size={13} />
      </a>
    </div>
  );
}


function ReportList({ reports, onOpen, onDelete, onRetry, retryBusyIds,
                       selectMode, selectedIds, onToggleSelect }) {
  return (
    <div data-testid="reports-list" className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {reports.map((r) => {
        const meta = TYPE_META[r.type] || TYPE_META.site_scan;
        const Icon = meta.icon;
        const isSelected = selectedIds?.has(r.id);
        const failed = isFailedReport(r);
        // When selectMode is on, the whole card becomes a toggle target
        // instead of an "open" link — that matches the gmail-style multi-
        // select flow users expect.
        const handleCardClick = () => {
          if (selectMode) onToggleSelect?.(r.id);
          else            onOpen(r.id);
        };
        return (
          <div key={r.id}
               data-testid={`report-card-${r.id}`}
               data-failed={failed ? 'true' : 'false'}
               data-selected={isSelected ? 'true' : 'false'}
               className={`group relative rounded-xl border transition ${meta.tone} ${
                  isSelected
                    ? 'ring-2 ring-violet-400/60 ring-offset-2 ring-offset-zinc-950'
                    : 'hover:bg-white/[0.04]'}`}>
            <button onClick={handleCardClick}
                    data-testid={`report-card-open-${r.id}`}
                    className="w-full text-left p-4">
              <div className="flex items-center gap-2 mb-2">
                {selectMode && (
                  <span data-testid={`report-checkbox-${r.id}`}
                        className={`w-4 h-4 rounded shrink-0 flex items-center justify-center border transition ${
                          isSelected
                            ? 'bg-violet-500 border-violet-400 text-white'
                            : 'bg-white/[0.04] border-white/20 text-transparent'}`}>
                    {isSelected ? <CheckSquare size={10} /> : null}
                  </span>
                )}
                <span className="w-7 h-7 rounded-md bg-white/[0.05] border border-white/5 flex items-center justify-center">
                  <Icon size={12} />
                </span>
                <span className="text-[10px] uppercase tracking-widest font-bold">
                  {meta.label}
                </span>
                {failed && (
                  <span data-testid={`report-failed-badge-${r.id}`}
                        className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 tracking-wider">
                    Failed
                  </span>
                )}
                <span className="text-[10px] text-zinc-500 ml-auto pr-7">
                  {fmtDate(r.created_at)}
                </span>
              </div>
              <div className="text-sm text-white font-semibold truncate mb-1">
                {r.url || r.target || '—'}
              </div>
              <div className="text-[12px] text-zinc-400 line-clamp-2">
                {(r.report?.summary) || 'Open to view findings.'}
              </div>
              <div className="flex items-center gap-1.5 mt-2 text-[11px] text-zinc-400">
                {selectMode ? (isSelected ? 'Selected · click to deselect' : 'Click to select') : <>View report <ChevronRight size={11} /></>}
              </div>
            </button>

            {/* Close / delete button — top-right, surfaces on hover.
                Hidden in select mode to avoid two competing affordances. */}
            {!selectMode && (
              <>
                {failed && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onRetry?.(r.id); }}
                    data-testid={`report-retry-${r.id}`}
                    disabled={retryBusyIds?.has(r.id)}
                    title="Retry this scan with a repaired URL"
                    aria-label="Retry scan"
                    className="absolute top-2 right-9 px-1.5 h-6 rounded-md flex items-center gap-1 text-[10.5px] font-semibold
                               text-emerald-300 hover:text-emerald-200 hover:bg-emerald-500/15 border border-emerald-500/30
                               opacity-0 group-hover:opacity-100 focus:opacity-100 transition disabled:opacity-50 disabled:cursor-not-allowed">
                    <RotateCw size={11} className={retryBusyIds?.has(r.id) ? 'animate-spin' : ''} />
                    {retryBusyIds?.has(r.id) ? '…' : 'Retry'}
                  </button>
                )}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete?.(r.id); }}
                  data-testid={`report-delete-${r.id}`}
                  title="Delete report"
                  aria-label="Delete report"
                  className="absolute top-2 right-2 w-6 h-6 rounded-md flex items-center justify-center
                             text-zinc-500 hover:text-rose-300 hover:bg-rose-500/15 border border-transparent
                             hover:border-rose-500/30 opacity-0 group-hover:opacity-100 focus:opacity-100
                             transition">
                  <X size={12} />
                </button>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}


function ReportDetail({ report, onBack }) {
  const meta = TYPE_META[report.type] || TYPE_META.site_scan;
  const Icon = meta.icon;
  const body = report.report || {};

  return (
    <div data-testid="report-detail" className="space-y-4">
      <button onClick={onBack}
              data-testid="report-back-btn"
              className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition">
        <ArrowLeft size={14} /> Back to all reports
      </button>

      <div className={`rounded-2xl border p-5 ${meta.tone}`}>
        <div className="flex items-center gap-2 mb-3">
          <span className="w-9 h-9 rounded-lg bg-white/[0.05] border border-white/5 flex items-center justify-center">
            <Icon size={16} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest font-bold">
              {meta.label}
            </div>
            <div className="text-base font-semibold text-white truncate">
              {report.url || '—'}
            </div>
          </div>
          <span className="text-[10px] text-zinc-500">{fmtDate(report.created_at)}</span>
          {report.url && (
            <a href={normalizeHref(report.url)} target="_blank" rel="noreferrer"
                data-testid="report-external-link"
                className="text-zinc-400 hover:text-white transition" title="Open URL">
              <ExternalLink size={14} />
            </a>
          )}
        </div>

        {body.summary && (
          <div className="rounded-lg bg-white/[0.03] border border-white/5 p-3 mb-3">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Summary</div>
            <div className="text-[13px] text-zinc-200 leading-relaxed">{body.summary}</div>
          </div>
        )}

        <Section title="Improvements" items={body.improvements}
                  testid="report-improvements" />
        <Section title="Issues" items={body.issues}
                  testid="report-issues" renderItem={renderIssue} />
        <Section title="Notable items" items={body.notable_items}
                  testid="report-notable" />
        <Section title="Recommendations" items={body.recommendations}
                  testid="report-recommendations" renderItem={renderRec} />
        <Section title="Post ideas" items={body.post_ideas}
                  testid="report-post-ideas" renderItem={renderPostIdea} />
      </div>
    </div>
  );
}


function Section({ title, items, testid, renderItem }) {
  if (!items || items.length === 0) return null;
  return (
    <div data-testid={testid} className="rounded-lg bg-white/[0.02] border border-white/5 p-3 mb-3">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">{title}</div>
      <ul className="space-y-1.5">
        {items.slice(0, 30).map((item, i) => (
          <li key={i} className="text-[12.5px] text-zinc-300 leading-relaxed flex items-start gap-2">
            <span className="text-violet-400 mt-1 shrink-0">•</span>
            <div className="flex-1">
              {renderItem ? renderItem(item) : String(item)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}


function renderIssue(item) {
  if (typeof item === 'string') return item;
  const sev = (item.severity || '').toLowerCase();
  const tone = sev === 'critical' || sev === 'high'
    ? 'text-rose-300' : sev === 'medium' ? 'text-amber-300' : 'text-zinc-400';
  return (
    <span>
      {item.severity && (
        <span className={`text-[10px] uppercase tracking-wider font-bold mr-2 ${tone}`}>
          {item.severity} {item.category ? `· ${item.category}` : ''}
        </span>
      )}
      <span className="text-zinc-200">{item.description || JSON.stringify(item)}</span>
      {item.impact && <span className="text-zinc-500 block text-[11px] mt-0.5">Impact: {item.impact}</span>}
    </span>
  );
}


function renderRec(item) {
  if (typeof item === 'string') return item;
  return (
    <span>
      <span className="text-zinc-200 font-semibold">{item.title || '—'}</span>
      {item.effort && (
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 ml-2">· {item.effort} effort</span>
      )}
      {item.rationale && <span className="block text-[11.5px] text-zinc-400 mt-0.5">{item.rationale}</span>}
    </span>
  );
}


function renderPostIdea(item) {
  if (typeof item === 'string') return item;
  return (
    <span>
      <span className="text-zinc-200 font-semibold">{item.title || '—'}</span>
      {item.platform && (
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 ml-2">· {item.platform}</span>
      )}
      {item.caption && <span className="block text-[11.5px] text-zinc-400 mt-0.5">{item.caption}</span>}
    </span>
  );
}


function fmtDate(v) {
  if (!v) return '';
  try {
    const d = new Date(v);
    return d.toLocaleString(undefined,
      { dateStyle: 'medium', timeStyle: 'short' });
  } catch (_e) { return String(v); }
}


// Some reports persist `url` without a scheme (e.g. "craftersmarket.org"),
// which browsers treat as relative and resolve against the current page —
// landing on /dashboard/craftersmarket.org (404). Normalize to absolute.
function normalizeHref(u) {
  if (!u) return '#';
  const s = String(u).trim();
  if (/^https?:\/\//i.test(s)) return s;
  return `https://${s.replace(/^\/+/, '')}`;
}
