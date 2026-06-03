// Single source of number/date formatting (PRD 06 §8). `null` -> "—".

export const DASH = "—";

export function money(value: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : opts.sign ? "+" : "";
  let out: string;
  if (abs >= 1e12) out = `$${(abs / 1e12).toFixed(2)}T`;
  else if (abs >= 1e9) out = `$${(abs / 1e9).toFixed(2)}B`;
  else if (abs >= 1e6) out = `$${(abs / 1e6).toFixed(2)}M`;
  else if (abs >= 1e3) out = `$${(abs / 1e3).toFixed(2)}K`;
  else out = `$${abs.toFixed(2)}`;
  return `${sign}${out}`;
}

export function price(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

export function ratio(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return value.toFixed(digits);
}

export function shares(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  return value.toLocaleString();
}

export function signClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-muted";
  return value >= 0 ? "text-positive" : "text-negative";
}
