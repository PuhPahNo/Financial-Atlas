"""Active point-in-time screening backtest engine (PRD active-sp500-screening, oom-fix).

Each day, scan the universe and buy names that *newly* meet the model's criteria
(point-in-time — only data available at that date), exit on take-profit / stop-loss /
max-hold / criteria-break, holding at most top-N, equal-weighted.

Memory: prices are held as compact parallel arrays (``dates`` + ``closes``), not a fat
list-of-dicts, so a full S&P 500 scan fits in a 512MB instance. Heavy runs are serialized
by ``_ENGINE_LOCK`` so concurrent requests / the live-mark tick can't stack and OOM the box.

Marking convention (shared with the rule engine and the live mark): a position stores a
positive ``qty`` + ``direction`` + ``entry_price``; long value = qty·price, short value =
qty·(entry − price). Cash is not credited with short proceeds — short P&L flows through the
entry-vs-price term, keeping net liquidation conserved.
"""
from __future__ import annotations

import threading
from datetime import date

from ..core import cache
from ..core.errors import ValidationError
from ..services import prices
from . import factors
from .metrics import summarize
from .pit_fundamentals import as_of

_DEFAULT_MAX_POSITIONS = 8

# Serialize heavy backtests process-wide: only one universe scan runs at a time, so
# concurrent backtest requests + the market-open live-mark tick can't stack their memory
# and blow past the instance limit. (Backtests queue rather than crash the whole app.)
_ENGINE_LOCK = threading.Lock()

# Dead-ticker skiplist: symbols whose price fetch hard-errors (404 / unresolved — typically
# delisted names in the historical superset) are remembered so the engine stops re-fetching
# corpses on every backtest. Short TTL so a transient error self-heals.
_DEAD_TTL = 7 * 86400

# Point-in-time entry is just how a backtest must work, so it isn't flagged. The one genuine
# remaining limitation worth noting is the user-specified universe (no survivorship).
_UNIVERSE_CAVEAT = ("Candidate universe is user-specified; survivorship/selection bias is "
                    "not modeled (delisted names and historical index membership are absent).")


def _is_dead(ticker: str) -> bool:
    return cache.peek("dead_ticker", ticker.upper(), _DEAD_TTL) is True


def _mark_dead(ticker: str) -> None:
    cache.put("dead_ticker", ticker.upper(), True)


def _leg_value(pos: dict, price: float) -> float:
    if pos["direction"] == "short":
        return pos["qty"] * (pos["entry_price"] - price)
    return pos["qty"] * price


def _max_positions(category: str, params: dict) -> int:
    if category == "risk_rotation":
        return 1  # rotation holds the single strongest name (or cash)
    try:
        return max(1, int(params.get("max_positions") or _DEFAULT_MAX_POSITIONS))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_POSITIONS


