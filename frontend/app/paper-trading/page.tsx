"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { paperTradingApi, TraderAccount } from "@/lib/paperTradingApi";
import { Icon, SlideOver, ConfirmDialog } from "@/components/paper-trading/ptkit";
import { Sparkline } from "@/components/paper-trading/ptcharts";
import { catMeta, toModel, getFavorites, toggleFavorite, genSeries, defaultBacktestWindow, fmt, CatMeta, Model } from "@/components/paper-trading/ptdata";
import BotsView from "@/components/paper-trading/BotsView";
import ModelDetail from "@/components/paper-trading/ModelDetail";
import Builder from "@/components/paper-trading/Builder";
import BacktestLab from "@/components/paper-trading/BacktestLab";
import Copilot from "@/components/paper-trading/Copilot";
import TradersView from "@/components/paper-trading/TradersView";
import TraderDetail from "@/components/paper-trading/TraderDetail";
import TraderForm from "@/components/paper-trading/TraderForm";
import AtlasMark from "@/components/AtlasMark";

type View = "bots" | "builder" | "backtest" | "traders" | "ai";
const NAV: { id: View; label: string; icon: string; title: string; sub: string }[] = [
  { id: "bots", label: "Models", icon: "grid", title: "Trading Models", sub: "Browse, tune and track algorithmic models across every strategy." },
  { id: "builder", label: "Build", icon: "sliders", title: "Strategy Builder", sub: "Tune the knobs and watch the projected equity curve react live." },
  { id: "backtest", label: "Backtest", icon: "chart", title: "Backtest Lab", sub: "Run any strategy across a historical regime — including the 2008 crash." },
  { id: "traders", label: "Traders", icon: "users", title: "Paper Traders", sub: "Spin up simulated traders and split their capital across your strategies." },
  { id: "ai", label: "Copilot", icon: "sparkles", title: "Atlas Copilot", sub: "" },
];

