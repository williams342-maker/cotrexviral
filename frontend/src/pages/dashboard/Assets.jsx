import React, { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, Link as LinkIcon, FileText, Image as ImageIcon, Globe, Loader2,
  Presentation, Film,
  Sparkles, RefreshCw, Trash2, ArrowLeft, Target, TrendingUp, AlertCircle,
  Lightbulb, Users, Tag, Megaphone, X, ChevronRight, AlertTriangle, CheckCircle2,
  Rocket, CheckSquare, Square,
} from 'lucide-react';
import DashboardLayout from '../../components/DashboardLayout';
import CreativeBriefPanel from './cortex/CreativeBriefPanel';
import { API } from '../../context/AuthContext';

/* Marketing Asset Upload Center — Phase A1.
 *
 * Drag-drop or paste a URL → Cortex extracts marketing intelligence
 * (products, audience, pain points, offers, keywords, CTAs) AND scores
 * the asset across 6 marketing dimensions (overall / copy / visual /
 * CTA / audience_fit / conversion) with specific recommended changes.
 *
 * Layout: list view (asset grid) OR detail view (single asset's
 * intelligence + marketing review). Detail view is reachable via
 * `?id=<asset_id>` deep-link.
 */

const KIND_META = {
  pdf:   { icon: FileText,    tone: 'text-rose-300 border-rose-500/25 bg-rose-500/[0.04]',   label: 'PDF' },
  image: { icon: ImageIcon,   tone: 'text-sky-300 border-sky-500/25 bg-sky-500/[0.04]',     label: 'Image' },
  url:   { icon: Globe,       tone: 'text-emerald-300 border-emerald-500/25 bg-emerald-500/[0.04]', label: 'URL' },
  pptx:  { icon: Presentation, tone: 'text-amber-300 border-amber-500/25 bg-amber-500/[0.04]', label: 'PPTX' },
  video: { icon: Film,        tone: 'text-violet-300 border-violet-500/25 bg-violet-500/[0.04]', label: 'Video' },
};

const STATUS_META = {
  queued:     { tone: 'text-zinc-400 bg-white/5',      label: 'Queued',     icon: Loader2 },
  extracting: { tone: 'text-cyan-300 bg-cyan-500/15',  label: 'Extracting', icon: Loader2 },
  analyzing:  { tone: 'text-violet-300 bg-violet-500/15', label: 'Analyzing', icon: Loader2 },
  complete:   { tone: 'text-emerald-300 bg-emerald-500/15', label: 'Ready',  icon: CheckCircle2 },
  failed:     { tone: 'text-rose-300 bg-rose-500/15',  label: 'Failed',     icon: AlertTriangle },
};


