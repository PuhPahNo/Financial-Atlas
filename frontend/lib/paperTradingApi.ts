import { ApiError, Envelope } from "@/lib/api";

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(init?.headers ?? {}) },
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = json?.error ?? {};
    throw new ApiError(err.code ?? "INTERNAL", err.message ?? `Request failed (${res.status})`, err);
  }
  return json as Envelope<T>;
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
export interface StrategyValidation {
  valid: boolean;
  issues: { field: string; code: string; message: string }[];
  warnings: { field?: string; code: string; message: string }[];
  parameters: Record<string, any>;
}

export interface Category {
  id: string;
  label: string;
  description: string;
  strategies: Strategy[];
}

export interface BacktestRun {
  id: number;
  strategy_id: number;
  name: string;
  metrics: Record<string, number | null>;
  warnings: string[];
  trades: any[];
  equity_curve: { date: string; cash: number; equity: number; benchmark_equity: number }[];
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

export interface Portfolio {
  id: number;
  strategy_id: number;
  name: string;
  cash: number;
  status: string;
  positions: any[];
  orders: any[];
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
  account_id: number; window: { start: string; end: string }; starting_cash: number; cash_dollars: number;
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
export interface RebalanceOrder {
  strategy_id: number; name: string; category: string | null; strategy_status: string; archived: boolean;
  current_weight: number; target_weight: number; delta_weight: number;
  current_dollars: number; target_dollars: number; trade_dollars: number; action: string;
}
export interface RebalancePreview {
  account_id: number; starting_cash: number; current_invested_pct: number; target_invested_pct: number;
  current_cash_pct: number; target_cash_pct: number; current_reconciled_pct: number; target_reconciled_pct: number;
  orders: RebalanceOrder[];
}

export const paperTradingApi = {
  categories: () => request<{ categories: Category[] }>("/paper-trading/categories"),
  strategies: () => request<{ strategies: Strategy[] }>("/paper-trading/strategies"),
  createStrategy: (payload: unknown) =>
    request<{ strategy: Strategy }>("/paper-trading/strategies", { method: "POST", body: body(payload) }),
  validateStrategy: (payload: unknown) =>
    request<StrategyValidation>("/paper-trading/strategies/validate", { method: "POST", body: body(payload) }),
  updateStrategy: (id: number, payload: unknown) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}`, { method: "PUT", body: body(payload) }),
  cloneStrategy: (id: number) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}/clone`, { method: "POST" }),
  deleteStrategy: (id: number) =>
    request<{ deleted: number }>(`/paper-trading/strategies/${id}`, { method: "DELETE" }),
  runBacktest: (payload: unknown) =>
    request<{ run: BacktestRun; holdings: any[] }>("/backtests", { method: "POST", body: body(payload) }),
  runSweep: (payload: unknown) =>
    request<{ sweep: ParameterSweep }>("/backtests/sweep", { method: "POST", body: body(payload) }),
  createPortfolio: (payload: unknown) =>
    request<{ portfolio: Portfolio }>("/paper-trading/portfolios", { method: "POST", body: body(payload) }),
  runPortfolio: (id: number) =>
    request<{ portfolio: Portfolio }>(`/paper-trading/portfolios/${id}/run`, { method: "POST", body: body({}) }),
  listAccounts: () => request<{ accounts: TraderAccount[] }>("/paper-trading/accounts"),
  createAccount: (payload: unknown) =>
    request<{ account: TraderAccount }>("/paper-trading/accounts", { method: "POST", body: body(payload) }),
  updateAccount: (id: number, payload: unknown) =>
    request<{ account: TraderAccount }>(`/paper-trading/accounts/${id}`, { method: "PUT", body: body(payload) }),
  rebalancePreview: (id: number, payload: unknown) =>
    request<{ preview: RebalancePreview }>(`/paper-trading/accounts/${id}/rebalance-preview`, { method: "POST", body: body(payload) }),
  rebalanceAccount: (id: number, payload: unknown) =>
    request<{ account: TraderAccount; preview: RebalancePreview }>(`/paper-trading/accounts/${id}/rebalance`, { method: "POST", body: body(payload) }),
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
