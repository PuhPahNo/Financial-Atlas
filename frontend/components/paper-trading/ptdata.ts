// Paper Trading data helpers — category hues, deterministic series (for card
// sparklines / builder projection), formatters, regime→date-range presets, and
// the adapter that maps a real backend strategy onto the design's "model" shape.

export interface Pt { t: number; v: number }
export interface CatMeta { id: string; label: string; short: string; hue: string; blurb: string }
export interface ModelStats { cagr: number; sharpe: number | null; maxDD: number; winRate: number; trades: number }
export interface Holding { ticker: string; w: number }
export interface Param { key: string; label: string; value: any; unit?: string }
export interface Model {
  id: number; name: string; category: string; author: "You" | "Atlas"; tagline: string; methodology: string;
  stats: ModelStats; sincePct: number; equity: Pt[]; holdings: Holding[]; params: Param[]; favorite: boolean;
  parameters: Record<string, any>; raw: any; isRule: boolean;
  backtested: boolean; metricState: "backtested" | "seeded_illustrative" | "custom_projection";
  backtestWindow?: { start: string; end: string }; benchmark?: Pt[];
}

// Default headline-backtest window: the last ~3 years (covers nearly every ticker).
export function defaultBacktestWindow(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - 3);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

// Plain-English explanations surfaced as tooltips on the stat labels.
export const STAT_TIPS = {
  cagr: "Total return over the stored backtest window (not annualized) — open the model for the exact dates.",
  sharpe: "Risk-adjusted return: how much return you earn per unit of volatility. Above 1 is solid, above 2 is excellent. “—” means it hasn't been measured yet.",
  maxDD: "Maximum drawdown — the largest peak-to-trough drop the strategy suffered. Closer to 0% means a smoother ride.",
  winRate: "Win rate — the share of closed trades that ended profitable. “New” means it hasn't been backtested yet.",
};

export const CAT_HUES: Record<string, string> = {
  long_term: "var(--cat-long)",
  short_term: "var(--cat-short)",
  short_selling: "var(--cat-sell)",
  options: "var(--cat-opt)",
  income_quality: "var(--cat-income)",
  risk_rotation: "var(--cat-rotation)",
};
const CAT_SHORT: Record<string, string> = {
  long_term: "Long Term", short_term: "Short Term", short_selling: "Short Sell",
  options: "Options", income_quality: "Income", risk_rotation: "Rotation",
};
export function catMeta(c: { id: string; label: string; description?: string }): CatMeta {
  return { id: c.id, label: c.label, short: CAT_SHORT[c.id] || c.label, hue: CAT_HUES[c.id] || "var(--accent)", blurb: c.description || "" };
}

