"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, type IChartApi } from "lightweight-charts";

export interface Bar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface Overlays {
  sma50?: boolean;
  sma200?: boolean;
  ema21?: boolean;
  boll?: boolean;
}

type Pt = { time: any; value: number };

function sma(c: Pt[], p: number): Pt[] {
  const out: Pt[] = [];
  let sum = 0;
  for (let i = 0; i < c.length; i++) {
    sum += c[i].value;
    if (i >= p) sum -= c[i - p].value;
    if (i >= p - 1) out.push({ time: c[i].time, value: sum / p });
  }
  return out;
}
function ema(c: Pt[], p: number): Pt[] {
  if (c.length < p) return [];
  const k = 2 / (p + 1);
  const out: Pt[] = [];
  let prev = c.slice(0, p).reduce((a, b) => a + b.value, 0) / p;
  out.push({ time: c[p - 1].time, value: prev });
  for (let i = p; i < c.length; i++) {
    prev = c[i].value * k + prev * (1 - k);
    out.push({ time: c[i].time, value: prev });
  }
  return out;
}
function bollinger(c: Pt[], p = 20, mult = 2): { upper: Pt[]; lower: Pt[] } {
  const upper: Pt[] = [], lower: Pt[] = [];
  for (let i = p - 1; i < c.length; i++) {
    const win = c.slice(i - p + 1, i + 1).map((x) => x.value);
    const mean = win.reduce((a, b) => a + b, 0) / p;
    const sd = Math.sqrt(win.reduce((a, b) => a + (b - mean) ** 2, 0) / p);
    upper.push({ time: c[i].time, value: mean + mult * sd });
    lower.push({ time: c[i].time, value: mean - mult * sd });
  }
  return { upper, lower };
}

// Candlestick + volume (lightweight-charts v4) with toggleable overlays.
export default function StockChart({ bars, overlays = {} }: { bars: Bar[]; overlays?: Overlays }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8c8a99" },
      grid: { vertLines: { color: "rgba(255,255,255,0.05)" }, horzLines: { color: "rgba(255,255,255,0.05)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: { borderColor: "rgba(255,255,255,0.1)" },
      autoSize: true,
      crosshair: { mode: 0 },
    });
    chartRef.current = chart;

    const candles = chart.addCandlestickSeries({
      upColor: "#3ECF8E", downColor: "#FF6B6B", borderUpColor: "#3ECF8E",
      borderDownColor: "#FF6B6B", wickUpColor: "#3ECF8E", wickDownColor: "#FF6B6B",
    });
    const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

    const valid = bars.filter((b) => b.open != null && b.close != null && b.high != null && b.low != null);
    candles.setData(valid.map((b) => ({ time: b.date as any, open: b.open!, high: b.high!, low: b.low!, close: b.close! })));
    volume.setData(valid.map((b) => ({ time: b.date as any, value: b.volume ?? 0, color: (b.close ?? 0) >= (b.open ?? 0) ? "#3ECF8E66" : "#FF6B6B66" })));

    const closes: Pt[] = valid.map((b) => ({ time: b.date as any, value: b.close! }));
    const addLine = (data: Pt[], color: string, width = 1) => {
      if (!data.length) return;
      const s = chart.addLineSeries({ color, lineWidth: width as any, priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false });
      s.setData(data);
    };
    if (overlays.sma50) addLine(sma(closes, 50), "#E0B341");
    if (overlays.sma200) addLine(sma(closes, 200), "#5B8CFF");
    if (overlays.ema21) addLine(ema(closes, 21), "#46d7e0");
    if (overlays.boll) {
      const { upper, lower } = bollinger(closes);
      addLine(upper, "rgba(124,108,255,0.6)");
      addLine(lower, "rgba(124,108,255,0.6)");
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars, overlays]);

  return <div ref={ref} className="h-[420px] w-full" />;
}