export default function Assets() {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeId = searchParams.get('id');

  // ---- bulk selection state ----
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/cortex/assets?limit=80`,
                                  { withCredentials: true });
      setAssets(r.data?.assets || []);
    } catch (_e) { setAssets([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll while any asset is still processing.
  useEffect(() => {
    const busy = assets.some((a) => ['queued', 'extracting', 'analyzing'].includes(a.status));
    if (!busy) return undefined;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [assets, load]);

  const active = assets.find((a) => a.id === activeId);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else              next.add(id);
      return next;
    });
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectMode(false);
  };

  const failedAssetIds = assets.filter((a) => a.status === 'failed').map((a) => a.id);

  const selectFailed = () => {
    if (failedAssetIds.length === 0) {
      window.alert('No failed uploads found.');
      return;
    }
    setSelectMode(true);
    setSelectedIds(new Set(failedAssetIds));
  };

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!window.confirm(`Delete ${ids.length} asset${ids.length > 1 ? 's' : ''}? Stored files will be purged. This cannot be undone.`)) return;
    setBulkBusy(true);
    try {
      const r = await axios.post(`${API}/cortex/assets/bulk-delete`,
                                    { ids }, { withCredentials: true });
      const deleted = r.data?.deleted ?? ids.length;
      setAssets((prev) => prev.filter((a) => !selectedIds.has(a.id)));
      if (activeId && selectedIds.has(activeId)) setSearchParams({});
      clearSelection();
      if (deleted !== ids.length) {
        window.alert(`Deleted ${deleted} of ${ids.length} assets.`);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Bulk delete failed';
      window.alert(detail);
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <DashboardLayout>
      <div data-testid="assets-page" className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-white tracking-tight">
              Asset Intelligence
            </h1>
            <p className="text-sm text-zinc-400 mt-1">
              Upload anything — Cortex extracts marketing intelligence and grades it.
            </p>
          </div>
        </div>

        {!active && <AssetUploader onUploaded={load} />}

        {loading ? (
          <div className="text-zinc-500 text-sm">Loading assets…</div>
        ) : active ? (
          <AssetDetail asset={active}
                        onBack={() => setSearchParams({})}
                        onChanged={load} />
        ) : assets.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <AssetBulkToolbar
              total={assets.length}
              failedCount={failedAssetIds.length}
              selectMode={selectMode}
              onToggleSelectMode={() => {
                if (selectMode) clearSelection();
                else            setSelectMode(true);
              }}
              onSelectFailed={selectFailed}
            />
            {selectedIds.size > 0 && (
              <AssetSelectionBar
                count={selectedIds.size}
                total={assets.length}
                busy={bulkBusy}
                onSelectAll={() => setSelectedIds(new Set(assets.map((a) => a.id)))}
                onClear={clearSelection}
                onDelete={bulkDelete}
              />
            )}
            <AssetGrid assets={assets}
                        onOpen={(id) => setSearchParams({ id })}
                        onRefresh={load}
                        selectMode={selectMode || selectedIds.size > 0}
                        selectedIds={selectedIds}
                        onToggleSelect={toggleSelect} />
          </>
        )}
      </div>
    </DashboardLayout>
  );
}


function AssetBulkToolbar({ total, failedCount, selectMode, onToggleSelectMode, onSelectFailed }) {
  return (
    <div data-testid="assets-bulk-toolbar"
         className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] text-zinc-500 mr-1">
        {total} asset{total === 1 ? '' : 's'}
      </span>
      {failedCount > 0 && (
        <button onClick={onSelectFailed}
                data-testid="assets-select-failed"
                title={`Select all ${failedCount} failed upload${failedCount > 1 ? 's' : ''}`}
                className="text-[10.5px] font-semibold px-2 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-200 border border-rose-500/25 transition flex items-center gap-1">
          <AlertTriangle size={10} /> Clear failed uploads ({failedCount})
        </button>
      )}
      <button onClick={onToggleSelectMode}
              data-testid="assets-toggle-select-mode"
              title={selectMode ? 'Exit selection mode' : 'Select multiple assets'}
              className={`text-[10.5px] font-semibold px-2 py-1 rounded-md border transition flex items-center gap-1 ${
                selectMode
                  ? 'bg-violet-500/20 text-violet-100 border-violet-500/40'
                  : 'bg-white/[0.02] text-zinc-300 border-white/10 hover:bg-white/[0.05]'}`}>
        {selectMode ? <CheckSquare size={10} /> : <Square size={10} />}
        {selectMode ? 'Selecting' : 'Select'}
      </button>
    </div>
  );
}


function AssetSelectionBar({ count, total, busy, onSelectAll, onClear, onDelete }) {
  return (
    <div data-testid="assets-selection-bar"
         className="sticky top-2 z-20 rounded-xl border border-violet-500/30 bg-violet-500/[0.08] backdrop-blur-md px-3 py-2 flex items-center gap-3">
      <div className="flex items-center gap-1.5 text-[12px] text-violet-100 font-semibold">
        <CheckSquare size={13} />
        <span data-testid="assets-selection-count">{count} selected</span>
        <span className="text-violet-300/70 font-normal">· of {total} visible</span>
      </div>
      <button onClick={onSelectAll}
              data-testid="assets-selection-select-all"
              disabled={busy || count >= total}
              className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] text-zinc-200 border border-white/10 transition disabled:opacity-40 disabled:cursor-not-allowed">
        Select all visible
      </button>
      <div className="flex-1" />
      <button onClick={onClear}
              data-testid="assets-selection-cancel"
              disabled={busy}
              className="text-[11px] font-semibold px-2 py-1 rounded-md text-zinc-300 hover:text-white hover:bg-white/[0.06] transition flex items-center gap-1">
        <X size={11} /> Cancel
      </button>
      <button onClick={onDelete}
              data-testid="assets-selection-delete"
              disabled={busy}
              className="text-[11.5px] font-semibold px-3 py-1.5 rounded-md bg-rose-500 hover:bg-rose-400 text-white transition flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-rose-500/20">
        <Trash2 size={12} />
        {busy ? 'Deleting…' : `Delete ${count}`}
      </button>
    </div>
  );
}


/* --------------------------------------------------- Upload component */
function AssetUploader({ onUploaded }) {
  const fileRef = useRef(null);
  const [drag, setDrag] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const upload = async (file) => {
    setError('');
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await axios.post(`${API}/cortex/assets/upload`, fd, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      onUploaded();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Upload failed.');
    } finally { setBusy(false); }
  };

  const submitUrl = async () => {
    const u = urlInput.trim();
    if (!u) return;
    setError('');
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('url', u);
      await axios.post(`${API}/cortex/assets/upload`, fd, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUrlInput('');
      onUploaded();
    } catch (e) {
      setError(e?.response?.data?.detail || 'URL analysis failed.');
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="asset-uploader" className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {/* Drag-drop zone */}
      <div className="md:col-span-2">
        <div onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
              onDragLeave={(e) => { e.preventDefault(); setDrag(false); }}
              onDragOver={(e)  => { e.preventDefault(); setDrag(true); }}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                const f = e.dataTransfer.files?.[0];
                if (f) upload(f);
              }}
              data-testid="asset-uploader-dropzone"
              className={`rounded-xl border-2 border-dashed p-7 text-center transition cursor-pointer h-full ${
                drag
                  ? 'border-violet-400 bg-violet-500/[0.08]'
                  : 'border-white/10 bg-white/[0.02] hover:border-violet-500/40 hover:bg-white/[0.04]'
              }`}
              onClick={() => fileRef.current?.click()}>
          <input ref={fileRef} type="file"
                  accept="application/pdf,image/png,image/jpeg,image/webp,application/vnd.openxmlformats-officedocument.presentationml.presentation,video/mp4,video/quicktime,video/webm"
                  data-testid="asset-uploader-input"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) upload(f);
                    e.target.value = '';
                  }} />
          <Upload size={20} className="text-violet-300 mx-auto mb-2" />
          <div className="text-sm font-semibold text-white">
            {busy ? 'Uploading…' : 'Drop a file or click to upload'}
          </div>
          <div className="text-[11px] text-zinc-500 mt-1">
            PDF · JPG · PNG · WebP · PPTX · MP4/MOV/WebM · up to 20MB (50MB for video)
          </div>
        </div>
      </div>

      {/* URL paste */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 flex flex-col">
        <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold mb-2 flex items-center gap-1">
          <LinkIcon size={11} /> Analyze a URL
        </div>
        <input value={urlInput} onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submitUrl(); }}
                placeholder="https://williamscnc.com"
                data-testid="asset-uploader-url-input"
                className="w-full text-[13px] text-zinc-100 bg-white/[0.03] border border-white/10 rounded-md px-3 py-2 mb-2 focus:outline-none focus:border-violet-500/40" />
        <button onClick={submitUrl}
                disabled={busy || !urlInput.trim()}
                data-testid="asset-uploader-url-submit"
                className="mt-auto text-[12px] font-semibold px-3 py-2 rounded-md bg-violet-500/20 hover:bg-violet-500/30 text-violet-200 border border-violet-500/40 transition flex items-center justify-center gap-1 disabled:opacity-50">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          Analyze
        </button>
      </div>

      {error && (
        <div data-testid="asset-uploader-error" className="md:col-span-3 text-[12px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-md px-3 py-2">
          {error}
        </div>
      )}
    </div>
  );
}


/* ------------------------------------------------------- Asset Grid */
function AssetGrid({ assets, onOpen, onRefresh, selectMode, selectedIds, onToggleSelect }) {
  return (
    <div data-testid="asset-grid" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      <AnimatePresence>
        {assets.map((a) => (
          <AssetCard key={a.id} asset={a}
                      onOpen={() => onOpen(a.id)}
                      onChanged={onRefresh}
                      selectMode={selectMode}
                      selected={selectedIds?.has(a.id)}
                      onToggleSelect={() => onToggleSelect?.(a.id)} />
        ))}
      </AnimatePresence>
    </div>
  );
}


function AssetCard({ asset, onOpen, onChanged, selectMode, selected, onToggleSelect }) {
  const meta = KIND_META[asset.kind] || KIND_META.image;
  const stat = STATUS_META[asset.status] || STATUS_META.queued;
  const Icon = meta.icon;
  const StatusIcon = stat.icon;
  const score = asset.review?.scores?.overall;
  const animate = ['queued', 'extracting', 'analyzing'].includes(asset.status);

  // In select mode, the whole card toggles selection instead of opening.
  const handleClick = () => {
    if (selectMode) onToggleSelect?.();
    else            onOpen();
  };

  return (
    <motion.div layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.25 }}
                  data-testid={`asset-card-${asset.id}`}
                  data-selected={selected ? 'true' : 'false'}
                  className={`rounded-xl border p-4 transition cursor-pointer ${meta.tone} ${
                    selected
                      ? 'ring-2 ring-violet-400/60 ring-offset-2 ring-offset-zinc-950'
                      : 'hover:bg-white/[0.04]'}`}
                  onClick={handleClick}>
      <div className="flex items-center gap-2 mb-2">
        {selectMode && (
          <span data-testid={`asset-checkbox-${asset.id}`}
                className={`w-4 h-4 rounded shrink-0 flex items-center justify-center border transition ${
                  selected
                    ? 'bg-violet-500 border-violet-400 text-white'
                    : 'bg-white/[0.04] border-white/20 text-transparent'}`}>
            {selected ? <CheckSquare size={10} /> : null}
          </span>
        )}
        <span className="w-7 h-7 rounded-md bg-white/[0.05] border border-white/5 flex items-center justify-center shrink-0">
          <Icon size={12} />
        </span>
        <span className="text-[10px] uppercase tracking-widest font-bold">{meta.label}</span>
        <div className="flex-1" />
        <span className={`text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded ${stat.tone} flex items-center gap-1`}>
          <StatusIcon size={9} className={animate ? 'animate-spin' : ''} /> {stat.label}
        </span>
      </div>
      <div className="text-sm text-white font-semibold truncate mb-1">
        {asset.name || asset.source_url || '—'}
      </div>
      <div className="text-[11.5px] text-zinc-400 leading-snug line-clamp-2 mb-2">
        {asset.intelligence?.summary || (asset.status === 'failed' ? `Error: ${asset.error || 'unknown'}` : 'Analyzing…')}
      </div>
      <div className="flex items-center gap-2 pt-2 border-t border-white/5">
        {typeof score === 'number' && (
          <span className={`text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded border ${
            score >= 80 ? 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10'
                         : score >= 60 ? 'text-amber-300 border-amber-500/30 bg-amber-500/10'
                                          : 'text-rose-300 border-rose-500/30 bg-rose-500/10'}`}>
            {score}/100
          </span>
        )}
        {asset.intelligence?.products?.length > 0 && (
          <span className="text-[10px] text-zinc-500">
            · {asset.intelligence.products.length} products
          </span>
        )}
        {asset.extraction_meta?.duration_s && (
          <span data-testid={`asset-video-duration-${asset.id}`}
                className="text-[10px] text-zinc-500">
            · {Math.round(asset.extraction_meta.duration_s)}s
          </span>
        )}
        {asset.extraction_meta?.transcription_cost_usd > 0 && (
          <span data-testid={`asset-whisper-cost-${asset.id}`}
                title={`Whisper ${asset.extraction_meta.transcription_provider} transcription`}
                className="text-[10px] font-bold text-violet-300/80 tabular-nums">
            ·  ${asset.extraction_meta.transcription_cost_usd.toFixed(3)}
          </span>
        )}
        {asset.extraction_meta?.slide_count && (
          <span className="text-[10px] text-zinc-500">
            · {asset.extraction_meta.slide_count} slides
          </span>
        )}
        <div className="flex-1" />
        <button onClick={(e) => { e.stopPropagation(); onOpen(); }}
                className="text-[10px] text-zinc-400 hover:text-white transition flex items-center gap-0.5">
          Open <ChevronRight size={9} />
        </button>
      </div>
    </motion.div>
  );
}


/* --------------------------------------------------- Asset Detail */
function AssetDetail({ asset, onBack, onChanged }) {
  const meta = KIND_META[asset.kind] || KIND_META.image;
  const Icon = meta.icon;
  const intel = asset.intelligence;
  const review = asset.review;
  const stat = STATUS_META[asset.status] || STATUS_META.queued;
  const StatusIcon = stat.icon;
  const animate = ['queued', 'extracting', 'analyzing'].includes(asset.status);

  const reanalyze = async () => {
    try {
      await axios.post(`${API}/cortex/assets/${asset.id}/reanalyze`,
                         {}, { withCredentials: true });
      onChanged();
    } catch (_e) { /* */ }
  };

  const [building, setBuilding] = useState(false);
  const [buildErr, setBuildErr] = useState('');
  const navigate = useNavigate();
  const canBuildCampaign = asset.status === 'complete' &&
    ['pdf', 'pptx', 'url', 'image', 'video'].includes(asset.kind);

  const buildCampaign = async () => {
    setBuilding(true);
    setBuildErr('');
    try {
      const r = await axios.post(
        `${API}/cortex/assets/${asset.id}/build-campaign`,
        {}, { withCredentials: true });
      navigate(`/dashboard/campaigns?id=${r.data.campaign_id}`);
    } catch (e) {
      setBuildErr(e?.response?.data?.detail || 'Build failed');
    } finally { setBuilding(false); }
  };

  const remove = async () => {
    if (!window.confirm(`Delete "${asset.name}"? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API}/cortex/assets/${asset.id}`,
                          { withCredentials: true });
      onBack();
      onChanged();
    } catch (_e) { /* */ }
  };

  return (
    <div data-testid="asset-detail" className="space-y-4">
      <button onClick={onBack}
              data-testid="asset-detail-back"
              className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition">
        <ArrowLeft size={14} /> Back to all assets
      </button>

      {/* Hero */}
      <div className={`rounded-2xl border p-5 ${meta.tone}`}>
        <div className="flex items-center gap-3">
          <span className="w-10 h-10 rounded-lg bg-white/[0.06] border border-white/10 flex items-center justify-center">
            <Icon size={16} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest font-bold">{meta.label}</div>
            <div className="text-base font-semibold text-white truncate">{asset.name}</div>
            {asset.source_url && (
              <a href={asset.source_url} target="_blank" rel="noreferrer"
                  className="text-[11px] text-zinc-400 hover:text-white truncate block">
                {asset.source_url}
              </a>
            )}
          </div>
          <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded ${stat.tone} flex items-center gap-1`}>
            <StatusIcon size={10} className={animate ? 'animate-spin' : ''} /> {stat.label}
          </span>
          <button onClick={reanalyze}
                  data-testid="asset-detail-reanalyze"
                  className="text-[11px] font-semibold px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 text-zinc-300 transition flex items-center gap-1">
            <RefreshCw size={10} /> Re-analyze
          </button>
          {canBuildCampaign && (
            <button onClick={buildCampaign}
                    disabled={building}
                    data-testid="asset-build-campaign"
                    className="text-[11px] font-bold px-2 py-1 rounded-md bg-violet-500/15 hover:bg-violet-500/25 text-violet-200 border border-violet-500/30 transition flex items-center gap-1 disabled:opacity-50">
              {building
                ? <><Loader2 size={10} className="animate-spin" /> Building…</>
                : <><Rocket size={10} /> Build Campaign</>}
            </button>
          )}
          <button onClick={remove}
                  data-testid="asset-detail-delete"
                  className="text-[11px] font-semibold px-2 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 transition flex items-center gap-1">
            <Trash2 size={10} /> Delete
          </button>
        </div>
        {buildErr && (
          <div className="mt-2 text-[11px] text-rose-300 flex items-center gap-1">
            <AlertTriangle size={10} /> {buildErr}
          </div>
        )}
        {asset.thumb_b64 && (
          <img src={`data:image/${asset.extraction_meta?.thumb_format || 'jpeg'};base64,${asset.thumb_b64}`}
                alt={asset.name}
                className="mt-3 rounded-lg max-h-48 object-contain" />
        )}
      </div>

      {asset.status === 'failed' && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/[0.05] p-3 text-[12px] text-rose-200">
          <AlertTriangle size={12} className="inline mr-1" />
          Analysis failed: <span className="text-rose-300 font-mono">{asset.error || 'unknown'}</span>
        </div>
      )}

      {/* Intelligence + Review side-by-side on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 space-y-3">
          <ReviewPanel review={review} pending={animate} />
        </div>
        <div className="lg:col-span-3 space-y-3">
          <IntelligencePanel intel={intel} pending={animate} />
        </div>
      </div>

      {/* Creative Brief — Phase A2. Full-width below intelligence + review
          since it's the actionable strategy output the user works from. */}
      <CreativeBriefPanel asset={asset} onChanged={onChanged} />
    </div>
  );
}


