import { ApiError, Envelope } from "@/lib/api";

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(init?.headers ?? {}) },
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = json?.error ?? {};
    throw new ApiError(err.code ?? "INTERNAL", err.message ?? `Request failed (${res.status})`);
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

export interface Portfolio {
  id: number;
  strategy_id: number;
  name: string;
  cash: number;
  status: string;
  positions: any[];
  orders: any[];
}

export interface Allocation { strategy_id: number; weight: number; name: string; category: string | null; dollars: number }
export interface TraderAccount {
  id: number; name: string; emoji: string; bio: string; starting_cash: number; status: string;
  allocations: Allocation[]; invested_pct: number; cash_pct: number; created_at: string;
}
export interface Contribution { strategy_id: number; name: string; category: string | null; weight: number; dollars: number; final: number; pnl: number; return_pct: number }
export interface AccountPerformance {
  account_id: number; window: { start: string; end: string }; starting_cash: number; cash_dollars: number;
  current_value: number; total_return: number; benchmark_return: number; alpha: number; max_drawdown: number;
  equity: { date: string; equity: number; benchmark_equity: number }[]; contributions: Contribution[]; warnings: string[];
}

export const paperTradingApi = {
  categories: () => request<{ categories: Category[] }>("/paper-trading/categories"),
  strategies: () => request<{ strategies: Strategy[] }>("/paper-trading/strategies"),
  createStrategy: (payload: unknown) =>
    request<{ strategy: Strategy }>("/paper-trading/strategies", { method: "POST", body: body(payload) }),
  updateStrategy: (id: number, payload: unknown) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}`, { method: "PUT", body: body(payload) }),
  cloneStrategy: (id: number) =>
    request<{ strategy: Strategy }>(`/paper-trading/strategies/${id}/clone`, { method: "POST" }),
  deleteStrategy: (id: number) =>
    request<{ deleted: number }>(`/paper-trading/strategies/${id}`, { method: "DELETE" }),
  runBacktest: (payload: unknown) =>
    request<{ run: BacktestRun; holdings: any[] }>("/backtests", { method: "POST", body: body(payload) }),
  createPortfolio: (payload: unknown) =>
    request<{ portfolio: Portfolio }>("/paper-trading/portfolios", { method: "POST", body: body(payload) }),
  runPortfolio: (id: number) =>
    request<{ portfolio: Portfolio }>(`/paper-trading/portfolios/${id}/run`, { method: "POST", body: body({}) }),
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
  createAssistantSession: () => request<{ session: any }>("/assistant/sessions", { method: "POST", body: body({}) }),
  sendAssistantMessage: (sessionId: number, message: string) =>
    request<any>(`/assistant/sessions/${sessionId}/messages`, { method: "POST", body: body({ message }) }),
  confirmAssistantAction: (actionId: number) =>
    request<any>(`/assistant/actions/${actionId}/confirm`, { method: "POST", body: body({}) }),
  rejectAssistantAction: (actionId: number) =>
    request<any>(`/assistant/actions/${actionId}/reject`, { method: "POST", body: body({}) }),
};
