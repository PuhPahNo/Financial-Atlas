"use client";

import { Strategy } from "@/lib/paperTradingApi";
import { pct } from "@/lib/format";
import { Card } from "@/components/ui";

export default function ModelCard({
  strategy,
  selected,
  onSelect,
  onClone,
  onDelete,
}: {
  strategy: Strategy;
  selected: boolean;
  onSelect: () => void;
  onClone: () => void;
  onDelete: () => void;
}) {
  const ret = typeof strategy.metrics.backtested_return === "number" ? strategy.metrics.backtested_return : null;
  const win = typeof strategy.metrics.win_rate === "number" ? strategy.metrics.win_rate : null;
  const drawdown = typeof strategy.metrics.max_drawdown === "number" ? strategy.metrics.max_drawdown : null;

  return (
    <Card className={`p-5 transition-colors ${selected ? "border-accent bg-accent/5" : ""}`}>
      <div className="flex items-start justify-between gap-4">
        <button onClick={onSelect} className="min-w-0 text-left" aria-pressed={selected}>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-serif text-lg font-semibold">{strategy.name}</h3>
            <span className="rounded-full border border-line px-2 py-0.5 text-[11px] uppercase tracking-wide text-muted">
              {strategy.origin}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">{strategy.description}</p>
        </button>
        <div className="flex shrink-0 gap-1">
          <button onClick={onClone} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-text">
            Clone
          </button>
          {strategy.origin !== "seeded" && (
            <button onClick={onDelete} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-negative/10 hover:text-negative">
              Archive
            </button>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <Metric label="Backtested" value={pct(ret)} />
        <Metric label="Win Rate" value={pct(win)} />
        <Metric label="Max DD" value={pct(drawdown)} />
      </div>

      <div className="mt-4 space-y-2 text-xs leading-relaxed text-muted">
        <p><span className="font-medium text-text">Method:</span> {strategy.methodology}</p>
        <p><span className="font-medium text-text">History:</span> {strategy.history || "User-defined strategy."}</p>
        {strategy.caveats?.[0] && <p><span className="font-medium text-text">Caveat:</span> {strategy.caveats[0]}</p>}
      </div>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2/50 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm">{value}</div>
    </div>
  );
}
