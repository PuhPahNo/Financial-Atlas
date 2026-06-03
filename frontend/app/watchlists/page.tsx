"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { price as fmtPrice, pct, signClass } from "@/lib/format";
import { Card, StateView } from "@/components/ui";
import SearchBar from "@/components/SearchBar";

export default function WatchlistsPage() {
  const [lists, setLists] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  async function refresh() { const res = await api.watchlists(); setLists(res.data.watchlists); setLoading(false); }
  useEffect(() => { refresh(); }, []);

  async function createList() { if (!newName.trim()) return; await api.createWatchlist(newName.trim()); setNewName(""); refresh(); }
  async function addItem(id: number, ticker: string) {
    if (!ticker) return;
    setBusy(id);
    try { await api.addWatchlistItem(id, ticker); await refresh(); } finally { setBusy(null); }
  }
  async function removeItem(id: number, ticker: string) { await api.removeWatchlistItem(id, ticker); refresh(); }
  async function deleteList(id: number) { await api.deleteWatchlist(id); refresh(); }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Watchlists</h1>
        <div className="flex gap-2">
          <input value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && createList()}
            placeholder="New watchlist name" className="rounded-lg border border-line bg-surface-2 px-3.5 py-2.5 text-sm outline-none focus:border-accent" />
          <button onClick={createList} className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white shadow-glow">Create</button>
        </div>
      </div>

      <StateView loading={loading} empty={!lists.length} emptyLabel="No watchlists yet. Create one above.">
        <div className="space-y-5">
          {lists.map((wl) => {
            const maxUp = Math.max(0.01, ...wl.items.map((it: any) => Math.abs(it.upside_pct ?? 0)));
            return (
              <Card key={wl.id} className="p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="font-serif text-lg font-semibold">{wl.name}</h2>
                  <button onClick={() => deleteList(wl.id)} className="rounded-md px-2 py-1 text-xs text-muted transition-colors hover:text-negative">Delete list</button>
                </div>

                <div className="mb-4 flex items-center gap-3">
                  <div className="max-w-xs flex-1">
                    <SearchBar placeholder="Search a company to add…" onSelect={(ticker) => addItem(wl.id, ticker)} />
                  </div>
                  {busy === wl.id && <span className="text-xs text-muted">Adding…</span>}
                </div>

                {wl.items.length === 0 ? (
                  <p className="text-sm text-muted">No tickers yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-sm">
                      <thead>
                        <tr className="text-left text-muted">
                          <th className="py-2 pr-3 font-medium">Ticker</th><th className="py-2 pr-3 font-medium">Name</th>
                          <th className="py-2 pr-3 text-right font-medium">Price</th><th className="py-2 pr-3 text-right font-medium">Fair Value</th>
                          <th className="py-2 pr-3 font-medium">Upside</th><th className="py-2 pr-3 text-right font-medium">MoS</th><th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {wl.items.map((it: any) => (
                          <tr key={it.ticker} className="border-t border-line">
                            <td className="py-2.5 pr-3"><Link href={`/company/${it.ticker}`} className="font-mono font-semibold text-accent hover:underline">{it.ticker}</Link></td>
                            <td className="py-2.5 pr-3 max-w-[180px] truncate text-muted">{it.name ?? (it.pending ? "loading…" : "—")}</td>
                            <td className="py-2.5 pr-3 text-right font-mono">{fmtPrice(it.price)}</td>
                            <td className="py-2.5 pr-3 text-right font-mono">{fmtPrice(it.blended_fair_value)}</td>
                            <td className="py-2.5 pr-3">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
                                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, (Math.abs(it.upside_pct ?? 0) / maxUp) * 100)}%`, background: (it.upside_pct ?? 0) >= 0 ? "#3ECF8E" : "#FF6B6B" }} />
                                </div>
                                <span className={`w-12 font-mono text-xs ${signClass(it.upside_pct)}`}>{pct(it.upside_pct)}</span>
                              </div>
                            </td>
                            <td className={`py-2.5 pr-3 text-right font-mono ${signClass(it.margin_of_safety)}`}>{pct(it.margin_of_safety)}</td>
                            <td className="py-2.5 text-right"><button onClick={() => removeItem(wl.id, it.ticker)} className="text-muted transition-colors hover:text-negative">✕</button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </StateView>
    </div>
  );
}
