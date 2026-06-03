"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { money, pct, price as fmtPrice, ratio, shares as fmtShares } from "@/lib/format";
import { growthInsight, fcfQualityInsight, capitalReturnInsight } from "@/lib/insights";
import { NoData, Panel, SourceBadge, StateView, Toggle } from "@/components/ui";
import InsightStrip from "@/components/InsightStrip";
import Collapsible from "@/components/Collapsible";
import ComboChart from "@/components/charts/ComboChart";
import MetricCompareChart from "@/components/charts/MetricCompareChart";
import Sparkline from "@/components/charts/Sparkline";

const PERIODS = [
  { label: "Annual", value: "annual" },
  { label: "Quarterly", value: "quarter" },
];

type Fmt = "money" | "price" | "shares";
const ROWS: Record<string, { label: string; field: string; fmt?: Fmt }[]> = {
  income: [
    { label: "Revenue", field: "revenue" }, { label: "Gross Profit", field: "gross_profit" },
    { label: "Operating Income", field: "operating_income" }, { label: "Net Income", field: "net_income" },
    { label: "EPS (diluted)", field: "eps_diluted", fmt: "price" }, { label: "Diluted Shares", field: "weighted_average_shares_diluted", fmt: "shares" },
  ],
  balance: [
    { label: "Cash & Equivalents", field: "cash_and_equivalents" }, { label: "Total Assets", field: "total_assets" },
    { label: "Total Liabilities", field: "total_liabilities" }, { label: "Total Debt", field: "total_debt" },
    { label: "Shareholder Equity", field: "shareholder_equity" },
  ],
  cashflow: [
    { label: "Operating Cash Flow", field: "operating_cash_flow" }, { label: "Capital Expenditures", field: "capital_expenditures" },
    { label: "Free Cash Flow", field: "free_cash_flow" }, { label: "Dividends Paid", field: "dividends_paid" }, { label: "Share Repurchases", field: "share_repurchases" },
  ],
};

function fv(v: number | null, kind?: Fmt) {
  if (kind === "price") return fmtPrice(v);
  if (kind === "shares") return fmtShares(v);
  return money(v);
}

