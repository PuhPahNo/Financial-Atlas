// Recently-viewed tickers, persisted in localStorage (powers the dashboard).
const KEY = "fa:recents";
const MAX = 8;

export function recordRecent(ticker: string) {
  if (typeof window === "undefined") return;
  const t = ticker.toUpperCase();
  try {
    const prev = getRecents().filter((x) => x !== t);
    const next = [t, ...prev].slice(0, MAX);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore quota/availability errors */
  }
}

export function getRecents(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}
