"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { money, pct, ratio, price as fmtPrice } from "@/lib/format";
import { Card, Panel, StateView } from "@/components/ui";
import Collapsible from "@/components/Collapsible";

const METRICS = [
  { label: "Market Cap", value: "market_cap" }, { label: "P/E", value: "pe" }, { label: "Price / FCF", value: "price_to_fcf" },
  { label: "EV / EBITDA", value: "ev_ebitda" }, { label: "Dividend Yield", value: "dividend_yield" },
  { label: "FCF Margin", value: "fcf_margin" }, { label: "FCF Conversion", value: "fcf_conversion" }, { label: "Margin of Safety", value: "margin_of_safety" },
];
const OPS = [{ label: ">", value: ">" }, { label: "<", value: "<" }, { label: "≥", value: ">=" }, { label: "≤", value: "<=" }];
const PCT_KEYS = ["dividend_yield", "fcf_margin", "fcf_conversion", "margin_of_safety"];

const PRESETS: Record<string, { metric: string; op: string; value: number }[]> = {
  "Quality compounders": [{ metric: "fcf_margin", op: ">", value: 0.2 }, { metric: "fcf_conversion", op: ">", value: 0.8 }],
  "Deep value": [{ metric: "margin_of_safety", op: ">", value: 0.15 }],
  "Cash machines": [{ metric: "fcf_margin", op: ">", value: 0.25 }],
  "Reasonable P/E": [{ metric: "pe", op: "<", value: 25 }, { metric: "pe", op: ">", value: 0 }],
};

interface Filter { metric: string; op: string; value: number }