export default function FinancialsPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const [period, setPeriod] = useState("annual");
  const cfa = useApi(() => api.cashflowAnalysis(ticker, period), [ticker, period]);
  const income = useApi(() => api.income(ticker, period), [ticker, period]);
  const balance = useApi(() => api.balance(ticker, period), [ticker, period]);
  const cashflow = useApi(() => api.cashflow(ticker, period), [ticker, period]);

  const periods = cfa.data?.periods ?? [];
  const label = (p: any) => (p.period === "FY" ? String(p.fiscal_year) : `${String(p.fiscal_year).slice(2)}${p.period}`);

  // oldest -> newest for charts
  const chrono = periods.slice(0, 8).slice().reverse();
  const revVsFcf = chrono.map((p: any) => ({ label: label(p), revenue: p.revenue, fcf: p.free_cash_flow }));
  const margins = chrono.map((p: any) => {
    const inc = (income.data?.statements ?? []).find((s: any) => s.fiscal_year === p.fiscal_year && s.period === p.period);
    return {
      label: label(p),
      gross: inc?.gross_profit && p.revenue ? inc.gross_profit / p.revenue : null,
      operating: inc?.operating_income && p.revenue ? inc.operating_income / p.revenue : null,
      net: p.net_income && p.revenue ? p.net_income / p.revenue : null,
    };
  });
  const growth = chrono.map((p: any, i: number) => ({
    label: label(p),
    growth: i > 0 && chrono[i - 1].revenue ? p.revenue / chrono[i - 1].revenue - 1 : null,
  }));

  const insights = [growthInsight(periods), fcfQualityInsight(periods), capitalReturnInsight(periods)];

  const hasRevenue = revVsFcf.some((p: any) => p.revenue != null);
  const hasFcf = revVsFcf.some((p: any) => p.fcf != null);
  const hasMargins = margins.some((m: any) => m.gross != null || m.operating != null || m.net != null);
  const hasGrowth = growth.some((g: any) => g.growth != null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-2xl font-semibold tracking-tight">Financials</h2>
        <Toggle options={PERIODS} value={period} onChange={setPeriod} />
      </div>
      <SourceBadge servedBy={cfa.meta?.served_by} stale={cfa.meta?.stale} />

      <StateView loading={cfa.loading} error={cfa.error} empty={!periods.length} emptyLabel={`No financial statements available for ${ticker} yet.`}>
        <InsightStrip insights={insights} />

        <Panel title="Revenue vs Free Cash Flow" hint={hasFcf ? "does revenue turn into cash? (bars = revenue, line = FCF)" : "revenue (FCF not available for this issuer)"}>
          {hasRevenue ? (
            <ComboChart data={revVsFcf} xKey="label"
              bars={[{ key: "revenue", name: "Revenue", color: "#5a48d6" }]}
              lines={hasFcf ? [{ key: "fcf", name: "Free Cash Flow", color: "#3ECF8E" }] : []}
              leftFmt={(v) => money(v)} />
          ) : (
            <NoData title="Revenue not available" message={`No standardized income-statement data for ${ticker}.`} />
          )}
        </Panel>

        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Margins" hint="gross · operating · net">
            {hasMargins ? (
              <MetricCompareChart data={margins} xKey="label" fmt={(v) => pct(v, 0)}
                lines={[{ key: "gross", name: "Gross", color: "#7C6CFF" }, { key: "operating", name: "Operating", color: "#5B8CFF" }, { key: "net", name: "Net", color: "#3ECF8E" }]} />
            ) : (
              <NoData title="Margins not available" message={`Profit-margin data isn't reported for ${ticker}.`} />
            )}
          </Panel>
          <Panel title="Revenue growth" hint="year over year">
            {hasGrowth ? (
              <ComboChart data={growth} xKey="label" bars={[{ key: "growth", name: "YoY growth", color: "#7C6CFF" }]} leftFmt={(v) => pct(v, 0)} />
            ) : (
              <NoData title="Growth not available" message={`Not enough revenue history for ${ticker}.`} />
            )}
          </Panel>
        </div>

        {/* Raw statements, tucked away */}
        <div className="space-y-3">
          {(["income", "balance", "cashflow"] as const).map((kind) => {
            const src = { income: income, balance: balance, cashflow: cashflow }[kind];
            const statements = (src.data?.statements ?? []).slice(0, 8);
            return (
              <Collapsible key={kind} title={`${kind === "income" ? "Income statement" : kind === "balance" ? "Balance sheet" : "Cash flow statement"} (raw)`}>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-sm">
                    <thead>
                      <tr className="text-left text-muted">
                        <th className="px-2 py-1.5 font-medium">Line item</th>
                        <th className="px-2 py-1.5 font-medium">Trend</th>
                        {statements.map((s: any, i: number) => <th key={i} className="px-2 py-1.5 text-right font-medium">{s.fiscal_year}{s.period !== "FY" ? ` ${s.period}` : ""}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {ROWS[kind].map((r) => {
                        const series = statements.slice().reverse().map((s: any) => s[r.field]).filter((x: any) => x != null);
                        return (
                          <tr key={r.field} className="border-t border-line">
                            <td className="px-2 py-1.5 text-muted">{r.label}</td>
                            <td className="px-2 py-1.5"><div className="h-6 w-20"><Sparkline data={series} height={24} /></div></td>
                            {statements.map((s: any, i: number) => <td key={i} className="px-2 py-1.5 text-right font-mono">{fv(s[r.field] ?? null, r.fmt)}</td>)}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Collapsible>
            );
          })}
        </div>
      </StateView>
    </div>
  );
}
