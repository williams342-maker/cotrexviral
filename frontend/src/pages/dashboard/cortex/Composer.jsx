import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { ArrowUp, Loader2, Command, Paperclip, X, FileText, Image as ImageIcon, FileVideo, File as FileIcon } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/* Composer — auto-resizing textarea + send button + file attachments.
   Attachments upload to /api/cortex/assets/upload, are polled for analysis,
   and their summary is forwarded to Cortex as message context. */

// Accept everything the backend /cortex/assets/upload route accepts.
const ACCEPT =
  'application/pdf,image/jpeg,image/png,image/webp,' +
  'application/vnd.openxmlformats-officedocument.presentationml.presentation,' +
  'video/mp4,video/quicktime,video/webm';

const iconForKind = (kind) => {
  if (kind === 'image') return ImageIcon;
  if (kind === 'video') return FileVideo;
  if (kind === 'pdf' || kind === 'pptx') return FileText;
  return FileIcon;
};

const statusLabel = (a) => {
  const s = a.status;
  if (!s)               return 'queued';
  if (s === 'queued')   return 'queued';
  if (s === 'failed')   return 'failed';
  if (s === 'complete') return 'ready';
  if (s === 'extracting') return 'reading…';
  // analyzing — extraction done, LLM analysis in flight. Cortex can
  // already chat about it using the extracted excerpt or filename, so
  // we call this "ready to chat" rather than the slower "analyzing".
  return 'ready to chat';
};

