"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiErrorText, Integrity, ParameterSweep, paperTradingApi, RunSummary } from "@/lib/paperTradingApi";
import { Btn, Icon, MetricTile, Segmented, SelectInput, TextInput } from "./ptkit";
import { AreaChart, Donut, ReturnBars, drawdownOf, Pt } from "./ptcharts";
import { fmt, REGIMES, Model } from "./ptdata";

interface Result {
  context: string;  // which strategy + window produced this — selections may have moved on
  equity: Pt[]; bench: Pt[];
  stats: { final: number; totalRet: number; alpha: number; cagr: number; maxDD: number; winRate: number; best: number; worst: number };
  metrics: Record<string, number | null>;
  integrity: Integrity | null;
  trades: any[]; holdings: { ticker: string; w: number }[]; warnings: string[];
}
interface NumericParam { path: string; label: string; value: number }

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span style={{ width: 16, height: 2.5, background: dashed ? "none" : color, borderTop: dashed ? `2.5px dashed ${color}` : "none", display: "inline-block" }} />
      <span style={{ fontSize: 12, color: "var(--text-2)" }}>{label}</span>
    </div>
  );
}

function adapt(data: any, capital: number, context: string): Result {
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
  const holdingsRaw = (data.run?.holdings?.length ? data.run.holdings : data.holdings) ?? [];
  const holdings = holdingsRaw.length
    ? holdingsRaw.map((h: any) => ({ ticker: h.ticker ?? "—", w: Math.round((h.weight ?? h.w ?? 0) * ((h.weight ?? h.w ?? 0) <= 1 ? 100 : 1)) })).filter((h: any) => h.w > 0)
    : [{ ticker: "Cash", w: 100 }];
  return {
    context,
    equity, bench,
    stats: { final, totalRet, alpha: totalRet - benchRet, cagr, maxDD, winRate, best: pnls.length ? Math.max(...pnls) : 0, worst: pnls.length ? Math.min(...pnls) : 0 },
    metrics: m,
    integrity: data.run?.integrity ?? null,
    trades, holdings, warnings: data.run?.warnings ?? [],
  };
}

const INTEGRITY_TONE: Record<string, { color: string; bg: string; mark: string }> = {
  pass: { color: "var(--pos)", bg: "var(--pos-soft)", mark: "✓" },
  warn: { color: "var(--gold, #E0B341)", bg: "rgba(224,179,65,0.12)", mark: "!" },
  info: { color: "var(--text-3)", bg: "var(--surface-2)", mark: "i" },
};

