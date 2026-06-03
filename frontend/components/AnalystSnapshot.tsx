"use client";

import { price, signClass } from "@/lib/format";

interface Analyst {
  target_high?: number | null;
  target_low?: number | null;
  target_consensus?: number | null;
  target_median?: number | null;
  strong_buy?: number | null;
  buy?: number | null;
  hold?: number | null;
  sell?: number | null;
  strong_sell?: number | null;
  rating?: string | null;
}

const RATING_TONE: Record<string, string> = {
  "Strong Buy": "text-positive border-positive/40 bg-positive/10",
  Buy: "text-positive border-positive/30 bg-positive/10",
  Hold: "text-gold border-gold/30 bg-gold/10",
  Sell: "text-negative border-negative/30 bg-negative/10",
  "Strong Sell": "text-negative border-negative/40 bg-negative/10",
};

// Wall-Street view: rating, price-target range vs current price, and the buy/hold/sell split.
export default function AnalystSnapshot({ analyst, currentPrice }: { analyst: Analyst; currentPrice?: number | null }) {
  const { target_low: lo, target_high: hi, target_consensus: cons } = analyst;
  const upside = cons && currentPrice ? (cons - currentPrice) / currentPrice : null;
  const recs = [
    { k: "strong_buy", label: "Strong Buy", color: "#2aa873" },
    { k: "buy", label: "Buy", color: "#3ECF8E" },
    { k: "hold", label: "Hold", color: "#E0B341" },
    { k: "sell", label: "Sell", color: "#FF8a6b" },
    { k: "strong_sell", label: "Strong Sell", color: "#FF6B6B" },
  ] as const;
  const total = recs.reduce((s, r) => s + ((analyst as any)[r.k] || 0), 0);

  const hasTarget = lo != null && hi != null && cons != null;
  // Domain spans low/high AND the current price so nothing clamps off-edge.
  const pts = [lo, hi, cons, currentPrice].filter((v): v is number => v != null);
  const dlo = pts.length ? Math.min(...pts) : 0;
  const dhi = pts.length ? Math.max(...pts) : 1;
  const dspan = dhi - dlo || 1;
  const xp = (v: number) => Math.max(5, Math.min(95, ((v - dlo) / dspan) * 100));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        {analyst.rating && (
          <span className={`rounded-full border px-3 py-1 text-sm font-medium ${RATING_TONE[analyst.rating] ?? "border-line text-text"}`}>
            {analyst.rating}
          </span>
        )}
        {upside != null && (
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wider text-muted">Implied upside</div>
            <div className={`font-mono text-lg ${signClass(upside)}`}>{(upside * 100).toFixed(1)}%</div>
          </div>
        )}
      </div>

      {hasTarget && (
        <div>
          <div className="mb-7 flex items-center justify-between text-[11px] text-muted">
            <span>Analyst price target</span><span>consensus <span className="font-mono text-text">{price(cons)}</span></span>
          </div>
          <div className="relative mx-1 h-1.5 rounded-full bg-surface-2">
            <div className="absolute h-1.5 rounded-full" style={{ left: `${xp(lo!)}%`, width: `${Math.max(0, xp(hi!) - xp(lo!))}%`, background: "linear-gradient(90deg,#5a48d6,#9d8bff)" }} />
            <Mark x={xp(cons!)} label="consensus" color="#7C6CFF" big />
            {currentPrice != null && <Mark x={xp(currentPrice)} label="" color="#E0B341" big below />}
          </div>
          <div className="mt-2.5 flex justify-between text-[11px] text-muted">
            <span>Low <span className="font-mono text-text">{price(lo)}</span></span>
            {currentPrice != null && <span className="text-gold">now <span className="font-mono">{price(currentPrice)}</span></span>}
            <span>High <span className="font-mono text-text">{price(hi)}</span></span>
          </div>
        </div>
      )}

      {total > 0 && (
        <div>
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">{total} analysts</div>
          <div className="flex h-2.5 overflow-hidden rounded-full">
            {recs.map((r) => {
              const n = (analyst as any)[r.k] || 0;
              return n ? <div key={r.k} style={{ width: `${(n / total) * 100}%`, background: r.color }} title={`${r.label}: ${n}`} /> : null;
            })}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {recs.map((r) => {
              const n = (analyst as any)[r.k] || 0;
              return n ? <span key={r.k}><span className="font-mono text-text">{n}</span> {r.label}</span> : null;
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Mark({ x, label, color, big = false, below = false }: { x: number; label: string; color: string; big?: boolean; below?: boolean }) {
  return (
    <div className="absolute -translate-x-1/2" style={{ left: `${x}%`, top: big ? -4 : -2 }}>
      <div className={`${big ? "h-3.5 w-3.5" : "h-2.5 w-2.5"} rounded-full`} style={{ background: color, boxShadow: "0 0 0 4px #0a0a0f" }} />
      {label && <div className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px]" style={{ color, top: below ? 14 : -16 }}>{label}</div>}
    </div>
  );
}
