"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { money, shares as fmtShares, price as fmtPrice, signClass } from "@/lib/format";
import { insiderInsight } from "@/lib/insights";
import { Card, Panel, SourceBadge, StateView } from "@/components/ui";
import InsightStrip from "@/components/InsightStrip";
import Collapsible from "@/components/Collapsible";
import InsiderTimeline from "@/components/charts/InsiderTimeline";

const CODE_LABEL: Record<string, string> = { P: "Buy", S: "Sell", A: "Grant", M: "Exercise", F: "Tax", G: "Gift", C: "Conv", X: "Exercise", D: "Disp" };

export default function OwnershipPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const ins = useApi(() => api.insiders(ticker), [ticker]);
  const inst = useApi(() => api.institutions(ticker), [ticker]);

  const txns = ins.data?.transactions ?? [];
  const summary = ins.data?.summary ?? {};

  // aggregate net open-market $ by insider
  const byInsider = new Map<string, number>();
  for (const t of txns) {
    if (!t.is_open_market || t.value == null || !t.insider_name) continue;
    byInsider.set(t.insider_name, (byInsider.get(t.insider_name) ?? 0) + (t.acquired_disposed === "A" ? t.value : -t.value));
  }
  const topInsiders = [...byInsider.entries()].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 6);

  return (
    <div className="space-y-6">
      <h2 className="font-serif text-2xl font-semibold tracking-tight">Ownership</h2>
      <SourceBadge servedBy={ins.meta?.served_by} stale={ins.meta?.stale} />

      <StateView loading={ins.loading} error={ins.error} empty={!txns.length} emptyLabel="No recent insider filings.">
        <InsightStrip insights={[
          insiderInsight(summary),
          summary.cluster_buy ? { label: "Signal", value: "Cluster buy", tone: "positive", detail: "Multiple insiders bought in open market within a short window." } : null,
          { label: "Open-market buys / sells", value: `${summary.buy_count ?? 0} / ${summary.sell_count ?? 0}`, tone: "neutral" },
        ]} />

        <Panel title="Insider activity over time" hint="net $ value of insider trades per month — green = buying, red = selling">
          <InsiderTimeline transactions={txns} />
        </Panel>

        {topInsiders.length > 0 && (
          <Panel title="Most active insiders" hint="net open-market value">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {topInsiders.map(([name, net]) => (
                <div key={name} className="rounded-lg border border-line bg-surface/60 px-4 py-3">
                  <div className="truncate text-sm">{name}</div>
                  <div className={`mt-1 font-mono ${signClass(net)}`}>{net >= 0 ? "+" : ""}{money(net)}</div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        <Panel title="Large stakes (13D / 13G)">
          <StateView loading={inst.loading} empty={!inst.data?.large_stakes?.length} emptyLabel="No 13D/13G filings on record.">
            <p className="mb-3 text-xs text-faint">{inst.data?.note}</p>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(inst.data?.large_stakes ?? []).slice(0, 9).map((s: any, i: number) => (
                <a key={i} href={s.primary_doc_url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between rounded-lg border border-line bg-surface/60 px-3 py-2 text-sm hover:border-accent">
                  <span className="font-mono text-xs">{s.filing_date}</span>
                  <span>{s.form_type}</span>
                  <span className={s.intent === "active" ? "text-negative" : "text-muted"}>{s.intent}</span>
                </a>
              ))}
            </div>
          </StateView>
        </Panel>

        <Collapsible title="All insider transactions (raw)">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="px-2 py-1.5 font-medium">Date</th><th className="px-2 py-1.5 font-medium">Insider</th>
                  <th className="px-2 py-1.5 font-medium">Role</th><th className="px-2 py-1.5 font-medium">Type</th>
                  <th className="px-2 py-1.5 text-right font-medium">Shares</th><th className="px-2 py-1.5 text-right font-medium">Price</th><th className="px-2 py-1.5 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                {txns.slice(0, 40).map((t: any, i: number) => (
                  <tr key={i} className="border-t border-line">
                    <td className="px-2 py-1.5 font-mono">{t.transaction_date}</td>
                    <td className="px-2 py-1.5">{t.insider_name}</td>
                    <td className="px-2 py-1.5 text-muted">{t.relationship || t.insider_title || "—"}</td>
                    <td className={`px-2 py-1.5 ${t.acquired_disposed === "A" ? "text-positive" : t.acquired_disposed === "D" ? "text-negative" : ""}`}>{CODE_LABEL[t.transaction_code] ?? t.transaction_code}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtShares(t.shares)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{fmtPrice(t.price)}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{money(t.value)}</td>
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
