"use client";

import { useState } from "react";
import { Btn, CatDot, Icon, IconBtn, Empty } from "./ptkit";
import { CAT_HUES, fmt } from "./ptdata";
import { TraderAccount } from "@/lib/paperTradingApi";

function AllocBar({ acc }: { acc: TraderAccount }) {
  return (
    <div style={{ display: "flex", height: 8, borderRadius: 999, overflow: "hidden", background: "var(--surface-3)" }}>
      {acc.allocations.map((a, i) => (
        <div key={i} title={`${a.name} · ${a.weight}%`} style={{ width: `${a.weight}%`, background: (a.category && CAT_HUES[a.category]) || "var(--accent)" }} />
      ))}
    </div>
  );
}

function Chip({ hue, children, muted }: { hue?: string; children: React.ReactNode; muted?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 9px", borderRadius: 999, fontSize: 11.5, fontWeight: 500,
      color: muted ? "var(--text-3)" : "var(--text-2)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
      {hue && <CatDot hue={hue} size={7} />}{children}
    </span>
  );
}

function TraderCard({ acc, onOpen, onEdit, onDelete }: { acc: TraderAccount; onOpen: (a: TraderAccount) => void; onEdit: (a: TraderAccount) => void; onDelete: (a: TraderAccount) => void }) {
  const [hover, setHover] = useState(false);
  return (
    <div className="card" onClick={() => onOpen(acc)} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ padding: 18, cursor: "pointer", display: "flex", flexDirection: "column", gap: 14, transition: "transform .18s var(--ease), border-color .18s, background .18s",
        transform: hover ? "translateY(-3px)" : "none", borderColor: hover ? "var(--border-strong)" : "var(--border)", background: hover ? "var(--surface-2)" : "var(--surface-1)" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div style={{ width: 46, height: 46, borderRadius: 13, display: "grid", placeItems: "center", fontSize: 24, background: "var(--surface-2)", border: "1px solid var(--border)", flexShrink: 0 }}>{acc.emoji}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-1)" }}>{acc.name}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 2 }}>{acc.bio || `${acc.allocations.length} ${acc.allocations.length === 1 ? "strategy" : "strategies"}`}</div>
        </div>
        <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", gap: 6, flexShrink: 0, opacity: hover ? 1 : 0, transition: "opacity .15s" }}>
          <IconBtn icon="edit" size={28} title="Edit trader" onClick={() => onEdit(acc)} />
          <IconBtn icon="trash" size={28} tone="danger" title="Archive trader" onClick={() => onDelete(acc)} />
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span className="mono" style={{ fontSize: 21, fontWeight: 600, color: "var(--text-1)" }}>{fmt.usd0(acc.starting_cash)}</span>
        <span style={{ fontSize: 12, color: "var(--text-3)" }}>starting capital</span>
      </div>

      <AllocBar acc={acc} />

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {acc.allocations.map((a, i) => <Chip key={i} hue={(a.category && CAT_HUES[a.category]) || "var(--accent)"} muted={a.archived}>{a.name}{a.archived ? " (archived)" : ""} · {a.weight}%</Chip>)}
        {acc.cash_pct > 0 && <Chip muted>Cash · {acc.cash_pct}%</Chip>}
        {acc.allocations.length === 0 && <span style={{ fontSize: 12.5, color: "var(--text-3)" }}>No strategies assigned yet — edit to allocate capital.</span>}
      </div>
    </div>
  );
}

export default function TradersView({ accounts, onOpen, onNew, onEdit, onDelete }: {
  accounts: TraderAccount[]; onOpen: (a: TraderAccount) => void; onNew: () => void; onEdit: (a: TraderAccount) => void; onDelete: (a: TraderAccount) => void }) {
  return (
    <div style={{ animation: "pt-fadeUp .3s var(--ease)" }}>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 24 }}>
        <Btn icon="plus" onClick={onNew}>New trader</Btn>
      </div>

      {accounts.length === 0 ? (
        <Empty icon="users" title="No traders yet" body="Create a simulated trader, give it starting capital, and split that capital across your strategies to see how the blend performs." />
      ) : (
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {accounts.map((a) => <TraderCard key={a.id} acc={a} onOpen={onOpen} onEdit={onEdit} onDelete={onDelete} />)}
        </div>
      )}
    </div>
  );
}
