"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { money, pct, price as fmtPrice } from "@/lib/format";
import { fcfQualityInsight, capitalReturnInsight } from "@/lib/insights";
import { NoData, Panel, SourceBadge, StateView, Toggle } from "@/components/ui";
import InsightStrip from "@/components/InsightStrip";
import Collapsible from "@/components/Collapsible";
import ComboChart from "@/components/charts/ComboChart";
import MetricCompareChart from "@/components/charts/MetricCompareChart";
import StackedAllocationChart from "@/components/charts/StackedAllocationChart";

const PERIODS = [
  { label: "Annual", value: "annual" },
  { label: "Quarterly", value: "quarter" },
];

export default function CashFlowPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const [period, setPeriod] = useState("annual");
  const { data, meta, loading, error } = useApi(() => api.cashflowAnalysis(ticker, period), [ticker, period]);

  const periods = data?.periods ?? [];
  const scorecard = data?.scorecard;
  const scorecards = scorecard?.cards ?? [];
  const label = (p: any) => (p.period === "FY" ? String(p.fiscal_year) : `${String(p.fiscal_year).slice(2)}${p.period}`);
  const chrono = periods.slice(0, 8).slice().reverse();

  const allocation = chrono.map((p: any) => {
    const ocf = p.operating_cash_flow || 0;
    const capex = p.capex || 0, buybacks = p.buybacks || 0, dividends = p.dividends || 0, debt = p.debt_repaid || 0;
    return { label: label(p), capex, buybacks, dividends, debt, retained: Math.max(0, ocf - capex - buybacks - dividends - debt) };
  });
  const fcfTrend = chrono.map((p: any) => ({ label: label(p), fcf: p.free_cash_flow, margin: p.fcf_margin }));
  const conversion = chrono.map((p: any) => ({ label: label(p), conversion: p.fcf_conversion }));

  const hasOcf = chrono.some((p: any) => p.operating_cash_flow != null);
  const hasFcf = chrono.some((p: any) => p.free_cash_flow != null);
  const hasConversion = chrono.some((p: any) => p.fcf_conversion != null);

  const insights = [fcfQualityInsight(periods), capitalReturnInsight(periods),
    periods[0]?.sbc_pct_ocf != null ? { label: "SBC dilution", value: pct(periods[0].sbc_pct_ocf, 0) + " of OCF", tone: (periods[0].sbc_pct_ocf > 0.15 ? "negative" : "neutral") as "negative" | "neutral", detail: "Stock-based comp as a share of operating cash flow — high values dilute holders." } : null];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-2xl font-semibold tracking-tight">Cash Flow Analysis</h2>
        <Toggle options={PERIODS} value={period} onChange={setPeriod} />
      </div>
      <SourceBadge servedBy={meta?.served_by} stale={meta?.stale} />

      <StateView loading={loading} error={error} empty={!periods.length} emptyLabel={`No cash-flow statements available for ${ticker} yet.`}>
        <InsightStrip insights={insights} />

        {scorecards.length > 0 && (
          <div>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <div className="text-[11px] uppercase tracking-wider text-muted">Cash-flow quality scorecard</div>
              <div className="font-mono text-sm text-accent-2">
                {scorecard?.overall_score == null ? "N/M" : `${scorecard.overall_score}/100`}
              </div>
            </div>
            <div className="metric-grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5">
              {scorecards.map((card: any) => (
                <div key={card.id} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] uppercase tracking-wider text-muted">{card.label}</div>
                      <div className={`mt-1.5 font-mono text-2xl ${toneClass(card.tone)}`}>
                        {card.score == null ? "N/M" : card.score}
                      </div>
                    </div>
                    <span className={`mt-0.5 rounded-full px-2 py-0.5 text-[11px] ${tonePill(card.tone)}`}>{card.tone}</span>
                  </div>
                  <p className="mt-3 min-h-12 text-xs leading-relaxed text-muted">{card.summary}</p>
                  <div className="mt-3 space-y-1.5">
                    {(card.drivers ?? []).slice(0, 2).map((driver: any) => (
                      <div key={driver.label} className="flex items-center justify-between gap-3 text-xs">
                        <span className="truncate text-faint" title={driver.reason}>{driver.label}</span>
                        <span className={`shrink-0 font-mono ${toneClass(driver.status)}`}>{formatDriver(driver)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <Panel title="Where operating cash went" hint="each year's operating cash flow split across uses">
          {hasOcf ? (
            <StackedAllocationChart data={allocation} xKey="label" fmt={(v) => money(v)} stacks={[
              { key: "capex", name: "CapEx (reinvest)", color: "#5B8CFF" },
              { key: "buybacks", name: "Buybacks", color: "#7C6CFF" },
              { key: "dividends", name: "Dividends", color: "#46d7e0" },
              { key: "debt", name: "Debt paydown", color: "#E0B341" },
              { key: "retained", name: "Retained cash", color: "#2f3b52" },
            ]} />
          ) : (
            <NoData title="Cash-flow breakdown not available" message={`${ticker} doesn't report operating cash flow in EDGAR's standardized fields.`} height={260} />
          )}
        </Panel>

        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Free cash flow & margin" hint="bars = FCF, line = FCF margin">
            {hasFcf ? (
              <ComboChart data={fcfTrend} xKey="label"
                bars={[{ key: "fcf", name: "FCF", color: "#7C6CFF" }]}
                lines={[{ key: "margin", name: "FCF margin", color: "#3ECF8E" }]}
                leftFmt={(v) => money(v)} rightFmt={(v) => pct(v, 0)} />
            ) : (
              <NoData title="Free cash flow not available" message={`${ticker} doesn't report capital expenditure under a standard line, so FCF can't be derived from EDGAR's data.`} />
            )}
          </Panel>
          <Panel title="FCF conversion" hint="FCF ÷ net income — cash quality of earnings">
            {hasConversion ? (
              <MetricCompareChart data={conversion} xKey="label" fmt={(v) => pct(v, 0)} lines={[{ key: "conversion", name: "Conversion", color: "#3ECF8E" }]} />
            ) : (
              <NoData title="FCF conversion not available" message={`Needs free cash flow, which isn't available for ${ticker}.`} />
            )}
          </Panel>
        </div>

        <Collapsible title="All cash-flow metrics by period (raw)">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="px-2 py-1.5 font-medium">Metric</th>
                  {periods.slice(0, 8).map((p: any, i: number) => <th key={i} className="px-2 py-1.5 text-right font-medium">{label(p)}</th>)}
                </tr>
              </thead>
              <tbody>
                {METRICS.map((m) => (
                  <tr key={m.field} className="border-t border-line">
                    <td className="px-2 py-1.5 text-muted">{m.label}</td>
                    {periods.slice(0, 8).map((p: any, i: number) => <td key={i} className="px-2 py-1.5 text-right font-mono">{m.fmt(p[m.field] ?? null)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Collapsible>
      </StateView>
    </div>
  );
}

function toneClass(tone: string) {
  if (tone === "positive") return "text-positive";
  if (tone === "negative") return "text-negative";
  return "text-text";
}

function tonePill(tone: string) {
  if (tone === "positive") return "bg-positive/10 text-positive";
  if (tone === "negative") return "bg-negative/10 text-negative";
  return "bg-surface-2 text-muted";
}

function formatDriver(driver: { label: string; value: number | null }) {
  if (driver.value == null) return "N/M";
  if (driver.label.includes("/ FCF")) return `${driver.value.toFixed(1)}x`;
  if (driver.label.includes("returned") || driver.label.includes("debt")) return money(driver.value);
  return pct(driver.value, driver.label.includes("CAGR") ? 1 : 0);
}

const METRICS: { label: string; field: string; fmt: (v: number | null) => string }[] = [
  { label: "Operating Cash Flow", field: "operating_cash_flow", fmt: (v) => money(v) },
  { label: "CapEx", field: "capex", fmt: (v) => money(v) },
  { label: "Free Cash Flow", field: "free_cash_flow", fmt: (v) => money(v) },
  { label: "FCF Margin", field: "fcf_margin", fmt: (v) => pct(v) },
  { label: "FCF Conversion", field: "fcf_conversion", fmt: (v) => pct(v) },
  { label: "FCF / Share", field: "fcf_per_share", fmt: (v) => fmtPrice(v) },
  { label: "CapEx % Revenue", field: "capex_pct_revenue", fmt: (v) => pct(v) },
  { label: "Buybacks", field: "buybacks", fmt: (v) => money(v) },
  { label: "Dividends", field: "dividends", fmt: (v) => money(v) },
  { label: "Capital Returned", field: "capital_returned", fmt: (v) => money(v) },
  { label: "Net Debt Issuance", field: "net_debt_issuance", fmt: (v) => money(v) },
  { label: "Net Debt", field: "net_debt", fmt: (v) => money(v) },
  { label: "Net Debt / FCF", field: "net_debt_to_fcf", fmt: (v) => v == null ? "N/M" : `${v.toFixed(1)}x` },
  { label: "SBC % of OCF", field: "sbc_pct_ocf", fmt: (v) => pct(v) },
  { label: "Reinvestment Rate", field: "reinvestment_rate", fmt: (v) => pct(v) },
];
