"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BacktestRun } from "@/lib/paperTradingApi";
import { AXIS, SERIES } from "@/components/charts/theme";
import { Card, NoData } from "@/components/ui";
import { money } from "@/lib/format";

export default function EquityCurveChart({ run }: { run: BacktestRun | null }) {
  if (!run?.equity_curve?.length) {
    return <NoData title="No backtest yet" message="Run a strategy to see equity and benchmark curves." height={260} />;
  }
  return (
    <Card className="p-5">
      <div className="mb-4">
        <h3 className="font-serif text-lg font-semibold">Account Balance Over Time</h3>
        <p className="text-xs text-muted">Equity vs benchmark, based on simulated daily closes.</p>
      </div>
      <div aria-label="Backtest equity curve chart" className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={run.equity_curve}>
            <XAxis dataKey="date" stroke={AXIS.stroke} tick={{ fill: AXIS.stroke }} />
            <YAxis stroke={AXIS.stroke} tick={{ fill: AXIS.stroke }} tickFormatter={(v) => money(v)} />
            <Tooltip formatter={(v: number) => money(v)} contentStyle={{ background: "#12121a", border: "1px solid #2a2a35" }} />
            <Line type="monotone" dataKey="equity" stroke={SERIES[0]} dot={false} strokeWidth={2} />
            <Line type="monotone" dataKey="benchmark_equity" stroke={SERIES[1]} dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
