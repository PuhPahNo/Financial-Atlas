"use client";

import { useEffect, useState } from "react";

export interface FilingRef {
  form_type: string;
  filing_date?: string;
  primary_doc_url: string;
  item_labels?: { code: string; label: string }[];
}

// Full-screen in-app reader for SEC filings (PRD 18). The cleaned document is
// served same-origin (scripts stripped) and rendered natively in a sandboxed
// iframe on a light "paper" surface — a clean reading view, not raw EDGAR.
export default function FilingReader({ filing, onClose }: { filing: FilingRef; onClose: () => void }) {
  const [loaded, setLoaded] = useState(false);
  const src = `/api/v1/filings/document/raw?url=${encodeURIComponent(filing.primary_doc_url)}`;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="mx-auto mt-6 flex h-[calc(100vh-48px)] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-line-2 bg-bg-2 shadow-pop" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="flex items-baseline gap-3">
            <span className="rounded-md bg-accent/15 px-2.5 py-1 font-mono text-sm font-semibold text-accent-2">{filing.form_type}</span>
            <span className="font-mono text-sm text-muted">{filing.filing_date}</span>
            <span className="hidden text-xs text-faint sm:inline">
              {(filing.item_labels ?? []).map((i) => i.label).filter(Boolean).join(" · ")}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <a href={filing.primary_doc_url} target="_blank" rel="noopener noreferrer" className="text-accent transition-colors hover:text-accent-2">Open in EDGAR ↗</a>
            <button onClick={onClose} className="rounded-md border border-line px-2.5 py-1 text-muted transition-colors hover:text-text">Esc</button>
          </div>
        </div>
        <div className="relative flex-1 overflow-hidden bg-[#f7f7f4]">
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center gap-3 text-neutral-500">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-600" /> Loading filing…
            </div>
          )}
          <iframe
            title={`${filing.form_type} ${filing.filing_date}`}
            src={src}
            sandbox="allow-same-origin"
            onLoad={() => setLoaded(true)}
            className="h-full w-full border-0 bg-white"
          />
        </div>
      </div>
    </div>
  );
}
