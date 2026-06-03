"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { money, price, pct, ratio, shares as fmtShares, signClass } from "@/lib/format";
import { valuationInsight, growthInsight, fcfQualityInsight, healthInsight } from "@/lib/insights";
import { Card, Panel, SourceBadge, StateView } from "@/components/ui";
import InsightStrip from "@/components/InsightStrip";
import AnalystSnapshot from "@/components/AnalystSnapshot";
import NewsList from "@/components/NewsList";
import PeerTable from "@/components/PeerTable";
import Sparkline from "@/components/charts/Sparkline";

export default function OverviewPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const snapshot = useApi(() => api.companySnapshot(ticker), [ticker]);

  const data = snapshot.data;
  const company = data?.company;
  const valuation = data?.valuation;
  const cashFlow = data?.cash_flow_analysis;
  const analyst = data?.analyst;
  const news = data?.news;
  const peers = data?.peers;
  const priceHistory = data?.prices;
  const warnings = data?.warnings ?? [];

  const km = company?.key_metrics;
  const periods = cashFlow?.periods ?? [];
  const closes = (priceHistory?.bars ?? []).map((b: any) => b.close).filter((c: number | null) => c != null);

  const insights = [
    valuationInsight(valuation ?? {}),
    growthInsight(periods),
    fcfQualityInsight(periods),
    healthInsight(km ?? {}),
  ];

  return (
    <StateView loading={snapshot.loading} error={snapshot.error} empty={!company}>
      {company && (
        <div className="space-y-7">
          {/* Hero */}
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="text-xs uppercase tracking-[0.14em] text-accent-2">
                {[company.profile.exchange, company.profile.industry].filter(Boolean).join(" · ") || "—"}
              </div>
              <h1 className="mt-2 font-serif text-4xl font-semibold tracking-tightest">{company.profile.name ?? ticker}</h1>
              <div className="mt-2 font-mono text-sm text-muted">{ticker}</div>
            </div>
            <div className="flex items-end gap-5">
              {closes.length > 1 && <div className="hidden h-12 w-32 sm:block"><Sparkline data={closes} height={48} /></div>}
              <div className="text-right">
                <div className="font-mono text-4xl font-medium tracking-tightest">{price(km?.price)}</div>
                <div className={`mt-1 font-mono text-sm ${signClass(km?.change_abs)}`}>
                  {money(km?.change_abs, { sign: true })} ({pct(km?.change_pct, 2)})
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <SourceBadge servedBy={data?.sections?.company?.served_by ?? snapshot.meta?.served_by} stale={data?.sections?.company?.stale ?? snapshot.meta?.stale} />
            {warnings.length > 0 && (
              <span className="rounded-full border border-line bg-surface-2/60 px-2.5 py-1 text-[11px] text-muted">
                {warnings.length} provider {warnings.length === 1 ? "note" : "notes"}
              </span>
            )}
          </div>

          {warnings.length > 0 && (
            <div className="rounded-lg border border-line bg-surface-2/35 px-4 py-3 text-xs text-muted">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-faint">Provider notes</div>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {warnings.slice(0, 4).map((warning: any, i: number) => (
                  <span key={`${warning.section}-${warning.code}-${i}`}>
                    <span className="text-text">{warning.section?.replaceAll("_", " ") ?? "Data"}</span>: {warning.message}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Insight strip — leads with the answer */}
          <InsightStrip insights={insights} />

          <div className="grid gap-5 lg:grid-cols-3">
            {/* Grouped metrics + peers */}
            <div className="space-y-5 lg:col-span-2">
              <MetricGroup title="Valuation" items={[
                ["Market Cap", money(km?.market_cap)],
                ["P / E", ratio(km?.pe)],
                ["Price / FCF", ratio(km?.price_to_fcf)],
                ["EV / EBITDA", ratio(km?.ev_ebitda)],
              ]} />
              <MetricGroup title="Quality & income" items={[
                ["FCF Margin", pct(periods[0]?.fcf_margin)],
                ["FCF Conversion", pct(periods[0]?.fcf_conversion)],
                ["Dividend Yield", pct(km?.dividend_yield, 2)],
                ["FCF / Share", price(periods[0]?.fcf_per_share)],
              ]} />
              <MetricGroup title="Balance sheet" items={[
                [km?.net_debt != null && km.net_debt < 0 ? "Net Cash" : "Net Debt", money(km?.net_debt != null ? Math.abs(km.net_debt) : null)],
                ["Shares Out", fmtShares(km?.shares_outstanding)],
                ["52-Wk Low", price(km?.week52_low)],
                ["52-Wk High", price(km?.week52_high)],
              ]} />
              <Panel title="Peers" hint="similar companies — click to compare">
                <StateView loading={false} empty={!peers?.peers?.length} emptyLabel="No peer data.">
                  <PeerTable peers={(peers?.peers ?? []).slice(0, 8)} />
                </StateView>
              </Panel>
            </div>

            {/* Analyst + news */}
            <div className="space-y-5">
              <Panel title="Wall Street view">
                <StateView loading={false} empty={!analyst?.analyst} emptyLabel="No analyst coverage available.">
                  {analyst?.analyst && <AnalystSnapshot analyst={analyst.analyst} currentPrice={km?.price} />}
                </StateView>
              </Panel>
              <Panel title="Recent news" right={<Link href={`/company/${ticker}/filings`} className="text-xs text-accent hover:underline">Filings →</Link>}>
                <StateView loading={false} empty={!news?.articles?.length} emptyLabel="No recent news.">
                  <NewsList articles={news?.articles ?? []} />
                </StateView>
              </Panel>
            </div>
          </div>
        </div>
      )}
    </StateView>
  );
}

function MetricGroup({ title, items }: { title: string; items: [string, React.ReactNode][] }) {
  return (
    <div>
      <div className="mb-2 text-[11px] uppercase tracking-wider text-muted">{title}</div>
      <div className="metric-grid grid-cols-2 md:grid-cols-4">
        {items.map(([label, value], i) => (
          <div key={i} className="px-5 py-3.5">
            <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
            <div className="mt-1.5 font-mono text-lg">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
