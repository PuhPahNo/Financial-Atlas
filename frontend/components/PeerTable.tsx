"use client";

import Link from "next/link";
import { money, ratio, pct } from "@/lib/format";

interface Peer {
  ticker: string;
  name?: string | null;
  price?: number | null;
  market_cap?: number | null;
  pe?: number | null;
  fcf_margin?: number | null;
  margin_of_safety?: number | null;
}

// Peer list with optional metric columns (when compare data is loaded).
export default function PeerTable({ peers, detailed = false }: { peers: Peer[]; detailed?: boolean }) {
  if (!peers?.length) return <div className="text-sm text-muted">No peers available.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1.5 pr-3 font-medium">Ticker</th>
            <th className="py-1.5 pr-3 font-medium">Name</th>
            <th className="py-1.5 pr-3 text-right font-medium">Mkt Cap</th>
            {detailed && <th className="py-1.5 pr-3 text-right font-medium">P/E</th>}
            {detailed && <th className="py-1.5 pr-3 text-right font-medium">FCF Margin</th>}
            {detailed && <th className="py-1.5 text-right font-medium">MoS</th>}
          </tr>
        </thead>
        <tbody>
          {peers.map((p) => (
            <tr key={p.ticker} className="border-t border-line">
              <td className="py-2 pr-3"><Link href={`/company/${p.ticker}`} className="font-mono font-semibold text-accent hover:underline">{p.ticker}</Link></td>
              <td className="py-2 pr-3 text-muted">{p.name ?? "—"}</td>
              <td className="py-2 pr-3 text-right font-mono">{money(p.market_cap)}</td>
              {detailed && <td className="py-2 pr-3 text-right font-mono">{ratio(p.pe)}</td>}
              {detailed && <td className="py-2 pr-3 text-right font-mono">{pct(p.fcf_margin)}</td>}
              {detailed && <td className="py-2 text-right font-mono">{pct(p.margin_of_safety)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
