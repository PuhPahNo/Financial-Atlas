"use client";

import { useMemo, useState } from "react";
import { Modal, Btn, Slider, TextInput, IconBtn, CatDot, Icon } from "./ptkit";
import { CAT_HUES, fmt, Model } from "./ptdata";
import { TraderAccount } from "@/lib/paperTradingApi";

const EMOJIS = ["🦈", "🐳", "🐂", "🐻", "🦅", "🚀", "💎", "🧠", "🎯", "⚡", "🦉", "🌊"];

interface Alloc { strategy_id: number; weight: number }

export default function TraderForm({ open, seed, models, onSave, onClose }: {
  open: boolean; seed: TraderAccount | null; models: Model[]; onSave: (payload: any, editId: number | null) => void; onClose: () => void }) {
  const [name, setName] = useState(seed?.name ?? "");
  const [emoji, setEmoji] = useState(seed?.emoji ?? "🦈");
  const [bio, setBio] = useState(seed?.bio ?? "");
  const [cash, setCash] = useState(seed?.starting_cash ?? 100000);
  const [allocs, setAllocs] = useState<Alloc[]>(seed?.allocations.map((a) => ({ strategy_id: a.strategy_id, weight: a.weight })) ?? []);

  const byId = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  const used = new Set(allocs.map((a) => a.strategy_id));
  const available = models.filter((m) => !used.has(m.id));
  const total = allocs.reduce((s, a) => s + a.weight, 0);
  const cashPct = Math.max(0, 100 - total);
  const valid = name.trim().length > 0 && total <= 100 && allocs.length > 0;

  const addStrategy = (id: number) => {
    if (!id || used.has(id)) return;
    const remaining = Math.max(0, 100 - total);
    setAllocs((a) => [...a, { strategy_id: id, weight: Math.min(remaining || 10, remaining === 0 ? 0 : Math.min(20, remaining)) || 10 }]);
  };
  const setWeight = (id: number, w: number) => setAllocs((a) => a.map((x) => (x.strategy_id === id ? { ...x, weight: w } : x)));
  const remove = (id: number) => setAllocs((a) => a.filter((x) => x.strategy_id !== id));

  function submit() {
    onSave({
      name: name.trim(), emoji, bio: bio.trim(), starting_cash: cash,
      allocations: allocs.filter((a) => a.weight > 0).map((a) => ({ strategy_id: a.strategy_id, weight: a.weight })),
    }, seed?.id ?? null);
  }

  return (
    <Modal open={open} onClose={onClose} width={580}>
      <div style={{ display: "flex", flexDirection: "column", maxHeight: "88vh" }}>
        <div style={{ padding: "22px 24px 16px", borderBottom: "1px solid var(--border)" }}>
          <h3 className="serif" style={{ margin: 0, fontSize: 23, fontWeight: 600 }}>{seed ? "Edit trader" : "New trader"}</h3>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-2)" }}>Give them capital and split it across your strategies.</p>
        </div>

        <div style={{ padding: "20px 24px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Avatar</div>
              <div style={{ width: 56, height: 56, borderRadius: 14, display: "grid", placeItems: "center", fontSize: 30, background: "var(--surface-2)", border: "1px solid var(--border)" }}>{emoji}</div>
            </div>
            <div style={{ flex: 1 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Name</div>
              <TextInput value={name} onChange={setName} placeholder="e.g. The Quant, Aunt Carol, Diamond Hands" />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                {EMOJIS.map((e) => (
                  <button key={e} onClick={() => setEmoji(e)} style={{ width: 30, height: 30, borderRadius: 8, fontSize: 16, cursor: "pointer",
                    background: e === emoji ? "var(--accent-soft)" : "var(--surface-2)", border: `1px solid ${e === emoji ? "var(--accent-line)" : "var(--border)"}` }}>{e}</button>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Starting capital</div>
              <TextInput mono value={cash} onChange={(v) => setCash(Math.max(1000, parseInt(v.replace(/\D/g, "") || "0", 10)))} />
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Style (optional)</div>
              <TextInput value={bio} onChange={setBio} placeholder="e.g. swings for the fences" />
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span className="eyebrow">Capital allocation</span>
              <span className="mono" style={{ fontSize: 12, color: total > 100 ? "var(--neg)" : "var(--text-3)" }}>{total.toFixed(0)}% invested · {cashPct.toFixed(0)}% cash</span>
            </div>

            {allocs.length === 0 && <div style={{ fontSize: 13, color: "var(--text-3)", padding: "4px 0 12px" }}>Add at least one strategy to fund this trader.</div>}

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {allocs.map((a) => {
                const m = byId.get(a.strategy_id);
                const hue = (m && CAT_HUES[m.category]) || "var(--accent)";
                return (
                  <div key={a.strategy_id} style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "12px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <CatDot hue={hue} />
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-1)", flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m?.name ?? `Strategy ${a.strategy_id}`}</span>
                      <span className="mono" style={{ fontSize: 12.5, color: "var(--text-2)" }}>{fmt.usd0(cash * a.weight / 100)}</span>
                      <IconBtn icon="x" size={26} title="Remove" onClick={() => remove(a.strategy_id)} />
                    </div>
                    <Slider label="" value={a.weight} min={0} max={100} step={1} unit="%" onChange={(v) => setWeight(a.strategy_id, v)} hue={hue} />
                  </div>
                );
              })}
            </div>

            {available.length > 0 && (
              <div style={{ position: "relative", marginTop: 14 }}>
                <select value="" onChange={(e) => addStrategy(Number(e.target.value))} style={{ width: "100%", appearance: "none", WebkitAppearance: "none", cursor: "pointer",
                  padding: "11px 38px 11px 14px", background: "var(--surface-2)", color: "var(--text-2)", border: "1px dashed var(--border-strong)", borderRadius: "var(--r-sm)", fontSize: 13.5, fontFamily: "var(--font-sans)", outline: "none" }}>
                  <option value="">+ Add a strategy…</option>
                  {available.map((m) => <option key={m.id} value={m.id} style={{ background: "#16161e" }}>{m.name}</option>)}
                </select>
                <span style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none", color: "var(--text-3)" }}><Icon name="plus" size={14} /></span>
              </div>
            )}
            {total > 100 && <div style={{ fontSize: 12, color: "var(--neg)", marginTop: 10 }}>Allocations exceed 100% — trim them to fund this trader.</div>}
          </div>
        </div>

        <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border)", display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <Btn variant="soft" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" icon={seed ? "edit" : "plus"} onClick={submit} disabled={!valid}>{seed ? "Save trader" : "Create trader"}</Btn>
        </div>
      </div>
    </Modal>
  );
}
