"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { ArtifactColumn, ArtifactTable as TableSpec } from "@/lib/assistantApi";
import { money, pct, price, ratio } from "@/lib/format";

function plain(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(plain).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatted(value: unknown, format: string): string {
  if (typeof value !== "number") return plain(value);
  if (format === "compact_currency") return money(value);
  if (format === "currency") return price(value);
  if (format === "percent") return pct(value);
  if (format === "percent_points") return `${value.toFixed(1)}%`;
  if (format === "multiple") return `${ratio(value)}×`;
  if (format === "integer") return Math.round(value).toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function cell(value: unknown, column: ArtifactColumn) {
  const text = formatted(value, column.format);
  if (column.format === "ticker" && text !== "—") {
    return <Link href={`/company/${encodeURIComponent(text)}`} className="font-semibold text-accent-2 hover:text-white">{text}</Link>;
  }
  return text;
}

export default function ArtifactTable({ table }: { table: TableSpec }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const filtered = query.trim()
      ? table.rows.filter((row) => Object.values(row).some((value) => plain(value).toLowerCase().includes(query.trim().toLowerCase())))
      : [...table.rows];
    if (!sortKey) return filtered;
    return filtered.sort((left, right) => {
      const a = left[sortKey];
      const b = right[sortKey];
      if (a === b) return 0;
      if (a === null || a === undefined) return 1;
      if (b === null || b === undefined) return -1;
      const order = typeof a === "number" && typeof b === "number" ? a - b : plain(a).localeCompare(plain(b));
      return direction === "asc" ? order : -order;
    });
  }, [direction, query, sortKey, table.rows]);

  function sort(column: ArtifactColumn) {
    if (sortKey === column.key) setDirection((current) => current === "asc" ? "desc" : "asc");
    else {
      setSortKey(column.key);
      setDirection("desc");
    }
  }

  return (
    <section className="atlas-artifact-card" aria-label={table.title}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h4 className="text-[13px] font-semibold text-text">{table.title}</h4>
          <p className="mt-0.5 text-[10px] text-faint">{table.rows.length} row{table.rows.length === 1 ? "" : "s"} · select a heading to sort</p>
        </div>
        {table.rows.length > 6 && (
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter rows"
            aria-label={`Filter ${table.title}`}
            className="w-28 rounded-lg border border-line bg-bg/70 px-2.5 py-1.5 text-[11px] text-text outline-none placeholder:text-faint focus:border-accent/60"
          />
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="min-w-full border-collapse text-left text-[11px]">
          <thead className="bg-white/[0.035] text-faint">
            <tr>
              {table.columns.map((column) => (
                <th key={column.key} className="whitespace-nowrap border-b border-line px-3 py-2 font-medium">
                  <button type="button" onClick={() => sort(column)} className="inline-flex items-center gap-1 hover:text-text">
                    {column.label}
                    {sortKey === column.key && <span aria-hidden="true">{direction === "asc" ? "↑" : "↓"}</span>}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${table.id}-${index}`} className="border-b border-line/70 last:border-b-0 hover:bg-white/[0.025]">
                {table.columns.map((column) => (
                  <td key={column.key} className={`max-w-[260px] whitespace-nowrap px-3 py-2.5 ${column.format === "text" || column.format === "date" || column.format === "ticker" ? "text-muted" : "font-mono text-text"}`}>
                    {cell(row[column.key], column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="px-4 py-8 text-center text-xs text-faint">No rows match that filter.</div>}
      </div>
    </section>
  );
}
