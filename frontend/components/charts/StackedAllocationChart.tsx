"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID, TOOLTIP_STYLE } from "./theme";

interface Stack { key: string; name: string; color: string }

// Stacked bars — capital allocation per year (capex / buybacks / dividends / debt / retained).
export default function StackedAllocationChart({
  data, xKey, stacks, fmt = (v) => String(v), height = 280,
}: {
  data: Record<string, any>[];
  xKey: string;
  stacks: Stack[];
  fmt?: (v: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} tickFormatter={fmt} width={56} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v: any, name) => [typeof v === "number" ? fmt(v) : v, name]} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#8c8a99" }} iconType="circle" />
        {stacks.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} stackId="alloc" fill={s.color} maxBarSize={48} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
