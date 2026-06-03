"use client";

import { useEffect, useState } from "react";
import { Strategy } from "@/lib/paperTradingApi";
import { Panel } from "@/components/ui";

export default function StrategyEditor({
  strategy,
  onSave,
  busy,
}: {
  strategy: Strategy | null;
  onSave: (payload: any) => void;
  busy?: boolean;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [methodology, setMethodology] = useState("");
  const [params, setParams] = useState("{}");

  useEffect(() => {
    setName(strategy?.origin === "seeded" ? `${strategy.name} Custom` : strategy?.name ?? "");
    setDescription(strategy?.description ?? "");
    setMethodology(strategy?.methodology ?? "");
    setParams(JSON.stringify(strategy?.parameters ?? { tickers: ["SPY"], lookback_days: 120 }, null, 2));
  }, [strategy]);

  function save() {
    let parsed: Record<string, any>;
    try {
      parsed = JSON.parse(params || "{}");
    } catch {
      alert("Parameters must be valid JSON.");
      return;
    }
    onSave({
      category: strategy?.category ?? "long_term",
      name,
      description,
      methodology,
      history: strategy?.history ?? "Created in the Paper Trading editor.",
      parameters: parsed,
      caveats: strategy?.caveats ?? ["Research simulation only; not financial advice."],
    });
  }

  return (
    <Panel title="Tune Or Create Model" hint="Clone a seeded model, then adjust assumptions and parameter JSON.">
      <div className="space-y-3">
        <label className="block text-xs font-medium text-muted">
          Model name
          <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        </label>
        <label className="block text-xs font-medium text-muted">
          Description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        </label>
        <label className="block text-xs font-medium text-muted">
          Methodology
          <textarea value={methodology} onChange={(e) => setMethodology(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-text outline-none focus:border-accent" />
        </label>
        <label className="block text-xs font-medium text-muted">
          Parameters
          <textarea value={params} onChange={(e) => setParams(e.target.value)} rows={8} spellCheck={false} className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2 font-mono text-xs text-text outline-none focus:border-accent" />
        </label>
        <button onClick={save} disabled={busy || !name.trim()} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white shadow-glow disabled:opacity-50">
          {busy ? "Saving..." : "Save as model"}
        </button>
      </div>
    </Panel>
  );
}
