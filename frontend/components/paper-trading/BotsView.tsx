"use client";

import { useMemo, useState } from "react";
import { CatDot, Icon, IconBtn, Pill, PtTip, Segmented, Btn, TextInput, Empty } from "./ptkit";
import { Sparkline } from "./ptcharts";
import { fmt, CatMeta, Model, STAT_TIPS, metricStateLabel, metricStateTip } from "./ptdata";

function MiniStat({ label, value, tone, tip, align }: { label: string; value: string; tone?: "pos" | "neg"; tip: string; align?: "left" | "right" }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <PtTip tip={tip} align={align} style={{ marginBottom: 3 }}>
        <span style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px dotted var(--border-strong)" }}>{label}</span>
        <Icon name="info" size={10} style={{ color: "var(--text-3)", opacity: 0.65 }} />
      </PtTip>
      <div className="mono" style={{ fontSize: 13.5, fontWeight: 600, color: tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--text-1)" }}>{value}</div>
    </div>
  );
}

export function ModelCard({ model, cat, onOpen, onEdit, onDelete, onToggleFav }: {
  model: Model; cat: CatMeta; onOpen: (m: Model) => void; onEdit: (m: Model) => void; onDelete: (m: Model) => void; onToggleFav: (id: number) => void }) {
  const [hover, setHover] = useState(false);
  const up = model.stats.cagr >= 0;
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onClick={() => onOpen(model)} className="card"
      style={{ padding: 18, cursor: "pointer", position: "relative", display: "flex", flexDirection: "column", gap: 13,
        transition: "transform .18s var(--ease), border-color .18s, background .18s",
        transform: hover ? "translateY(-3px)" : "none", borderColor: hover ? "var(--border-strong)" : "var(--border)",
        background: hover ? "var(--surface-2)" : "var(--surface-1)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
            <CatDot hue={cat.hue} />
            <span className="eyebrow" style={{ color: "var(--text-2)", whiteSpace: "nowrap" }}>{cat.short}</span>
            <span style={{ fontSize: 10.5, fontWeight: 600, padding: "2px 7px", borderRadius: 999,
              color: model.author === "You" ? "var(--accent-2)" : "var(--text-3)", background: model.author === "You" ? "var(--accent-soft)" : "var(--surface-3)" }}>
              {model.author === "You" ? "Custom" : "Atlas"}</span>
            <PtTip tip={metricStateTip(model)}>
              <span style={{ fontSize: 10.5, fontWeight: 600, padding: "2px 7px", borderRadius: 999,
                color: model.backtested ? "var(--pos)" : "var(--text-3)", background: model.backtested ? "var(--pos-soft)" : "var(--surface-3)" }}>
                {metricStateLabel(model)}</span>
            </PtTip>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-1)", lineHeight: 1.2 }}>{model.name}</div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0, opacity: hover ? 1 : 0, pointerEvents: hover ? "auto" : "none", transform: hover ? "none" : "translateX(6px)", transition: "opacity .15s, transform .15s" }} onClick={(e) => e.stopPropagation()}>
          <IconBtn icon="star" size={28} title={model.favorite ? "Unfavorite" : "Favorite"} onClick={() => onToggleFav(model.id)} />
          {model.author === "You" && <IconBtn icon="edit" size={28} title="Edit parameters" onClick={() => onEdit(model)} />}
          {model.author === "You" && <IconBtn icon="trash" size={28} tone="danger" title="Archive model" onClick={() => onDelete(model)} />}
        </div>
        {model.favorite && !hover && (
          <span style={{ position: "absolute", top: 16, right: 16, color: "var(--cat-rotation)", pointerEvents: "none" }}>
            <Icon name="star" size={15} fill />
          </span>
        )}
      </div>

      <div style={{ fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.45, minHeight: 36 }}>{model.tagline}</div>
      <Sparkline series={model.equity} color={up ? "var(--pos)" : "var(--neg)"} height={36} />

      <div style={{ display: "flex", alignItems: "center", gap: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
        <MiniStat label="Return" value={fmt.pct(model.stats.cagr)} tone={up ? "pos" : "neg"} tip={STAT_TIPS.cagr} />
        <MiniStat label="Sharpe" value={model.stats.sharpe != null ? model.stats.sharpe.toFixed(2) : "—"} tip={STAT_TIPS.sharpe} />
        <MiniStat label="Max DD" value={model.stats.maxDD.toFixed(1) + "%"} tone="neg" tip={STAT_TIPS.maxDD} align="right" />
        <PtTip tip={metricStateTip(model)} align="right">
          <Pill tone={model.backtested ? "pos" : "accent"}>{model.backtested ? `Win ${model.stats.winRate.toFixed(0)}%` : metricStateLabel(model)}</Pill>
        </PtTip>
      </div>
    </div>
  );
}

function CategoryHeader({ cat, count }: { cat: CatMeta; count: number }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ width: 30, height: 30, borderRadius: 9, background: `color-mix(in srgb, ${cat.hue} 18%, transparent)`, display: "grid", placeItems: "center" }}>
          <span style={{ width: 9, height: 9, borderRadius: 999, background: cat.hue }} />
        </span>
        <div>
          <h3 className="serif" style={{ margin: 0, fontSize: 25, fontWeight: 600, color: "var(--text-1)" }}>{cat.label}</h3>
          <div style={{ fontSize: 12.5, color: "var(--text-3)", marginTop: 2 }}>{cat.blurb}</div>
        </div>
      </div>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-3)", whiteSpace: "nowrap" }}>{count} models</span>
    </div>
  );
}

