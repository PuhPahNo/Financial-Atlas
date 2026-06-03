"use client";

import { CSSProperties, ReactNode, useEffect, useState } from "react";

// ---- Icons (stroke geometry, ported from the design) ---------------------
const PATHS: Record<string, string> = {
  plus: "M12 5v14M5 12h14",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  edit: "M4 20h4L18.5 9.5a2 2 0 0 0-3-3L5 17v3z",
  x: "M6 6l12 12M18 6 6 18",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  sparkles: "M12 3l1.8 4.6L18.5 9l-4.7 1.4L12 15l-1.8-4.6L5.5 9l4.7-1.4L12 3zM19 14l.9 2.3 2.3.9-2.3.9L19 21l-.9-2.3-2.3-.9 2.3-.9L19 14z",
  play: "M7 5l12 7-12 7V5z",
  chart: "M4 19V5M4 19h16M8 16l3-4 3 2 4-7",
  layers: "M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5",
  star: "M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 17l-5.2 2.7 1-5.8L3.5 9.7l5.9-.9L12 3.5z",
  copy: "M9 9h10v10H9zM5 15H4V5h10v1",
  chevron: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  send: "M4 12l16-7-7 16-2-7-7-2z",
  sliders: "M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M8 15v4",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  clock: "M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  home: "M4 11l8-7 8 7M6 10v9h12v-9",
  back: "M11 5l-7 7 7 7M4 12h16",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 11v6M12 7h.01",
  users: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM22 19v-1a4 4 0 0 0-3-3.87M16 4.13a4 4 0 0 1 0 7.75",
  wallet: "M3 7h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zM3 7l2-3h12M17 13h.01",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01",
  shield: "M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6l8-3z",
  trend: "M3 17l6-6 4 4 8-8M21 7h-5M21 7v5",
};

export function Icon({ name, size = 16, sw = 1.8, style, fill = false }: { name: string; size?: number; sw?: number; style?: CSSProperties; fill?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw}
         strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, ...style }}>
      <path d={PATHS[name]} fill={fill ? "currentColor" : "none"} stroke={fill ? "none" : "currentColor"} />
    </svg>
  );
}

type Tone = "pos" | "neg" | "accent" | "neutral";

export function Pill({ tone = "neutral", children, style }: { tone?: Tone; children: ReactNode; style?: CSSProperties }) {
  const map: Record<Tone, { c: string; b: string }> = {
    pos: { c: "var(--pos)", b: "var(--pos-soft)" },
    neg: { c: "var(--neg)", b: "var(--neg-soft)" },
    accent: { c: "var(--accent-2)", b: "var(--accent-soft)" },
    neutral: { c: "var(--text-2)", b: "var(--surface-2)" },
  };
  const m = map[tone];
  return (
    <span className="mono" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, fontWeight: 600,
      color: m.c, background: m.b, padding: "3px 8px", borderRadius: "var(--r-pill)", lineHeight: 1, whiteSpace: "nowrap", ...style }}>{children}</span>
  );
}

export function Stat({ label, value, sub, tone, mono = true }: { label: string; value: ReactNode; sub?: string; tone?: "pos" | "neg"; mono?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div className="eyebrow">{label}</div>
      <div className={mono ? "mono" : ""} style={{ fontSize: 21, fontWeight: 600, color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--text-1)" }}>{value}</div>
      {sub && <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)" }}>{sub}</div>}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = "md" }: { options: { id: T; label: string }[]; value: T; onChange: (v: T) => void; size?: "sm" | "md" }) {
  const pad = size === "sm" ? "6px 12px" : "9px 16px";
  return (
    <div style={{ display: "inline-flex", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-pill)", padding: 3, gap: 2, flexWrap: "wrap" }}>
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button key={o.id} onClick={() => onChange(o.id)} style={{ padding: pad, border: "none", cursor: "pointer", borderRadius: "var(--r-pill)",
            fontFamily: "var(--font-sans)", fontSize: size === "sm" ? 12.5 : 13.5, fontWeight: 600,
            background: on ? "var(--accent)" : "transparent", color: on ? "#0a0a12" : "var(--text-2)",
            boxShadow: on ? "0 2px 12px -2px var(--accent-line)" : "none", transition: "all .18s var(--ease)", whiteSpace: "nowrap" }}>{o.label}</button>
        );
      })}
    </div>
  );
}