// ---- deterministic RNG + series (ported) --------------------------------
function rng(seed: number) {
  let a = seed >>> 0;
  return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function gauss(r: () => number) { return (r() + r() + r() - 1.5) * 1.1; }
export function genSeries(seed: number, n: number, { start = 100, drift = 0.0004, vol = 0.012, crash = null as null | { at: number; len: number; depth: number; recover?: number } } = {}): Pt[] {
  const r = rng(seed); const out: Pt[] = []; let v = start;
  for (let i = 0; i < n; i++) {
    let d = drift;
    if (crash && i >= crash.at && i < crash.at + crash.len) d -= crash.depth / crash.len;
    if (crash && i >= crash.at + crash.len) d += (crash.recover || 0) / Math.max(1, n - (crash.at + crash.len));
    v = v * (1 + d + gauss(r) * vol);
    out.push({ t: i, v: Math.max(v, 1) });
  }
  return out;
}
export const seriesPct = (s: Pt[]) => (s.length ? (s[s.length - 1].v / s[0].v - 1) * 100 : 0);

export const fmt = {
  usd: (n: number) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  usd0: (n: number) => "$" + Math.round(n).toLocaleString("en-US"),
  pct: (n: number) => (n >= 0 ? "+" : "") + n.toFixed(1) + "%",
  pct2: (n: number) => (n >= 0 ? "+" : "") + n.toFixed(2) + "%",
};

function hashStr(s: string) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function humanize(key: string) { return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }

// ---- adapter: real backend strategy → design model ----------------------
export function toModel(s: any): Model {
  const m = s.metrics || {};
  const bt = m._backtest;
  let cagr: number, maxDD: number, winRate: number, trades: number;
  let sharpe: number | null;
  let equity: Pt[]; let benchmark: Pt[] | undefined; let backtested = false;
  let backtestWindow: { start: string; end: string } | undefined;

  if (bt && Array.isArray(bt.equity) && bt.equity.length > 1) {
    // Real, persisted backtest — use it verbatim (including the engine's real Sharpe).
    backtested = true;
    backtestWindow = bt.window;
    const bm = bt.metrics || {};
    cagr = (bm.total_return ?? 0) * 100;
    maxDD = (bm.max_drawdown ?? 0) * 100;
    winRate = bm.win_rate != null ? bm.win_rate * (Math.abs(bm.win_rate) <= 1.5 ? 100 : 1) : 0;
    trades = bm.trades ?? 0;
    sharpe = typeof bm.sharpe === "number" ? bm.sharpe : null;
    equity = bt.equity.map((p: any, i: number) => ({ t: i, v: p.v, d: p.d }));
    benchmark = Array.isArray(bt.benchmark) && bt.benchmark.length > 1
      ? bt.benchmark.map((p: any, i: number) => ({ t: i, v: p.v, d: p.d })) : undefined;
  } else {
    // No backtest yet — illustrative deterministic series from seed metrics.
    // Metrics we don't actually have stay empty ("—") instead of being invented.
    cagr = (m.backtested_return ?? m.cagr ?? 0) * (Math.abs(m.backtested_return ?? 0) <= 2 ? 100 : 1);
    maxDD = (m.max_drawdown ?? 0) * (Math.abs(m.max_drawdown ?? 0) <= 2 ? 100 : 1);
    winRate = (m.win_rate ?? 0) * (Math.abs(m.win_rate ?? 0) <= 1.5 ? 100 : 1);
    const seed = hashStr(String(s.id) + s.name);
    const drift = Math.max(-0.0006, (cagr / 100) / 252);
    const vol = 0.006 + Math.min(Math.abs(maxDD), 40) * 0.0004;
    equity = genSeries(seed, 120, { drift, vol });
    trades = typeof m.trades === "number" ? m.trades : 0;
    sharpe = typeof m.sharpe === "number" ? m.sharpe : null;
  }
  const rawParams = s.parameters || {};
  const isRule = !!rawParams.rules;
  let params: Param[];
  if (isRule) {
    const r = rawParams.rules; const sig = r.signal || {};
    params = [
      { key: "instrument", label: "Trades", value: r.instrument },
      { key: "direction", label: "Direction", value: (r.direction || "long") === "short" ? "Short" : "Long" },
      { key: "signal", label: "Entry signal", value: signalLabel(sig, r.instrument) },
      { key: "tp", label: "Take profit", value: `+${Math.round((r.take_profit_pct ?? 0) * 100)}%` },
      { key: "sl", label: "Stop loss", value: `−${Math.round((r.stop_loss_pct ?? 0) * 100)}%` },
    ];
    if (r.max_hold_days) params.push({ key: "hold", label: "Max hold", value: `${r.max_hold_days} days` });
  } else {
    params = Object.entries(rawParams)
      .filter(([k]) => k !== "tickers")
      .map(([k, v]) => ({ key: k, label: humanize(k), value: typeof v === "number" && Math.abs(v) < 1 && /pct|threshold|margin|yield|risk|cost|limit|coverage/i.test(k) ? `${(v * 100).toFixed(0)}%` : v }));
  }
  const tickers: string[] = rawParams.tickers || [];
  const per = tickers.length ? Math.floor(82 / tickers.length) : 0;
  const holdings: Holding[] = tickers.length
    ? [...tickers.map((t) => ({ ticker: t, w: per })), { ticker: "Cash", w: Math.max(0, 100 - per * tickers.length) }]
    : [{ ticker: "Cash", w: 100 }];
  const sincePct = backtested ? +cagr.toFixed(1) : +seriesPct(equity).toFixed(1);
  return {
    id: s.id, name: s.name, category: s.category, author: s.origin === "user" ? "You" : "Atlas",
    tagline: s.description || "", methodology: s.methodology || "",
    stats: { cagr, sharpe, maxDD, winRate, trades },
    sincePct, equity, holdings, params,
    favorite: false, parameters: rawParams, raw: s, isRule,
    backtested,
    metricState: backtested ? "backtested" : s.origin === "seeded" ? "seeded_illustrative" : "custom_projection",
    backtestWindow, benchmark,
  };
}

export function metricStateLabel(model: Model): string {
  if (model.metricState === "backtested") return "Backtested";
  if (model.metricState === "seeded_illustrative") return "Seeded estimate";
  return "Not backtested";
}

export function metricStateTip(model: Model): string {
  if (model.metricState === "backtested") return "Generated by an Atlas backtest using the stored run window.";
  if (model.metricState === "seeded_illustrative") return "Seeded Atlas catalogue metric, not a run from your workspace yet.";
  return "No stored backtest yet — open the model or run it in the Lab to populate real metrics.";
}

// ---- signal / rule strategies -------------------------------------------
export const REF_LABEL: Record<string, string> = {
  "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones", "^RUT": "Russell 2000",
};
export function refLabel(sym: string) { return REF_LABEL[sym] || sym; }

export function signalLabel(sig: any, instrument?: string): string {
  const ref = refLabel(sig.reference || instrument || "");
  switch (sig.type) {
    case "new_high": return `${ref} new high`;
    case "new_low": return `${ref} new low`;
    case "pct_drop": return `${ref} −${Math.round((sig.pct ?? 0.05) * 100)}% dip`;
    case "pct_gain": return `${ref} +${Math.round((sig.pct ?? 0.05) * 100)}% surge`;
    case "ma_cross_up": return `${ref} ${sig.fast_days ?? 20}/${sig.slow_days ?? 50} golden cross`;
    case "ma_cross_down": return `${ref} ${sig.fast_days ?? 20}/${sig.slow_days ?? 50} death cross`;
    default: return "signal";
  }
}

export interface Rule {
  instrument: string; direction: "long" | "short";
  signalType: "new_high" | "new_low" | "pct_drop" | "pct_gain" | "ma_cross_up" | "ma_cross_down";
  reference: string; pct: number; windowDays: number; fastDays: number; slowDays: number;
  takeProfit: number; stopLoss: number; maxHold: number;
}

export const SIGNALS: { id: Rule["signalType"]; label: string; needsRef: boolean; needsPct?: boolean; needsMA?: boolean; blurb: string }[] = [
  { id: "new_high", label: "New all-time high", needsRef: true, blurb: "Fires when the reference index closes above its prior peak." },
  { id: "new_low", label: "New all-time low", needsRef: true, blurb: "Fires when the reference index closes below its prior trough." },
  { id: "pct_drop", label: "Drops by %", needsRef: true, needsPct: true, blurb: "Fires when the reference falls by X% over a rolling window." },
  { id: "pct_gain", label: "Gains by %", needsRef: true, needsPct: true, blurb: "Fires when the reference rises by X% over a rolling window." },
  { id: "ma_cross_up", label: "Golden cross (MA)", needsRef: false, needsMA: true, blurb: "Fires when the fast moving average crosses above the slow one." },
  { id: "ma_cross_down", label: "Death cross (MA)", needsRef: false, needsMA: true, blurb: "Fires when the fast moving average crosses below the slow one." },
];

export const REF_OPTIONS = [
  { value: "^GSPC", label: "S&P 500 (^GSPC)" },
  { value: "^IXIC", label: "Nasdaq (^IXIC)" },
  { value: "^DJI", label: "Dow Jones (^DJI)" },
  { value: "^RUT", label: "Russell 2000 (^RUT)" },
];

export const blankRule = (): Rule => ({
  instrument: "SQQQ", direction: "long", signalType: "new_high", reference: "^GSPC",
  pct: 5, windowDays: 10, fastDays: 20, slowDays: 50, takeProfit: 10, stopLoss: 3, maxHold: 30,
});

export function ruleSummary(r: Rule): string {
  const inst = (r.instrument || "?").toUpperCase();
  const verb = r.direction === "short" ? "short" : "buy";
  let trigger: string;
  switch (r.signalType) {
    case "new_high": trigger = `${refLabel(r.reference)} prints a new all-time high`; break;
    case "new_low": trigger = `${refLabel(r.reference)} prints a new all-time low`; break;
    case "pct_drop": trigger = `${refLabel(r.reference)} drops ${r.pct}% over ${r.windowDays} days`; break;
    case "pct_gain": trigger = `${refLabel(r.reference)} gains ${r.pct}% over ${r.windowDays} days`; break;
    case "ma_cross_up": trigger = `${inst}'s ${r.fastDays}-day average crosses above its ${r.slowDays}-day`; break;
    case "ma_cross_down": trigger = `${inst}'s ${r.fastDays}-day average crosses below its ${r.slowDays}-day`; break;
  }
  const hold = r.maxHold ? `, or after ${r.maxHold} days` : "";
  return `When ${trigger}, ${verb} ${inst} and exit at +${r.takeProfit}% (take profit) or −${r.stopLoss}% (stop loss)${hold}.`;
}

export function ruleToPayload(name: string, category: string, r: Rule, tagline: string) {
  const inst = r.instrument.trim().toUpperCase();
  const reference = r.signalType === "ma_cross_up" || r.signalType === "ma_cross_down" ? inst : r.reference;
  const signal: Record<string, any> = { type: r.signalType, reference };
  if (r.signalType === "pct_drop" || r.signalType === "pct_gain") { signal.pct = r.pct / 100; signal.window_days = r.windowDays; }
  if (r.signalType === "ma_cross_up" || r.signalType === "ma_cross_down") { signal.fast_days = r.fastDays; signal.slow_days = r.slowDays; }
  const rules = {
    instrument: inst, direction: r.direction, signal,
    take_profit_pct: r.takeProfit / 100, stop_loss_pct: r.stopLoss / 100,
    max_hold_days: r.maxHold || null,
  };
  const parameters: Record<string, any> = { tickers: [inst], rules };
  if (category === "options") {
    parameters.synthetic_options = {
      style: "underlying_proxy",
      underlying: inst,
      assumption: "Option-like payoff is approximated with underlying daily closes until options-chain history is available.",
    };
  }
  return {
    category, name: name.trim(),
    description: (tagline || "").trim() || ruleSummary(r),
    history: "Built in the Atlas signal-rule builder.",
    methodology: ruleSummary(r) + " Backtest it to populate live performance.",
    parameters,
    metrics: {},
    caveats: [
      "Research simulation only; not financial advice.",
      "Signal rules can whipsaw — validate with a backtest before relying on it.",
    ],
  };
}

export interface RuleValidationIssue { field: string; message: string }

export function validateRuleDraft(category: string, name: string, r: Rule): RuleValidationIssue[] {
  const issues: RuleValidationIssue[] = [];
  const inst = r.instrument.trim().toUpperCase();
  if (name.trim().length < 2) issues.push({ field: "name", message: "Model name must be at least 2 characters." });
  if (!inst) issues.push({ field: "instrument", message: "Instrument ticker is required." });
  if (inst && !/^[A-Z0-9.^-]{1,16}$/.test(inst)) issues.push({ field: "instrument", message: "Instrument ticker can only contain letters, numbers, dots, carets, or hyphens." });

  if ((r.signalType === "pct_drop" || r.signalType === "pct_gain") && (r.pct <= 0 || r.pct > 100)) {
    issues.push({ field: "signal.pct", message: "Signal move size must be greater than 0% and no more than 100%." });
  }
  if ((r.signalType === "pct_drop" || r.signalType === "pct_gain") && (r.windowDays < 1 || r.windowDays > 252)) {
    issues.push({ field: "signal.windowDays", message: "Signal lookback window must be between 1 and 252 days." });
  }
  if ((r.signalType === "ma_cross_up" || r.signalType === "ma_cross_down") && r.fastDays >= r.slowDays) {
    issues.push({ field: "signal.fastDays", message: "Fast moving average must be shorter than the slow moving average." });
  }
  if (r.takeProfit <= 0 || r.takeProfit > 200) issues.push({ field: "takeProfit", message: "Take profit must be greater than 0% and no more than 200%." });
  if (r.stopLoss <= 0 || r.stopLoss > 100) issues.push({ field: "stopLoss", message: "Stop loss must be greater than 0% and no more than 100%." });
  if (r.maxHold < 0 || r.maxHold > 1095) issues.push({ field: "maxHold", message: "Max holding period must be between 0 and 1095 days." });
  if (["long_term", "income_quality", "risk_rotation"].includes(category) && r.direction === "short") {
    issues.push({ field: "direction", message: "This family only supports long rule exposure. Use Short Selling for bearish rules." });
  }
  if (category === "short_selling" && r.direction !== "short") {
    issues.push({ field: "direction", message: "Short Selling rules must use short direction." });
  }
  return issues;
}

export function rulesFromModel(m: Model): Rule | null {
  const r = (m.parameters || {}).rules;
  if (!r) return null;
  const s = r.signal || {};
  return {
    instrument: r.instrument || (m.parameters?.tickers || [])[0] || "SQQQ",
    direction: r.direction === "short" ? "short" : "long",
    signalType: s.type || "new_high",
    reference: s.reference || "^GSPC",
    pct: Math.round((s.pct ?? 0.05) * 100),
    windowDays: s.window_days ?? 10,
    fastDays: s.fast_days ?? 20,
    slowDays: s.slow_days ?? 50,
    takeProfit: Math.round((r.take_profit_pct ?? 0.1) * 100),
    stopLoss: Math.round((r.stop_loss_pct ?? 0.05) * 100),
    maxHold: r.max_hold_days ?? 0,
  };
}

// ---- guided builder knobs -------------------------------------------------
// Every knob maps 1:1 onto a parameter the backtest engine actually reads
// (take_profit_pct / stop_loss_pct / max_hold_days / max_positions / tickers).
// Engine category defaults: take profit 25%, stop loss 12%, max hold 252 days.
export interface Knobs { tickers: string; tp: number; stop: number; hold: number; maxpos: number }
export const blankKnobs = (): Knobs => ({ tickers: "SPY", tp: 25, stop: 12, hold: 252, maxpos: 15 });

export function parseTickers(raw: string): string[] {
  return Array.from(new Set(
    raw.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter((t) => /^[A-Z0-9.^-]{1,16}$/.test(t))
  ));
}

// Build a backend create/update payload from the knobs. `base` is the strategy's
// existing parameters when editing — everything not owned by a knob (model key,
// thresholds, universe, …) is preserved, never wiped.
export function knobsToPayload(name: string, category: string, knobs: Knobs, tagline: string, base?: Record<string, any>) {
  const parameters: Record<string, any> = { ...(base ?? {}) };
  parameters.take_profit_pct = knobs.tp / 100;
  parameters.stop_loss_pct = knobs.stop / 100;
  parameters.max_hold_days = knobs.hold;
  parameters.max_positions = knobs.maxpos;
  const tickers = parseTickers(knobs.tickers);
  if (tickers.length) {
    // Explicit tickers pin the model to a fixed basket (unless it already declared a basket kind).
    parameters.tickers = tickers;
    const kind = String(base?.universe ?? "");
    parameters.universe = ["tickers", "fixed", "custom"].includes(kind) ? kind : "tickers";
  } else if (!base?.tickers?.length) {
    delete parameters.tickers;
  }
  // An empty box on a model that had tickers means "no change" — the spread keeps them.
  const basket = tickers.length ? tickers.join(", ") : "its screened universe";
  return {
    category, name: name.trim(),
    description: (tagline || "").trim() || `${CAT_SHORT[category] || category} strategy over ${basket}.`,
    history: base ? undefined : "Created in the Atlas strategy builder.",
    methodology: `Trades ${basket} with a +${knobs.tp}% take profit, −${knobs.stop}% stop loss, ${knobs.hold}-day max hold, up to ${knobs.maxpos} positions. Fills at next-session closes with costs; results come from real backtests only.`,
    parameters,
    // Never persist projected/fabricated metrics — cards stay honest until a real run lands.
    metrics: {},
    caveats: ["Builder-generated idea; validate with a backtest before relying on it."],
  };
}

// ---- backtest regimes → real date ranges --------------------------------
const isoDate = (d: Date) => d.toISOString().slice(0, 10);
const yearsAgo = (n: number) => { const d = new Date(); d.setFullYear(d.getFullYear() - n); return isoDate(d); };

export const REGIMES = [
  { id: "dotcom", label: "2000 – 2003", sub: "Dot-com bust", start: "2000-01-01", end: "2003-12-31" },
  { id: "gfc", label: "2006 – 2009", sub: "Global Financial Crisis", start: "2006-06-01", end: "2009-12-31" },
  { id: "bull", label: "2013 – 2017", sub: "Steady bull market", start: "2013-01-01", end: "2017-12-31" },
  { id: "covid", label: "2019 – 2021", sub: "COVID crash & melt-up", start: "2019-06-01", end: "2021-06-30" },
  { id: "bear", label: "2022", sub: "Rate-shock bear", start: "2022-01-01", end: "2022-12-31" },
  { id: "recent", label: "Last 3 years", sub: "Recent market", start: yearsAgo(3), end: isoDate(new Date()) },
];

// ---- favorites (localStorage) -------------------------------------------
const FAV_KEY = "fa:pt:favorites";
export function getFavorites(): number[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); } catch { return []; }
}
export function toggleFavorite(id: number): number[] {
  const cur = getFavorites();
  const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
  try { localStorage.setItem(FAV_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  return next;
}