export default function BotsView({ models, cats, onOpen, onNew, onEdit, onDelete, onToggleFav }: {
  models: Model[]; cats: CatMeta[]; onOpen: (m: Model) => void; onNew: () => void; onEdit: (m: Model) => void; onDelete: (m: Model) => void; onToggleFav: (id: number) => void }) {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");

  const filtered = useMemo(() => models.filter((m) =>
    (filter === "all" || m.category === filter) && (!q || m.name.toLowerCase().includes(q.toLowerCase()) || m.tagline.toLowerCase().includes(q.toLowerCase()))
  ), [models, filter, q]);

  const shownCats = cats.filter((c) => filter === "all" || c.id === filter);
  const segOpts = [{ id: "all", label: "All" }].concat(cats.map((c) => ({ id: c.id, label: c.short })));

  return (
    <div style={{ animation: "pt-fadeUp .3s var(--ease)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <Segmented options={segOpts} value={filter} onChange={setFilter} size="sm" />
        <div style={{ display: "flex", gap: 12, alignItems: "center", flex: "1 1 240px", justifyContent: "flex-end" }}>
          <div style={{ position: "relative", flex: "0 1 260px" }}>
            <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-3)" }}><Icon name="search" size={15} /></span>
            <TextInput value={q} onChange={setQ} placeholder="Search models" style={{ padding: "9px 14px 9px 36px" }} />
          </div>
          <Btn icon="plus" onClick={onNew}>New model</Btn>
        </div>
      </div>

      {filtered.length === 0 && <Empty icon="layers" title="No models here yet" body="Try a different category, clear your search, or spin up a new model from scratch." />}

      <div style={{ display: "flex", flexDirection: "column", gap: 44 }}>
        {shownCats.map((cat) => {
          const ms = filtered.filter((m) => m.category === cat.id);
          if (!ms.length) return null;
          return (
            <section key={cat.id}>
              <CategoryHeader cat={cat} count={ms.length} />
              <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))" }}>
                {ms.map((m) => <ModelCard key={m.id} model={m} cat={cat} onOpen={onOpen} onEdit={onEdit} onDelete={onDelete} onToggleFav={onToggleFav} />)}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
