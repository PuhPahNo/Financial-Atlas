"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID, TOOLTIP_STYLE } from "./theme";

function rsi(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = closes.map(() => null);
  if (closes.length <= period) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  let avgG = gain / period, avgL = loss / period;
  out[period] = 100 - 100 / (1 + (avgL === 0 ? 100 : avgG / avgL));
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    avgG = (avgG * (period - 1) + Math.max(d, 0)) / period;
    avgL = (avgL * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = 100 - 100 / (1 + (avgL === 0 ? 100 : avgG / avgL));
  }
  return out;
}

export default function RsiPanel({ bars, height = 130 }: { bars: { date: string; close: number | null }[]; height?: number }) {
  const valid = bars.filter((b) => b.close != null) as { date: string; close: number }[];
  const values = rsi(valid.map((b) => b.close));
  const data = valid.map((b, i) => ({ date: b.date, rsi: values[i] }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" {...AXIS} minTickGap={60} />
        <YAxis domain={[0, 100]} ticks={[30, 50, 70]} {...AXIS} width={28} />
        <ReferenceLine y={70} stroke="rgba(255,107,107,0.4)" strokeDasharray="3 3" />
        <ReferenceLine y={30} stroke="rgba(62,207,142,0.4)" strokeDasharray="3 3" />
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any) => [typeof v === "number" ? v.toFixed(0) : v, "RSI"]} />
        <Line type="monotone" dataKey="rsi" stroke="#9d8bff" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