/* ----------------------------------------------- Marketing Review panel */
function ReviewPanel({ review, pending }) {
  if (pending && !review) {
    return (
      <div data-testid="review-pending" className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">
        <Loader2 size={14} className="inline mr-2 animate-spin" />
        Cortex is reviewing this asset…
      </div>
    );
  }
  if (!review) return null;
  const s = review.scores || {};
  return (
    <div data-testid="review-panel"
          className="rounded-xl border border-violet-500/20 bg-gradient-to-br from-violet-500/[0.06] to-transparent p-4">
      <div className="text-[10px] uppercase tracking-widest text-violet-300 font-semibold mb-3 flex items-center gap-1">
        <Sparkles size={11} /> Marketing Review
      </div>

      {/* Big score */}
      <div className="flex items-end gap-3 mb-3">
        <div className={`text-4xl font-bold tabular-nums ${
          s.overall >= 80 ? 'text-emerald-300'
                          : s.overall >= 60 ? 'text-amber-300' : 'text-rose-300'}`}
              data-testid="review-overall-score">
          {s.overall}<span className="text-base text-zinc-500">/100</span>
        </div>
        <div className="text-[11px] text-zinc-400 mb-2">Overall score</div>
      </div>

      {/* Sub-scores grid */}
      <div className="grid grid-cols-2 gap-1.5 mb-4">
        <SubScore label="Copy"        value={s.copy} testid="review-score-copy" />
        <SubScore label="Visual"      value={s.visual} testid="review-score-visual" />
        <SubScore label="CTA"         value={s.cta} testid="review-score-cta" />
        <SubScore label="Audience"    value={s.audience_fit} testid="review-score-audience" />
        <SubScore label="Conversion"  value={s.conversion}   testid="review-score-conversion" />
      </div>

      <ReviewList icon={CheckCircle2} title="Strengths"           items={review.strengths}           tone="text-emerald-300" testid="review-strengths" />
      <ReviewList icon={AlertTriangle} title="Weaknesses"         items={review.weaknesses}          tone="text-rose-300"    testid="review-weaknesses" />
      <ReviewList icon={Target} title="Recommended changes"       items={review.recommended_changes} tone="text-violet-300"  testid="review-recommendations" emphasize />
      <ReviewList icon={Megaphone} title="Campaign angles"        items={review.suggested_campaigns} tone="text-cyan-300"    testid="review-campaigns" />
    </div>
  );
}


