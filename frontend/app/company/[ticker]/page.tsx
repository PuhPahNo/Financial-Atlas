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
  const company = useApi(() => api.company(ticker), [ticker]);
  const valuation = useApi(() => api.valuation(ticker), [ticker]);
  const cfa = useApi(() => api.cashflowAnalysis(ticker, "annual"), [ticker]);
  const analyst = useApi(() => api.analyst(ticker), [ticker]);
  const news = useApi(() => api.news(ticker), [ticker]);
  const peers = useApi(() => api.peers(ticker), [ticker]);
  const prices = useApi(() => api.prices(ticker, "1y", "1d"), [ticker]);

  const km = company.data?.key_metrics;
  const periods = cfa.data?.periods ?? [];
  const closes = (prices.data?.bars ?? []).map((b: any) => b.close).filter((c: number | null) => c != null);

  const insights = [
    valuationInsight(valuation.data ?? {}),
    growthInsight(periods),
    fcfQualityInsight(periods),
    healthInsight(km ?? {}),
  ];

  return (
    <StateView loading={company.loading} error={company.error} empty={!company.data}>
      {company.data && (
        <div className="space-y-7">
          {/* Hero */}
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="text-xs uppercase tracking-[0.14em] text-accent-2">
                {[company.data.profile.exchange, company.data.profile.industry].filter(Boolean).join(" · ") || "—"}
              </div>
              <h1 className="mt-2 font-serif text-4xl font-semibold tracking-tightest">{company.data.profile.name ?? ticker}</h1>
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

          <SourceBadge servedBy={company.meta?.served_by} stale={company.meta?.stale} />

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
                <StateView loading={peers.loading} empty={!peers.data?.peers?.length} emptyLabel="No peer data.">
                  <PeerTable peers={(peers.data?.peers ?? []).slice(0, 8)} />
                </StateView>
              </Panel>
            </div>

            {/* Analyst + news */}
            <div className="space-y-5">
              <Panel title="Wall Street view">
                <StateView loading={analyst.loading} empty={!analyst.data?.analyst} emptyLabel="No analyst coverage available.">
                  {analyst.data?.analyst && <AnalystSnapshot analyst={analyst.data.analyst} currentPrice={km?.price} />}
                </StateView>
              </Panel>
              <Panel title="Recent news" right={<Link href={`/company/${ticker}/filings`} className="text-xs text-accent hover:underline">Filings →</Link>}>
                <StateView loading={news.loading} empty={!news.data?.articles?.length} emptyLabel="No recent news.">
                  <NewsList articles={news.data?.articles ?? []} />
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
