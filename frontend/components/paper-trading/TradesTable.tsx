"use client";

import { BacktestRun } from "@/lib/paperTradingApi";
import { money, shares } from "@/lib/format";
import { Card, NoData } from "@/components/ui";

export default function TradesTable({ run }: { run: BacktestRun | null }) {
  if (!run?.trades?.length) {
    return <NoData title="No trades" message="Backtest trades will appear here after a run." height={220} />;
  }
  return (
    <Card className="p-5">
      <h3 className="mb-4 font-serif text-lg font-semibold">Trades The Strategy Would Have Made</h3>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-2 pr-3 font-medium">Date</th>
              <th className="py-2 pr-3 font-medium">Ticker</th>
              <th className="py-2 pr-3 font-medium">Side</th>
              <th className="py-2 pr-3 text-right font-medium">Qty</th>
              <th className="py-2 pr-3 text-right font-medium">Price</th>
              <th className="py-2 pr-3 text-right font-medium">Value</th>
              <th className="py-2 pr-3 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody>
            {run.trades.map((trade, idx) => (
              <tr key={`${trade.date}-${trade.side}-${idx}`} className="border-t border-line">
                <td className="py-2.5 pr-3 font-mono text-xs">{trade.date}</td>
                <td className="py-2.5 pr-3 font-mono font-semibold text-accent">{trade.ticker}</td>
                <td className="py-2.5 pr-3 capitalize">{trade.side}</td>
                <td className="py-2.5 pr-3 text-right font-mono">{shares(trade.quantity)}</td>
                <td className="py-2.5 pr-3 text-right font-mono">{money(trade.price)}</td>
                <td className="py-2.5 pr-3 text-right font-mono">{money(trade.value)}</td>
                <td className="py-2.5 pr-3 text-muted">{trade.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
