"use client";

import { useState } from "react";
import { Btn, CatDot, Icon, Slider, TextInput } from "./ptkit";
import {
  CatMeta, Model, Rule, SIGNALS, REF_OPTIONS, blankRule, ruleSummary, ruleToPayload, rulesFromModel,
} from "./ptdata";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{label}</div>
      {children}
      {hint && <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6, lineHeight: 1.4 }}>{hint}</div>}
    </div>
  );
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <div style={{ position: "relative" }}>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={{ width: "100%", appearance: "none", WebkitAppearance: "none", cursor: "pointer",
        padding: "11px 38px 11px 14px", background: "var(--surface-2)", color: "var(--text-1)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", fontSize: 14, fontFamily: "var(--font-sans)", outline: "none" }}>
        {options.map((o) => <option key={o.value} value={o.value} style={{ background: "#16161e" }}>{o.label}</option>)}
      </select>
      <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--text-3)" }}><Icon name="chevronDown" size={15} /></span>
    </div>
  );
}

export default function RuleBuilder({ seed, cats, onSave, onCancel }: {
  seed: Model | null; cats: CatMeta[]; onSave: (payload: any, editId: number | null) => void; onCancel: () => void }) {
  const [name, setName] = useState(seed?.name ?? "");
  const [tagline, setTagline] = useState(seed && seed.isRule ? seed.tagline : "");
  const [category, setCategory] = useState(seed?.category ?? "risk_rotation");
  const [rule, setRule] = useState<Rule>(() => (seed ? rulesFromModel(seed) : null) ?? blankRule());
  const set = <K extends keyof Rule>(k: K, v: Rule[K]) => setRule((d) => ({ ...d, [k]: v }));

  const cat = cats.find((c) => c.id === category) ?? cats[0];
  const sigMeta = SIGNALS.find((s) => s.id === rule.signalType)!;
  const valid = name.trim().length > 1 && rule.instrument.trim().length >= 1;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 0.92fr)", gap: 26, alignItems: "start", animation: "pt-fadeUp .3s var(--ease)" }}>
      <div className="card" style={{ padding: 26 }}>
        <h3 className="serif" style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 600 }}>{seed ? "Tune signal rule" : "Design a signal rule"}</h3>
        <p style={{ margin: "0 0 24px", fontSize: 13.5, color: "var(--text-2)" }}>Define a trigger and exits — Atlas will backtest it bar-by-bar on real prices.</p>

        <Field label="Model name"><TextInput value={name} onChange={setName} placeholder="e.g. S&P High Fade" /></Field>

        <Field label="Category">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {cats.map((c) => {
              const on = c.id === category;
              return (
                <button key={c.id} onClick={() => setCategory(c.id)} style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 13px", cursor: "pointer",
                  fontSize: 12.5, fontWeight: 600, fontFamily: "var(--font-sans)", borderRadius: "var(--r-pill)", color: on ? "var(--text-1)" : "var(--text-2)",
                  background: on ? "var(--surface-3)" : "var(--surface-2)", border: `1px solid ${on ? "var(--border-strong)" : "var(--border)"}` }}>
                  <CatDot hue={c.hue} />{c.short}
                </button>
              );
            })}
          </div>
        </Field>

        <div style={{ height: 1, background: "var(--border)", margin: "4px 0 22px" }} />

        <Field label="Entry signal" hint={sigMeta.blurb}>
          <div style={{ display: "grid", gap: 8 }}>
            {SIGNALS.map((s) => {
              const on = s.id === rule.signalType;
              return (
                <button key={s.id} onClick={() => set("signalType", s.id)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", cursor: "pointer", textAlign: "left",
                  borderRadius: "var(--r-sm)", background: on ? "var(--accent-soft)" : "var(--surface-2)", border: `1px solid ${on ? "var(--accent-line)" : "var(--border)"}`,
                  color: on ? "var(--accent-2)" : "var(--text-2)", fontFamily: "var(--font-sans)", fontSize: 13.5, fontWeight: 600 }}>
                  <span style={{ width: 16, height: 16, borderRadius: 999, border: `2px solid ${on ? "var(--accent)" : "var(--border-strong)"}`, display: "grid", placeItems: "center", flexShrink: 0 }}>
                    {on && <span style={{ width: 7, height: 7, borderRadius: 999, background: "var(--accent)" }} />}
                  </span>
                  {s.label}
                </button>
              );
            })}
          </div>
        </Field>

        {sigMeta.needsRef && (
          <Field label="Reference index" hint="The series the signal watches (you trade the instrument below, not this).">
            <Select value={rule.reference} onChange={(v) => set("reference", v)} options={REF_OPTIONS} />
          </Field>
        )}

        {sigMeta.needsPct && (
          <>
            <Field label="Move size"><Slider label="% move" value={rule.pct} min={1} max={30} step={1} unit="%" onChange={(v) => set("pct", v)} hue={cat.hue} /></Field>
            <Field label="Over window"><Slider label="Lookback" value={rule.windowDays} min={2} max={60} step={1} unit=" days" onChange={(v) => set("windowDays", v)} hue={cat.hue} /></Field>
          </>
        )}
        {sigMeta.needsMA && (
          <>
            <Field label="Fast average"><Slider label="Fast MA" value={rule.fastDays} min={5} max={60} step={1} unit=" days" onChange={(v) => set("fastDays", v)} hue={cat.hue} /></Field>
            <Field label="Slow average"><Slider label="Slow MA" value={rule.slowDays} min={20} max={200} step={5} unit=" days" onChange={(v) => set("slowDays", v)} hue={cat.hue} /></Field>
          </>
        )}

        <div style={{ height: 1, background: "var(--border)", margin: "4px 0 22px" }} />

        <Field label="Instrument to trade" hint="The ticker actually bought or shorted — e.g. SQQQ, an inverse Nasdaq ETF.">
          <TextInput mono value={rule.instrument} onChange={(v) => set("instrument", v.toUpperCase())} placeholder="SQQQ" />
        </Field>
        <Field label="Direction">
          <div style={{ display: "flex", gap: 8 }}>
            {(["long", "short"] as const).map((d) => {
              const on = rule.direction === d;
              return (
                <button key={d} onClick={() => set("direction", d)} style={{ flex: 1, padding: "10px 14px", cursor: "pointer", fontSize: 13, fontWeight: 600, fontFamily: "var(--font-sans)",
                  borderRadius: "var(--r-sm)", textTransform: "capitalize", color: on ? (d === "short" ? "var(--neg)" : "var(--pos)") : "var(--text-2)",
                  background: on ? (d === "short" ? "var(--neg-soft)" : "var(--pos-soft)") : "var(--surface-2)", border: `1px solid ${on ? "transparent" : "var(--border)"}` }}>{d}</button>
              );
            })}
          </div>
        </Field>

        <Field label="Take profit"><Slider label="Exit at gain of" value={rule.takeProfit} min={1} max={50} step={1} unit="%" onChange={(v) => set("takeProfit", v)} hue="var(--pos)" /></Field>
        <Field label="Stop loss"><Slider label="Exit at loss of" value={rule.stopLoss} min={1} max={25} step={1} unit="%" onChange={(v) => set("stopLoss", v)} hue="var(--neg)" /></Field>
        <Field label="Max holding period" hint="Time stop — close the position after this many days even if neither exit is hit. 0 disables it.">
          <Slider label="Force exit after" value={rule.maxHold} min={0} max={120} step={5} unit={rule.maxHold === 0 ? " (off)" : " days"} onChange={(v) => set("maxHold", v)} hue={cat.hue} />
        </Field>
      </div>

      <div style={{ position: "sticky", top: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card" style={{ padding: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 12 }}>Strategy in plain English</div>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "var(--text-1)" }}>{ruleSummary(rule)}</p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 20 }}>
            <div style={{ padding: "12px 14px", background: "var(--pos-soft)", borderRadius: "var(--r-sm)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--pos)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}><Icon name="target" size={13} /> Take profit</div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 600, color: "var(--pos)" }}>+{rule.takeProfit}%</div>
            </div>
            <div style={{ padding: "12px 14px", background: "var(--neg-soft)", borderRadius: "var(--r-sm)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--neg)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 5 }}><Icon name="shield" size={13} /> Stop loss</div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 600, color: "var(--neg)" }}>−{rule.stopLoss}%</div>
            </div>
          </div>

          <div style={{ marginTop: 16, padding: "11px 13px", background: "var(--surface-2)", borderRadius: "var(--r-sm)", display: "flex", gap: 9, alignItems: "flex-start" }}>
            <span style={{ color: "var(--accent-2)", marginTop: 1 }}><Icon name="info" size={14} /></span>
            <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.5 }}>Save it, then open the <strong style={{ color: "var(--text-1)" }}>Backtest</strong> tab to run this rule over a real market regime and see every fill.</span>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <Btn variant="primary" icon={seed ? "edit" : "plus"} onClick={() => onSave(ruleToPayload(name, category, rule, tagline), seed?.id ?? null)} disabled={!valid} style={{ flex: 1 }}>
            {seed ? "Save changes" : "Create & track"}</Btn>
          <Btn variant="soft" onClick={onCancel}>Cancel</Btn>
        </div>
        {!valid && <div style={{ fontSize: 12, color: "var(--text-3)", textAlign: "center" }}>Add a model name and an instrument ticker to save.</div>}
      </div>
    </div>
  );
}
