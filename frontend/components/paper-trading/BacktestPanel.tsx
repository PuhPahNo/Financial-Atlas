"use client";

import { useState } from "react";
import { BacktestRun, Strategy } from "@/lib/paperTradingApi";
import { money, pct } from "@/lib/format";
import { Panel, StatChip } from "@/components/ui";

export default function BacktestPanel({
  strategy,
  run,
  onRun,
  busy,
}: {
  strategy: Strategy | null;
  run: BacktestRun | null;
  onRun: (payload: any) => void;
  busy?: boolean;
}) {
  const [start, setStart] = useState("2006-01-01");
  const [end, setEnd] = useState("2009-12-31");
  const [cash, setCash] = useState(100000);
  const [benchmark, setBenchmark] = useState("SPY");

  function runBacktest() {
    if (!strategy) return;
    const tickers = Array.isArray(strategy.parameters.tickers) ? strategy.parameters.tickers : ["SPY"];
    onRun({
      strategy_id: strategy.id,
      tickers,
      start_date: start,
      end_date: end,
      starting_cash: cash,
      benchmark,
    });
  }

  return (
    <Panel title="Backtest Strategy" hint="Run historical simulations against daily free-data bars.">
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Start" value={start} type="date" onChange={setStart} />
        <Field label="End" value={end} type="date" onChange={setEnd} />
        <Field label="Starting cash" value={String(cash)} type="number" onChange={(v) => setCash(Number(v))} />
        <Field label="Benchmark" value={benchmark} onChange={setBenchmark} />
      </div>
      <button onClick={runBacktest} disabled={!strategy || busy} className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-glow disabled:opacity-50">
        {busy ? "Running..." : "Run backtest"}
      </button>

      {run && (
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <StatChip label="Total Return" value={pct(run.metrics.total_return as number)} sign={run.metrics.total_return as number} />
          <StatChip label="CAGR" value={pct(run.metrics.cagr as number)} sign={run.metrics.cagr as number} />
          <StatChip label="Max Drawdown" value={pct(run.metrics.max_drawdown as number)} sign={run.metrics.max_drawdown as number} />
          <StatChip label="Ending Equity" value={money(run.metrics.ending_equity as number)} />
        </div>
      )}
      {run?.warnings?.length ? <p className="mt-3 text-xs text-muted">{run.warnings.join(" ")}</p> : null}
    </Panel>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; type?: string; onChange: (value: string) => void }) {
  return (
    <label className="block text-xs font-medium text-muted">
      {label}
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent" />
    </label>
  );
}
