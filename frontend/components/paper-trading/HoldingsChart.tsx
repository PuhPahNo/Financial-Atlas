"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Portfolio } from "@/lib/paperTradingApi";
import { AXIS, SERIES } from "@/components/charts/theme";
import { Card, NoData } from "@/components/ui";
import { money, shares } from "@/lib/format";

export default function HoldingsChart({ portfolio }: { portfolio: Portfolio | null }) {
  const rows = portfolio?.positions?.map((position) => ({
    ticker: position.ticker,
    value: (position.last_price ?? 0) * (position.quantity ?? 0),
    quantity: position.quantity,
  })) ?? [];

  if (!portfolio) return <NoData title="No paper portfolio" message="Create a portfolio from the selected strategy." height={240} />;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-lg font-semibold">{portfolio.name}</h3>
          <p className="text-xs text-muted">Cash: {money(portfolio.cash)} · Status: {portfolio.status}</p>
        </div>
      </div>
      {!rows.length ? (
        <NoData title="No holdings yet" message="Run the simulated portfolio to create paper fills." height={180} />
      ) : (
        <div aria-label="Portfolio holdings chart" className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows}>
              <XAxis dataKey="ticker" stroke={AXIS.stroke} tick={{ fill: AXIS.stroke }} />
              <YAxis stroke={AXIS.stroke} tick={{ fill: AXIS.stroke }} tickFormatter={(v) => money(v)} />
              <Tooltip formatter={(v: number, _name, item: any) => [money(v), `${shares(item.payload.quantity)} shares`]} contentStyle={{ background: "#12121a", border: "1px solid #2a2a35" }} />
              <Bar dataKey="value" fill={SERIES[1]} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {portfolio.orders?.length ? <p className="mt-3 text-xs text-muted">Last order: {portfolio.orders[0].side} {shares(portfolio.orders[0].quantity)} {portfolio.orders[0].ticker} ({portfolio.orders[0].status}).</p> : null}
    </Card>
  );
}
