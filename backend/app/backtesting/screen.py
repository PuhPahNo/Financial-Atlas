"""Point-in-time screening backtest engine (PRD backtest-integrity).

Walks the window and, at each monthly rebalance, evaluates the model's criteria for every
candidate using only data available at that date (prices up to D; fundamentals filed on or
before D). Holds only the names that pass — a position is opened because the criteria
triggered *then*, never because the ticker is a known future winner. This replaces the old
buy-first-ticker-on-day-1 buy-and-hold for real (non-fixture, non-rule) backtests.

Marking convention (shared with the rule engine and the live mark): a position stores a
positive ``qty`` plus a ``direction`` and ``entry_price``; long value = qty·price, short
value = qty·(entry − price). Cash is not credited with short proceeds — short P&L flows
through the entry-vs-price term, which keeps net liquidation conserved at each rebalance.
"""
from __future__ import annotations

from datetime import date

from ..core.errors import ValidationError
from ..services import prices
from . import factors
from .metrics import summarize
from .pit_fundamentals import as_of

_DEFAULT_MAX_POSITIONS = 8
# Point-in-time entry is just how a backtest must work, so it isn't flagged. The one
# genuine remaining limitation worth noting is the user-specified universe (no survivorship).
_UNIVERSE_CAVEAT = ("Candidate universe is user-specified; survivorship/selection bias is "
                    "not modeled (delisted names and historical index membership are absent).")


def _leg_value(pos: dict, price: float) -> float:
    if pos["direction"] == "short":
        return pos["qty"] * (pos["entry_price"] - price)
    return pos["qty"] * price


def _month_starts(calendar: list[date]) -> set[date]:
    """First trading day of each calendar month (the window start is always included)."""
    starts: set[date] = set()
    seen: set[tuple[int, int]] = set()
    for d in calendar:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            starts.add(d)
    return starts


def _max_positions(category: str, params: dict) -> int:
    if category == "risk_rotation":
        return 1  # rotation holds the single strongest name (or cash)
    try:
        return max(1, int(params.get("max_positions") or _DEFAULT_MAX_POSITIONS))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_POSITIONS


def eligible(category: str, params: dict, ticker: str, d, bars: list[dict], bench_bars: list[dict]):
    """Point-in-time eligibility for one candidate at date d → (ok, score, direction)."""
    px = factors.close_on(bars, d)
    if px is None or px <= 0:
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
        t = factors.trend(bars, d, 200)
        return (t is not None and t > 0, t or 0.0, "long")

    if category == "short_selling":
        slow = int(params.get("slow_days") or 100)
        sma = factors.sma(bars, d, slow)
        mom = factors.momentum(bars, d, 120)
        if sma is None or mom is None:
            return (False, 0.0, "short")
        return (px < sma and mom < 0, -mom, "short")

    if category == "risk_rotation":
        look = int(params.get("lookback_days") or 126)
        mom = factors.momentum(bars, d, look)
        sma200 = factors.sma(bars, d, 200)
        if mom is None or sma200 is None:
            return (False, 0.0, "long")
        return (px > sma200 and mom > 0, mom, "long")

    # short_term and any unmapped category → trend + momentum gate
    slow = int(params.get("slow_days") or 100)
    sma = factors.sma(bars, d, slow)
    mom = factors.momentum(bars, d, 120)
    if sma is None or mom is None:
        return (False, 0.0, "long")
    return (px > sma and mom > 0, mom, "long")