function SubScore({ label, value, testid }) {
  const v = Number(value) || 0;
  const tone = v >= 80 ? 'text-emerald-300' : v >= 60 ? 'text-amber-300' : 'text-rose-300';
  const bar  = v >= 80 ? 'bg-emerald-400'   : v >= 60 ? 'bg-amber-400'   : 'bg-rose-400';
  return (
    <div data-testid={testid} className="rounded-md bg-white/[0.02] border border-white/5 p-1.5">
      <div className="flex justify-between items-baseline">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</span>
        <span className={`text-[11px] font-bold tabular-nums ${tone}`}>{v}</span>
      </div>
      <div className="h-1 bg-white/5 rounded-full overflow-hidden mt-1">
        <div className={`h-full ${bar}`} style={{ width: `${Math.max(2, v)}%` }} />
      </div>
    </div>
  );
}


function ReviewList({ icon: Icon, title, items, tone, emphasize, testid }) {
  if (!items || items.length === 0) return null;
  return (
    <div data-testid={testid} className={`rounded-lg p-2.5 mb-2 ${
      emphasize ? 'bg-violet-500/[0.06] border border-violet-500/15'
                 : 'bg-white/[0.02] border border-white/5'}`}>
      <div className={`text-[9.5px] uppercase tracking-wider font-semibold mb-1 flex items-center gap-1 ${tone}`}>
        <Icon size={10} /> {title}
      </div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-[12px] text-zinc-200 leading-snug flex gap-2">
            <span className="text-zinc-600 mt-0.5">•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}


/* ----------------------------------------------- Intelligence panel */
function IntelligencePanel({ intel, pending }) {
  if (pending && !intel) {
    return (
      <div data-testid="intel-pending" className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-sm text-zinc-500">
        <Loader2 size={14} className="inline mr-2 animate-spin" />
        Cortex is extracting intelligence…
      </div>
    );
  }
  if (!intel) return null;
  const brand = intel.brand || {};
  return (
    <div data-testid="intel-panel" className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
      <div className="text-[10px] uppercase tracking-widest text-cyan-300 font-semibold mb-3 flex items-center gap-1">
        <Lightbulb size={11} /> Marketing Intelligence
      </div>
      {intel.summary && (
        <div className="text-[13px] text-zinc-200 leading-relaxed mb-3">
          {intel.summary}
        </div>
      )}
      {(brand.name || brand.tagline || brand.value_prop || brand.tone) && (
        <div data-testid="intel-brand"
              className="rounded-lg bg-white/[0.02] border border-white/5 p-2.5 mb-3">
          <div className="text-[9.5px] uppercase tracking-wider text-zinc-500 font-semibold mb-1">Brand</div>
          {brand.name &&     <div className="text-[13px] text-white font-semibold">{brand.name}</div>}
          {brand.tagline &&  <div className="text-[12px] text-zinc-300 italic">"{brand.tagline}"</div>}
          {brand.value_prop &&<div className="text-[12px] text-zinc-300 mt-1">{brand.value_prop}</div>}
          {brand.tone &&     <div className="text-[10px] text-zinc-500 mt-1">Tone: {brand.tone}</div>}
        </div>
      )}
      <IntelSection icon={Tag}        title="Products"     items={intel.products}     tone="text-violet-300" testid="intel-products" />
      <IntelSection icon={Sparkles}   title="Services"     items={intel.services}     tone="text-sky-300"    testid="intel-services" />
      <IntelSection icon={Users}      title="Audience"     items={intel.audience}     tone="text-emerald-300" testid="intel-audience" />
      <IntelSection icon={AlertCircle} title="Pain points" items={intel.pain_points}  tone="text-amber-300"  testid="intel-pain-points" />
      <IntelSection icon={Megaphone}  title="Offers"       items={intel.offers}       tone="text-fuchsia-300" testid="intel-offers" />
      <IntelSection icon={TrendingUp} title="Keywords"     items={intel.keywords}     tone="text-zinc-300"   testid="intel-keywords"   chips />
      <IntelSection icon={Target}     title="Detected CTAs" items={intel.ctas}        tone="text-cyan-300"   testid="intel-ctas" />
      <IntelSection icon={Users}      title="Competitors"  items={intel.competitors}  tone="text-rose-300"   testid="intel-competitors" />
    </div>
  );
}


function IntelSection({ icon: Icon, title, items, tone, testid, chips }) {
  if (!items || items.length === 0) return null;
  return (
    <div data-testid={testid} className="rounded-lg bg-white/[0.02] border border-white/5 p-2.5 mb-2">
      <div className={`text-[9.5px] uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1 ${tone}`}>
        <Icon size={10} /> {title}
      </div>
      {chips ? (
        <div className="flex flex-wrap gap-1">
          {items.map((it, i) => (
            <span key={i} className="text-[11px] px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/5 text-zinc-300">
              {it}
            </span>
          ))}
        </div>
      ) : (
        <ul className="space-y-1">
          {items.map((it, i) => (
            <li key={i} className="text-[12px] text-zinc-200 leading-snug flex gap-2">
              <span className="text-zinc-600 mt-0.5">•</span>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


function EmptyState() {
  return (
    <div data-testid="assets-empty"
          className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
      <Sparkles size={26} className="text-violet-300 mx-auto mb-2" />
      <div className="text-white font-semibold mb-1">No assets yet</div>
      <div className="text-sm text-zinc-400">
        Drop a PDF, product photo, or paste a URL to see Cortex extract marketing intelligence and grade your work.
      </div>
    </div>
  );
}