export function Btn({ variant = "primary", size = "md", icon, iconFill, children, onClick, disabled, style, title }: {
  variant?: "primary" | "ghost" | "soft" | "danger"; size?: "sm" | "md" | "lg"; icon?: string; iconFill?: boolean;
  children?: ReactNode; onClick?: () => void; disabled?: boolean; style?: CSSProperties; title?: string }) {
  const sz = size === "sm" ? { p: "7px 12px", f: 12.5 } : size === "lg" ? { p: "13px 22px", f: 15 } : { p: "10px 16px", f: 13.5 };
  const V = {
    primary: { bg: "var(--accent)", col: "#0a0a12", bd: "transparent" },
    ghost: { bg: "transparent", col: "var(--text-1)", bd: "var(--border-strong)" },
    soft: { bg: "var(--surface-2)", col: "var(--text-1)", bd: "var(--border)" },
    danger: { bg: "var(--neg-soft)", col: "var(--neg)", bd: "transparent" },
  }[variant];
  return (
    <button onClick={onClick} disabled={disabled} title={title} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
      padding: sz.p, fontSize: sz.f, fontWeight: 600, fontFamily: "var(--font-sans)", background: V.bg, color: V.col, border: `1px solid ${V.bd}`,
      borderRadius: "var(--r-sm)", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.45 : 1,
      boxShadow: variant === "primary" && !disabled ? "0 4px 18px -6px var(--accent-line)" : "none", transition: "filter .15s", whiteSpace: "nowrap", ...style }}>
      {icon && <Icon name={icon} size={sz.f + 2} fill={iconFill} />}{children}
    </button>
  );
}

export function IconBtn({ icon, onClick, title, tone, size = 32, fill }: { icon: string; onClick?: () => void; title?: string; tone?: "danger"; size?: number; fill?: boolean }) {
  return (
    <button onClick={onClick} title={title} style={{ width: size, height: size, display: "grid", placeItems: "center", cursor: "pointer",
      background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
      color: tone === "danger" ? "var(--neg)" : "var(--text-2)", transition: "all .15s var(--ease)" }}
      onMouseEnter={(e) => { e.currentTarget.style.background = tone === "danger" ? "var(--neg-soft)" : "var(--surface-3)"; e.currentTarget.style.color = tone === "danger" ? "var(--neg)" : "var(--text-1)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.color = tone === "danger" ? "var(--neg)" : "var(--text-2)"; }}>
      <Icon name={icon} size={size * 0.46} fill={fill} />
    </button>
  );
}

export function Slider({ label, value, min, max, step, unit, onChange, hue = "var(--accent)" }: { label: string; value: number; min: number; max: number; step: number; unit?: string; onChange: (v: number) => void; hue?: string }) {
  const fillPct = ((value - min) / (max - min)) * 100;
  return (
    <label style={{ display: "block" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <span style={{ fontSize: 13, color: "var(--text-2)", fontWeight: 500 }}>{label}</span>
        <span className="mono" style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 600 }}>{value}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", height: 4, appearance: "none", WebkitAppearance: "none", borderRadius: 999, accentColor: hue,
          background: `linear-gradient(90deg, ${hue} ${fillPct}%, var(--surface-3) ${fillPct}%)`, cursor: "pointer" }} />
    </label>
  );
}

export function TextInput({ value, onChange, placeholder, mono, style }: { value: string | number; onChange: (v: string) => void; placeholder?: string; mono?: boolean; style?: CSSProperties }) {
  return (
    <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={mono ? "mono" : ""}
      style={{ width: "100%", padding: "11px 14px", background: "var(--surface-2)", color: "var(--text-1)", border: "1px solid var(--border)",
        borderRadius: "var(--r-sm)", fontSize: 14, fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)", outline: "none", ...style }}
      onFocus={(e) => (e.target.style.borderColor = "var(--accent-line)")} onBlur={(e) => (e.target.style.borderColor = "var(--border)")} />
  );
}

function Backdrop({ onClose, children, align = "flex-end" }: { onClose: () => void; children: ReactNode; align?: string }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div onClick={onClose} className="pt-scope" style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", justifyContent: align,
      background: "rgba(4,4,8,0.62)", backdropFilter: "blur(4px)", animation: "pt-fadeIn .2s ease" }}>{children}</div>
  );
}