def _pct(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    return v / 100 if v > 1 else v


def _load_series(sym: str, warmup_start: date, end_date: date) -> tuple[list[str], list[float]]:
    """Fetch a ticker's daily history as compact ascending (dates, closes) arrays, discarding
    the raw bar dicts immediately (the dicts are the memory hog at universe scale)."""
    payload, _ = prices.price_window(sym, start=warmup_start, end=end_date, interval="1d")
    rows = sorted(
        ((str(b["date"])[:10], float(b["close"])) for b in payload["bars"] if b.get("close") is not None),
        key=lambda r: r[0],
    )
    return [r[0] for r in rows], [r[1] for r in rows]


def eligible(category: str, params: dict, ticker: str, d, dates: list[str], closes: list[float]):
    """Point-in-time eligibility for one candidate at date d → (ok, score, direction).
    Uses only closes dated on/before d (and, for fundamental categories, filings filed by d)."""
    k = factors.idx_asof(dates, d)
    if k == 0:
        return (False, 0.0, "long")
    px = closes[k - 1]
    if px <= 0:
        return (False, 0.0, "long")

    if category == "long_term":
        f = as_of(ticker, d)
        if not f or not f.get("fcf"):
            return (False, 0.0, "long")
        max_dtf = float(params.get("max_debt_to_fcf") or 6.0)
        ndf = f.get("net_debt_to_fcf")
        ok = (f["fcf"] > 0 and (f.get("fcf_margin") or 0.0) >= 0.05
              and (ndf is None or ndf <= max_dtf))
        shares = f.get("shares")
        fcf_yield = (f["fcf"] / (shares * px)) if (shares and shares > 0) else 0.0
        return (ok, fcf_yield, "long")

    if category == "income_quality":
        f = as_of(ticker, d)
        if not f or not f.get("fcf"):
            return (False, 0.0, "long")
        shares = f.get("shares")
        dividends = f.get("dividends_paid") or 0.0
        div_yield = (dividends / (shares * px)) if (shares and shares > 0) else 0.0
        min_yield = float(params.get("min_yield") or 0.02)
        min_cov = float(params.get("min_fcf_coverage") or 1.5)
        covered = dividends > 0 and f["fcf"] >= dividends * min_cov
        return (covered and div_yield >= min_yield, div_yield, "long")

    if category == "options":  # synthetic proxy → point-in-time trend filter on the underlying
        sma200 = factors.sma_at(closes, k, 200)
        t = (px / sma200 - 1) if sma200 else None
        return (t is not None and t > 0, t or 0.0, "long")

    if category == "short_selling":
        slow = int(params.get("slow_days") or 100)
        sma = factors.sma_at(closes, k, slow)
        mom = factors.momentum_at(closes, k, 120)
        if sma is None or mom is None:
            return (False, 0.0, "short")
        return (px < sma and mom < 0, -mom, "short")

    if category == "risk_rotation":
        look = int(params.get("lookback_days") or 126)
        mom = factors.momentum_at(closes, k, look)
        sma200 = factors.sma_at(closes, k, 200)
        if mom is None or sma200 is None:
            return (False, 0.0, "long")
        return (px > sma200 and mom > 0, mom, "long")

    # short_term and any unmapped category → trend + momentum gate
    slow = int(params.get("slow_days") or 100)
    sma = factors.sma_at(closes, k, slow)
    mom = factors.momentum_at(closes, k, 120)
    if sma is None or mom is None:
        return (False, 0.0, "long")
    return (px > sma and mom > 0, mom, "long")


def warm_universe_for_backtests(universe: list[str] | None = None, *, end_date: date | None = None,
                                years: int = 5, include_fundamentals: bool = True) -> dict:
    """Best-effort pre-fetch of the universe's price windows (and, optionally, fundamentals)
    so on-demand backtests read warm caches instead of hundreds of cold fetches. Loads each
    ticker transiently (compact arrays, discarded) so it stays low-memory. Never raises."""
    from .universe import sp500_tickers
    universe = universe or sp500_tickers()
    end_date = end_date or date.today()
    warmup_start = date(max(1962, end_date.year - years), 1, 1)
    prices_ok = funds_ok = 0
    for t in universe:
        if _is_dead(t):
            continue
        try:
            _load_series(t, warmup_start, end_date)
            prices_ok += 1
        except Exception:  # noqa: BLE001 — unresolved symbol → skiplist so we stop re-fetching it
            _mark_dead(t)
            continue
        if include_fundamentals:
            try:
                if as_of(t, end_date) is not None:
                    funds_ok += 1
            except Exception:  # noqa: BLE001
                pass
    return {"universe": len(universe), "prices_warmed": prices_ok, "fundamentals_warmed": funds_ok}


def run_active_backtest(*, strategy: dict, universe: list[str], start_date: date, end_date: date,
                        starting_cash: float, transaction_cost_bps: float = 5.0,
                        slippage_bps: float = 5.0, benchmark: str = "SPY", membership_on=None) -> dict:
    """Actively manage the universe: each day, close positions that hit a take-profit /
    stop-loss / max-hold / criteria-break, then fill free slots with the best names that
    *newly* meet the model's criteria (point-in-time). Hold at most top-N, equal-weighted.
    Serialized via ``_ENGINE_LOCK`` and memory-lean (compact price arrays)."""
    if end_date <= start_date:
        raise ValidationError("Backtest end_date must be after start_date")
    category = strategy.get("category") or "short_term"
    params = strategy.get("parameters", {}) or {}
    universe = sorted({t.strip().upper() for t in (universe or []) if t and t.strip()})
    if not universe:
        raise ValidationError("Active screening needs a non-empty universe")

    cost_rate = (transaction_cost_bps + slippage_bps) / 10000
    top_n = _max_positions(category, params)
    if category != "risk_rotation":
        try:
            top_n = max(1, int(params.get("max_positions") or 15))
        except (TypeError, ValueError):
            top_n = 15
    take_profit = _pct(params.get("take_profit_pct") or params.get("take_profit"), 0.25)
    stop_loss = _pct(params.get("stop_loss_pct") or params.get("stop_loss"), 0.12)
    max_hold = int(params.get("max_hold_days") or 252)
    warnings: list[str] = [_UNIVERSE_CAVEAT]
    warmup_start = date(max(1962, start_date.year - 2), 1, 1)

    # Only one heavy universe scan at a time — prevents concurrent requests / the live-mark
    # tick from stacking memory and OOM-killing the instance.
    with _ENGINE_LOCK:
        series: dict[str, tuple[list[str], list[float]]] = {}
        for t in universe:
            if _is_dead(t):
                continue  # known no-data symbol — don't re-fetch corpses
            try:
                dates, closes = _load_series(t, warmup_start, end_date)
                if closes:
                    series[t] = (dates, closes)
            except Exception:  # noqa: BLE001 — symbol won't resolve (often delisted) → skiplist it
                _mark_dead(t)
                continue
        if not series:
            raise ValidationError("No price history available for the universe in this window")

        bench_dates: list[str] = []
        bench_closes: list[float] = []
        if benchmark:
            try:
                bench_dates, bench_closes = _load_series(benchmark, warmup_start, end_date)
            except Exception:  # noqa: BLE001
                warnings.append(f"Benchmark {benchmark.upper()} history was unavailable for this window.")

        s_iso, e_iso = start_date.isoformat(), end_date.isoformat()
        cal_set = {ds for (dates, _) in series.values() for ds in dates if s_iso <= ds <= e_iso}
        calendar = [date.fromisoformat(ds) for ds in sorted(cal_set)]
        if len(calendar) < 2:
            raise ValidationError("Not enough trading days in the window")
        bench_first = factors.close_at(bench_dates, bench_closes, calendar[0]) if bench_closes else None

        def close(sym: str, d):
            ds, cs = series[sym]
            return factors.close_at(ds, cs, d)

        cash = float(starting_cash)
        positions: dict[str, dict] = {}
        trades: list[dict] = []
        equity_curve: list[dict] = []

        def mark_equity(d) -> float:
            return cash + sum(_leg_value(p, (close(t, d) or p["entry_price"])) for t, p in positions.items())

        for d in calendar:
            # 1) Exits — take-profit / stop-loss / max-hold / criteria-break, whichever first.
            for t in list(positions):
                p = positions[t]
                px = close(t, d)
                if px is None:
                    continue
                gain = (px / p["entry_price"] - 1) if p["direction"] == "long" else (p["entry_price"] / px - 1)
                held = (d - p["entry_date"]).days
                reason = None
                if gain >= take_profit:
                    reason = f"take-profit +{take_profit * 100:.0f}%"
                elif gain <= -stop_loss:
                    reason = f"stop-loss -{stop_loss * 100:.0f}%"
                elif held >= max_hold:
                    reason = f"max-hold {max_hold}d"
                else:
                    ok, _, _ = eligible(category, params, t, d, *series[t])
                    if not ok:
                        reason = "criteria exit"
                if reason:
                    pnl = (p["qty"] * (px - p["entry_price"]) if p["direction"] == "long"
                           else p["qty"] * (p["entry_price"] - px))
                    cash += pnl if p["direction"] == "short" else p["qty"] * px
                    cash -= p["qty"] * px * cost_rate
                    trades.append({"date": d, "ticker": t, "side": "cover" if p["direction"] == "short" else "sell",
                                   "quantity": p["qty"], "price": px, "value": abs(p["qty"] * px),
                                   "reason": reason, "pnl": pnl})
                    del positions[t]

            # 2) Entries — fill free slots with the best newly-qualifying names.
            if len(positions) < top_n:
                equity_now = mark_equity(d)
                target = max(0.0, equity_now) / top_n
                members = membership_on(d) if membership_on is not None else None
                cands = []
                for t, (dates, closes) in series.items():
                    if t in positions:
                        continue
                    if members is not None and t not in members:
                        continue  # not in the index on this date (point-in-time membership)
                    ok, score, direction = eligible(category, params, t, d, dates, closes)
                    if ok:
                        cands.append((score, t, direction, closes[factors.idx_asof(dates, d) - 1]))
                cands.sort(key=lambda x: x[0], reverse=True)
                for score, t, direction, px in cands:
                    if len(positions) >= top_n:
                        break
                    dollars = target if direction == "short" else min(target, cash)
                    if dollars <= 1 or px <= 0:
                        continue
                    qty = dollars / px
                    cash -= dollars if direction == "long" else 0.0
                    cash -= dollars * cost_rate
                    positions[t] = {"qty": qty, "direction": direction, "entry_price": px, "entry_date": d}
                    trades.append({"date": d, "ticker": t, "side": "short" if direction == "short" else "buy",
                                   "quantity": qty, "price": px, "value": dollars, "reason": "criteria met"})

            # 3) Mark net liquidation.
            eq = mark_equity(d)
            point = {"date": d, "cash": cash, "equity": eq}
            if bench_first:
                bclose = factors.close_at(bench_dates, bench_closes, d)
                point["benchmark_equity"] = starting_cash * ((bclose or bench_first) / bench_first)
            equity_curve.append(point)

        last_day = calendar[-1]
        final_holdings = [{
            "ticker": t, "quantity": p["qty"], "direction": p["direction"],
            "entry_price": p["entry_price"], "last_close": (close(t, last_day) or p["entry_price"]),
        } for t, p in positions.items()]
        final_equity = equity_curve[-1]["equity"] if equity_curve else starting_cash
        holdings = [{"ticker": t, "weight": round(abs(_leg_value(p, (close(t, last_day) or p["entry_price"]))) / final_equity, 4)}
                    for t, p in positions.items() if final_equity] or [{"ticker": "Cash", "weight": 1.0}]
        if not trades:
            warnings.append("No S&P 500 name met the model's criteria in this window — the model stayed in cash.")

        return {
            "strategy": strategy,
            "served_by": "yahoo",
            "trades": trades,
            "equity_curve": equity_curve,
            "metrics": summarize(equity_curve, trades, starting_cash),
            "warnings": warnings,
            "holdings": holdings,
            "final_holdings": final_holdings,
            "residual_cash": cash,
            "date_range": {"start": start_date, "end": end_date},
        }