export default function ScreenerPage() {
  const [count, setCount] = useState(0);
  const [ingestInput, setIngestInput] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [warming, setWarming] = useState(false);
  const [lastJob, setLastJob] = useState<any | null>(null);
  const [starterCount, setStarterCount] = useState(0);
  const [filters, setFilters] = useState<Filter[]>([{ metric: "fcf_margin", op: ">", value: 0.15 }]);
  const [sortMetric, setSortMetric] = useState("market_cap");
  const [results, setResults] = useState<any[]>([]);
  const [ran, setRan] = useState(false);
  const [running, setRunning] = useState(false);

  async function refreshUniverse() {
    const u = await api.screenerUniverse();
    setCount(u.data.count);
    setStarterCount(u.data.starter_universe_count ?? 0);
  }
  useEffect(() => { refreshUniverse(); }, []);

  async function ingest() {
    const tickers = ingestInput.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
    if (!tickers.length) return;
    setIngesting(true);
    try {
      const res = await api.screenerIngest(tickers);
      setLastJob({ label: "Manual ingest", ...res.data });
      setIngestInput("");
      await refreshUniverse();
    } finally { setIngesting(false); }
  }
  async function seedStarterUniverse() {
    setIngesting(true);
    try {
      const res = await api.screenerSeed();
      setLastJob({ label: "Starter universe", ...res.data });
      await refreshUniverse();
    } finally { setIngesting(false); }
  }
  async function warmDataset() {
    setWarming(true);
    try {
      const res = await api.screenerWarm();
      setLastJob({ label: "Warm job", ...res.data });
      await refreshUniverse();
    } finally { setWarming(false); }
  }
  async function run(f = filters) {
    setRunning(true);
    try {
      const res = await api.screen({ filters: f.map((x) => ({ ...x, value: Number(x.value) })), sort: { metric: sortMetric, dir: "desc" }, limit: 100 });
      setResults(res.data.results); setRan(true);
    } finally { setRunning(false); }
  }
  function applyPreset(name: string) { const f = PRESETS[name]; setFilters(f); run(f); }
  const setFilter = (i: number, patch: Partial<Filter>) => setFilters((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const isPct = (m: string) => PCT_KEYS.includes(m);

  const maxAbsMos = Math.max(0.01, ...results.map((r) => Math.abs(r.margin_of_safety ?? 0)));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl font-semibold tracking-tight">Screener</h1>
          <p className="mt-1 text-sm text-muted">Screening {count} compan{count === 1 ? "y" : "ies"} in your local dataset.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.keys(PRESETS).map((name) => (
            <button key={name} onClick={() => applyPreset(name)} className="rounded-full border border-line bg-surface/60 px-3.5 py-1.5 text-xs text-muted transition-colors hover:border-accent hover:text-text">{name}</button>
          ))}
        </div>
      </div>

      <Collapsible title="How the screener works" defaultOpen>
        <div className="space-y-3 text-sm text-muted">
          <p>The screener finds candidates by <span className="text-text">filtering companies on the metrics that matter</span> — instead of looking up one ticker, you describe the kind of company you want and it returns every match.</p>
          <ol className="ml-4 list-decimal space-y-1.5">
            <li><span className="text-text">Add companies</span> below (or via any company page) to build your dataset — each pulls live SEC + market data once and caches it.</li>
            <li><span className="text-text">Set filters</span> — stack conditions like <span className="font-mono text-text">FCF Margin &gt; 20%</span>, <span className="font-mono text-text">P/E &lt; 25</span>, <span className="font-mono text-text">Margin of Safety &gt; 15%</span>. A company must pass <em>all</em> filters. Percent fields use fractions (0.15 = 15%).</li>
            <li><span className="text-text">Run</span>, then sort and click any result to open its full analysis.</li>
          </ol>
          <p>Or hit a <span className="text-text">preset</span> (top-right): <span className="text-text">Quality compounders</span> (durable cash generators), <span className="text-text">Deep value</span> (big margin of safety), <span className="text-text">Cash machines</span> (high FCF margin), <span className="text-text">Reasonable P/E</span>.</p>
          <p className="rounded-lg border border-line bg-surface-2/40 px-3 py-2 text-xs">
            <span className="text-gold">Note:</span> the screener only covers companies you've <span className="text-text">ingested</span> into your dataset (currently {count}) — not the entire market yet. Use “Add companies” to grow it, or seed the starter universe ({starterCount}) below.
          </p>
        </div>
      </Collapsible>

      <Panel title="Add companies" hint="each pulls live SEC + market data, then caches">
        <div className="flex flex-wrap gap-2">
          <input value={ingestInput} onChange={(e) => setIngestInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ingest()}
            placeholder="e.g. AAPL, MSFT, GOOGL, AMZN" className="flex-1 rounded-lg border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-accent" />
          <button onClick={ingest} disabled={ingesting} className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white shadow-glow disabled:opacity-50">{ingesting ? "Ingesting…" : "Ingest"}</button>
          <button onClick={seedStarterUniverse} disabled={ingesting} className="rounded-lg border border-line px-4 py-2.5 text-sm text-muted transition-colors hover:border-accent hover:text-text disabled:opacity-50">Seed starter universe</button>
          <button onClick={warmDataset} disabled={warming || count === 0} className="rounded-lg border border-line px-4 py-2.5 text-sm text-muted transition-colors hover:border-accent hover:text-text disabled:opacity-50">{warming ? "Warming…" : "Warm dataset"}</button>
        </div>
        {lastJob && (
          <div className="mt-3 rounded-lg border border-line bg-surface-2/40 px-3 py-2 text-xs text-muted">
            <span className="text-text">{lastJob.label}:</span>{" "}
            {lastJob.ingested ? `${lastJob.ingested.length} ingested` : `${lastJob.warmed ?? 0} warmed`}
            {lastJob.failed != null && <> · {Array.isArray(lastJob.failed) ? lastJob.failed.length : lastJob.failed} failed</>}
            {lastJob.tickers != null && <> · {lastJob.tickers} tickers checked</>}
          </div>
        )}
      </Panel>

      <Panel title="Filters">
        <div className="space-y-2.5">
          {filters.map((f, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select value={f.metric} onChange={(e) => setFilter(i, { metric: e.target.value })} className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent">
                {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
              <select value={f.op} onChange={(e) => setFilter(i, { op: e.target.value })} className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-accent">
                {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <input type="number" step="0.5" value={f.value} onChange={(e) => setFilter(i, { value: parseFloat(e.target.value) })} className="w-28 rounded-lg border border-line bg-surface-2 px-3 py-2 text-right font-mono text-sm outline-none focus:border-accent" />
              <span className="text-xs text-faint">{isPct(f.metric) ? "fraction (0.15 = 15%)" : ""}</span>
              <button onClick={() => setFilters((fs) => fs.filter((_, j) => j !== i))} className="ml-auto rounded-md px-2 py-1 text-muted transition-colors hover:text-negative">✕</button>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <button onClick={() => setFilters((fs) => [...fs, { metric: "pe", op: "<", value: 25 }])} className="text-sm text-accent hover:underline">+ Add filter</button>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="text-muted">Sort by</span>
            <select value={sortMetric} onChange={(e) => setSortMetric(e.target.value)} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
              {METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <button onClick={() => run()} disabled={running} className="rounded-lg bg-accent px-5 py-2 font-medium text-white shadow-glow disabled:opacity-50">{running ? "Running…" : "Run"}</button>
          </div>
        </div>
      </Panel>

      {ran && (
        <StateView loading={false} empty={!results.length} emptyLabel="No companies match these filters.">
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line bg-surface-2/60 text-left text-muted">
                    <th className="px-4 py-3 font-medium">Ticker</th><th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 text-right font-medium">Mkt Cap</th><th className="px-4 py-3 text-right font-medium">P/E</th>
                    <th className="px-4 py-3 text-right font-medium">FCF Margin</th><th className="px-4 py-3 text-right font-medium">Fair Value</th>
                    <th className="px-4 py-3 text-right font-medium">Margin of Safety</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr key={r.ticker} className="border-t border-line transition-colors hover:bg-surface-2/40">
                      <td className="px-4 py-2.5"><Link href={`/company/${r.ticker}`} className="font-mono font-semibold text-accent hover:underline">{r.ticker}</Link></td>
                      <td className="px-4 py-2.5 max-w-[200px] truncate text-muted">{r.name}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{money(r.market_cap)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{ratio(r.pe)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{pct(r.fcf_margin)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{fmtPrice(r.blended_fair_value)}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-2">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                            <div className="h-full rounded-full" style={{ width: `${Math.min(100, (Math.abs(r.margin_of_safety ?? 0) / maxAbsMos) * 100)}%`, background: (r.margin_of_safety ?? 0) >= 0 ? "#3ECF8E" : "#FF6B6B", marginLeft: "auto" }} />
                          </div>
                          <span className={`w-14 text-right font-mono ${(r.margin_of_safety ?? 0) >= 0 ? "text-positive" : "text-negative"}`}>{pct(r.margin_of_safety)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </StateView>
      )}
    </div>
  );
}