export const Composer = ({ value, onChange, onSubmit, sending }) => {
  const ref      = useRef(null);
  const fileRef  = useRef(null);
  const pollsRef = useRef({});   // assetId -> intervalId
  const [attachments, setAttachments] = useState([]);  // [{id, name, kind, status, intelligence?}]
  const [uploading, setUploading]     = useState(false);

  // Auto-resize textarea
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 144) + 'px';
  }, [value]);

  // Clean up any in-flight pollers on unmount
  useEffect(() => () => {
    Object.values(pollsRef.current).forEach((id) => clearInterval(id));
    pollsRef.current = {};
  }, []);

  const pollAsset = (assetId) => {
    if (pollsRef.current[assetId]) return;
    pollsRef.current[assetId] = setInterval(async () => {
      try {
        const r = await axios.get(`${API}/cortex/assets/${assetId}`,
                                    { withCredentials: true });
        const a = r.data || {};
        setAttachments((prev) => prev.map((x) =>
          x.id === assetId
            ? { ...x,
                status:        a.status,
                intelligence:  a.intelligence,
                text_excerpt:  a.text_excerpt || x.text_excerpt }
            : x));
        if (a.status === 'complete' || a.status === 'failed') {
          clearInterval(pollsRef.current[assetId]);
          delete pollsRef.current[assetId];
        }
      } catch (_e) { /* keep polling; transient */ }
    }, 2500);
  };

  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const fd = new FormData();
        fd.append('file', file);
        const r = await axios.post(`${API}/cortex/assets/upload`, fd, {
          withCredentials: true,
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        const a = r.data || {};
        setAttachments((prev) => [...prev, {
          id: a.id, name: a.name || file.name, kind: a.kind || 'file',
          status: a.status || 'queued',
        }]);
        toast.success(`Attached: ${a.name || file.name}`);
        pollAsset(a.id);
      } catch (err) {
        const detail = err?.response?.data?.detail || err?.message || 'Upload failed';
        toast.error(detail);
      }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const removeAttachment = (id) => {
    setAttachments((prev) => prev.filter((x) => x.id !== id));
    if (pollsRef.current[id]) {
      clearInterval(pollsRef.current[id]);
      delete pollsRef.current[id];
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      doSubmit();
    }
  };

  const doSubmit = () => {
    if (sending) return;
    const text = (value || '').trim();
    if (!text && attachments.length === 0) return;
    // Hand attachments to parent; parent decides how to thread them into
    // the LLM message. After a successful send we clear them locally.
    onSubmit(attachments);
    setAttachments([]);
    Object.values(pollsRef.current).forEach((id) => clearInterval(id));
    pollsRef.current = {};
  };

  return (
    <div data-testid="cortex-composer"
         className="rounded-2xl border border-white/10 bg-white/[0.03] focus-within:border-violet-500/40 backdrop-blur-md transition">

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div data-testid="composer-attachments"
             className="flex flex-wrap gap-1.5 px-2.5 pt-2.5">
          {attachments.map((a) => {
            const Icon = iconForKind(a.kind);
            const isComplete = a.status === 'complete';
            const isFailed = a.status === 'failed';
            // After extraction finishes (status moves out of queued/extracting),
            // the user can already send — Cortex has the filename + extracted
            // text excerpt to reason over.
            const isChatReady = isComplete
              || (a.status && a.status !== 'queued' && a.status !== 'extracting');
            const tone = isFailed
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
              : isComplete
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                : isChatReady
                  ? 'border-emerald-500/25 bg-emerald-500/[0.06] text-emerald-100/90'
                  : 'border-violet-500/25 bg-violet-500/10 text-violet-100';
            const labelTone = isFailed
              ? 'text-rose-300'
              : (isComplete || isChatReady)
                ? 'text-emerald-300'
                : 'text-violet-300';
            return (
              <div key={a.id}
                   data-testid={`composer-attachment-${a.id}`}
                   className={`flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md border text-[11.5px] max-w-[260px] ${tone}`}>
                <Icon size={12} className="shrink-0 opacity-80" />
                <span className="truncate">{a.name}</span>
                <span className={`shrink-0 text-[10px] ${labelTone}`}>
                  · {statusLabel(a)}
                </span>
                {!isComplete && !isFailed && !isChatReady && (
                  <Loader2 size={10} className="animate-spin opacity-70 shrink-0" />
                )}
                <button onClick={() => removeAttachment(a.id)}
                        data-testid={`composer-attachment-remove-${a.id}`}
                        aria-label={`Remove ${a.name}`}
                        className="ml-0.5 w-4 h-4 rounded hover:bg-white/10 flex items-center justify-center text-zinc-300 hover:text-white">
                  <X size={10} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-end gap-2 p-2">
        {/* Attach button */}
        <input ref={fileRef} type="file" accept={ACCEPT} multiple
               onChange={(e) => handleFiles(e.target.files)}
               data-testid="cortex-composer-file-input"
               className="hidden" />
        <button type="button" onClick={() => fileRef.current?.click()}
                disabled={sending || uploading}
                data-testid="cortex-composer-attach"
                title="Attach document or image"
                aria-label="Attach document or image"
                className="shrink-0 w-9 h-9 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-violet-500/40 text-zinc-400 hover:text-violet-200 flex items-center justify-center transition disabled:opacity-50 disabled:cursor-not-allowed">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Paperclip size={14} />}
        </button>

        <textarea ref={ref} rows={1}
          data-testid="cortex-composer-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Message Cortex — try: 'recruit 50 woodworking sellers' or 'what should I focus on this week?'"
          className="flex-1 resize-none bg-transparent px-2 py-2 text-[13.5px] text-white placeholder:text-zinc-500 focus:outline-none leading-relaxed"
          disabled={sending} />

        <button onClick={doSubmit} disabled={sending || (!value.trim() && attachments.length === 0)}
                data-testid="cortex-composer-send"
                className="shrink-0 w-9 h-9 rounded-lg bg-violet-500 hover:bg-violet-400 disabled:bg-white/5 disabled:cursor-not-allowed text-white flex items-center justify-center transition shadow-lg shadow-violet-500/20 disabled:shadow-none">
          {sending ? <Loader2 size={14} className="animate-spin" /> : <ArrowUp size={14} />}
        </button>
      </div>
      <div className="px-3 pb-2 pt-0.5 text-[10px] text-zinc-500 flex items-center gap-2">
        <Command size={10} /> Press Enter to send, Shift+Enter for newline
        <span className="ml-auto opacity-60">PDF · PPTX · JPG · PNG · WebP · MP4 · MOV · WebM</span>
      </div>
    </div>
  );
};

export default Composer;
