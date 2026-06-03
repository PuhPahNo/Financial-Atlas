"use client";

import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { AXIS, GRID, SERIES, TOOLTIP_STYLE } from "./theme";

interface Series { key: string; name: string; color?: string }

// Bars + line on a dual axis — e.g. Revenue (bars) vs Free Cash Flow (line).
export default function ComboChart({
  data, xKey, bars = [], lines = [], leftFmt = (v) => String(v), rightFmt, height = 280,
}: {
  data: Record<string, any>[];
  xKey: string;
  bars?: Series[];
  lines?: Series[];
  leftFmt?: (v: number) => string;
  rightFmt?: (v: number) => string;
  height?: number;
}) {
  const rf = rightFmt ?? leftFmt;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis yAxisId="left" {...AXIS} tickFormatter={leftFmt} width={56} />
        {lines.length > 0 && <YAxis yAxisId="right" orientation="right" {...AXIS} tickFormatter={rf} width={52} />}
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
          formatter={(v: any, name: string) => [typeof v === "number" ? (lines.some((l) => l.name === name) ? rf(v) : leftFmt(v)) : v, name]}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "#8c8a99" }} iconType="circle" />
        {bars.map((b, i) => (
          <Bar key={b.key} yAxisId="left" dataKey={b.key} name={b.name} fill={b.color ?? SERIES[i % SERIES.length]} radius={[4, 4, 0, 0]} maxBarSize={46} isAnimationActive={false} />
        ))}
        {lines.map((l, i) => (
          <Line key={l.key} yAxisId="right" type="monotone" dataKey={l.key} name={l.name} stroke={l.color ?? SERIES[(i + 1) % SERIES.length]} strokeWidth={2.5} dot={{ r: 2.5 }} isAnimationActive={false} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
