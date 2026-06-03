"use client";

import { ReactNode, useState } from "react";

// Collapsed-by-default section — used to tuck raw tables below insights & visuals.
export default function Collapsible({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-line bg-surface/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-3.5 text-left text-sm font-medium text-text transition-colors hover:bg-surface-2/40"
      >
        {title}
        <span className={`text-muted transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
      </button>
      {open && <div className="border-t border-line p-5">{children}</div>}
    </div>
  );
}
