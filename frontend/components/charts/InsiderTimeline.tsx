"use client";

import { Bar, BarChart, CartesianGrid, Rectangle, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BarShapeProps } from "recharts";
import { AXIS, GRID, POSITIVE, NEGATIVE, TOOLTIP_STYLE } from "./theme";
import { money } from "@/lib/format";

interface Txn { transaction_date?: string | null; value?: number | null; acquired_disposed?: string | null; is_open_market?: boolean }

function InsiderBar({ x, y, width, height, payload }: BarShapeProps) {
  return (
    <Rectangle
      x={x}
      y={y}
      width={width}
      height={height}
      radius={[3, 3, 0, 0]}
      fill={payload?.net >= 0 ? POSITIVE : NEGATIVE}
    />
  );
}

// Net insider $ value by month — green (acquired) above zero, red (disposed) below.
export default function InsiderTimeline({ transactions, height = 240 }: { transactions: Txn[]; height?: number }) {
  const byMonth = new Map<string, number>();
  for (const t of transactions) {
    if (!t.transaction_date || t.value == null) continue;
    const month = t.transaction_date.slice(0, 7); // YYYY-MM
    const signed = t.acquired_disposed === "A" ? t.value : -t.value;
    byMonth.set(month, (byMonth.get(month) ?? 0) + signed);
  }
  const data = [...byMonth.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([month, net]) => ({ month, net }));
  if (data.length === 0) return <div className="py-8 text-sm text-muted">No dated insider transactions.</div>;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="month" {...AXIS} />
        <YAxis {...AXIS} tickFormatter={(v) => money(v)} width={60} />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v: any) => [money(v), "Net insider"]} />
        <Bar dataKey="net" maxBarSize={36} shape={InsiderBar} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
