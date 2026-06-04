"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { getRecents } from "@/lib/recents";
import { money, price, pct, ratio, signClass } from "@/lib/format";
import { Card, SectionTitle, StateView, Toggle } from "@/components/ui";
import SearchBar from "@/components/SearchBar";
import Sparkline from "@/components/charts/Sparkline";

export default function Dashboard() {
  const context = useApi(() => api.marketContext(), []);
  const picks = useApi(() => api.bestPicks(6), []);
  const movers = useApi(() => api.marketMovers(), []);
  const watchlists = useApi(() => api.watchlists(), []);
  const [moverTab, setMoverTab] = useState<"gainers" | "losers">("gainers");
  const [recents, setRecents] = useState<string[]>([]);
  useEffect(() => setRecents(getRecents()), []);

  return (
    <div className="space-y-8">
      {/* Hero — search is the centerpiece */}
      <div className="flex flex-col items-center gap-7 pb-2 pt-10 text-center">
        <div>
          <h1 className="font-serif text-5xl font-semibold tracking-tightest">Good to see you.</h1>
          <p className="mt-3 text-muted">Search any company — or dive into your picks and the market below.</p>
        </div>
        <div className="w-full max-w-2xl">
          <SearchBar large autoFocus />
        </div>
        <div className="flex flex-wrap justify-center gap-3">
          {(context.data?.indices ?? []).map((idx: any) => (
            <div key={idx.symbol} className="flex items-center gap-3 rounded-lg border border-line bg-surface/60 px-4 py-2.5">
              <div className="text-left">
                <div className="text-xs text-muted">{idx.label}</div>
                <div className="font-mono text-sm">{idx.price?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
              </div>
              <div className={`font-mono text-xs ${signClass(idx.change_pct)}`}>{pct(idx.change_pct, 2)}</div>
              <div className="w-16"><Sparkline data={idx.points ?? []} height={28} /></div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Best picks */}
        <section className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <SectionTitle>Best picks</SectionTitle>
            <span className="text-xs text-muted">highest margin of safety in your universe</span>
          </div>
          <StateView loading={picks.loading} error={picks.error} empty={!picks.data?.picks?.length} emptyLabel="Ingest companies in the Screener to populate picks.">
            <div className="grid gap-3 sm:grid-cols-2">
              {(picks.data?.picks ?? []).map((p: any) => (
                <Link key={p.ticker} href={`/company/${p.ticker}`} className="group rounded-xl border border-line bg-surface/60 p-4 transition-colors hover:border-accent/50">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-mono font-semibold text-accent-2">{p.ticker}</div>
                      <div className="mt-0.5 max-w-[150px] truncate text-xs text-muted">{p.name}</div>
                    </div>
                    <div className={`rounded-full px-2 py-0.5 text-xs font-medium ${(p.margin_of_safety ?? 0) >= 0 ? "bg-positive/10 text-positive" : "bg-negative/10 text-negative"}`}>
                      {pct(p.margin_of_safety, 0)} MoS
                    </div>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between text-sm">
                    <span className="font-mono">{price(p.price)}</span>
                    <span className="text-xs text-muted">fair {price(p.blended_fair_value)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </StateView>
        </section>

        {/* Right column */}
        <div className="space-y-6">
          {/* Your interests */}
          <Card className="p-5">
            <div className="mb-3 text-[11px] uppercase tracking-wider text-muted">Your interests</div>
            {watchlists.error && recents.length === 0 ? (
              <p className="text-sm text-muted">
                <Link href="/login?next=/" className="text-accent hover:underline">Sign in</Link>
                {" "}to view watchlists.
              </p>
            ) : recents.length === 0 && !(watchlists.data?.watchlists?.length) ? (
              <p className="text-sm text-muted">Search a ticker to start — recents and watchlists show here.</p>
            ) : (
              <div className="space-y-4">
                {recents.length > 0 && (
                  <div>
                    <div className="mb-2 text-xs text-faint">Recently viewed</div>
                    <div className="flex flex-wrap gap-2">
                      {recents.map((t) => (
                        <Link key={t} href={`/company/${t}`} className="rounded-md border border-line bg-surface-2/50 px-2.5 py-1 font-mono text-xs hover:border-accent">{t}</Link>
                      ))}
                    </div>
                  </div>
                )}
                {(watchlists.data?.watchlists ?? []).map((wl: any) => (
                  <div key={wl.id}>
                    <div className="mb-1.5 flex items-center justify-between text-xs">
                      <span className="text-faint">{wl.name}</span>
                      <Link href="/watchlists" className="text-accent hover:underline">open</Link>
                    </div>
                    {wl.items.slice(0, 4).map((it: any) => (
                      <Link key={it.ticker} href={`/company/${it.ticker}`} className="flex items-center justify-between py-1 text-sm hover:text-accent-2">
                        <span className="font-mono">{it.ticker}</span>
                        <span className={`font-mono text-xs ${signClass(it.upside_pct)}`}>{pct(it.upside_pct)}</span>
                      </Link>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Market context */}
          <Card className="p-5">
            <div className="mb-3 text-[11px] uppercase tracking-wider text-muted">Market context</div>
            <div className="space-y-3">
              {(context.data?.indices ?? []).map((idx: any) => (
                <div key={idx.symbol} className="flex items-center gap-3">
                  <div className="w-24 text-sm">{idx.label}</div>
                  <div className="flex-1"><Sparkline data={idx.points ?? []} height={30} /></div>
                  <div className={`w-14 text-right font-mono text-xs ${signClass(idx.change_pct)}`}>{pct(idx.change_pct, 2)}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* Movers */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <SectionTitle>Biggest movers</SectionTitle>
          <Toggle options={[{ label: "Gainers", value: "gainers" }, { label: "Losers", value: "losers" }]} value={moverTab} onChange={setMoverTab} />
        </div>
        <StateView loading={movers.loading} error={movers.error} empty={!(movers.data?.[moverTab]?.length)} emptyLabel="Movers need the FMP key (or are unavailable right now).">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {(movers.data?.[moverTab] ?? []).slice(0, 12).map((m: any) => (
              <Link key={m.ticker} href={`/company/${m.ticker}`} className="flex items-center justify-between rounded-lg border border-line bg-surface/60 px-4 py-2.5 transition-colors hover:border-accent/50">
                <div>
                  <div className="font-mono font-semibold">{m.ticker}</div>
                  <div className="max-w-[160px] truncate text-xs text-muted">{m.name}</div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm">{price(m.price)}</div>
                  <div className={`font-mono text-xs ${signClass(m.change_pct)}`}>{pct(m.change_pct, 1)}</div>
                </div>
              </Link>
            ))}
          </div>
          {movers.data?.scope === "universe" && <p className="text-xs text-faint">Showing your ingested universe — add the FMP key for market-wide movers.</p>}
        </StateView>
      </section>
    </div>
  );
}
