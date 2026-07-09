"use client";

import { useState } from "react";
import { Btn, CategoryPicker, Icon, Slider, TextInput } from "./ptkit";
import { knobsToPayload, blankKnobs, parseTickers, CatMeta, Knobs, Model } from "./ptdata";
import RuleBuilder from "./RuleBuilder";

// Every knob maps onto a parameter the engine actually reads. Editing merges
// into the model's existing parameters — model keys, thresholds and universe
// pins are preserved, never replaced.
function knobsFromModel(m: Model): Knobs {
  const p = m.parameters || {};
  return {
    tickers: Array.isArray(p.tickers) ? p.tickers.join(", ") : "",
    tp: typeof p.take_profit_pct === "number" ? Math.round(p.take_profit_pct * 100) : 25,
    stop: typeof p.stop_loss_pct === "number" ? Math.round(p.stop_loss_pct * 100) : 12,
    hold: typeof p.max_hold_days === "number" ? p.max_hold_days : 252,
    maxpos: typeof p.max_positions === "number" ? p.max_positions : 15,
  };
}

export default function Builder({ seed, cats, onSave, onCancel }: {
  seed: Model | null; cats: CatMeta[]; onSave: (payload: any, editId: number | null) => void | Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState(seed?.name ?? "");
  const tagline = seed?.tagline ?? "";
  const [category, setCategory] = useState(seed?.category ?? cats[0]?.id ?? "long_term");
  const [knobs, setKnobs] = useState<Knobs>(() => (seed ? knobsFromModel(seed) : blankKnobs()));
  const [mode, setMode] = useState<"guided" | "rule">(seed?.isRule ? "rule" : "guided");
  const [saving, setSaving] = useState(false);
  const setKnob = (k: keyof Knobs, v: number | string) => setKnobs((d) => ({ ...d, [k]: v }));
  const cat = cats.find((c) => c.id === category) ?? cats[0];
  const tickers = parseTickers(knobs.tickers);
  const isModelLibrary = !!seed && !seed.isRule && typeof seed.parameters?.model === "string";
  const indexWide = seed ? !seed.parameters?.tickers?.length && !tickers.length : false;
  const valid = name.trim().length > 1 && (!!seed || tickers.length > 0);

  async function save() {
    if (saving) return;
    setSaving(true);
    try { await onSave(knobsToPayload(name, category, knobs, tagline, seed?.parameters), seed?.id ?? null); }
    finally { setSaving(false); }
  }

  // Mode switch only when creating from scratch — editing locks to the model's type.
  const toggle = !seed ? (
    <div style={{ marginBottom: 22 }}>
      <div style={{ display: "flex", gap: 8 }}>
        {(["guided", "rule"] as const).map((m) => (
          <button key={m} onClick={() => setMode(m)} style={{ padding: "8px 14px", cursor: "pointer", fontSize: 12.5, fontWeight: 600, fontFamily: "var(--font-sans)",
            borderRadius: "var(--r-pill)", color: mode === m ? "var(--text-1)" : "var(--text-2)",
            background: mode === m ? "var(--surface-3)" : "var(--surface-2)", border: `1px solid ${mode === m ? "var(--border-strong)" : "var(--border)"}` }}>
            {m === "guided" ? "Basket & exits" : "Signal rule"}
          </button>
        ))}
      </div>
    </div>
  ) : null;

  if (mode === "rule") {
    return (
      <div style={{ animation: "pt-fadeUp .3s var(--ease)" }}>
        {toggle}
        <RuleBuilder seed={seed && seed.isRule ? seed : null} cats={cats} onSave={onSave} onCancel={onCancel} />
      </div>
    );
  }

  return (
   <div style={{ animation: "pt-fadeUp .3s var(--ease)" }}>
    {toggle}
    <div className="m-stack" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 0.95fr)", gap: 26, alignItems: "start" }}>
      <div className="card" style={{ padding: 26 }}>
        <h3 className="serif" style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 600 }}>{seed ? "Tune model" : "Design a basket strategy"}</h3>
        <p style={{ margin: "0 0 24px", fontSize: 13.5, color: "var(--text-2)" }}>
          {seed ? "Adjust the exits and sizing — everything else about the model is preserved." : "Pick tickers and exits — Atlas backtests it on real prices when you save."}
        </p>

        <div style={{ marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Model name</div>
          <TextInput value={name} onChange={setName} placeholder="e.g. Mega-cap Compounders" />
        </div>
        <div style={{ marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Category</div>
          <CategoryPicker categories={cats} value={category} onChange={setCategory} />
        </div>

        <div style={{ marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Tickers</div>
          <TextInput mono value={knobs.tickers} onChange={(v) => setKnob("tickers", v)} placeholder="e.g. AAPL, MSFT, GOOGL" />
          <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6, lineHeight: 1.4 }}>
            {indexWide
              ? "This model screens its full index universe. Leave empty to keep that, or enter tickers to pin it to a fixed basket."
              : "Comma-separated basket the strategy trades. The category's entry criteria decide when each name is bought."}
          </div>
        </div>

        <div style={{ height: 1, background: "var(--border)", margin: "6px 0 22px" }} />

        <div style={{ marginBottom: 22 }}><Slider label="Take profit" value={knobs.tp} min={5} max={100} step={1} unit="%" onChange={(v) => setKnob("tp", v)} hue="var(--pos)" /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Stop loss" value={knobs.stop} min={2} max={25} step={1} unit="%" onChange={(v) => setKnob("stop", v)} hue="var(--neg)" /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Max holding period" value={knobs.hold} min={5} max={365} step={1} unit=" days" onChange={(v) => setKnob("hold", v)} hue={cat.hue} /></div>
        <div style={{ marginBottom: 4 }}><Slider label="Max positions" value={knobs.maxpos} min={1} max={50} step={1} onChange={(v) => setKnob("maxpos", v)} hue={cat.hue} /></div>
      </div>

      <div style={{ position: "sticky", top: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card" style={{ padding: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 12 }}>What gets saved</div>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6, color: "var(--text-1)" }}>
            Trades <span className="mono">{tickers.length ? tickers.join(", ") : indexWide ? "its screened index universe" : "—"}</span> with
            a <span style={{ color: "var(--pos)" }}>+{knobs.tp}% take profit</span>, a <span style={{ color: "var(--neg)" }}>−{knobs.stop}% stop loss</span>,
            a {knobs.hold}-day time stop, and up to {knobs.maxpos} open positions.
          </p>
          {isModelLibrary && (
            <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--r-sm)", display: "flex", gap: 9, alignItems: "flex-start" }}>
              <span style={{ color: "var(--accent-2)", marginTop: 1 }}><Icon name="info" size={14} /></span>
              <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.5 }}>
                This is a model-library strategy (<span className="mono">{String(seed?.parameters?.model)}</span>). Its ranking logic and thresholds are kept as-is — only the exits, sizing and basket above change.
              </span>
            </div>
          )}
          <div style={{ marginTop: 14, padding: "11px 13px", background: "var(--surface-2)", borderRadius: "var(--r-sm)", display: "flex", gap: 9, alignItems: "flex-start" }}>
            <span style={{ color: "var(--accent-2)", marginTop: 1 }}><Icon name="info" size={14} /></span>
            <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.5 }}>
              No projections here: when you save, Atlas runs a real backtest on adjusted prices (last 3 years) and the card fills in with measured results.
            </span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Btn variant="primary" icon={seed ? "edit" : "plus"} onClick={save} disabled={!valid || saving} style={{ flex: 1 }}>
            {saving ? "Saving…" : seed ? "Save changes" : "Create & track"}</Btn>
          <Btn variant="soft" onClick={onCancel} disabled={saving}>Cancel</Btn>
        </div>
        {!valid && <div style={{ fontSize: 12, color: "var(--text-3)", textAlign: "center" }}>{name.trim().length > 1 ? "Add at least one ticker." : "Give your model a name to save it."}</div>}
      </div>
    </div>
   </div>
  );
}
