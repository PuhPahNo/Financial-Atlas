"use client";

import { useRef, useState } from "react";

// Lightweight responsive SVG charts (ported from the design's charts.jsx).
export interface Pt { t: number; v: number; d?: string }

const VB = 1000;

function buildPath(series: Pt[], h: number, pad: number) {
  const ys = series.map((d) => d.v);
  const min = Math.min(...ys), max = Math.max(...ys);
  const span = max - min || 1;
  const innerH = h - pad * 2;
  const X = (i: number) => (i / (series.length - 1)) * VB;
  const Y = (v: number) => pad + innerH - ((v - min) / span) * innerH;
  const line = series.map((d, i) => `${i ? "L" : "M"}${X(i).toFixed(2)} ${Y(d.v).toFixed(2)}`).join(" ");
  const area = `${line} L${VB} ${h} L0 ${h} Z`;
  return { line, area };
}

export function Sparkline({ series, color = "var(--pos)", height = 34, strokeWidth = 1.6 }: { series: Pt[]; color?: string; height?: number; strokeWidth?: number }) {
  if (!series || series.length < 2) return <div style={{ height }} />;
  const p = buildPath(series, height, 3);
  return (
    <svg viewBox={`0 0 ${VB} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height, display: "block", overflow: "visible" }}>
      <path d={p.line} fill="none" stroke={color} strokeWidth={strokeWidth} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function EmptyChart({ height, label = "Not enough data yet" }: { height: number; label?: string }) {
  return (
    <div style={{ height, display: "grid", placeItems: "center", color: "var(--text-3)", fontSize: 12,
      border: "1px dashed var(--border)", borderRadius: "var(--r-sm)" }}>{label}</div>
  );
}

export function AreaChart({ series, benchmark = null, color = "var(--accent)", height = 260, grid = true, animate = true, benchColor = "var(--text-3)", uid = "a", interactive = true, valueFmt, seriesLabel = "Strategy", benchLabel = "S&P 500", axes = true }: {
  series: Pt[]; benchmark?: Pt[] | null; color?: string; height?: number; grid?: boolean; animate?: boolean; benchColor?: string; uid?: string;
  interactive?: boolean; valueFmt?: (v: number) => string; seriesLabel?: string; benchLabel?: string; axes?: boolean }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [hov, setHov] = useState<number | null>(null);
  if (!series || series.length < 2) return <EmptyChart height={height} label="Run a backtest to see the equity curve" />;
  const pad = 14;
  const gid = "grad-" + uid;
  const innerH = height - pad * 2;
  const hasBench = !!(benchmark && benchmark.length > 1);
  const all = hasBench ? series.map((d) => d.v).concat(benchmark!.map((d) => d.v)) : series.map((d) => d.v);
  const min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
  const Y = (v: number) => pad + innerH - ((v - min) / span) * innerH;
  const Xs = (n: number, i: number) => (i / (n - 1)) * VB;
  const fmtV = valueFmt || ((v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }));

  const primaryLine = series.map((d, i) => `${i ? "L" : "M"}${Xs(series.length, i).toFixed(2)} ${Y(d.v).toFixed(2)}`).join(" ");
  const primaryArea = `${primaryLine} L${VB} ${height} L0 ${height} Z`;
  const bp = hasBench ? benchmark!.map((d, i) => `${i ? "L" : "M"}${Xs(benchmark!.length, i).toFixed(2)} ${Y(d.v).toFixed(2)}`).join(" ") : null;

  const onMove = (e: React.MouseEvent) => {
    if (!interactive || !wrap.current) return;
    const r = wrap.current.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    setHov(Math.round(frac * (series.length - 1)));
  };
  const hp = hov != null ? series[hov] : null;
  const hbV = hov != null && hasBench ? benchmark![Math.min(benchmark!.length - 1, Math.round((hov / (series.length - 1)) * (benchmark!.length - 1)))]?.v : undefined;
  const hovLeft = hov != null ? (hov / (series.length - 1)) * 100 : 0;
  const tipRight = hovLeft > 60;

  // Axis labels are HTML overlays, not SVG text: the chart uses preserveAspectRatio="none"
  // (non-uniform scaling) which would distort any in-SVG glyphs.
  const startDate = series[0]?.d;
  const endDate = series[series.length - 1]?.d;
  const axisTxt: React.CSSProperties = { position: "absolute", fontSize: 9.5, color: "var(--text-3)", fontFamily: "var(--font-mono)", pointerEvents: "none" };

  return (
    <div ref={wrap} style={{ position: "relative", height }} onMouseMove={onMove} onMouseLeave={() => setHov(null)}
      role="img" aria-label={`${seriesLabel} equity curve${startDate ? ` from ${startDate} to ${endDate}` : ""}, ranging ${fmtV(min)} to ${fmtV(max)}`}>
      {axes && (
        <>
          <span style={{ ...axisTxt, left: 2, top: 2 }}>{fmtV(max)}</span>
          <span style={{ ...axisTxt, left: 2, bottom: 14 }}>{fmtV(min)}</span>
          {startDate && <span style={{ ...axisTxt, left: 2, bottom: 1 }}>{startDate}</span>}
          {endDate && <span style={{ ...axisTxt, right: 2, bottom: 1 }}>{endDate}</span>}
        </>
      )}
      <svg viewBox={`0 0 ${VB} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height, display: "block" }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.32" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {grid && [0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1="0" x2={VB} y1={pad + innerH * g} y2={pad + innerH * g} stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        {bp && <path d={bp} fill="none" stroke={benchColor} strokeWidth="1.4" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />}
        <path d={primaryArea} fill={`url(#${gid})`} />
        <path d={primaryLine} fill="none" stroke={color} strokeWidth="2.2" vectorEffect="non-scaling-stroke" strokeLinejoin="round"
          style={animate ? ({ strokeDasharray: 2600, animation: "pt-drawLine .9s var(--ease) forwards", ["--len" as any]: 2600 } as any) : undefined} />
      </svg>

      {hp && (
        <>
          <div style={{ position: "absolute", left: `${hovLeft}%`, top: 0, bottom: 0, width: 1, background: "var(--border-strong)", pointerEvents: "none" }} />
          <div style={{ position: "absolute", left: `${hovLeft}%`, top: Y(hp.v), width: 9, height: 9, marginLeft: -4.5, marginTop: -4.5, borderRadius: 999, background: color, boxShadow: `0 0 0 3px color-mix(in srgb, ${color} 25%, transparent)`, pointerEvents: "none" }} />
          {hbV != null && <div style={{ position: "absolute", left: `${hovLeft}%`, top: Y(hbV), width: 7, height: 7, marginLeft: -3.5, marginTop: -3.5, borderRadius: 999, background: benchColor, pointerEvents: "none" }} />}
          <div style={{ position: "absolute", top: 6,
            ...(tipRight ? { right: `${100 - hovLeft}%`, transform: "translateX(-8px)" } : { left: `${hovLeft}%`, transform: "translateX(8px)" }),
            pointerEvents: "none", background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: "var(--r-sm)", boxShadow: "var(--shadow-pop)", padding: "7px 10px", minWidth: 96, zIndex: 5 }}>
            {hp.d && <div style={{ fontSize: 10.5, color: "var(--text-3)", marginBottom: 4, fontFamily: "var(--font-mono)" }}>{hp.d}</div>}
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <span style={{ width: 8, height: 2.5, background: color, display: "inline-block" }} />
              <span style={{ color: "var(--text-3)" }}>{seriesLabel}</span>
              <span className="mono" style={{ marginLeft: "auto", color: "var(--text-1)", fontWeight: 600 }}>{fmtV(hp.v)}</span>
            </div>
            {hbV != null && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, marginTop: 3 }}>
                <span style={{ width: 8, height: 0, borderTop: `2px dashed ${benchColor}`, display: "inline-block" }} />
                <span style={{ color: "var(--text-3)" }}>{benchLabel}</span>
                <span className="mono" style={{ marginLeft: "auto", color: "var(--text-2)", fontWeight: 600 }}>{fmtV(hbV)}</span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

const PALETTE = ["var(--accent)", "var(--pos)", "var(--cat-rotation)", "var(--cat-opt)", "var(--cat-long)", "var(--text-3)"];

export function Donut({ data, size = 132, thickness = 16 }: { data: { ticker: string; w: number }[]; size?: number; thickness?: number }) {
  const total = data.reduce((s, d) => s + d.w, 0) || 1;
  const R = (size - thickness) / 2;
  const C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} style={{ width: size, height: size, transform: "rotate(-90deg)" }}>
      {data.map((d, i) => {
        const frac = d.w / total;
        const seg = (
          <circle key={i} cx={size / 2} cy={size / 2} r={R} fill="none"
            stroke={d.ticker === "Cash" ? "var(--surface-3)" : PALETTE[i % PALETTE.length]} strokeWidth={thickness}
            strokeDasharray={`${frac * C} ${C}`} strokeDashoffset={-acc * C} style={{ transition: "stroke-dasharray .5s var(--ease)" }} />
        );
        acc += frac;
        return seg;
      })}
    </svg>
  );
}
export const DONUT_PALETTE = PALETTE;

export function ReturnBars({ series, height = 70, bars = 18 }: { series: Pt[]; height?: number; bars?: number }) {
  if (!series || series.length < 2) return <EmptyChart height={height} label="No period returns yet" />;
  const step = Math.max(1, Math.floor(series.length / bars));
  const rets: number[] = [];
  for (let i = step; i < series.length; i += step) rets.push(series[i].v / series[i - step].v - 1);
  if (!rets.length) return <EmptyChart height={height} label="No period returns yet" />;
  const maxAbs = Math.max(...rets.map((r) => Math.abs(r)), 0.001);
  const bw = VB / rets.length;
  const mid = height / 2;
  return (
    <svg viewBox={`0 0 ${VB} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height, display: "block" }}>
      {rets.map((r, i) => {
        const h = (Math.abs(r) / maxAbs) * (mid - 3);
        return <rect key={i} x={i * bw + bw * 0.18} width={bw * 0.64} y={r >= 0 ? mid - h : mid} height={h || 1} rx="1.5" fill={r >= 0 ? "var(--pos)" : "var(--neg)"} opacity="0.85" />;
      })}
    </svg>
  );
}

export function drawdownOf(series: Pt[]) {
  let peak = -Infinity, maxDD = 0;
  for (const d of series) { peak = Math.max(peak, d.v); maxDD = Math.min(maxDD, d.v / peak - 1); }
  return { maxDD: maxDD * 100 };
}
