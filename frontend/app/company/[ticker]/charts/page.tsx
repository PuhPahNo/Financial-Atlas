"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { pct, signClass, shares as fmtShares } from "@/lib/format";
import { Card, Panel, SourceBadge, StateView, Toggle, Tooltip } from "@/components/ui";
import StockChart, { Overlays } from "@/components/StockChart";
import MetricCompareChart from "@/components/charts/MetricCompareChart";
import RsiPanel from "@/components/charts/RsiPanel";
import { SERIES } from "@/components/charts/theme";

const RANGES = [
  { label: "6M", value: "6m" }, { label: "1Y", value: "1y" }, { label: "3Y", value: "3y" },
  { label: "5Y", value: "5y" }, { label: "Max", value: "max" },
];
const INTERVALS = [{ label: "Daily", value: "1d" }, { label: "Weekly", value: "1wk" }, { label: "Monthly", value: "1mo" }];

const INDICATORS: { key: keyof Overlays | "rsi"; label: string; color: string; tip: string }[] = [
  { key: "sma50", label: "SMA 50", color: "#E0B341", tip: "50-day simple moving average — the average close over the last 50 days. A medium-term trend gauge; price holding above it is generally read as bullish." },
  { key: "sma200", label: "SMA 200", color: "#5B8CFF", tip: "200-day simple moving average — the classic long-term trend line. When the 50 crosses above the 200 it's a 'golden cross'; below, a 'death cross'." },
  { key: "ema21", label: "EMA 21", color: "#46d7e0", tip: "21-day exponential moving average — like an SMA but weights recent prices more, so it turns faster. Used to read shorter-term momentum." },
  { key: "boll", label: "Bollinger", color: "#9d8bff", tip: "Bollinger Bands (20-day, ±2σ) — bands two standard deviations around a 20-day average. They widen as volatility rises; price riding a band can signal an over-extended move." },
  { key: "rsi", label: "RSI 14", color: "#9d8bff", tip: "Relative Strength Index (14) — a 0–100 momentum oscillator shown below. Above 70 is often called 'overbought', below 30 'oversold'." },
];

function stats(closes: number[]) {
  if (closes.length < 2) return null;
  const ret = closes[closes.length - 1] / closes[0] - 1;
  const rets: number[] = [];
  for (let i = 1; i < closes.length; i++) rets.push(closes[i] / closes[i - 1] - 1);
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length;
  const vol = Math.sqrt(variance) * Math.sqrt(252);
  let peak = closes[0], maxDd = 0;
  for (const c of closes) { peak = Math.max(peak, c); maxDd = Math.min(maxDd, c / peak - 1); }
  return { ret, vol, maxDd };
}

