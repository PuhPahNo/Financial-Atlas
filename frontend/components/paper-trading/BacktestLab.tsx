"use client";

import { useEffect, useState } from "react";
import { paperTradingApi } from "@/lib/paperTradingApi";
import { Btn, Icon, Segmented, TextInput } from "./ptkit";
import { AreaChart, Donut, ReturnBars, drawdownOf, Pt } from "./ptcharts";
import { fmt, REGIMES, Model } from "./ptdata";

interface Result {
  equity: Pt[]; bench: Pt[];
  stats: { final: number; totalRet: number; alpha: number; cagr: number; maxDD: number; winRate: number; best: number; worst: number };
  trades: any[]; holdings: { ticker: string; w: number }[]; warnings: string[];
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div style={{ position: "relative" }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ width: "100%", appearance: "none", WebkitAppearance: "none", cursor: "pointer",
        padding: "11px 38px 11px 14px", background: "var(--surface-2)", color: "var(--text-1)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", fontSize: 14, fontFamily: "var(--font-sans)", outline: "none" }}>
        {options.map((o) => <option key={o.value} value={o.value} style={{ background: "#16161e" }}>{o.label}</option>)}
      </select>
      <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--text-3)" }}><Icon name="chevronDown" size={15} /></span>
    </div>
  );
}

function Tile({ label, value, tone, big }: { label: string; value: string; tone?: "pos" | "neg"; big?: boolean }) {
  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <div className="eyebrow" style={{ marginBottom: 7 }}>{label}</div>
      <div className="mono" style={{ fontSize: big ? 24 : 18, fontWeight: 600, color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--text-1)" }}>{value}</div>
    </div>
  );
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span style={{ width: 16, height: 2.5, background: dashed ? "none" : color, borderTop: dashed ? `2.5px dashed ${color}` : "none", display: "inline-block" }} />
      <span style={{ fontSize: 12, color: "var(--text-2)" }}>{label}</span>
    </div>
  );
}

function adapt(data: any, capital: number): Result {
  const curve = data.run?.equity_curve ?? [];
  const equity: Pt[] = curve.map((p: any, i: number) => ({ t: i, v: p.equity, d: p.date }));
  const bench: Pt[] = curve.map((p: any, i: number) => ({ t: i, v: p.benchmark_equity ?? p.equity, d: p.date }));
  const start = equity[0]?.v ?? capital;
  const final = equity[equity.length - 1]?.v ?? capital;
  const totalRet = start ? (final / start - 1) * 100 : 0;
  const bStart = bench[0]?.v ?? capital, bFinal = bench[bench.length - 1]?.v ?? capital;
  const benchRet = bStart ? (bFinal / bStart - 1) * 100 : 0;
  const n = equity.length || 1;
  const cagr = start ? (Math.pow(final / start, 252 / n) - 1) * 100 : 0;
  const { maxDD } = drawdownOf(equity);
  const m = data.run?.metrics ?? {};
  const winRate = (m.win_rate != null ? (m.win_rate <= 1.5 ? m.win_rate * 100 : m.win_rate) : 0);
  const trades = data.run?.trades ?? [];
  const pnls = trades.map((t: any) => t.value).filter((v: any) => typeof v === "number");
  const holdingsRaw = data.holdings ?? [];
  const holdings = holdingsRaw.length
    ? holdingsRaw.map((h: any) => ({ ticker: h.ticker ?? "—", w: Math.round((h.weight ?? h.w ?? 0) * ((h.weight ?? h.w ?? 0) <= 1 ? 100 : 1)) })).filter((h: any) => h.w > 0)
    : [{ ticker: "Cash", w: 100 }];
  return {
    equity, bench,
    stats: { final, totalRet, alpha: totalRet - benchRet, cagr, maxDD, winRate, best: pnls.length ? Math.max(...pnls) : 0, worst: pnls.length ? Math.min(...pnls) : 0 },
    trades, holdings, warnings: data.run?.warnings ?? [],
  };
}

