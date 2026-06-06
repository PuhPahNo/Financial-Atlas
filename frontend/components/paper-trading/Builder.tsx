"use client";

import { useMemo, useState } from "react";
import { Btn, CatDot, Segmented, Slider, Stat, TextInput, Pill } from "./ptkit";
import { AreaChart } from "./ptcharts";
import { fmt, project, knobsToPayload, blankKnobs, seriesPct, CatMeta, Knobs, Model } from "./ptdata";
import RuleBuilder from "./RuleBuilder";

function knobsFromModel(m: Model): Knobs {
  const p = m.parameters || {};
  return {
    risk: typeof p.risk === "number" ? p.risk : Math.min(10, Math.max(1, Math.round(m.stats.cagr / 2.5))),
    stop: typeof p.stop_pct === "number" ? Math.round(p.stop_pct * 100) : 8,
    hold: typeof p.hold_days === "number" ? p.hold_days : (typeof p.lookback_days === "number" ? Math.min(250, p.lookback_days) : 20),
    lev: typeof p.leverage === "number" ? p.leverage : 1,
    maxpos: typeof p.max_positions === "number" ? p.max_positions : 20,
    trend: typeof p.trend_filter === "boolean" ? p.trend_filter : true,
  };
}

export default function Builder({ seed, cats, onSave, onCancel }: {
  seed: Model | null; cats: CatMeta[]; onSave: (payload: any, editId: number | null) => void; onCancel: () => void }) {
  const [name, setName] = useState(seed?.name ?? "");
  const [tagline, setTagline] = useState(seed?.tagline ?? "");
  const [category, setCategory] = useState(seed?.category ?? cats[0]?.id ?? "long_term");
  const [knobs, setKnobs] = useState<Knobs>(() => (seed ? knobsFromModel(seed) : blankKnobs()));
  const [mode, setMode] = useState<"guided" | "rule">(seed?.isRule ? "rule" : "guided");
  const setKnob = (k: keyof Knobs, v: number | boolean) => setKnobs((d) => ({ ...d, [k]: v }));
  const cat = cats.find((c) => c.id === category) ?? cats[0];
  const proj = useMemo(() => project(knobs), [knobs]);
  const up = proj.cagr >= 0;
  const valid = name.trim().length > 1;

  // Mode switch only when creating from scratch — editing locks to the model's type.
  const toggle = !seed ? (
    <div style={{ marginBottom: 22 }}>
      <Segmented size="sm" value={mode} onChange={(m) => setMode(m as "guided" | "rule")}
        options={[{ id: "guided", label: "Guided knobs" }, { id: "rule", label: "Signal rule" }]} />
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
        <h3 className="serif" style={{ margin: "0 0 4px", fontSize: 23, fontWeight: 600 }}>{seed ? "Tune model" : "Design an algorithm"}</h3>
        <p style={{ margin: "0 0 24px", fontSize: 13.5, color: "var(--text-2)" }}>Adjust the knobs — the projection on the right recomputes live.</p>

        <div style={{ marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Model name</div>
          <TextInput value={name} onChange={setName} placeholder="e.g. Volatility Carry Sleeve" />
        </div>
        <div style={{ marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Category</div>
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
        </div>

        <div style={{ height: 1, background: "var(--border)", margin: "6px 0 22px" }} />

        <div style={{ marginBottom: 22 }}><Slider label="Risk appetite" value={knobs.risk} min={1} max={10} step={1} unit=" / 10" onChange={(v) => setKnob("risk", v)} hue={cat.hue} /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Stop loss" value={knobs.stop} min={2} max={25} step={1} unit="%" onChange={(v) => setKnob("stop", v)} hue={cat.hue} /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Avg holding period" value={knobs.hold} min={1} max={250} step={1} unit=" days" onChange={(v) => setKnob("hold", v)} hue={cat.hue} /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Leverage" value={knobs.lev} min={1} max={3} step={0.25} unit="x" onChange={(v) => setKnob("lev", v)} hue={cat.hue} /></div>
        <div style={{ marginBottom: 22 }}><Slider label="Max positions" value={knobs.maxpos} min={1} max={50} step={1} onChange={(v) => setKnob("maxpos", v)} hue={cat.hue} /></div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px", background: "var(--surface-2)", borderRadius: "var(--r-sm)" }}>
          <span style={{ fontSize: 13, color: "var(--text-2)", fontWeight: 500 }}>Long-term trend filter</span>
          <button onClick={() => setKnob("trend", !knobs.trend)} style={{ width: 42, height: 24, borderRadius: 999, border: "none", cursor: "pointer", position: "relative", background: knobs.trend ? "var(--accent)" : "var(--surface-3)", transition: "background .2s" }}>
            <span style={{ position: "absolute", top: 3, left: knobs.trend ? 21 : 3, width: 18, height: 18, borderRadius: 999, background: "#fff", transition: "left .2s var(--ease)" }} />
          </button>
        </div>
      </div>

      <div style={{ position: "sticky", top: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="card" style={{ padding: 22 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span className="eyebrow">Projected equity · 1Y</span>
            <Pill tone={up ? "pos" : "neg"}>{fmt.pct(seriesPct(proj.series))}</Pill>
          </div>
          <AreaChart series={proj.series} color={cat.hue} height={170} uid="builder" animate={false} />
          <div className="m-grid-2" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginTop: 16 }}>
            <Stat label="CAGR" value={fmt.pct(proj.cagr)} tone="pos" />
            <Stat label="Sharpe" value={proj.sharpe.toFixed(2)} />
            <Stat label="Max DD" value={proj.maxDD.toFixed(1) + "%"} tone="neg" />
            <Stat label="Win" value={proj.winRate + "%"} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Btn variant="primary" icon={seed ? "edit" : "plus"} onClick={() => onSave(knobsToPayload(name, category, knobs, tagline), seed?.id ?? null)} disabled={!valid} style={{ flex: 1 }}>
            {seed ? "Save changes" : "Create & track"}</Btn>
          <Btn variant="soft" onClick={onCancel}>Cancel</Btn>
        </div>
        {!valid && <div style={{ fontSize: 12, color: "var(--text-3)", textAlign: "center" }}>Give your model a name to save it.</div>}
      </div>
    </div>
   </div>
  );
}
