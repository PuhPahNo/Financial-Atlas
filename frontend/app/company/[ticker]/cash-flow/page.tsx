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
  { label: "SBC % of OCF", field: "sbc_pct_ocf", fmt: (v) => pct(v) },
  { label: "Reinvestment Rate", field: "reinvestment_rate", fmt: (v) => pct(v) },
];