export default function BacktestLab({ models, preselectId, initialRegime }: { models: Model[]; preselectId?: number | null; initialRegime?: string }) {
  const [stratId, setStratId] = useState<number>(preselectId || models[0]?.id);
  const [regimeId, setRegimeId] = useState(initialRegime || "gfc");
  const [capital, setCapital] = useState(100000);
  const [result, setResult] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const model = models.find((m) => m.id === stratId) || models[0];
  const regime = REGIMES.find((r) => r.id === regimeId)!;

  async function run() {
    if (!model) return;
    setRunning(true); setResult(null); setError(null);
    try {
      const res = await paperTradingApi.runBacktest({
        strategy_id: model.id, tickers: model.parameters?.tickers ?? [],
        start_date: regime.start, end_date: regime.end, starting_cash: capital, benchmark: "SPY",
      });
      setResult(adapt(res.data, capital));
    } catch (e: any) {
      setError(e.message || "Backtest failed.");
    } finally { setRunning(false); }
  }
  // run when the chosen strategy/regime changes (and on mount)
  useEffect(() => { run(); /* eslint-disable-next-line */ }, [stratId, regimeId]);

  const up = result && result.stats.totalRet >= 0;
  const beat = result && result.stats.alpha >= 0;

  return (
    <div style={{ animation: "pt-fadeUp .3s var(--ease)", display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="card" style={{ padding: 20, display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 240px" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Strategy</div>
          <Select value={String(stratId)} onChange={(v) => setStratId(Number(v))} options={models.map((m) => ({ value: String(m.id), label: m.name }))} />
        </div>
        <div style={{ flex: "0 1 160px" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Starting capital</div>
          <TextInput mono value={capital} onChange={(v) => setCapital(Math.max(1000, parseInt(v.replace(/\D/g, "") || "0", 10)))} />
        </div>
        <Btn variant="primary" icon="play" iconFill onClick={run} style={{ minWidth: 110 }}>{running ? "Running…" : "Run"}</Btn>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Historical regime</div>
          <Segmented options={REGIMES.map((r) => ({ id: r.id, label: r.label }))} value={regimeId} onChange={setRegimeId} size="sm" />
        </div>
        <span style={{ fontSize: 12.5, color: "var(--text-3)" }}>{regime.sub} · {regime.start} → {regime.end}</span>
      </div>

      {model?.isRule && model.methodology && (
        <div className="card" style={{ padding: "13px 16px", display: "flex", gap: 10, alignItems: "flex-start", background: "var(--surface-2)" }}>
          <span style={{ color: "var(--accent-2)", marginTop: 1 }}><Icon name="sparkles" size={15} fill /></span>
          <div style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
            <strong style={{ color: "var(--text-1)" }}>Signal rule. </strong>{model.methodology}
          </div>
        </div>
      )}

      {running && (
        <div className="card" style={{ height: 320, display: "grid", placeItems: "center", color: "var(--text-3)" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ width: 30, height: 30, border: "3px solid var(--surface-3)", borderTopColor: "var(--accent)", borderRadius: 999, margin: "0 auto 14px", animation: "pt-spin .8s linear infinite" }} />
            <div className="mono" style={{ fontSize: 13 }}>Simulating {model?.name} · {regime.label}…</div>
          </div>
        </div>
      )}

      {error && !running && (
        <div className="card" style={{ padding: 24, color: "var(--neg)", fontSize: 14 }}>{error}</div>
      )}

      {result && !running && (
        <>
          <div className="card" style={{ padding: 24 }}>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 8 }}>
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Ending balance · {model?.name}</div>
                <div className="mono" style={{ fontSize: 34, fontWeight: 600, color: up ? "var(--pos)" : "var(--neg)" }}>{fmt.usd0(result.stats.final)}</div>
              </div>
              <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
                <Legend color={up ? "var(--pos)" : "var(--neg)"} label={model?.name || "Strategy"} />
                <Legend color="var(--text-3)" label="S&P 500" dashed />
              </div>
            </div>
            <AreaChart series={result.equity} benchmark={result.bench} color={up ? "var(--pos)" : "var(--neg)"} height={230} uid="bt" valueFmt={fmt.usd0} seriesLabel={(model?.name?.length ?? 0) > 16 ? "Strategy" : (model?.name || "Strategy")} benchLabel="S&P 500" />
            <div style={{ marginTop: 10, padding: "10px 14px", background: beat ? "var(--pos-soft)" : "var(--neg-soft)", borderRadius: "var(--r-sm)", fontSize: 13, color: beat ? "var(--pos)" : "var(--neg)", fontWeight: 500 }}>
              {beat ? `Beat the market by ${result.stats.alpha.toFixed(1)} pts over ${regime.sub.toLowerCase()}.` : `Trailed the market by ${Math.abs(result.stats.alpha).toFixed(1)} pts — the ${regime.sub.toLowerCase()} was unforgiving.`}
            </div>
            {result.warnings.length > 0 && <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-3)" }}>{result.warnings.slice(0, 2).join(" · ")}</div>}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
            <Tile label="Total return" value={fmt.pct(result.stats.totalRet)} tone={up ? "pos" : "neg"} big />
            <Tile label="vs S&P 500" value={fmt.pct(result.stats.alpha)} tone={beat ? "pos" : "neg"} big />
            <Tile label="CAGR" value={fmt.pct(result.stats.cagr)} tone={result.stats.cagr >= 0 ? "pos" : "neg"} />
            <Tile label="Max drawdown" value={result.stats.maxDD.toFixed(1) + "%"} tone="neg" />
            {result.stats.winRate > 0 && <Tile label="Win rate" value={result.stats.winRate.toFixed(0) + "%"} />}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", gap: 18 }}>
            <div className="card" style={{ overflow: "hidden" }}>
              <div style={{ padding: "15px 18px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="eyebrow">Simulated trades</span>
                <span className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>{result.trades.length} fills</span>
              </div>
              <div style={{ maxHeight: 360, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ position: "sticky", top: 0, background: "var(--surface-2)", zIndex: 1 }}>
                      {[{ h: "Date", a: "left" }, { h: "Ticker", a: "left" }, { h: "Side", a: "left" }, { h: "Qty", a: "right" }, { h: "Price", a: "right" }, { h: "Value", a: "right" }, { h: "Reason", a: "left" }].map((c) => (
                        <th key={c.h} style={{ textAlign: c.a as any, padding: "10px 16px", fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", fontWeight: 600 }}>{c.h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.length === 0 && <tr><td colSpan={7} style={{ padding: 24, textAlign: "center", color: "var(--text-3)" }}>No fills in this period (tickers may lack history for {regime.label}).</td></tr>}
                    {result.trades.map((t: any, i: number) => (
                      <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                        <td className="mono" style={{ padding: "10px 16px", color: "var(--text-3)" }}>{t.date}</td>
                        <td className="mono" style={{ padding: "10px 16px", color: "var(--accent-2)", fontWeight: 600 }}>{t.ticker}</td>
                        <td style={{ padding: "10px 16px" }}><span style={{ fontSize: 10.5, fontWeight: 600, padding: "2px 7px", borderRadius: 999, color: /sell|short/i.test(t.side) ? "var(--neg)" : "var(--pos)", background: "var(--surface-2)" }}>{String(t.side).toUpperCase()}</span></td>
                        <td className="mono" style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-2)" }}>{typeof t.quantity === "number" ? t.quantity.toFixed(2) : t.quantity}</td>
                        <td className="mono" style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-2)" }}>{typeof t.price === "number" ? fmt.usd(t.price) : "—"}</td>
                        <td className="mono" style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-1)", fontWeight: 600 }}>{typeof t.value === "number" ? fmt.usd0(t.value) : "—"}</td>
                        <td style={{ padding: "10px 16px", color: "var(--text-3)", fontSize: 11.5, maxWidth: 190, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={t.reason}>{t.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div className="card" style={{ padding: 20 }}>
                <div className="eyebrow" style={{ marginBottom: 16 }}>Final allocation</div>
                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                  <Donut data={result.holdings} size={112} thickness={14} />
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
                    {result.holdings.map((h, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                        <span className="mono" style={{ color: "var(--text-2)" }}>{h.ticker}</span>
                        <span className="mono" style={{ color: "var(--text-1)" }}>{h.w}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className="card" style={{ padding: 20 }}>
                <div className="eyebrow" style={{ marginBottom: 14 }}>Period returns</div>
                <ReturnBars series={result.equity} height={64} />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
