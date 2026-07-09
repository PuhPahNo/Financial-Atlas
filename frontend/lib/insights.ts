// Insight engine (PRD: insights + tools). Pure functions that turn raw data into
// ranked, human-readable callouts. Reused by every tab's <InsightStrip/>.
import { money, pct } from "./format";

export type Tone = "positive" | "negative" | "neutral";
export interface Insight {
  label: string;
  value: string;
  tone: Tone;
  detail?: string;
}

function cagr(series: { year: number; value: number }[]): number | null {
  const valid = series.filter((p) => p.value != null && p.value > 0).sort((a, b) => a.year - b.year);
  if (valid.length < 2) return null;
  const first = valid[0].value;
  const last = valid[valid.length - 1].value;
  const years = valid[valid.length - 1].year - valid[0].year;
  if (years <= 0 || first <= 0) return null;
  return (last / first) ** (1 / years) - 1;
}

function trend(series: (number | null)[]): "rising" | "falling" | "flat" {
  const v = series.filter((x): x is number => x != null);
  if (v.length < 2) return "flat";
  const delta = v[v.length - 1] - v[0];
  const scale = Math.abs(v[0]) || 1;
  if (delta / scale > 0.05) return "rising";
  if (delta / scale < -0.05) return "falling";
  return "flat";
}

/** Valuation verdict from a /valuation response. */
export function valuationInsight(v: { blended_fair_value?: number | null; current_price?: number | null; margin_of_safety?: number | null }): Insight | null {
  const fv = v.blended_fair_value;
  const mos = v.margin_of_safety;
  if (fv == null || mos == null) return null;
  const over = mos < 0;
  return {
    label: "Valuation",
    value: over ? `${pct(Math.abs(mos), 0)} overvalued` : `${pct(mos, 0)} margin of safety`,
    tone: over ? (mos < -0.2 ? "negative" : "neutral") : "positive",
    detail: `Trades ${over ? "above" : "below"} the blended fair value of ${money(fv)}. ${over ? "The market is pricing in more growth than the models assume." : "The models see upside to intrinsic value."}`,
  };
}

/** Revenue growth from cash-flow-analysis periods (which carry revenue). */
export function growthInsight(periods: { fiscal_year: number; revenue?: number | null }[]): Insight | null {
  const g = cagr(periods.map((p) => ({ year: p.fiscal_year, value: p.revenue ?? 0 })));
  if (g == null) return null;
  return {
    label: "Revenue growth",
    value: `${pct(g, 1)} / yr`,
    tone: g > 0.1 ? "positive" : g > 0 ? "neutral" : "negative",
    detail: `Compound annual revenue growth across the available history.`,
  };
}

/** FCF quality: conversion + margin trend. */
export function fcfQualityInsight(periods: { fcf_conversion?: number | null; fcf_margin?: number | null }[]): Insight | null {
  const latest = periods[0];
  if (!latest || latest.fcf_conversion == null) return null;
  const conv = latest.fcf_conversion;
  const marginTrend = trend(periods.map((p) => p.fcf_margin ?? null).reverse());
  return {
    label: "FCF quality",
    value: `${pct(conv, 0)} conversion`,
    tone: conv > 0.9 ? "positive" : conv > 0.6 ? "neutral" : "negative",
    detail: `${pct(conv, 0)} of net income converts to free cash flow; FCF margin is ${marginTrend}.`,
  };
}

/** Balance-sheet health from overview key metrics. */
export function healthInsight(km: { net_debt?: number | null; market_cap?: number | null }): Insight | null {
  if (km.net_debt == null) return null;
  const netCash = km.net_debt < 0;
  return {
    label: "Balance sheet",
    value: netCash ? `${money(Math.abs(km.net_debt))} net cash` : `${money(km.net_debt)} net debt`,
    tone: netCash ? "positive" : "neutral",
    detail: netCash ? "More cash than debt — a fortress balance sheet." : "Carries net debt; check coverage against cash flow.",
  };
}

/** Capital allocation: how much FCF is returned to shareholders. */
export function capitalReturnInsight(periods: { capital_returned?: number | null; free_cash_flow?: number | null }[]): Insight | null {
  const latest = periods[0];
  if (!latest || !latest.free_cash_flow || latest.capital_returned == null) return null;
  const ratioVal = latest.capital_returned / latest.free_cash_flow;
  return {
    label: "Capital returned",
    value: `${pct(ratioVal, 0)} of FCF`,
    tone: ratioVal > 0.6 ? "positive" : "neutral",
    detail: `${money(latest.capital_returned)} returned via buybacks + dividends, vs ${money(latest.free_cash_flow)} of FCF.`,
  };
}

/** Insider sentiment from the ownership summary. */
export function insiderInsight(summary: { net_value_90d?: number | null; cluster_buy?: boolean }): Insight | null {
  if (!summary || summary.net_value_90d == null) return null;
  const net = summary.net_value_90d;
  const buying = net > 0;
  return {
    label: "Insider activity (90d)",
    value: `${buying ? "+" : ""}${money(net)} net`,
    tone: buying ? "positive" : net < 0 ? "negative" : "neutral",
    detail: summary.cluster_buy ? "Multiple insiders buying — a cluster-buy signal." : buying ? "Insiders are net buyers over the last 90 days." : "Insiders are net sellers over the last 90 days (often routine).",
  };
}

export { cagr, trend };
