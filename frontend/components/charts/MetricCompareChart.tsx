"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID, SERIES, TOOLTIP_STYLE } from "./theme";

interface Series { key: string; name: string; color?: string }

// General multi-line chart — margins trends, growth rates, or multi-company
// normalized performance overlays.
export default function MetricCompareChart({
  data, xKey, lines, fmt = (v) => String(v), height = 260,
}: {
  data: Record<string, any>[];
  xKey: string;
  lines: Series[];
  fmt?: (v: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} tickFormatter={fmt} width={52} />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any, name) => [typeof v === "number" ? fmt(v) : v, name]} />
        {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: "#8c8a99" }} iconType="circle" />}
        {lines.map((l, i) => (
          <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color ?? SERIES[i % SERIES.length]} strokeWidth={2.5} dot={{ r: 2 }} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
