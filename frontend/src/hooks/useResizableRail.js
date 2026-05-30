import { useEffect, useState, useCallback, useRef } from 'react';

/* useResizableRail — persistent collapsible + drag-resizable panel state.

   Usage:
     const rail = useResizableRail({
       key: 'cortex-right-rail',
       defaultWidth: 320,
       min: 240, max: 520,
     });
     // rail.width, rail.collapsed, rail.toggle(), rail.dragProps

   Width + collapsed state are persisted to localStorage. The hook
   returns props for a drag-handle <div> the caller renders. */
export default function useResizableRail({
  key,
  defaultWidth = 320,
  min = 220,
  max = 520,
  side = 'right',     // 'right' or 'left' — controls drag direction
}) {
  const lsWidthKey     = `${key}:width`;
  const lsCollapsedKey = `${key}:collapsed`;

  const [width, setWidth] = useState(() => {
    if (typeof window === 'undefined') return defaultWidth;
    const v = parseInt(localStorage.getItem(lsWidthKey) || '', 10);
    return Number.isFinite(v) && v >= min && v <= max ? v : defaultWidth;
  });
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem(lsCollapsedKey) === '1';
  });

  // Persist on change.
  useEffect(() => {
    try { localStorage.setItem(lsWidthKey, String(width)); } catch { /* */ }
  }, [width, lsWidthKey]);
  useEffect(() => {
    try { localStorage.setItem(lsCollapsedKey, collapsed ? '1' : '0'); } catch { /* */ }
  }, [collapsed, lsCollapsedKey]);

  // Drag handlers.
  const dragRef = useRef({ active: false, startX: 0, startWidth: 0 });
  const onMouseMove = useCallback((e) => {
    const d = dragRef.current;
    if (!d.active) return;
    const dx = e.clientX - d.startX;
    const delta = side === 'right' ? -dx : dx;     // right rail grows when dragging LEFT
    const next = Math.max(min, Math.min(max, d.startWidth + delta));
    setWidth(next);
  }, [side, min, max]);
  const onMouseUp = useCallback(() => {
    dragRef.current.active = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
  }, [onMouseMove]);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragRef.current = {
      active: true, startX: e.clientX, startWidth: width,
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [width, onMouseMove, onMouseUp]);

  const toggle = useCallback(() => setCollapsed((c) => !c), []);

  return {
    width,
    collapsed,
    toggle,
    setWidth,
    dragProps: { onMouseDown, role: 'separator', 'aria-orientation': 'vertical' },
  };
}
