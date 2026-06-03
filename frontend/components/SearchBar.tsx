"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function SearchBar({
  autoFocus = false,
  large = false,
  onSelect,
  placeholder,
}: {
  autoFocus?: boolean;
  large?: boolean;
  /** If provided, selecting a result calls this instead of navigating (e.g. add-to-watchlist). */
  onSelect?: (ticker: string) => void;
  placeholder?: string;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ ticker: string; name: string }[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (q.trim().length < 1) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const id = setTimeout(async () => {
      try {
        const res = await api.search(q.trim());
        if (!cancelled) {
          setResults(res.data);
          setOpen(true);
          setActive(0);
        }
      } catch {
        /* ignore typeahead errors */
      }
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [q]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function go(ticker: string) {
    setOpen(false);
    setQ("");
    if (onSelect) onSelect(ticker);
    else router.push(`/company/${ticker}`);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || results.length === 0) {
      if (e.key === "Enter" && q.trim()) go(q.trim().toUpperCase());
      return;
    }
    if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, results.length - 1));
    else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
    else if (e.key === "Enter") go(results[active].ticker);
    else if (e.key === "Escape") setOpen(false);
  }

  return (
    <div ref={boxRef} className="relative w-full">
      {large && <span className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-muted">⌕</span>}
      <input
        autoFocus={autoFocus}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => results.length && setOpen(true)}
        placeholder={placeholder ?? (large ? "Search any ticker or company — e.g. AAPL, NVDA, Apple…" : "Search ticker or company…")}
        className={large
          ? "w-full rounded-2xl border border-line bg-surface/70 py-4 pl-12 pr-4 text-base shadow-panel outline-none transition-colors focus:border-accent"
          : "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"}
      />
      {open && results.length > 0 && (
        <ul className="absolute z-30 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-line bg-surface-2 shadow-pop">
          {results.map((r, i) => (
            <li key={r.ticker}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => go(r.ticker)}
                className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                  i === active ? "bg-accent/20" : ""
                }`}
              >
                <span className="font-mono font-semibold text-text">{r.ticker}</span>
                <span className="ml-3 truncate text-muted">{r.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
