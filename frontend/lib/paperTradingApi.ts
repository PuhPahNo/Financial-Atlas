import { ApiError, Envelope } from "@/lib/api";

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(init?.headers ?? {}) },
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = json?.error ?? {};
    // FastAPI request-validation errors bypass the Atlas envelope: {"detail": [{loc, msg}, ...]}
    if (!err.message && Array.isArray(json?.detail)) {
      const msg = json.detail
        .map((d: any) => `${(d.loc ?? []).filter((p: any) => p !== "body").join(".")}: ${d.msg}`)
        .join("; ");
      throw new ApiError("INVALID_REQUEST", msg || `Request failed (${res.status})`, json);
    }
    throw new ApiError(err.code ?? "INTERNAL", err.message ?? `Request failed (${res.status})`, err);
  }
  return json as Envelope<T>;
}

/** Enqueue a backtest and poll until it settles. Throws ApiError on failed/cancelled.
 * Abort the signal to stop POLLING — the server job itself keeps running (and its
 * result still persists), which is what background/headline callers want. */
export async function runBacktestAndWait(
  payload: Record<string, unknown>,
  opts: { signal?: AbortSignal; onStatus?: (status: RunStatus) => void; pollMs?: number } = {},
): Promise<BacktestRun> {
  const queued = await paperTradingApi.queueBacktest(payload);
  let run = queued.data.run;
  while (run.status === "queued" || run.status === "running") {
    opts.onStatus?.(run.status);
    if (opts.signal?.aborted) throw new DOMException("Backtest polling aborted", "AbortError");
    await new Promise((r) => setTimeout(r, opts.pollMs ?? 1600));
    if (opts.signal?.aborted) throw new DOMException("Backtest polling aborted", "AbortError");
    run = (await paperTradingApi.getBacktest(run.id)).data.run;
  }
  if (run.status === "failed") throw new ApiError("BACKTEST_FAILED", run.warnings?.[0] || "Backtest failed");
  if (run.status === "cancelled") throw new ApiError("BACKTEST_CANCELLED", "Backtest was cancelled");
  opts.onStatus?.(run.status);
  return run;
}

/** Human-readable message from an ApiError, including field-level validator issues. */
export function apiErrorText(e: any): string {
  const base = e?.message || "Request failed";
  const issues = e?.details?.issues;
  if (Array.isArray(issues) && issues.length) {
    const lines = issues.map((i: any) => (i.field ? `${i.field}: ${i.message}` : i.message)).filter(Boolean);
    return `${base} — ${lines.join("; ")}`;
  }
  return base;
}

const body = (value: unknown) => JSON.stringify(value);

export interface Strategy {
  id: number;
  category: string;
  name: string;
  origin: string;
  description: string;
  history: string;
  methodology: string;
  parameters: Record<string, any>;
  defaults: Record<string, any>;
  metrics: Record<string, number | string | null>;
  caveats: string[];
}
export interface Category {
  id: string;
  label: string;
  description: string;
  strategies: Strategy[];
}

export interface IntegrityCheck {
  id: string;
  label: string;
  status: "pass" | "warn" | "info";
  detail: string;
}
export interface Integrity {
  checks: IntegrityCheck[];
  grade: "pass" | "warn" | "info";
}
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export interface BacktestRun {
  id: number;
  strategy_id: number;
  name: string;
  status: RunStatus;
  created_at?: string | null;
  start_date?: string;
  end_date?: string;
  metrics: Record<string, number | null>;
  warnings: string[];
  integrity?: Integrity | null;
  holdings?: { ticker: string; weight: number }[];
  trades: any[];
  equity_curve: { date: string; cash: number; equity: number; benchmark_equity: number }[];
}
export interface RunSummary {
  id: number; strategy_id: number | null; name: string; status: RunStatus;
  start_date: string | null; end_date: string | null; created_at: string | null;
  metrics: Record<string, number | null>; sweep: boolean;
}
export interface SweepRun {
  rank: number;
  run_id: number;
  parameter: string;
  value: number;
  metrics: Record<string, number | null>;
  parameters: Record<string, any>;
  warnings: string[];
}
export interface ParameterSweep {
  strategy_id: number;
  strategy_name: string;
  parameter: string;
  rank_by: string;
  runs: SweepRun[];
}