export default function ChartsPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const [range, setRange] = useState("1y");
  const [interval, setInterval] = useState("1d");
  const [ind, setInd] = useState<Record<string, boolean>>({ sma50: true, sma200: true });
  const [compares, setCompares] = useState<string[]>(["^GSPC"]);
  const [addInput, setAddInput] = useState("");
  const [cmpData, setCmpData] = useState<Record<string, { date: string; close: number }[]>>({});

  const subject = useApi(() => api.prices(ticker, range, interval), [ticker, range, interval]);
  const bars = subject.data?.bars ?? [];
  const closes = bars.map((b: any) => b.close).filter((c: number | null) => c != null);
  const s = stats(closes);

  // Volume stats from the loaded bars (historic + relative volume).
  const vols = bars.map((b: any) => b.volume).filter((v: number | null) => v != null) as number[];
  const latestVol = vols.length ? vols[vols.length - 1] : null;
  const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : null;
  const relVol = latestVol != null && avgVol ? latestVol / avgVol : null;

  // fetch comparison series
  useEffect(() => {
    let cancelled = false;
    Promise.all(compares.map((t) => api.prices(t, range, interval).then((r) => [t, r.data.bars] as const).catch(() => [t, []] as const)))
      .then((pairs) => { if (!cancelled) setCmpData(Object.fromEntries(pairs.map(([t, b]) => [t, (b as any[]).map((x) => ({ date: x.date, close: x.close }))]))); });
    return () => { cancelled = true; };
  }, [compares, range, interval]);

  // normalized % performance: subject + comparisons, aligned on subject dates
  const labelFor = (t: string) => (t === "^GSPC" ? "S&P 500" : t === "^IXIC" ? "Nasdaq" : t);
  const seriesKeys = [ticker, ...compares];
  const maps: Record<string, Map<string, number>> = {};
  const bases: Record<string, number> = {};
  for (const k of seriesKeys) {
    const arr = k === ticker ? bars.map((b: any) => ({ date: b.date, close: b.close })) : cmpData[k] ?? [];
    const valid = arr.filter((x: any) => x.close != null);
    maps[k] = new Map(valid.map((x: any) => [x.date, x.close]));
    if (valid.length) bases[k] = valid[0].close;
  }
  const perf = bars.filter((b: any) => b.close != null).map((b: any) => {
    const row: any = { date: b.date };
    for (const k of seriesKeys) {
      const v = maps[k].get(b.date);
      row[k] = v != null && bases[k] ? v / bases[k] - 1 : null;
    }
    return row;
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Toggle options={RANGES} value={range} onChange={setRange} />
        <Toggle options={INTERVALS} value={interval} onChange={setInterval} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs text-faint">Indicators:</span>
        {INDICATORS.map((d) => (
          <Tooltip key={d.key} underline={false} width={260}
            content={<div className="text-xs"><div className="mb-1.5 flex items-center gap-2 font-medium"><span className="h-2 w-2 rounded-full" style={{ background: d.color }} />{d.label}</div><p className="leading-relaxed text-muted">{d.tip}</p></div>}>
            <button onClick={() => setInd((s) => ({ ...s, [d.key]: !s[d.key] }))}
              className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${ind[d.key] ? "border-accent bg-accent/10 text-accent-2" : "border-line text-muted hover:text-text"}`}>
              {d.label}
            </button>
          </Tooltip>
        ))}
      </div>

      <SourceBadge servedBy={subject.meta?.served_by} stale={subject.meta?.stale} />

      {s && (
        <div className="metric-grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
          <div className="px-5 py-3.5"><div className="text-[11px] uppercase tracking-wider text-muted">{range.toUpperCase()} return</div><div className={`mt-1.5 font-mono text-lg ${signClass(s.ret)}`}>{pct(s.ret, 1)}</div></div>
          <div className="px-5 py-3.5"><div className="text-[11px] uppercase tracking-wider text-muted">Volatility (ann.)</div><div className="mt-1.5 font-mono text-lg">{pct(s.vol, 1)}</div></div>
          <div className="px-5 py-3.5"><div className="text-[11px] uppercase tracking-wider text-muted">Max drawdown</div><div className="mt-1.5 font-mono text-lg text-negative">{pct(s.maxDd, 1)}</div></div>
          <div className="px-5 py-3.5"><div className="text-[11px] uppercase tracking-wider text-muted">Volume</div><div className="mt-1.5 font-mono text-lg">{fmtShares(latestVol)}</div></div>
          <div className="px-5 py-3.5"><div className="text-[11px] uppercase tracking-wider text-muted">Avg volume</div><div className="mt-1.5 font-mono text-lg">{fmtShares(avgVol)}</div></div>
          <div className="px-5 py-3.5">
            <div className="text-[11px] uppercase tracking-wider text-muted">
              <Tooltip width={240} content={<p className="text-xs leading-relaxed text-muted">Relative volume — today's volume vs the average over this range. Above 1× means unusually active trading (often around news or earnings).</p>}>Rel. volume</Tooltip>
            </div>
            <div className={`mt-1.5 font-mono text-lg ${relVol != null && relVol >= 1 ? "text-positive" : ""}`}>{relVol != null ? `${relVol.toFixed(2)}×` : "—"}</div>
          </div>
        </div>
      )}

      <Card className="p-3">
        <StateView loading={subject.loading} error={subject.error} empty={!bars.length} emptyLabel={`No price history available for ${ticker}.`}>
          {bars.length > 0 && <StockChart bars={bars} overlays={{ sma50: ind.sma50, sma200: ind.sma200, ema21: ind.ema21, boll: ind.boll }} />}
        </StateView>
      </Card>

      {ind.rsi && bars.length > 0 && (
        <Panel title="RSI (14)" hint="momentum oscillator · 70 overbought / 30 oversold">
          <RsiPanel bars={bars.map((b: any) => ({ date: b.date, close: b.close }))} />
        </Panel>
      )}

      <Panel title="Relative performance" hint="normalized % return — compare against benchmarks or peers">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {compares.map((t) => (
            <span key={t} className="flex items-center gap-1.5 rounded-full border border-line bg-surface-2/50 px-2.5 py-1 text-xs">
              {labelFor(t)}
              <button onClick={() => setCompares((c) => c.filter((x) => x !== t))} className="text-muted hover:text-negative">✕</button>
            </span>
          ))}
          <input
            value={addInput}
            onChange={(e) => setAddInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && addInput.trim()) { setCompares((c) => [...new Set([...c, addInput.trim().toUpperCase()])]); setAddInput(""); } }}
            placeholder="+ add ticker"
            className="w-28 rounded-md border border-line bg-surface-2 px-2.5 py-1 text-xs outline-none focus:border-accent"
          />
        </div>
        <MetricCompareChart data={perf} xKey="date" fmt={(v) => pct(v, 0)}
          lines={seriesKeys.map((k, i) => ({ key: k, name: labelFor(k), color: SERIES[i % SERIES.length] }))} />
      </Panel>
    </div>
  );
}