def run_screen_backtest(*, strategy: dict, tickers: list[str], start_date: date, end_date: date,
                        starting_cash: float, transaction_cost_bps: float = 5.0,
                        slippage_bps: float = 5.0, benchmark: str = "SPY") -> dict:
    if end_date <= start_date:
        raise ValidationError("Backtest end_date must be after start_date")
    category = strategy.get("category") or "short_term"
    params = strategy.get("parameters", {}) or {}
    tickers = [t.strip().upper() for t in (tickers or params.get("tickers", [])) if t and t.strip()]
    if not tickers:
        raise ValidationError("At least one ticker is required")

    cost_rate = (transaction_cost_bps + slippage_bps) / 10000
    warnings: list[str] = [_UNIVERSE_CAVEAT]

    # Warm-up history before the window so SMA200 / momentum are established on day one.
    warmup_start = date(max(1962, start_date.year - 2), 1, 1)

    def _load(sym: str) -> list[dict]:
        payload, _ = prices.price_window(sym, start=warmup_start, end=end_date, interval="1d")
        bars = [b for b in payload["bars"] if b.get("close") is not None]
        bars.sort(key=lambda b: str(b["date"]))
        return bars

    bars: dict[str, list[dict]] = {}
    for t in tickers:
        try:
            tb = _load(t)
            if tb:
                bars[t] = tb
        except Exception:  # noqa: BLE001
            warnings.append(f"{t}: price history unavailable for this window.")
    if not bars:
        raise ValidationError(f"No price history for {', '.join(tickers)} in this window")

    bench_bars: list[dict] = []
    if benchmark:
        try:
            bench_bars = _load(benchmark)
        except Exception:  # noqa: BLE001
            warnings.append(f"Benchmark {benchmark.upper()} history was unavailable for this window.")

    # In-window trading calendar = union of candidate bar dates.
    s_iso, e_iso = start_date.isoformat(), end_date.isoformat()
    cal_set = {str(b["date"])[:10] for tb in bars.values() for b in tb if s_iso <= str(b["date"])[:10] <= e_iso}
    calendar = [date.fromisoformat(ds) for ds in sorted(cal_set)]
    if len(calendar) < 2:
        raise ValidationError("Not enough trading days in the window for a screening backtest")

    rebal_days = _month_starts(calendar)
    max_pos = _max_positions(category, params)
    max_short = float(params.get("max_short_exposure") or 0.25)
    bench_first = factors.close_on(bench_bars, calendar[0]) if bench_bars else None

    def close(sym: str, d) -> float | None:
        return factors.close_on(bars[sym], d)

    cash = float(starting_cash)
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    equity_curve: list[dict] = []

    def mark_equity(d) -> float:
        return cash + sum(_leg_value(p, (close(t, d) or p["entry_price"])) for t, p in positions.items())

    for d in calendar:
        if d in rebal_days:
            equity = mark_equity(d)
            # Evaluate every candidate point-in-time and keep the top scorers.
            cands = []
            for t in bars:
                px = close(t, d)
                if px is None or px <= 0:
                    continue
                ok, score, direction = eligible(category, params, t, d, bars[t], bench_bars)
                if ok:
                    cands.append((score, t, direction, px))
            cands.sort(key=lambda x: x[0], reverse=True)
            selected = cands[:max_pos]

            new_positions: dict[str, dict] = {}
            target_gross: dict[str, float] = {}
            if selected:
                direction = selected[0][2]
                n = len(selected)
                budget = (min(max_short, 0.95) if direction == "short" else 0.95) / n
                for _, t, _, px in selected:
                    dollars = max(0.0, equity) * budget
                    new_positions[t] = {"qty": dollars / px, "direction": direction, "entry_price": px}
                    target_gross[t] = dollars

            old_gross = {t: abs(_leg_value(p, (close(t, d) or p["entry_price"]))) for t, p in positions.items()}
            turnover = sum(abs(target_gross.get(t, 0.0) - old_gross.get(t, 0.0)) for t in set(old_gross) | set(target_gross))
            cost = turnover * cost_rate

            for t, p in positions.items():  # exits
                if t not in new_positions:
                    px = close(t, d) or p["entry_price"]
                    pnl = (p["qty"] * (px - p["entry_price"]) if p["direction"] == "long"
                           else p["qty"] * (p["entry_price"] - px))
                    trades.append({"date": d, "ticker": t, "side": "cover" if p["direction"] == "short" else "sell",
                                   "quantity": p["qty"], "price": px, "value": abs(p["qty"] * px),
                                   "reason": "criteria no longer met", "pnl": pnl})
            for t, p in new_positions.items():  # new entries
                if t not in positions:
                    trades.append({"date": d, "ticker": t, "side": "short" if p["direction"] == "short" else "buy",
                                   "quantity": p["qty"], "price": p["entry_price"], "value": target_gross[t],
                                   "reason": "criteria met"})

            invested_long = sum(g for t, g in target_gross.items() if new_positions[t]["direction"] == "long")
            cash = equity - cost - invested_long
            positions = new_positions

        eq = mark_equity(d)
        point = {"date": d, "cash": cash, "equity": eq}
        if bench_first:
            bclose = factors.close_on(bench_bars, d)
            point["benchmark_equity"] = starting_cash * ((bclose or bench_first) / bench_first)
        equity_curve.append(point)

    # Settled holdings going into the next session (no end-of-window liquidation here).
    last_day = calendar[-1]
    final_holdings = [{
        "ticker": t, "quantity": p["qty"], "direction": p["direction"],
        "entry_price": p["entry_price"], "last_close": (close(t, last_day) or p["entry_price"]),
    } for t, p in positions.items()]
    residual_cash = cash

    final_equity = equity_curve[-1]["equity"] if equity_curve else starting_cash
    holdings = [{"ticker": t, "weight": round(abs(_leg_value(p, (close(t, last_day) or p["entry_price"]))) / final_equity, 4)}
                for t, p in positions.items() if final_equity] or [{"ticker": "Cash", "weight": 1.0}]

    if not trades:
        warnings.append("No candidate met the model's criteria in this window — the model stayed in cash.")

    return {
        "strategy": strategy,
        "served_by": "yahoo",
        "trades": trades,
        "equity_curve": equity_curve,
        "metrics": summarize(equity_curve, trades, starting_cash),
        "warnings": warnings,
        "holdings": holdings,
        "final_holdings": final_holdings,
        "residual_cash": residual_cash,
        "date_range": {"start": start_date, "end": end_date},
    }
