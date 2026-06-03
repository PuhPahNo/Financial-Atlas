"use client";

import { Insight, Tone } from "@/lib/insights";
import { Tooltip } from "./ui";

const TONE: Record<Tone, string> = {
  positive: "text-positive",
  negative: "text-negative",
  neutral: "text-text",
};
const DOT: Record<Tone, string> = {
  positive: "#3ECF8E",
  negative: "#FF6B6B",
  neutral: "#8c8a99",
};

// A row of auto-generated insight callouts — every data tab leads with this.
export default function InsightStrip({ insights }: { insights: (Insight | null)[] }) {
  const items = insights.filter((x): x is Insight => x != null);
  if (!items.length) return null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {items.map((ins, i) => (
        <div key={i} className="rounded-xl border border-line bg-surface/60 px-4 py-3.5">
          <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: DOT[ins.tone] }} />
            {ins.detail ? (
              <Tooltip content={<p className="text-xs leading-relaxed text-muted">{ins.detail}</p>} width={240}>
                {ins.label}
              </Tooltip>
            ) : (
              ins.label
            )}
          </div>
          <div className={`mt-1.5 font-mono text-lg ${TONE[ins.tone]}`}>{ins.value}</div>
        </div>
      ))}
    </div>
  );
}
