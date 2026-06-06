"use client";

import { useEffect, useState } from "react";
import { paperTradingApi } from "@/lib/paperTradingApi";
import { Btn, CatDot, IconBtn } from "./ptkit";
import { AreaChart, Donut, DONUT_PALETTE, drawdownOf, Pt } from "./ptcharts";
import { fmt, CatMeta, Model, defaultBacktestWindow, metricStateLabel, metricStateTip } from "./ptdata";

function StatBox({ label, value, tone }: { label: string; value: string | number; tone?: "pos" | "neg" }) {
  return (
    <div className="card" style={{ padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--r-md)" }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
      <div className="mono" style={{ fontSize: 17, fontWeight: 600, color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--text-1)" }}>{value}</div>
    </div>
  );
}

interface Live { equity: Pt[]; benchmark?: Pt[]; cagr: number; maxDD: number; winRate: number; trades: number; window: { start: string; end: string } }

export default function ModelDetail({ model, cat, onClose, onEdit, onBacktest, onDelete, onBacktested }: {
  model: Model | null; cat?: CatMeta; onClose: () => void; onEdit: (m: Model) => void; onBacktest: (m: Model) => void; onDelete: (m: Model) => void; onBacktested?: () => void }) {
  const [live, setLive] = useState<Live | null>(null);
  const [running, setRunning] = useState(false);

  // Lazily backtest a model the first time it's opened (seeded models have no run yet),
  // so the detail shows real equity instead of an illustrative series.
  useEffect(() => {
    setLive(null);
    if (!model || model.backtested) return;
    let cancelled = false;
    (async () => {
      setRunning(true);
      try {
        const w = defaultBacktestWindow();
        const res = await paperTradingApi.runBacktest({
          strategy_id: model.id, tickers: model.parameters?.tickers ?? [],
          start_date: w.start, end_date: w.end, starting_cash: 100000, benchmark: "SPY", persist_headline: true,
        });
        if (cancelled) return;
        const eq = res.data.run.equity_curve || [];
        const equity: Pt[] = eq.map((p: any, i: number) => ({ t: i, v: p.equity, d: p.date }));
        const benchmark: Pt[] = eq.map((p: any, i: number) => ({ t: i, v: p.benchmark_equity, d: p.date }));
        const start = equity[0]?.v ?? 100000, final = equity[equity.length - 1]?.v ?? 100000;
        const mm: any = res.data.run.metrics || {};
        setLive({
          equity, benchmark, cagr: (final / start - 1) * 100, maxDD: drawdownOf(equity).maxDD,
          winRate: mm.win_rate != null ? (mm.win_rate <= 1.5 ? mm.win_rate * 100 : mm.win_rate) : 0,
          trades: (res.data.run.trades || []).length, window: w,
        });
        onBacktested?.();
      } catch { /* keep illustrative on failure */ } finally { if (!cancelled) setRunning(false); }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model?.id]);

  if (!model || !cat) return null;

  const isLive = model.backtested || !!live;
  const equity = model.backtested ? model.equity : (live?.equity ?? model.equity);
  const benchmark = model.backtested ? model.benchmark : live?.benchmark;
  const totalRet = model.backtested ? model.sincePct : (live?.cagr ?? model.sincePct);
  const win = model.backtested ? model.backtestWindow : live?.window;
  const stats = live
    ? { ...model.stats, cagr: live.cagr, maxDD: live.maxDD, winRate: live.winRate, trades: live.trades }
    : model.stats;
  const up = totalRet >= 0;

  return (
    <div style={{ padding: "0 0 32px" }}>
      <div style={{ position: "sticky", top: 0, zIndex: 2, background: "var(--surface-1)", borderBottom: "1px solid var(--border)", padding: "20px 24px 18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <CatDot hue={cat.hue} />
              <span className="eyebrow" style={{ color: "var(--text-2)" }}>{cat.label}</span>
              <span style={{ fontSize: 10.5, fontWeight: 600, padding: "2px 7px", borderRadius: 999, color: model.author === "You" ? "var(--accent-2)" : "var(--text-3)", background: model.author === "You" ? "var(--accent-soft)" : "var(--surface-3)" }}>
                {model.author === "You" ? "Custom build" : "Atlas model"}</span>
              <span title={metricStateTip(model)} style={{ fontSize: 10.5, fontWeight: 600, padding: "2px 7px", borderRadius: 999, color: model.backtested ? "var(--pos)" : "var(--text-3)", background: model.backtested ? "var(--pos-soft)" : "var(--surface-3)" }}>
                {metricStateLabel(model)}</span>
            </div>
            <h2 className="serif" style={{ margin: 0, fontSize: 28, fontWeight: 600, lineHeight: 1.1 }}>{model.name}</h2>
          </div>
          <IconBtn icon="x" onClick={onClose} title="Close" />
        </div>
      </div>

      <div style={{ padding: "22px 24px", display: "flex", flexDirection: "column", gap: 26 }}>
        <p style={{ margin: 0, fontSize: 14.5, color: "var(--text-2)", lineHeight: 1.5 }}>{model.tagline}</p>

        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 4, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 34, fontWeight: 600, color: up ? "var(--pos)" : "var(--neg)" }}>{fmt.pct(totalRet)}</span>
            <span style={{ fontSize: 13, color: "var(--text-3)" }}>
              {running ? "backtesting on real prices…" : isLive && win ? `total return · ${win.start} → ${win.end} vs S&P 500` : "illustrative equity (run a backtest for live results)"}
            </span>
          </div>
          <div className="card" style={{ padding: "14px 8px 4px", background: "var(--surface-2)", borderRadius: "var(--r-md)", position: "relative" }}>
            <AreaChart series={equity} benchmark={benchmark} color={up ? "var(--pos)" : "var(--neg)"} height={150} uid={"d" + model.id}
              valueFmt={isLive ? fmt.usd0 : undefined} seriesLabel={model.name.length > 18 ? "Strategy" : model.name} animate={!live} />
            {running && (
              <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", background: "color-mix(in srgb, var(--surface-2) 70%, transparent)", borderRadius: "var(--r-md)" }}>
                <div style={{ width: 24, height: 24, border: "3px solid var(--surface-3)", borderTopColor: "var(--accent)", borderRadius: 999, animation: "pt-spin .8s linear infinite" }} />
              </div>
            )}
          </div>
        </div>

        <div className="m-grid-2" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
          <StatBox label="Return" value={fmt.pct(stats.cagr)} tone={stats.cagr >= 0 ? "pos" : "neg"} />
          <StatBox label="Sharpe" value={stats.sharpe.toFixed(2)} />
          <StatBox label="Max DD" value={stats.maxDD.toFixed(1) + "%"} tone="neg" />
          <StatBox label="Win rate" value={isLive ? stats.winRate.toFixed(0) + "%" : "—"} />
          <StatBox label="Trades" value={stats.trades} />
          <StatBox label="Author" value={model.author} />
        </div>

        <section>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Methodology</div>
          <p style={{ margin: 0, fontSize: 14, color: "var(--text-2)", lineHeight: 1.65 }}>{model.methodology}</p>
        </section>

        {model.params.length > 0 && (
          <section>
            <div className="eyebrow" style={{ marginBottom: 12 }}>Parameters</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {model.params.map((p) => (
                <div key={p.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 13px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
                  <span style={{ fontSize: 13, color: "var(--text-2)" }}>{p.label}</span>
                  <span className="mono" style={{ fontSize: 13.5, fontWeight: 600 }}>{String(p.value)}{p.unit || ""}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <div className="eyebrow" style={{ marginBottom: 14 }}>Universe / allocation</div>
          <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
            <Donut data={model.holdings} size={120} thickness={15} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9 }}>
              {model.holdings.map((h, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: h.ticker === "Cash" ? "var(--surface-3)" : DONUT_PALETTE[i % DONUT_PALETTE.length] }} />
                    <span className="mono" style={{ fontSize: 13, color: "var(--text-1)" }}>{h.ticker}</span>
                  </div>
                  <span className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>{h.w}%</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div style={{ position: "sticky", bottom: 0, background: "linear-gradient(transparent, var(--surface-1) 22%)", padding: "18px 24px", display: "flex", gap: 10 }}>
        <Btn variant="primary" icon="play" iconFill onClick={() => onBacktest(model)} style={{ flex: 1 }}>Backtest in lab</Btn>
        {model.author === "You" && <Btn variant="soft" icon="edit" onClick={() => onEdit(model)}>Tune</Btn>}
        {model.author === "You" && <IconBtn icon="trash" size={42} tone="danger" title="Archive model" onClick={() => onDelete(model)} />}
      </div>
    </div>
  );
}
