// API client (PRD 04). All requests go through the Next.js rewrite to the backend.

interface Meta {
  ticker: string | null;
  served_by: string | null;
  stale: boolean;
  as_of?: string | null;
  warnings?: { section?: string; code: string; message: string }[];
}
export interface Envelope<T> {
  data: T;
  meta: Meta;
}

export class ApiError extends Error {
  code: string;
  details?: any;
  constructor(code: string, message: string, details?: any) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const res = await fetch(`/api/v1${path}`, { ...init, headers });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = json?.error ?? {};
    throw new ApiError(err.code ?? "INTERNAL", err.message ?? `Request failed (${res.status})`, err);
  }
  return json as Envelope<T>;
}

async function get<T>(path: string): Promise<Envelope<T>> {
  return request<T>(path);
}

async function post<T>(path: string, body: unknown): Promise<Envelope<T>> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  search: (q: string) => get<{ ticker: string; name: string }[]>(`/search?q=${encodeURIComponent(q)}`),
  companySnapshot: (t: string) => get<any>(`/company/${t}/snapshot`),
  prices: (t: string, range: string, interval: string) =>
    get<{ bars: any[]; currency: string }>(`/prices/${t}?range=${range}&interval=${interval}`),
  income: (t: string, period: string) => get<any>(`/financials/${t}/income?period=${period}`),
  balance: (t: string, period: string) => get<any>(`/financials/${t}/balance-sheet?period=${period}`),
  cashflow: (t: string, period: string) => get<any>(`/financials/${t}/cash-flow?period=${period}`),
  cashflowAnalysis: (t: string, period: string) => get<any>(`/financials/${t}/cash-flow-analysis?period=${period}`),
  valuation: (t: string) => get<any>(`/valuation/${t}`),
  valuationCustom: (t: string, body: unknown) => post<any>(`/valuation/${t}`, body),
  valuationHistory: (t: string, limit = 8) => get<any>(`/valuation/${t}/history?limit=${limit}`),
  insiders: (t: string) => get<any>(`/ownership/${t}/insiders`),
  institutions: (t: string) => get<any>(`/ownership/${t}/institutions`),
  filings: (t: string, forms?: string) => get<any>(`/filings/${t}${forms ? `?forms=${forms}` : ""}`),
  marketMovers: () => get<any>(`/market/movers`),
  marketContext: () => get<any>(`/market/context`),
  bestPicks: (limit = 8) => get<any>(`/market/best-picks?limit=${limit}`),
  screenerUniverse: () => get<any>(`/screener/universe`),
  screenerIngest: (tickers: string[]) => post<any>(`/screener/ingest`, { tickers }),
  screenerSeed: () => post<any>(`/screener/seed`, {}),
  screenerWarm: (tickers?: string[]) => post<any>(`/screener/warm`, { tickers }),
  screen: (body: unknown) => post<any>(`/screener`, body),
  watchlists: () => get<any>(`/watchlists`),
  createWatchlist: (name: string) => post<any>(`/watchlists`, { name }),
  addWatchlistItem: (id: number, ticker: string) => post<any>(`/watchlists/${id}/items`, { ticker }),
  deleteWatchlist: (id: number) =>
    fetch(`/api/v1/watchlists/${id}`, { method: "DELETE" }).then((r) => r.json()),
  removeWatchlistItem: (id: number, ticker: string) =>
    fetch(`/api/v1/watchlists/${id}/items/${ticker}`, { method: "DELETE" }).then((r) => r.json()),
};
