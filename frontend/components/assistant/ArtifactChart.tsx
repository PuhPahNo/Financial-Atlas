"use client";

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ArtifactChart as ChartSpec } from "@/lib/assistantApi";
import { money, pct, price, ratio } from "@/lib/format";
import { AXIS, GRID, TOOLTIP_STYLE } from "@/components/charts/theme";

function formatter(format: string, value: number): string {
  if (format === "compact_currency") return money(value);
  if (format === "currency") return price(value);
  if (format === "percent") return pct(value);
  if (format === "multiple") return `${ratio(value)}×`;
  if (format === "index") return value.toFixed(1);
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export default function ArtifactChart({ chart }: { chart: ChartSpec }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const active = useMemo(() => chart.series.filter((series) => !hidden.has(series.key)), [chart.series, hidden]);

  function toggle(key: string) {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else if (current.size < chart.series.length - 1) next.add(key);
      return next;
    });
  }

  const common = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey={chart.x_key} {...AXIS} minTickGap={22} />
      <YAxis {...AXIS} tickFormatter={(value) => formatter(chart.value_format, Number(value))} width={58} />
      <Tooltip
        contentStyle={TOOLTIP_STYLE}
        cursor={{ fill: "rgba(255,255,255,0.035)" }}
        formatter={(value, name) => [typeof value === "number" ? formatter(chart.value_format, value) : value ?? "—", name ?? ""]}
      />
    </>
  );

  return (
    <section className="atlas-artifact-card" aria-label={chart.title}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <h4 className="text-[13px] font-semibold text-text">{chart.title}</h4>
        {chart.series.length > 1 && (
          <div className="flex flex-wrap justify-end gap-1.5" aria-label="Toggle chart series">
            {chart.series.map((series) => {
              const visible = !hidden.has(series.key);
              return (
                <button
                  type="button"
                  key={series.key}
                  onClick={() => toggle(series.key)}
                  aria-pressed={visible}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] transition ${visible ? "border-line-2 bg-white/[0.055] text-text" : "border-line text-faint opacity-60"}`}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: series.color }} />
                  {series.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="h-[236px] min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          {chart.type === "bar" ? (
            <BarChart data={chart.data as any[]} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              {common}
              {active.map((series) => (
                <Bar key={series.key} dataKey={series.key} name={series.label} fill={series.color} radius={[5, 5, 0, 0]} maxBarSize={48} isAnimationActive={false} />
              ))}
            </BarChart>
          ) : (
            <LineChart data={chart.data as any[]} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              {common}
              {active.map((series) => (
                <Line key={series.key} type="monotone" dataKey={series.key} name={series.label} stroke={series.color} strokeWidth={2.25} dot={chart.data.length < 24 ? { r: 2 } : false} connectNulls isAnimationActive={false} />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}
