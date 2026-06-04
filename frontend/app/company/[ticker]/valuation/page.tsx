"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { price, pct, signClass } from "@/lib/format";
import { etDateTime } from "@/lib/datetime";
import { Panel, StateView, Tooltip } from "@/components/ui";

const MODELS: Record<string, { label: string; formula: string; plain: string; lever: string }> = {
  dcf: { label: "Discounted Cash Flow", formula: "Σ PV(projected FCF, 10y) + PV(terminal value) − net debt ÷ shares", plain: "Projects free cash flow a decade out and discounts every dollar back to today.", lever: "Most sensitive to the discount rate and terminal growth." },
  owner_earnings: { label: "Owner Earnings", formula: "Net income + D&A − maintenance capex ± ΔWC, then discounted", plain: "Buffett's cash-earnings proxy, discounted like a DCF.", lever: "Most sensitive to the discount rate and the maintenance-capex estimate." },
  earnings_multiple: { label: "Earnings Multiple", formula: "EPS × (1+g)ⁿ × fair P/E, discounted to today", plain: "Grows EPS forward, applies a target P/E, then discounts back.", lever: "Most sensitive to the fair P/E and EPS growth." },
  revenue_multiple: { label: "Revenue Multiple", formula: "Revenue × (1+g)ⁿ × EV/Sales → equity ÷ shares, discounted", plain: "For growth or low-margin names — values the business off sales.", lever: "Most sensitive to the fair EV/Sales multiple." },
  ebitda_multiple: { label: "EBITDA Multiple", formula: "EBITDA × (1+g)ⁿ × EV/EBITDA → equity ÷ shares, discounted", plain: "Values the whole enterprise off cash operating profit.", lever: "Most sensitive to the fair EV/EBITDA multiple." },
  dividend_discount: { label: "Dividend Discount", formula: "next dividend ÷ (required return − dividend growth)", plain: "Gordon-growth model — only meaningful for steady dividend payers.", lever: "Most sensitive to the gap between required return and growth." },
};

const FIELDS: [string, string, boolean][] = [
  ["growth_1_5", "FCF growth yrs 1–5", true], ["growth_6_10", "FCF growth yrs 6–10", true],
  ["discount_rate", "Discount rate", true], ["terminal_growth", "Terminal growth", true],
  ["eps_growth", "EPS growth", true], ["fair_pe", "Fair P/E", false],
  ["fair_ev_ebitda", "Fair EV/EBITDA", false], ["fair_ev_sales", "Fair EV/Sales", false],
];
const ASSUMPTION_LABELS: Record<string, string> = {
  discount_rate: "discount rate", terminal_growth: "terminal growth", growth_1_5: "FCF growth (1–5y)",
  growth: "growth rate", eps_growth: "EPS growth", years: "projection years",
  fair_pe: "fair P/E", fair_ev_ebitda: "fair EV/EBITDA", fair_ev_sales: "fair EV/Sales",
};
const round1 = (v: number) => Math.round(v * 10) / 10;
const isPctKey = (k: string) => ["growth_1_5", "growth_6_10", "discount_rate", "terminal_growth", "eps_growth", "growth", "dividend_growth", "required_return"].includes(k);
const fmtAssumption = (k: string, v: number) => (isPctKey(k) ? `${(v * 100).toFixed(1)}%` : k === "years" ? String(v) : v.toFixed(1));