function IntegrityPanel({ integrity }: { integrity: Integrity | null }) {
  const [open, setOpen] = useState(false);
  if (!integrity?.checks?.length) return null;
  const warns = integrity.checks.filter((c) => c.status === "warn").length;
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <button onClick={() => setOpen(!open)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "13px 16px",
        background: "none", border: "none", cursor: "pointer", color: "var(--text-1)", textAlign: "left" }}>
        <span style={{ color: "var(--pos)" }}><Icon name="sparkles" size={15} fill /></span>
        <span className="eyebrow" style={{ flex: 1 }}>Integrity checks — no look-ahead, no survivorship cheats</span>
        <span style={{ fontSize: 12, color: warns ? "var(--gold, #E0B341)" : "var(--pos)" }}>
          {integrity.checks.length - warns} controlled{warns ? ` · ${warns} disclosed` : ""}
        </span>
        <span style={{ color: "var(--text-3)", transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
          <Icon name="chevronDown" size={14} />
        </span>
      </button>
      {open && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "6px 0" }}>
          {integrity.checks.map((c) => {
            const tone = INTEGRITY_TONE[c.status] ?? INTEGRITY_TONE.info;
            return (
              <div key={c.id} style={{ display: "flex", gap: 12, padding: "10px 16px", alignItems: "flex-start" }}>
                <span className="mono" style={{ width: 20, height: 20, borderRadius: 999, flexShrink: 0, display: "grid", placeItems: "center",
                  fontSize: 11, fontWeight: 700, color: tone.color, background: tone.bg }}>{tone.mark}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>{c.label}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", lineHeight: 1.5, marginTop: 2 }}>{c.detail}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function humanizeParam(path: string) {
  return path.split(".").map((part) => part.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())).join(" / ");
}

function numericParams(value: any, prefix = ""): NumericParam[] {
  if (!value || typeof value !== "object") return [];
  const out: NumericParam[] = [];
  for (const [key, raw] of Object.entries(value)) {
    if (key === "tickers") continue;
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof raw === "number" && Number.isFinite(raw)) out.push({ path, label: humanizeParam(path), value: raw });
    else if (raw && typeof raw === "object" && !Array.isArray(raw)) out.push(...numericParams(raw, path));
  }
  return out;
}

function defaultSweepValues(current: number | undefined): string {
  const base = typeof current === "number" && Number.isFinite(current) ? current : 1;
  const spread = Math.max(Math.abs(base) * 0.25, base === 0 ? 1 : 0.01);
  const vals = [base - spread, base, base + spread].map((v) => Number(v.toFixed(Math.abs(v) < 1 ? 4 : 2)));
  return vals.join(", ");
}

function pctMetric(value: any): string {
  return typeof value === "number" ? fmt.pct(value * 100) : "—";
}

function plainMetric(value: any, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

export default function BacktestLab({ models, preselectId, initialRegime }: { models: Model[]; preselectId?: number | null; initialRegime?: string }) {
  const [stratId, setStratId] = useState<number>(preselectId || models[0]?.id);
  const [regimeId, setRegimeId] = useState(initialRegime || "gfc");
  const [customStart, setCustomStart] = useState("2015-01-01");
  const [customEnd, setCustomEnd] = useState(() => new Date().toISOString().slice(0, 10));
  // Free typing; clamp only on blur so "5" can become "50000".
  const [capitalText, setCapitalText] = useState("100000");
  const capital = Math.max(1000, parseInt(capitalText.replace(/\D/g, "") || "0", 10) || 0);
  const [result, setResult] = useState<Result | null>(null);
  const [phase, setPhase] = useState<null | "queued" | "running">(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RunSummary[]>([]);
  const [sweepParam, setSweepParam] = useState("");
  const [sweepValues, setSweepValues] = useState("");
  const [sweep, setSweep] = useState<ParameterSweep | null>(null);
  const [sweepRunning, setSweepRunning] = useState(false);
  const [sweepError, setSweepError] = useState<string | null>(null);
  // Supersede protection: only the newest run may write results; older polls abort,
  // and their still-queued server jobs are cancelled best-effort.
  const runSeq = useRef(0);
  const runAbort = useRef<AbortController | null>(null);
  const activeRun = useRef<{ id: number; settled: boolean } | null>(null);

  const model = models.find((m) => m.id === stratId) || models[0];
  const isoOk = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v);
  const regime = regimeId === "custom"
    ? { id: "custom", label: "Custom", sub: "Custom window", start: customStart, end: customEnd }
    : (REGIMES.find((r) => r.id === regimeId) ?? REGIMES[0]);
  // Key on parameter CONTENT, not object identity — the page rebuilds model objects on
  // every background refresh, and resetting here would wipe the user's sweep mid-typing.
  const paramsKey = useMemo(() => JSON.stringify(model?.parameters ?? {}), [model?.parameters]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const sweepOptions = useMemo(() => numericParams(model?.parameters ?? {}), [paramsKey]);

  useEffect(() => {
    const first = sweepOptions[0];
    setSweep(null);
    setSweepError(null);
    setSweepParam(first?.path ?? "");
    setSweepValues(defaultSweepValues(first?.value));
  }, [model?.id, sweepOptions]);

  const refreshRecent = useCallback(async () => {
    if (!model?.id) return;
    try {
      const res = await paperTradingApi.listBacktests(model.id, 8);
      setRecent(res.data.runs);
    } catch { /* the history rail is non-critical */ }
  }, [model?.id]);
  useEffect(() => { refreshRecent(); }, [refreshRecent]);

  const cancelActive = () => {
    runAbort.current?.abort();
    const prev = activeRun.current;
    if (prev && !prev.settled) paperTradingApi.cancelBacktest(prev.id).catch(() => {});
    activeRun.current = null;
  };
  // Leaving the lab: stop polling and cancel anything still queued.
  useEffect(() => () => cancelActive(), []);

  async function run() {
    if (!model) return;
    const seq = ++runSeq.current;
    cancelActive();
    const abort = new AbortController();
    runAbort.current = abort;
    const capitalNow = capital;
    const context = `${model.name} · ${regime.start} → ${regime.end}`;
    setPhase("queued"); setResult(null); setError(null);
    try {
      const queued = await paperTradingApi.queueBacktest({
        strategy_id: model.id, tickers: model.parameters?.tickers ?? [],
        start_date: regime.start, end_date: regime.end, starting_cash: capitalNow, benchmark: "SPY",
      });
      let job = queued.data.run;
      activeRun.current = { id: job.id, settled: false };
      while (job.status === "queued" || job.status === "running") {
        if (abort.signal.aborted || seq !== runSeq.current) return;
        setPhase(job.status);
        await new Promise((r) => setTimeout(r, 1500));
        if (abort.signal.aborted || seq !== runSeq.current) return;
        job = (await paperTradingApi.getBacktest(job.id)).data.run;
      }
      if (activeRun.current?.id === job.id) activeRun.current.settled = true;
      if (abort.signal.aborted || seq !== runSeq.current) return;  // superseded — drop the stale response
      if (job.status === "failed") setError(job.warnings?.[0] || "Backtest failed.");
      else if (job.status === "cancelled") setError("Backtest was cancelled.");
      else setResult(adapt({ run: job }, capitalNow, context));
      refreshRecent();
    } catch (e: any) {
      if (abort.signal.aborted || seq !== runSeq.current) return;
      setError(apiErrorText(e) || "Backtest failed.");
    } finally {
      if (seq === runSeq.current) setPhase(null);
    }
  }

  async function loadRun(id: number) {
    runSeq.current++;
    cancelActive();
    setPhase(null); setError(null);
    try {
      const res = await paperTradingApi.getBacktest(id);
      const job = res.data.run;
      if (job.status !== "completed") { setError(`That run is ${job.status} — nothing to display.`); return; }
      setResult(adapt({ run: job }, (job as any).starting_cash ?? 100000, job.name));
    } catch (e: any) { setError(apiErrorText(e)); }
  }
  async function runSweep() {
    if (!model || !sweepParam) return;
    const values = sweepValues.split(",").map((value) => Number(value.trim())).filter((value) => Number.isFinite(value));
    if (!values.length) {
      setSweepError("Enter at least one numeric sweep value.");
      return;
    }
    setSweepRunning(true); setSweep(null); setSweepError(null);
    try {
      const res = await paperTradingApi.runSweep({
        strategy_id: model.id,
        parameter: sweepParam,
        values,
        start_date: regime.start,
        end_date: regime.end,
        starting_cash: capital,
        benchmark: "SPY",
      });
      setSweep(res.data.sweep);
    } catch (e: any) {
      setSweepError(e.message || "Sweep failed.");
    } finally { setSweepRunning(false); }
  }
  // Re-run when the user *changes* strategy/regime — but never auto-run on mount:
  // index-wide models can take minutes on a cold price store, and kicking one off
  // before the user asked for anything serializes every later run behind it.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    if (regimeId !== "custom") run();
    // eslint-disable-next-line
  }, [stratId, regimeId]);

  const up = result && result.stats.totalRet >= 0;
  const beat = result && result.stats.alpha >= 0;

  return (
    <div style={{ animation: "pt-fadeUp .3s var(--ease)", display: "flex", flexDirection: "column", gap: 22 }}>
      <div className="card" style={{ padding: 20, display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-end" }}>
        <div style={{ flex: "1 1 240px" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Strategy</div>
          <SelectInput value={String(stratId)} onChange={(v) => setStratId(Number(v))} options={models.map((m) => ({ value: String(m.id), label: m.name }))} />
        </div>
        <div style={{ flex: "0 1 160px" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Starting capital</div>
          <TextInput mono value={capitalText} onChange={setCapitalText} onBlur={() => setCapitalText(String(capital))} placeholder="100000" />
        </div>
        <Btn variant="primary" icon="play" iconFill onClick={run} disabled={!!phase} style={{ minWidth: 110 }}>
          {phase === "queued" ? "Queued…" : phase === "running" ? "Running…" : "Run"}</Btn>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Historical regime</div>
          <Segmented options={[...REGIMES.map((r) => ({ id: r.id, label: r.label })), { id: "custom", label: "Custom" }]}
            value={regimeId} onChange={setRegimeId} size="sm" />
        </div>
        {regimeId === "custom" ? (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <TextInput mono value={customStart} onChange={setCustomStart} placeholder="YYYY-MM-DD" style={{ width: 132, padding: "8px 10px", fontSize: 13 }} />
            <span style={{ color: "var(--text-3)" }}>→</span>
            <TextInput mono value={customEnd} onChange={setCustomEnd} placeholder="YYYY-MM-DD" style={{ width: 132, padding: "8px 10px", fontSize: 13 }} />
            <Btn variant="soft" icon="play" onClick={run} disabled={!!phase || !isoOk(customStart) || !isoOk(customEnd) || customEnd <= customStart}>Test window</Btn>
          </div>
        ) : (
          <span style={{ fontSize: 12.5, color: "var(--text-3)" }}>{regime.sub} · {regime.start} → {regime.end}</span>
        )}
      </div>

      <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 240px" }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Parameter sweep</div>
            <SelectInput value={sweepParam} onChange={(v) => {
              setSweepParam(v);
              setSweepValues(defaultSweepValues(sweepOptions.find((option) => option.path === v)?.value));
            }} options={sweepOptions.map((option) => ({ value: option.path, label: option.label }))} />
          </div>
          <div style={{ flex: "1 1 220px" }}>
            <div className="eyebrow" style={{ marginBottom: 8 }}>Values</div>
            <TextInput mono value={sweepValues} onChange={setSweepValues} placeholder="0.05, 0.10, 0.15" />
          </div>
          <Btn variant="soft" icon="layers" onClick={runSweep} disabled={!sweepParam || sweepRunning} style={{ minWidth: 128 }}>
            {sweepRunning ? "Sweeping..." : "Run sweep"}</Btn>
        </div>
        {sweepOptions.length === 0 && <div style={{ fontSize: 12.5, color: "var(--text-3)" }}>No numeric parameters found for this model.</div>}
        {sweepError && <div style={{ fontSize: 12.5, color: "var(--neg)" }}>{sweepError}</div>}
        {sweep && (
          <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 720 }}>
              <thead>
                <tr style={{ background: "var(--surface-2)" }}>
                  {["Rank", "Value", "Return", "Sharpe", "Max DD", "Win", "Turnover", "Exposure"].map((h) => (
                    <th key={h} style={{ textAlign: h === "Value" ? "left" : "right", padding: "10px 12px", fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-3)", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sweep.runs.map((row) => (
                  <tr key={row.run_id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right", color: "var(--accent-2)", fontWeight: 700 }}>{row.rank}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "left", color: "var(--text-1)" }}>{row.value}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right", color: (row.metrics.total_return ?? 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>{pctMetric(row.metrics.total_return)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{plainMetric(row.metrics.sharpe)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right", color: "var(--neg)" }}>{pctMetric(row.metrics.max_drawdown)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{pctMetric(row.metrics.win_rate)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{plainMetric(row.metrics.turnover)}x</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{pctMetric(row.metrics.exposure)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {recent.length > 0 && (
        <div className="card" style={{ overflow: "hidden" }}>
          <div style={{ padding: "13px 16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="eyebrow">Recent runs · {model?.name}</span>
            <span className="mono" style={{ fontSize: 11.5, color: "var(--text-3)" }}>{recent.length} stored</span>
          </div>
          <div>
            {recent.map((r) => {
              const tone = r.status === "completed" ? "var(--pos)" : r.status === "failed" ? "var(--neg)"
                : r.status === "cancelled" ? "var(--text-3)" : "var(--accent-2)";
              const ret = r.metrics?.total_return;
              return (
                <button key={r.id} onClick={() => r.status === "completed" && loadRun(r.id)}
                  disabled={r.status !== "completed"}
                  style={{ width: "100%", display: "flex", alignItems: "center", gap: 12, padding: "9px 16px", background: "none",
                    border: "none", borderTop: "1px solid var(--border)", cursor: r.status === "completed" ? "pointer" : "default",
                    textAlign: "left", fontFamily: "var(--font-sans)" }}>
                  <span className="mono" style={{ fontSize: 10.5, fontWeight: 700, color: tone, textTransform: "uppercase", width: 76, flexShrink: 0 }}>{r.status}</span>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: "var(--text-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {r.start_date} → {r.end_date}{r.sweep ? " · sweep" : ""}
                  </span>
                  <span className="mono" style={{ fontSize: 12, color: typeof ret === "number" ? (ret >= 0 ? "var(--pos)" : "var(--neg)") : "var(--text-3)", width: 74, textAlign: "right" }}>
                    {typeof ret === "number" ? fmt.pct(ret * 100) : "—"}
                  </span>
                  {r.status === "completed" && <span style={{ color: "var(--text-3)", flexShrink: 0 }}><Icon name="chevronDown" size={13} style={{ transform: "rotate(-90deg)" }} /></span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {model?.isRule && model.methodology && (
        <div className="card" style={{ padding: "13px 16px", display: "flex", gap: 10, alignItems: "flex-start", background: "var(--surface-2)" }}>
          <span style={{ color: "var(--accent-2)", marginTop: 1 }}><Icon name="sparkles" size={15} fill /></span>
          <div style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
            <strong style={{ color: "var(--text-1)" }}>Signal rule. </strong>{model.methodology}
          </div>
        </div>
      )}

      {phase && (
        <div className="card" style={{ height: 320, display: "grid", placeItems: "center", color: "var(--text-3)" }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ width: 30, height: 30, border: "3px solid var(--surface-3)", borderTopColor: "var(--accent)", borderRadius: 999, margin: "0 auto 14px", animation: "pt-spin .8s linear infinite" }} />
            <div className="mono" style={{ fontSize: 13 }}>
              {phase === "queued" ? `Queued — ${model?.name} · ${regime.label} starts when the engine frees up…` : `Simulating ${model?.name} · ${regime.label}…`}
            </div>
            <div style={{ fontSize: 11.5, marginTop: 6 }}>The run keeps going server-side even if you leave this tab — find it under Recent runs.</div>
          </div>
        </div>
      )}

      {error && !phase && (
        <div className="card" style={{ padding: 24, color: "var(--neg)", fontSize: 14 }}>{error}</div>
      )}

      {result && !phase && (
        <>
          <div className="card" style={{ padding: 24 }}>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 8 }}>
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>Ending balance · {result.context}</div>
                <div className="mono" style={{ fontSize: 34, fontWeight: 600, color: up ? "var(--pos)" : "var(--neg)" }}>{fmt.usd0(result.stats.final)}</div>
              </div>
              <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
                <Legend color={up ? "var(--pos)" : "var(--neg)"} label={model?.name || "Strategy"} />
                <Legend color="var(--text-3)" label="S&P 500" dashed />
              </div>
            </div>
            <AreaChart series={result.equity} benchmark={result.bench} color={up ? "var(--pos)" : "var(--neg)"} height={230} uid="bt" valueFmt={fmt.usd0} seriesLabel={(model?.name?.length ?? 0) > 16 ? "Strategy" : (model?.name || "Strategy")} benchLabel="S&P 500" />
            <div style={{ marginTop: 10, padding: "10px 14px", background: beat ? "var(--pos-soft)" : "var(--neg-soft)", borderRadius: "var(--r-sm)", fontSize: 13, color: beat ? "var(--pos)" : "var(--neg)", fontWeight: 500 }}>
              {beat ? `Beat the market by ${result.stats.alpha.toFixed(1)} pts over this window.` : `Trailed the market by ${Math.abs(result.stats.alpha).toFixed(1)} pts over this window.`}
            </div>
            {result.warnings.length > 0 && <div style={{ marginTop: 8, fontSize: 12, color: "var(--text-3)" }}>{result.warnings.slice(0, 2).join(" · ")}</div>}
          </div>

          <IntegrityPanel integrity={result.integrity} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
            <MetricTile label="Total return" value={fmt.pct(result.stats.totalRet)} tone={up ? "pos" : "neg"} big />
            <MetricTile label="vs S&P 500" value={fmt.pct(result.stats.alpha)} tone={beat ? "pos" : "neg"} big />
            <MetricTile label="CAGR" value={fmt.pct(result.stats.cagr)} tone={result.stats.cagr >= 0 ? "pos" : "neg"} />
            <MetricTile label="Max drawdown" value={result.stats.maxDD.toFixed(1) + "%"} tone="neg" />
            {result.stats.winRate > 0 && <MetricTile label="Win rate" value={result.stats.winRate.toFixed(0) + "%"} />}
            {result.metrics.sharpe != null && <MetricTile label="Sharpe" value={plainMetric(result.metrics.sharpe)} tone={result.metrics.sharpe >= 1 ? "pos" : undefined} />}
            {result.metrics.sortino != null && <MetricTile label="Sortino" value={plainMetric(result.metrics.sortino)} />}
            {result.metrics.volatility != null && <MetricTile label="Volatility (ann.)" value={(result.metrics.volatility * 100).toFixed(1) + "%"} />}
            {result.metrics.calmar != null && <MetricTile label="Calmar" value={plainMetric(result.metrics.calmar)} />}
            {result.metrics.beta != null && <MetricTile label="Beta" value={plainMetric(result.metrics.beta)} />}
            {result.metrics.profit_factor != null && <MetricTile label="Profit factor" value={plainMetric(result.metrics.profit_factor)} />}
          </div>

          <div className="m-stack" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", gap: 18 }}>
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
