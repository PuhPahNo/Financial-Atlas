"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { SourceBadge, StateView, Toggle } from "@/components/ui";
import FilingReader, { FilingRef } from "@/components/FilingReader";

const FILTERS = [
  { label: "All", value: "" },
  { label: "10-K", value: "10-K" },
  { label: "10-Q", value: "10-Q" },
  { label: "8-K", value: "8-K" },
  { label: "Proxies", value: "DEF 14A" },
  { label: "13F / 13G", value: "SC 13G" },
  { label: "Insider (4)", value: "4" },
];

export default function FilingsPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const [filter, setFilter] = useState("");
  const [reading, setReading] = useState<FilingRef | null>(null);
  const { data, meta, loading, error } = useApi(() => api.filings(ticker, filter || undefined), [ticker, filter]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-serif text-2xl font-semibold tracking-tight">SEC Filings</h2>
        <Toggle options={FILTERS} value={filter} onChange={setFilter} />
      </div>
      <SourceBadge servedBy={meta?.served_by} stale={meta?.stale} />
      <StateView loading={loading} error={error} empty={!data?.filings?.length}>
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-surface-2/60 text-left text-muted">
                <th className="px-4 py-3 font-medium">Filed</th>
                <th className="px-4 py-3 font-medium">Form</th>
                <th className="px-4 py-3 font-medium">Description / Items</th>
                <th className="px-4 py-3 text-right font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.filings ?? []).map((f: any, i: number) => (
                <tr key={i} className="border-t border-line transition-colors hover:bg-surface-2/40">
                  <td className="px-4 py-2.5 font-mono text-muted">{f.filing_date}</td>
                  <td className="px-4 py-2.5 font-medium">{f.form_type}</td>
                  <td className="px-4 py-2.5 text-muted">
                    {(f.item_labels ?? []).map((it: any) => `${it.code} ${it.label}`).join(" · ") ||
                      (f.period_of_report ? `Period: ${f.period_of_report}` : "—")}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => setReading(f)} className="rounded-md border border-line px-2.5 py-1 text-accent transition-colors hover:border-accent hover:text-accent-2">
                      Read
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </StateView>
      {reading && <FilingReader filing={reading} onClose={() => setReading(null)} />}
    </div>
  );
}