export default function ValuationPage() {
  const ticker = String(useParams().ticker || "").toUpperCase();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, number>>({});
  const baseRef = useRef<Record<string, number>>({});
  const [recomputing, setRecomputing] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    setLoading(true);
    api.valuation(ticker)
      .then((res) => {
        setData(res.data);
        setForm(res.data.assumptions);
        baseRef.current = res.data.assumptions;
        setError(null);
        return api.valuationHistory(ticker).then((hist) => setHistory(hist.data.results ?? []));
      })
      .catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [ticker]);

  async function recompute(assumptions: Record<string, number>) {
    setRecomputing(true);
    try {
      const res = await api.valuationCustom(ticker, { assumptions });
      setData(res.data);
      setForm(assumptions);
      const hist = await api.valuationHistory(ticker);
      setHistory(hist.data.results ?? []);
    }
    catch (e: any) { setError(e.message); } finally { setRecomputing(false); }
  }

  function preset(kind: "conservative" | "base" | "aggressive") {
    const b = baseRef.current;
    if (kind === "base") return recompute(b);
    const gm = kind === "conservative" ? 0.6 : 1.4;
    const mm = kind === "conservative" ? 0.85 : 1.15;
    recompute({
      ...b,
      growth_1_5: (b.growth_1_5 ?? 0.05) * gm, growth_6_10: (b.growth_6_10 ?? 0.03) * gm, eps_growth: (b.eps_growth ?? 0.05) * gm,
      discount_rate: kind === "conservative" ? 0.11 : 0.09, terminal_growth: kind === "conservative" ? 0.02 : 0.03,
      fair_pe: (b.fair_pe ?? 18) * mm, fair_ev_ebitda: (b.fair_ev_ebitda ?? 12) * mm, fair_ev_sales: (b.fair_ev_sales ?? 3) * mm,
    });
  }

  const verdict = (() => {
    if (!data || data.blended_fair_value == null || data.current_price == null) return null;
    const mos = data.margin_of_safety;
    const over = mos < 0;
    return {
      tone: over ? (mos < -0.2 ? "negative" : "neutral") : "positive",
      text: over
        ? `${ticker} trades ${pct(Math.abs(mos), 0)} above the blended fair value of ${price(data.blended_fair_value)}. At today's price the market is pricing in materially stronger growth than these models assume — demand a clear thesis for that premium.`
        : `${ticker} trades ${pct(mos, 0)} below the blended fair value of ${price(data.blended_fair_value)} — a margin of safety the models see as genuine upside. Confirm the assumptions hold before acting.`,
    };
  })();

  return (
    <StateView loading={loading} error={error} empty={!data}>
      {data && (
        <div className="space-y-6">
          <h2 className="font-serif text-2xl font-semibold tracking-tight">Valuation</h2>

          {data.note ? (
            <>
              <div className="rounded-xl border border-gold/30 bg-gold/5 p-5">
                <div className="text-[11px] uppercase tracking-wider text-muted">Valuation unavailable</div>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">{data.note}</p>
              </div>
              <div className="metric-grid grid-cols-1 md:grid-cols-2">
                <div className="px-5 py-4"><div className="text-[11px] uppercase tracking-wider text-muted">Current price</div><div className="mt-2 font-mono text-3xl">{price(data.current_price)}</div></div>
                <div className="px-5 py-4"><div className="text-[11px] uppercase tracking-wider text-muted">Financials</div><div className="mt-2 text-sm text-muted">See the <a href={`/company/${ticker}/financials`} className="text-accent hover:underline">Financials</a> and <a href={`/company/${ticker}/cash-flow`} className="text-accent hover:underline">Cash Flow</a> tabs — statement data is available.</div></div>
              </div>
            </>
          ) : (
          <>
          {verdict && (
            <div className={`rounded-xl border p-5 ${verdict.tone === "negative" ? "border-negative/30 bg-negative/5" : verdict.tone === "positive" ? "border-positive/30 bg-positive/5" : "border-line bg-surface/60"}`}>
              <div className="text-[11px] uppercase tracking-wider text-muted">The verdict</div>
              <p className="mt-2 text-[15px] leading-relaxed">{verdict.text}</p>
            </div>
          )}

          <div className="metric-grid grid-cols-1 md:grid-cols-3">
            <div className="px-5 py-4"><div className="text-[11px] uppercase tracking-wider text-muted">Current price</div><div className="mt-2 font-mono text-3xl">{price(data.current_price)}</div></div>
            <div className="px-5 py-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">
                <Tooltip content={<div className="text-xs"><div className="mb-2 font-serif text-sm font-semibold">Blended fair value</div><p className="leading-relaxed text-muted">Weighted average of every applicable model below. Weights renormalize when a model doesn't apply.</p></div>}>Blended fair value</Tooltip>
              </div>
              <div className="mt-2 font-mono text-3xl text-accent-2">{price(data.blended_fair_value)}</div>
            </div>
            <div className="px-5 py-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">
                <Tooltip content={<div className="text-xs"><div className="mb-2 font-serif text-sm font-semibold">Margin of safety</div><p className="leading-relaxed text-muted">(fair value − price) ÷ fair value. Positive = trades below intrinsic value; the bigger the cushion, the more room for error.</p></div>}>Margin of safety</Tooltip>
              </div>
              <div className={`mt-2 font-mono text-3xl ${signClass(data.margin_of_safety)}`}>{pct(data.margin_of_safety, 1)}</div>
            </div>
          </div>

          <Panel title="Fair value range" hint="bear · base · bull · where the price sits today">
            <FairValueRange bear={data.scenarios.bear} bull={data.scenarios.bull} blended={data.blended_fair_value} price={data.current_price} />
          </Panel>

          {data.diagnostics && <ValuationDiagnostics diagnostics={data.diagnostics} />}

          <div className="grid gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Panel title="Per-model fair value" hint="base case · hover a model for its formula, inputs & sensitivity">
                <div className="divide-y divide-line">
                  {data.models.map((m: any) => {
                    const meta = MODELS[m.model] ?? { label: m.model, formula: "", plain: "", lever: "" };
                    return (
                      <div key={m.model} className="flex items-center justify-between py-3">
                        <Tooltip width={300} content={
                          <div className="text-xs">
                            <div className="mb-2 font-serif text-sm font-semibold">{meta.label}</div>
                            <p className="leading-relaxed text-muted">{meta.plain}</p>
                            <div className="mt-2.5 rounded-md bg-surface-2 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-text">{meta.formula}</div>
                            {m.applicable && m.assumptions && (
                              <div className="mt-2.5 space-y-1">
                                {Object.entries(m.assumptions).filter(([k]) => ["discount_rate", "terminal_growth", "growth_1_5", "growth", "eps_growth", "years", "fair_pe", "fair_ev_ebitda", "fair_ev_sales"].includes(k)).map(([k, v]) => (
                                  <div key={k} className="flex justify-between text-muted"><span>{ASSUMPTION_LABELS[k] ?? k}</span><b className="font-mono font-medium text-text">{fmtAssumption(k, v as number)}</b></div>
                                ))}
                              </div>
                            )}
                            <div className="mt-2.5 border-t border-line pt-2 text-accent-2">{meta.lever}</div>
                          </div>
                        }>
                          <span className="text-sm">{meta.label}</span>
                        </Tooltip>
                        <div className="font-mono text-sm">
                          {m.applicable ? price(m.fair_value_per_share) : <span className="text-muted">N/M</span>}
                          {data.applied_weights[m.model] != null && <span className="ml-2 text-xs text-faint">{pct(data.applied_weights[m.model], 0)}</span>}
                          {!m.applicable && m.reason && <span className="ml-2 text-xs text-faint">{m.reason}</span>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Panel>
            </div>

            <Panel title="Assumptions" right={recomputing ? <span className="text-xs text-muted">…</span> : null}>
              <div className="mb-3 flex gap-1.5">
                {(["conservative", "base", "aggressive"] as const).map((k) => (
                  <button key={k} onClick={() => preset(k)} className="flex-1 rounded-md border border-line px-2 py-1.5 text-xs capitalize text-muted transition-colors hover:border-accent hover:text-text">{k}</button>
                ))}
              </div>
              <div className="space-y-2.5">
                {FIELDS.map(([key, label, p]) => (
                  <label key={key} className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-muted">{label}</span>
                    <span className="flex items-center gap-1.5">
                      <input type="number" step={0.5} value={p ? round1((form[key] ?? 0) * 100) : round1(form[key] ?? 0)}
                        onChange={(e) => { const raw = parseFloat(e.target.value); setForm((f) => ({ ...f, [key]: p ? raw / 100 : raw })); }}
                        className="w-20 rounded-md border border-line bg-surface-2 px-2 py-1 text-right font-mono outline-none focus:border-accent" />
                      <span className="w-3 text-xs text-faint">{p ? "%" : "×"}</span>
                    </span>
                  </label>
                ))}
                <button onClick={() => recompute(form)} disabled={recomputing} className="mt-2 w-full rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white shadow-glow disabled:opacity-50">{recomputing ? "Recomputing…" : "Recompute"}</button>
              </div>
            </Panel>
          </div>

          <SensitivityDiagnostics sensitivity={data.diagnostics?.sensitivity} currentPrice={data.current_price} />

          <ValuationHistory rows={history} />

          <p className="text-xs text-faint">Fair values are model outputs based on the assumptions shown — not financial advice. Use presets and the sensitivity grid to stress-test the thesis.</p>
          </>
          )}
        </div>
      )}
    </StateView>
  );
}

function ValuationDiagnostics({ diagnostics }: { diagnostics: any }) {
  const blend = diagnostics.blend ?? {};
  const models = diagnostics.models ?? [];
  return (
    <Panel title="Diagnostics" hint="model applicability, exclusions, and weight rebalancing">
      <div className="grid gap-3 md:grid-cols-3">
        <DiagStat label="Applicable models" value={`${blend.applicable_count ?? 0}`} />
        <DiagStat label="Excluded models" value={`${blend.excluded_count ?? 0}`} tone={(blend.excluded_count ?? 0) > 0 ? "neutral" : "positive"} />
        <DiagStat label="Weights" value={blend.renormalized ? "Reweighted" : "As requested"} tone={blend.renormalized ? "neutral" : "positive"} />
      </div>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-2 pr-4 font-medium">Model</th>
              <th className="py-2 pr-4 text-right font-medium">Fair value</th>
              <th className="py-2 pr-4 text-right font-medium">Requested</th>
              <th className="py-2 pr-4 text-right font-medium">Applied</th>
              <th className="py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {models.map((row: any) => {
              const meta = MODELS[row.model] ?? { label: row.model };
              return (
                <tr key={row.model} className="border-t border-line">
                  <td className="py-2 pr-4">{meta.label}</td>
                  <td className="py-2 pr-4 text-right font-mono">{price(row.fair_value_per_share)}</td>
                  <td className="py-2 pr-4 text-right font-mono">{pct(row.requested_weight, 0)}</td>
                  <td className="py-2 pr-4 text-right font-mono">{pct(row.applied_weight, 0)}</td>
                  <td className={row.included_in_blend ? "py-2 text-positive" : "py-2 text-muted"}>
                    {row.included_in_blend ? "Included" : row.reason ?? "Excluded"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function DiagStat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "positive" | "neutral" | "negative" }) {
  const color = tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text";
  return (
    <div className="rounded-lg border border-line bg-surface/60 px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1.5 font-mono text-lg ${color}`}>{value}</div>
    </div>
  );
}

function SensitivityDiagnostics({ sensitivity, currentPrice }: { sensitivity?: Record<string, any>; currentPrice?: number | null }) {
  if (!sensitivity) {
    return null;
  }
  const grids = [sensitivity.discount_growth, sensitivity.discount_terminal, sensitivity.multiples].filter(Boolean);
  return (
    <Panel title="Sensitivity" hint="computed by the same valuation service as the main fair value">
      <div className="grid gap-5 xl:grid-cols-3">
        {grids.map((grid) => <SensitivityTable key={grid.label} grid={grid} currentPrice={currentPrice} />)}
      </div>
    </Panel>
  );
}

function SensitivityTable({ grid, currentPrice }: { grid: any; currentPrice?: number | null }) {
  return (
    <div className="overflow-x-auto">
      <div className="mb-2 text-[11px] uppercase tracking-wider text-muted">{grid.label}</div>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="p-2 text-left text-xs text-faint">{grid.row_label} ↓ / {grid.column_label} →</th>
            {grid.columns.map((col: any) => <th key={col.label} className="p-2 text-right font-mono text-xs text-muted">{col.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {grid.values.map((row: (number | null)[], i: number) => (
            <tr key={grid.rows[i]?.label ?? i}>
              <td className="p-2 font-mono text-xs text-muted">{grid.rows[i]?.label}</td>
              {row.map((fv, j) => {
                const above = fv != null && currentPrice != null && fv >= currentPrice;
                return <td key={j} className={`p-2 text-right font-mono ${fv == null ? "text-faint" : above ? "text-positive" : "text-negative"}`} style={{ background: fv == null ? undefined : above ? "rgba(62,207,142,0.08)" : "rgba(255,107,107,0.06)" }}>{price(fv)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValuationHistory({ rows }: { rows: any[] }) {
  if (!rows.length) {
    return null;
  }
  return (
    <Panel title="History" hint="recent valuations saved from this page">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-2 pr-4 font-medium">Date</th>
              <th className="py-2 pr-4 text-right font-medium">Price</th>
              <th className="py-2 pr-4 text-right font-medium">Fair value</th>
              <th className="py-2 text-right font-medium">MoS</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 6).map((row) => (
              <tr key={row.id} className="border-t border-line">
                <td className="py-2 pr-4 text-muted">{etDateTime(row.valuation_date)}</td>
                <td className="py-2 pr-4 text-right font-mono">{price(row.current_price)}</td>
                <td className="py-2 pr-4 text-right font-mono">{price(row.blended_fair_value)}</td>
                <td className={`py-2 text-right font-mono ${signClass(row.margin_of_safety)}`}>{pct(row.margin_of_safety, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function FairValueRange({ bear, bull, blended, price: cur }: { bear: number | null; bull: number | null; blended: number | null; price: number | null }) {
  const points = [bear, bull, blended, cur].filter((v): v is number => v != null);
  if (points.length < 2) return <div className="text-sm text-muted">Insufficient data.</div>;
  const lo = Math.min(...points), hi = Math.max(...points);
  const span = hi - lo || 1;
  const x = (v: number) => ((v - lo) / span) * 100;
  return (
    <div className="pb-10 pt-8">
      <div className="relative h-1.5 rounded-full bg-surface-2">
        {bear != null && bull != null && <div className="absolute h-1.5 rounded-full" style={{ left: `${x(bear)}%`, width: `${x(bull) - x(bear)}%`, background: "linear-gradient(90deg, rgba(124,108,255,.35), rgba(124,108,255,.7))" }} />}
        <Marker x={x} value={bear} label="Bear" color="#6b6a78" />
        <Marker x={x} value={bull} label="Bull" color="#3ECF8E" />
        {blended != null && <Marker x={x} value={blended} label="Blended" color="#7C6CFF" big />}
        {cur != null && <Marker x={x} value={cur} label="Price" color="#E0B341" big below />}
      </div>
    </div>
  );
}

function Marker({ x, value, label, color, big = false, below = false }: { x: (v: number) => number; value: number | null; label: string; color: string; big?: boolean; below?: boolean }) {
  if (value == null) return null;
  return (
    <div className="absolute -translate-x-1/2" style={{ left: `${x(value)}%`, top: big ? -4 : -2 }}>
      <div className={`${big ? "h-3.5 w-3.5" : "h-2.5 w-2.5"} rounded-full`} style={{ background: color, boxShadow: "0 0 0 4px #0a0a0f" }} />
      <div className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px]" style={{ color, top: below ? 16 : -18 }}>{label} <span className="font-mono">{price(value)}</span></div>
    </div>
  );
}
