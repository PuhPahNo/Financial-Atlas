"use client";

import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { POSITIVE, NEGATIVE, ACCENT } from "./theme";

// Tiny inline trend line for cards & table cells.
export default function Sparkline({ data, height = 32, color }: { data: number[]; height?: number; color?: string }) {
  const pts = data.filter((v) => v != null);
  if (pts.length < 2) return <div style={{ height }} />;
  const stroke = color ?? (pts[pts.length - 1] >= pts[0] ? POSITIVE : NEGATIVE);
  const rows = pts.map((value, i) => ({ i, value }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line type="monotone" dataKey="value" stroke={stroke || ACCENT} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
