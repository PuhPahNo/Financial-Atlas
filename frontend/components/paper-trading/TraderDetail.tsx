"use client";

import { useEffect, useState } from "react";
import { paperTradingApi, TraderAccount, AccountPerformance } from "@/lib/paperTradingApi";
import { Btn, IconBtn, Pill, CatDot, Icon } from "./ptkit";
import { AreaChart, Pt } from "./ptcharts";
import { CAT_HUES, fmt } from "./ptdata";

function Tile({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  return (
    <div className="card" style={{ padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--r-md)" }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
      <div className="mono" style={{ fontSize: 17, fontWeight: 600, color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--text-1)" }}>{value}</div>
    </div>
  );
}

export default function TraderDetail({ account, onClose, onEdit, onDelete }: {
  account: TraderAccount | null; onClose: () => void; onEdit: (a: TraderAccount) => void; onDelete: (a: TraderAccount) => void }) {
  const [perf, setPerf] = useState<AccountPerformance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPerf(null); setError(null);
    if (!account) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await paperTradingApi.accountPerformance(account.id);
        if (!cancelled) setPerf(res.data);
      } catch (e: any) { if (!cancelled) setError(e.message || "Could not compute performance"); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [account?.id]);

  if (!account) return null;

  const up = perf ? perf.total_return >= 0 : true;
  const beat = perf ? perf.alpha >= 0 : true;
  const equity: Pt[] = perf ? perf.equity.map((p, i) => ({ t: i, v: p.equity, d: p.date })) : [];
  const bench: Pt[] = perf ? perf.equity.map((p, i) => ({ t: i, v: p.benchmark_equity, d: p.date })) : [];

  return (
    <div style={{ padding: "0 0 32px" }}>
      <div style={{ position: "sticky", top: 0, zIndex: 2, background: "var(--surface-1)", borderBottom: "1px solid var(--border)", padding: "20px 24px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", minWidth: 0 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, display: "grid", placeItems: "center", fontSize: 24, background: "var(--surface-2)", border: "1px solid var(--border)", flexShrink: 0 }}>{account.emoji}</div>
            <div style={{ minWidth: 0 }}>
              <h2 className="serif" style={{ margin: 0, fontSize: 25, fontWeight: 600, lineHeight: 1.1 }}>{account.name}</h2>
              <div style={{ fontSize: 12.5, color: "var(--text-3)", marginTop: 3 }}>{account.bio || `${account.allocations.length} strategies · ${fmt.usd0(account.starting_cash)} capital`}</div>
            </div>
          </div>
          <IconBtn icon="x" onClick={onClose} title="Close" />
        </div>
      </div>

      <div style={{ padding: "22px 24px", display: "flex", flexDirection: "column", gap: 24 }}>
        {loading && (
          <div style={{ height: 280, display: "grid", placeItems: "center" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ width: 28, height: 28, border: "3px solid var(--surface-3)", borderTopColor: "var(--accent)", borderRadius: 999, margin: "0 auto 14px", animation: "pt-spin .8s linear infinite" }} />
              <div className="mono" style={{ fontSize: 12.5, color: "var(--text-3)" }}>Blending {account.allocations.length} strategies on real prices…</div>
            </div>
          </div>
        )}
        {error && !loading && <div className="card" style={{ padding: 20, color: "var(--neg)", fontSize: 14 }}>{error}</div>}

        {perf && !loading && (
          <>
            <div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap", marginBottom: 4 }}>
                <span className="mono" style={{ fontSize: 32, fontWeight: 600, color: up ? "var(--pos)" : "var(--neg)" }}>{fmt.usd0(perf.current_value)}</span>
                <Pill tone={up ? "pos" : "neg"}>{fmt.pct(perf.total_return * 100)}</Pill>
                <span style={{ fontSize: 12.5, color: "var(--text-3)" }}>from {fmt.usd0(perf.starting_cash)} · {perf.window.start} → {perf.window.end}</span>
              </div>
              <div className="card" style={{ padding: "14px 8px 4px", background: "var(--surface-2)", borderRadius: "var(--r-md)" }}>
                <AreaChart series={equity} benchmark={bench} color={up ? "var(--pos)" : "var(--neg)"} height={170} uid={"t" + account.id} valueFmt={fmt.usd0} seriesLabel={account.name.length > 16 ? "Account" : account.name} animate={false} />
              </div>
              <div style={{ marginTop: 10, padding: "10px 14px", background: beat ? "var(--pos-soft)" : "var(--neg-soft)", borderRadius: "var(--r-sm)", fontSize: 13, color: beat ? "var(--pos)" : "var(--neg)", fontWeight: 500 }}>
                {beat ? `Beat a 100% S&P 500 portfolio by ${(perf.alpha * 100).toFixed(1)} pts.` : `Trailed a 100% S&P 500 portfolio by ${Math.abs(perf.alpha * 100).toFixed(1)} pts.`}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              <Tile label="Total return" value={fmt.pct(perf.total_return * 100)} tone={up ? "pos" : "neg"} />
              <Tile label="vs S&P 500" value={fmt.pct(perf.alpha * 100)} tone={beat ? "pos" : "neg"} />
              <Tile label="Max DD" value={(perf.max_drawdown * 100).toFixed(1) + "%"} tone="neg" />
              <Tile label="Cash" value={fmt.usd0(perf.cash_dollars)} />
            </div>

            <section>
              <div className="eyebrow" style={{ marginBottom: 12 }}>Strategy contributions</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {perf.contributions.map((c) => {
                  const win = c.pnl >= 0;
                  const hue = (c.category && CAT_HUES[c.category]) || "var(--accent)";
                  return (
                    <div key={c.strategy_id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
                      <CatDot hue={hue} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-1)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.name}</div>
                        <div className="mono" style={{ fontSize: 11.5, color: "var(--text-3)" }}>{c.weight}% · {fmt.usd0(c.dollars)} → {fmt.usd0(c.final)}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div className="mono" style={{ fontSize: 13.5, fontWeight: 600, color: win ? "var(--pos)" : "var(--neg)" }}>{fmt.pct(c.return_pct)}</div>
                        <div className="mono" style={{ fontSize: 11.5, color: win ? "var(--pos)" : "var(--neg)" }}>{win ? "+" : "−"}{fmt.usd0(Math.abs(c.pnl))}</div>
                      </div>
                    </div>
                  );
                })}
                {perf.cash_dollars > 0 && (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "var(--surface-2)", borderRadius: "var(--r-sm)", opacity: 0.8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 999, background: "var(--surface-3)" }} />
                    <span style={{ flex: 1, fontSize: 13.5, color: "var(--text-2)" }}>Uninvested cash</span>
                    <span className="mono" style={{ fontSize: 13.5, color: "var(--text-2)" }}>{fmt.usd0(perf.cash_dollars)}</span>
                  </div>
                )}
              </div>
            </section>

            {perf.warnings.length > 0 && <div style={{ fontSize: 12, color: "var(--text-3)", lineHeight: 1.5 }}>{perf.warnings.slice(0, 3).join(" · ")}</div>}
          </>
        )}
      </div>

      <div style={{ position: "sticky", bottom: 0, background: "linear-gradient(transparent, var(--surface-1) 22%)", padding: "18px 24px", display: "flex", gap: 10 }}>
        <Btn variant="primary" icon="edit" onClick={() => onEdit(account)} style={{ flex: 1 }}>Edit allocation</Btn>
        <IconBtn icon="trash" size={42} tone="danger" title="Delete trader" onClick={() => onDelete(account)} />
      </div>
    </div>
  );
}