export function SlideOver({ open, onClose, children, width = 480 }: { open: boolean; onClose: () => void; children: ReactNode; width?: number }) {
  if (!open) return null;
  return (
    <Backdrop onClose={onClose} align="flex-end">
      <div onClick={(e) => e.stopPropagation()} style={{ width: `min(${width}px, 96vw)`, height: "100%", background: "var(--surface-1)",
        borderLeft: "1px solid var(--border-strong)", boxShadow: "var(--shadow-pop)", overflowY: "auto", animation: "pt-slideIn .3s var(--ease)" }}>{children}</div>
    </Backdrop>
  );
}

export function Modal({ open, onClose, children, width = 460 }: { open: boolean; onClose: () => void; children: ReactNode; width?: number }) {
  if (!open) return null;
  return (
    <Backdrop onClose={onClose} align="center">
      <div onClick={(e) => e.stopPropagation()} style={{ alignSelf: "center", width: `min(${width}px, 94vw)`, background: "var(--surface-1)",
        border: "1px solid var(--border-strong)", borderRadius: "var(--r-lg)", boxShadow: "var(--shadow-pop)", animation: "pt-fadeUp .25s var(--ease)" }}>{children}</div>
    </Backdrop>
  );
}

export function ConfirmDialog({ open, title, body, confirmLabel = "Delete", onConfirm, onClose }: { open: boolean; title: string; body: string; confirmLabel?: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} width={400}>
      <div style={{ padding: 24 }}>
        <h3 className="serif" style={{ margin: "0 0 8px", fontSize: 22, fontWeight: 600 }}>{title}</h3>
        <p style={{ margin: "0 0 20px", color: "var(--text-2)", fontSize: 14, lineHeight: 1.5 }}>{body}</p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <Btn variant="soft" onClick={onClose}>Cancel</Btn>
          <Btn variant="danger" icon="trash" onClick={onConfirm}>{confirmLabel}</Btn>
        </div>
      </div>
    </Modal>
  );
}

// Hover tooltip scoped to the pt-scope tokens. Anchored above the trigger;
// `align` flips it to the right edge for stats near a card's right side.
export function PtTip({ children, tip, align = "left", width = 210, style }: {
  children: ReactNode; tip: ReactNode; align?: "left" | "right"; width?: number; style?: CSSProperties }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 4, cursor: "help", ...style }}
      onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      {open && (
        <span role="tooltip" style={{ position: "absolute", bottom: "calc(100% + 8px)", ...(align === "right" ? { right: 0 } : { left: 0 }), zIndex: 90, width,
          padding: "9px 11px", background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: "var(--r-sm)",
          boxShadow: "var(--shadow-pop)", fontSize: 11.5, lineHeight: 1.5, color: "var(--text-2)", fontWeight: 500,
          fontFamily: "var(--font-sans)", textTransform: "none", letterSpacing: "normal", whiteSpace: "normal", pointerEvents: "none" }}>{tip}</span>
      )}
    </span>
  );
}

export function CatDot({ hue, size = 8 }: { hue: string; size?: number }) {
  return <span style={{ width: size, height: size, borderRadius: 999, background: hue, boxShadow: `0 0 8px -1px ${hue}`, flexShrink: 0, display: "inline-block" }} />;
}

export function Empty({ icon = "layers", title, body }: { icon?: string; title: string; body: string }) {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-3)" }}>
      <div style={{ display: "inline-grid", placeItems: "center", width: 56, height: 56, borderRadius: 16, background: "var(--surface-2)", border: "1px solid var(--border)", marginBottom: 16 }}>
        <Icon name={icon} size={24} />
      </div>
      <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: 13.5, maxWidth: 320, margin: "0 auto", lineHeight: 1.5 }}>{body}</div>
    </div>
  );
}
