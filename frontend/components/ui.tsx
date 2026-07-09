"use client";

import { ReactNode, useRef, useState } from "react";
import { createPortal } from "react-dom";

// --- containers ------------------------------------------------------------
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-line bg-surface/70 shadow-panel backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}

export function Panel({ title, hint, right, children }: { title?: string; hint?: string; right?: ReactNode; children: ReactNode }) {
  return (
    <Card className="p-6">
      {(title || right) && (
        <div className="mb-5 flex items-baseline justify-between gap-3">
          <div>
            {title && <h3 className="font-serif text-lg font-semibold tracking-tight">{title}</h3>}
            {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </Card>
  );
}

export function SectionTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h2 className={`font-serif text-2xl font-semibold tracking-tight ${className}`}>{children}</h2>;
}

// --- badges & metrics ------------------------------------------------------
export function SourceBadge({ servedBy, stale }: { servedBy?: string | null; stale?: boolean }) {
  if (!servedBy) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2/60 px-2.5 py-1 text-[11px] text-muted">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: stale ? "#E0B341" : "#3ECF8E" }} />
      {stale ? "cached" : "live"} · {servedBy}
    </span>
  );
}

// --- states ----------------------------------------------------------------
export function StateView({
  loading, error, empty, emptyLabel = "No data available.", children,
}: { loading: boolean; error?: string | null; empty?: boolean; emptyLabel?: string; children: ReactNode }) {
  if (loading)
    return (
      <div className="flex items-center gap-3 py-16 text-muted">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
        Loading…
      </div>
    );
  if (error)
    return (
      <div className="rounded-xl border border-negative/40 bg-negative/10 px-5 py-4 text-sm text-negative">{error}</div>
    );
  if (empty) return <div className="py-16 text-muted">{emptyLabel}</div>;
  return <>{children}</>;
}

/** Tasteful "this data isn't available" placeholder — used in place of an empty
 *  chart/section so missing data reads as intentional, not a broken pipeline. */
export function NoData({ title = "Data not available", message, height = 200 }: { title?: string; message?: string; height?: number }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 rounded-lg border border-dashed border-line bg-surface-2/20 px-6 text-center" style={{ minHeight: height }}>
      <div className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface-2/60 text-muted">⃠</div>
      <div className="text-sm font-medium text-text">{title}</div>
      {message && <div className="max-w-sm text-xs leading-relaxed text-muted">{message}</div>}
    </div>
  );
}

// --- segmented control -----------------------------------------------------
export function Toggle<T extends string>({
  options, value, onChange,
}: { options: { label: string; value: T }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface/60 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
            value === o.value ? "bg-accent font-medium text-white shadow-glow" : "text-muted hover:text-text"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- tooltip ---------------------------------------------------------------
/** Hover/focus popover, portaled to <body> with fixed positioning so it can
 *  never be clipped by a parent's overflow:hidden or z-index (PRD: tooltips). */
export function Tooltip({ children, content, width = 280, underline = true }: { children: ReactNode; content: ReactNode; width?: number; underline?: boolean }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; above: boolean } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);

  function place() {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 10;
    const left = Math.max(margin, Math.min(r.left + r.width / 2 - width / 2, window.innerWidth - width - margin));
    const above = r.top > 230; // place above when there's room, else below
    setPos({ top: above ? r.top - 10 : r.bottom + 10, left, above });
  }
  const show = () => { place(); setOpen(true); };
  const hide = () => setOpen(false);

  return (
    <>
      <span
        ref={ref}
        className={underline ? "cursor-help border-b border-dashed border-line-2/70" : "inline-flex"}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
      >
        {children}
      </span>
      {open && pos && typeof document !== "undefined" &&
        createPortal(
          <div
            role="tooltip"
            style={{ position: "fixed", top: pos.top, left: pos.left, width, transform: pos.above ? "translateY(-100%)" : undefined }}
            className="z-[100] rounded-xl border border-line-2 bg-bg-2 p-4 text-left shadow-pop"
          >
            {content}
          </div>,
          document.body
        )}
    </>
  );
}