export interface Allocation {
  strategy_id: number; weight: number; name: string; category: string | null; dollars: number;
  strategy_status?: string; archived?: boolean;
}
export interface TraderAccount {
  id: number; name: string; emoji: string; bio: string; starting_cash: number; status: string;
  allocations: Allocation[]; invested_pct: number; cash_pct: number; reconciled_pct?: number; created_at: string;
}
export interface Contribution {
  strategy_id: number; name: string; category: string | null; strategy_status?: string; archived?: boolean;
  weight: number; dollars: number; final: number; pnl: number; return_pct: number; turnover?: number;
}
export interface AccountRisk {
  gross_exposure: number; cash_pct: number; concentration: number; herfindahl: number; turnover: number; max_drawdown: number;
}
export interface AccountAttribution {
  top_contributors: Contribution[]; laggards: Contribution[]; allocation: any[];
  reconciliation: { contribution_final: number; cash_dollars: number; current_value: number; difference: number };
}
export interface AccountPerformance {
  account_id: number; window: { start: string; end: string }; basis?: string; basis_note?: string;
  starting_cash: number; cash_dollars: number;
  current_value: number; total_return: number; benchmark_return: number; alpha: number; max_drawdown: number;
  equity: { date: string; equity: number; benchmark_equity: number }[];
  drawdown_curve?: { date: string; drawdown: number }[];
  risk?: AccountRisk; attribution?: AccountAttribution;
  contributions: Contribution[]; warnings: string[];
}
export interface AccountValue {
  account_id: number; current_value: number; eod_value: number;
  day_change: number; day_change_pct: number; as_of: string;
  market_open: boolean; delayed_minutes: number; served_by: string; stale: boolean;
  warnings: string[];
}
export const paperTradingApi = {
  categories: () => request<{ categories: Category[] }>("/paper-trading/categories"),
  createStrategy: (payload: unknown) =>
    request<{ strategy: Strategy }>("/paper-trading/strategies", { method: "POST", body: body(payload) }),
  updateStrategy: (id: number, payload: unknown) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}`, { method: "PUT", body: body(payload) }),
  deleteStrategy: (id: number) =>
    request<{ archived: number; in_use_by: string[] }>(`/paper-trading/strategies/${id}`, { method: "DELETE" }),
  listArchivedStrategies: () =>
    request<{ strategies: Strategy[] }>("/paper-trading/strategies-archived"),
  unarchiveStrategy: (id: number) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}/unarchive`, { method: "POST", body: body({}) }),
  queueBacktest: (payload: Record<string, unknown>) =>
    request<{ run: BacktestRun }>("/backtests", { method: "POST", body: body({ ...payload, queue: true }) }),
  getBacktest: (id: number) => request<{ run: BacktestRun }>(`/backtests/${id}`),
  listBacktests: (strategyId?: number, limit = 20) =>
    request<{ runs: RunSummary[] }>(`/backtests?limit=${limit}${strategyId ? `&strategy_id=${strategyId}` : ""}`),
  cancelBacktest: (id: number) =>
    request<{ run: BacktestRun }>(`/backtests/${id}/cancel`, { method: "POST", body: body({}) }),
  runSweep: (payload: unknown) =>
    request<{ sweep: ParameterSweep }>("/backtests/sweep", { method: "POST", body: body(payload) }),
  listAccounts: () => request<{ accounts: TraderAccount[] }>("/paper-trading/accounts"),
  createAccount: (payload: unknown) =>
    request<{ account: TraderAccount }>("/paper-trading/accounts", { method: "POST", body: body(payload) }),
  updateAccount: (id: number, payload: unknown) =>
    request<{ account: TraderAccount }>(`/paper-trading/accounts/${id}`, { method: "PUT", body: body(payload) }),
  deleteAccount: (id: number) =>
    request<{ deleted: number }>(`/paper-trading/accounts/${id}`, { method: "DELETE" }),
  accountPerformance: (id: number, start?: string, end?: string) => {
    const qs = start && end ? `?start=${start}&end=${end}` : "";
    return request<AccountPerformance>(`/paper-trading/accounts/${id}/performance${qs}`);
  },
  accountValue: (id: number) => request<AccountValue>(`/paper-trading/accounts/${id}/value`),
  createAssistantSession: () => request<{ session: any; actions: any[] }>("/assistant/sessions", { method: "POST", body: body({}) }),
  sendAssistantMessage: (sessionId: number, message: string) =>
    request<any>(`/assistant/sessions/${sessionId}/messages`, { method: "POST", body: body({ message }) }),
  confirmAssistantAction: (actionId: number) =>
    request<any>(`/assistant/actions/${actionId}/confirm`, { method: "POST", body: body({}) }),
  rejectAssistantAction: (actionId: number) =>
    request<any>(`/assistant/actions/${actionId}/reject`, { method: "POST", body: body({}) }),
};