export default function PaperTradingPage() {
  const [cats, setCats] = useState<CatMeta[]>([]);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [favorites, setFavorites] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("bots");
  const [detail, setDetail] = useState<Model | null>(null);
  const [editing, setEditing] = useState<Model | null>(null);
  const [delTarget, setDelTarget] = useState<Model | null>(null);
  const [bt, setBt] = useState<{ id: number | null; regime: string }>({ id: null, regime: "gfc" });
  const [toast, setToast] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<TraderAccount[]>([]);
  const [traderDetail, setTraderDetail] = useState<TraderAccount | null>(null);
  const [traderForm, setTraderForm] = useState<{ open: boolean; seed: TraderAccount | null }>({ open: false, seed: null });
  const [traderDel, setTraderDel] = useState<TraderAccount | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [catRes, accRes] = await Promise.all([paperTradingApi.categories(), paperTradingApi.listAccounts()]);
      const cs = catRes.data.categories || [];
      setCats(cs.map(catMeta));
      setStrategies(cs.flatMap((c: any) => c.strategies || []));
      setAccounts(accRes.data.accounts || []);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); setFavorites(getFavorites()); }, [refresh]);

  const models: Model[] = useMemo(
    () => strategies.map(toModel).map((m) => ({ ...m, favorite: favorites.includes(m.id) }))
      .sort((a, b) => Number(b.favorite) - Number(a.favorite)),
    [strategies, favorites]
  );

  // Quietly backtest any not-yet-backtested models in the background (3 at a time)
  // so every card shows real equity without the user opening each one.
  const warmedRef = useRef(false);
  useEffect(() => {
    if (loading || warmedRef.current) return;
    const pending = models.filter((m) => !m.backtested);
    if (!pending.length) return;
    warmedRef.current = true;
    const w = defaultBacktestWindow();
    const queue = [...pending];
    const worker = async () => {
      while (queue.length) {
        const m = queue.shift()!;
        try {
          await paperTradingApi.runBacktest({
            strategy_id: m.id, tickers: m.parameters?.tickers ?? [],
            start_date: w.start, end_date: w.end, starting_cash: 100000, benchmark: "SPY", persist_headline: true,
          });
        } catch { /* leave illustrative on failure */ }
      }
    };
    Promise.all([worker(), worker(), worker()]).then(() => refresh());
  }, [loading, models, refresh]);

  const flash = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2600); };
  const openBuilder = (m: Model | null) => { setEditing(m); setDetail(null); setView("builder"); };
  const openBacktest = (id: number) => { setBt({ id, regime: "gfc" }); setDetail(null); setView("backtest"); };

  async function save(payload: any, editId: number | null) {
    try {
      const isRule = !!payload?.parameters?.rules;
      let id: number | null = editId;
      if (editId) { await paperTradingApi.updateStrategy(editId, payload); flash(`Updated “${payload.name}”`); }
      else { const res = await paperTradingApi.createStrategy(payload); id = res.data?.strategy?.id ?? null; flash(`Backtesting “${payload.name}” on real prices…`); }
      // Auto-run a headline backtest so the model is backtested the moment it's created.
      if (id) {
        const w = defaultBacktestWindow();
        try {
          await paperTradingApi.runBacktest({
            strategy_id: id, tickers: payload?.parameters?.tickers ?? [],
            start_date: w.start, end_date: w.end, starting_cash: 100000, benchmark: "SPY", persist_headline: true,
          });
        } catch { /* a backtest failure shouldn't block saving */ }
      }
      await refresh();
      if (!editId) flash(`Added “${payload.name}” to your models`);
      // Rule strategies are best explored in the lab next.
      if (isRule && id) { setBt({ id, regime: "covid" }); setView("backtest"); }
      else { setView("bots"); }
    } catch (e: any) { flash(e.message || "Could not save the strategy"); }
  }
  async function remove(m: Model) {
    setDelTarget(null); setDetail(null);
    try { await paperTradingApi.deleteStrategy(m.id); await refresh(); flash(`Archived “${m.name}”`); }
    catch (e: any) { flash(e.message || "Could not archive"); }
  }
  const onToggleFav = (id: number) => setFavorites(toggleFavorite(id));

  async function saveTrader(payload: any, editId: number | null) {
    try {
      if (editId) await paperTradingApi.updateAccount(editId, payload);
      else await paperTradingApi.createAccount(payload);
      setTraderForm({ open: false, seed: null });
      await refresh();
      flash(editId ? `Updated “${payload.name}”` : `Created trader “${payload.name}”`);
    } catch (e: any) { flash(e.message || "Could not save the trader"); }
  }
  async function removeTrader(a: TraderAccount) {
    setTraderDel(null); setTraderDetail(null);
    try { await paperTradingApi.deleteAccount(a.id); await refresh(); flash(`Archived “${a.name}”`); }
    catch (e: any) { flash(e.message || "Could not archive"); }
  }
  const editTrader = (a: TraderAccount) => { setTraderDetail(null); setTraderForm({ open: true, seed: a }); };

  const totalCapital = accounts.reduce((s, a) => s + a.starting_cash, 0);
  const cur = NAV.find((n) => n.id === view)!;
  const aiView = view === "ai";
  const detailCat = detail ? cats.find((c) => c.id === detail.category) : undefined;

  return (
    <div className="pt-scope pt-shell" style={{ display: "grid", gridTemplateColumns: "240px minmax(0,1fr)", minHeight: "100vh", background: "var(--bg)", fontFamily: "var(--font-sans)" }}>
      <aside className="pt-aside" style={{ borderRight: "1px solid var(--border)", padding: "24px 18px", display: "flex", flexDirection: "column", gap: 24, position: "sticky", top: 0, height: "100vh", boxSizing: "border-box" }}>
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "var(--text-1)" }} title="Back to Atlas">
          <AtlasMark size={30} />
          <span className="serif" style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em" }}>Atlas</span>
        </Link>

        <nav className="pt-navlist" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {NAV.map((n) => {
            const active = view === n.id;
            return (
              <button key={n.id} onClick={() => setView(n.id)} style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left",
                padding: "11px 14px", cursor: "pointer", borderRadius: "var(--r-sm)", background: active ? "var(--accent-soft)" : "transparent", border: "1px solid transparent",
                color: active ? "var(--accent-2)" : "var(--text-2)", fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 600, transition: "all .15s var(--ease)" }}>
                <Icon name={n.icon} size={17} fill={n.id === "ai" && active} />{n.label}
              </button>
            );
          })}
        </nav>

        <div className="pt-desk" style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
          <button onClick={() => setView("traders")} className="card" style={{ padding: 16, background: "var(--surface-2)", textAlign: "left", cursor: "pointer", border: "1px solid var(--border)" }}>
            <div className="eyebrow" style={{ marginBottom: 6, display: "flex", alignItems: "center", justifyContent: "space-between" }}>Paper desk <Icon name="users" size={13} /></div>
            {accounts.length > 0 ? (
              <>
                <div className="mono" style={{ fontSize: 21, fontWeight: 600, marginBottom: 2 }}>{fmt.usd0(totalCapital)}</div>
                <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 10 }}>{accounts.length} trader{accounts.length > 1 ? "s" : ""} · manage →</div>
                <Sparkline series={genSeries(7, 40, { drift: 0.0008, vol: 0.01 })} color="var(--pos)" height={28} />
              </>
            ) : (
              <>
                <div className="mono" style={{ fontSize: 21, fontWeight: 600, marginBottom: 2 }}>$128,440</div>
                <div style={{ fontSize: 12, color: "var(--text-3)" }}>Create your first trader →</div>
              </>
            )}
          </button>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", color: "var(--text-3)", textDecoration: "none", fontSize: 13, fontWeight: 500 }}>
            <Icon name="back" size={15} /> Back to Atlas
          </Link>
        </div>
      </aside>

      <main style={aiView
        ? { padding: "24px clamp(20px, 3vw, 40px) 20px", height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", boxSizing: "border-box" }
        : { padding: "40px clamp(24px, 4vw, 56px)" }}>
        {aiView ? (
          <Copilot onChanged={refresh} />
        ) : (
          <div style={{ maxWidth: 1180, margin: "0 auto" }}>
            <div style={{ marginBottom: 28 }}>
              <h1 className="serif" style={{ margin: 0, fontSize: "clamp(26px, 5.5vw, 38px)", fontWeight: 600, letterSpacing: "-0.02em" }}>{cur.title}</h1>
              <p style={{ margin: "6px 0 0", color: "var(--text-2)", fontSize: 15 }}>{cur.sub}</p>
            </div>

            {loading ? (
              <div style={{ display: "grid", placeItems: "center", height: 320 }}>
                <div style={{ width: 28, height: 28, border: "3px solid var(--surface-3)", borderTopColor: "var(--accent)", borderRadius: 999, animation: "pt-spin .8s linear infinite" }} />
              </div>
            ) : (
              <>
                {view === "bots" && <BotsView models={models} cats={cats} onOpen={setDetail} onNew={() => openBuilder(null)} onEdit={openBuilder} onDelete={setDelTarget} onToggleFav={onToggleFav} />}
                {view === "builder" && <Builder key={editing?.id ?? "new"} seed={editing} cats={cats} onSave={save} onCancel={() => setView("bots")} />}
                {view === "backtest" && <BacktestLab key={String(bt.id) + bt.regime} models={models} preselectId={bt.id} initialRegime={bt.regime} />}
                {view === "traders" && <TradersView accounts={accounts} onOpen={setTraderDetail} onNew={() => setTraderForm({ open: true, seed: null })} onEdit={(a) => setTraderForm({ open: true, seed: a })} onDelete={setTraderDel} />}
              </>
            )}
          </div>
        )}
      </main>

      <SlideOver open={!!detail} onClose={() => setDetail(null)} width={500}>
        <ModelDetail model={detail} cat={detailCat} onClose={() => setDetail(null)} onEdit={openBuilder} onBacktest={(m) => openBacktest(m.id)} onDelete={setDelTarget} onBacktested={refresh} />
      </SlideOver>

      <ConfirmDialog open={!!delTarget} title="Archive this model?"
        body={delTarget ? `“${delTarget.name}” will leave the active model list. Historical backtests and account allocations keep their stored snapshots.` : ""}
        confirmLabel="Archive"
        onClose={() => setDelTarget(null)} onConfirm={() => delTarget && remove(delTarget)} />

      <SlideOver open={!!traderDetail} onClose={() => setTraderDetail(null)} width={520}>
        <TraderDetail account={traderDetail} onClose={() => setTraderDetail(null)} onEdit={editTrader} onDelete={setTraderDel} />
      </SlideOver>

      <TraderForm key={`${traderForm.open ? "o" : "c"}-${traderForm.seed?.id ?? "new"}`} open={traderForm.open} seed={traderForm.seed} models={models} onSave={saveTrader} onClose={() => setTraderForm({ open: false, seed: null })} />

      <ConfirmDialog open={!!traderDel} title="Archive this trader?"
        body={traderDel ? `“${traderDel.name}” will leave the active trader list. Historical account context is preserved in local records.` : ""}
        confirmLabel="Archive"
        onClose={() => setTraderDel(null)} onConfirm={() => traderDel && removeTrader(traderDel)} />

      {toast && (
        <div className="pt-scope" style={{ position: "fixed", bottom: 26, left: "50%", transform: "translateX(-50%)", zIndex: 80, display: "flex", alignItems: "center", gap: 10,
          padding: "12px 18px", background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: "var(--r-pill)", boxShadow: "var(--shadow-pop)", fontSize: 13.5, fontWeight: 500, color: "var(--text-1)", animation: "pt-fadeUp .25s var(--ease)" }}>
          <span style={{ color: "var(--pos)", display: "grid", placeItems: "center" }}><Icon name="sparkles" size={15} fill /></span>{toast}
        </div>
      )}
    </div>
  );
}
