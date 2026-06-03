"use client";

import { useState } from "react";

export interface TrendPoint {
  label: string;
  value: number | null;
}

// Lightweight SVG trend chart (PRD 06 §7) — bar or line. Gaps (null) are preserved,
// never zero-filled. One shared component for all metric trends.
export default function TrendChart({
  data,
  type = "bar",
  height = 160,
  format = (v) => v.toLocaleString(),
  color = "#7C6CFF",
}: {
  data: TrendPoint[];
  type?: "bar" | "line";
  height?: number;
  format?: (v: number) => string;
  color?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const pad = { top: 12, right: 8, bottom: 22, left: 8 };
  const width = 520;
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const values = data.map((d) => d.value).filter((v): v is number => v !== null);
  if (values.length === 0) return <div className="py-8 text-sm text-muted">No data.</div>;
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const y = (v: number) => pad.top + innerH - ((v - min) / span) * innerH;
  const zeroY = y(0);
  const step = innerW / data.length;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none" style={{ maxHeight: height }}>
        <line x1={pad.left} y1={zeroY} x2={width - pad.right} y2={zeroY} stroke="rgba(255,255,255,0.1)" strokeWidth={1} />
        {type === "bar" &&
          data.map((d, i) => {
            if (d.value === null) return null;
            const bx = pad.left + i * step + step * 0.15;
            const bw = step * 0.7;
            const top = Math.min(y(d.value), zeroY);
            const h = Math.abs(y(d.value) - zeroY);
            return (
              <rect
                key={i}
                x={bx}
                y={top}
                width={bw}
                height={Math.max(h, 1)}
                fill={d.value >= 0 ? color : "#FF6B6B"}
                opacity={hover === null || hover === i ? 1 : 0.5}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
        {type === "line" && (
          <polyline
            fill="none"
            stroke={color}
            strokeWidth={2}
            points={data
              .map((d, i) => (d.value === null ? null : `${pad.left + i * step + step / 2},${y(d.value)}`))
              .filter(Boolean)
              .join(" ")}
          />
        )}
        {type === "line" &&
          data.map((d, i) =>
            d.value === null ? null : (
              <circle
                key={i}
                cx={pad.left + i * step + step / 2}
                cy={y(d.value)}
                r={hover === i ? 4 : 2.5}
                fill={color}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            )
          )}
        {data.map((d, i) => (
          <text
            key={`l${i}`}
            x={pad.left + i * step + step / 2}
            y={height - 6}
            textAnchor="middle"
            className="fill-muted"
            fontSize={10}
          >
            {d.label}
          </text>
        ))}
      </svg>
      {hover !== null && data[hover].value !== null && (
        <div className="pointer-events-none absolute -top-1 left-1/2 -translate-x-1/2 rounded border border-border bg-surface-2 px-2 py-1 text-xs">
          <span className="text-muted">{data[hover].label}: </span>
          <span className="font-semibold text-text">{format(data[hover].value!)}</span>
        </div>
      )}
    </div>
  );
}
