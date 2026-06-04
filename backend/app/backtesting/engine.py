"""Deterministic end-of-day backtesting engine.

Two execution paths share one contract:

* **Buy & hold** — the default for catalogue strategies with no explicit rules.
  Buys the first ticker on day one and marks it to market through the window.
* **Rule-based** — when ``parameters.rules`` describes a signal (e.g. "S&P 500
  makes a new all-time high"), an instrument to trade (e.g. ``SQQQ``), and exits
  (take-profit / stop-loss / time stop). The engine walks the bars day by day,
  opens a position when the signal fires while flat, and closes it the moment an
  exit condition is hit.

Yahoo's ``range`` parameter is measured backwards from *today*, so the range is
chosen from ``start_date`` (not the window length) — otherwise a 2008 backtest
would silently fetch only recent bars and find nothing in the date filter.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from ..core.errors import ValidationError
from ..services import prices
from .metrics import summarize
from .screen import run_active_backtest
from .universe import sp500_tickers

SP500_REFERENCE = "^GSPC"


def fixture_bars(ticker: str) -> list[dict]:
    base = [
        ("2020-01-01", 10.0),
        ("2020-01-02", 11.0),
        ("2020-01-03", 12.0),
        ("2020-01-04", 11.5),
        ("2020-01-05", 13.0),
    ]
    return [{"date": day, "close": close, "ticker": ticker} for day, close in base]


def _parse_day(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _fetch_window(ticker: str, start: date, end: date) -> tuple[list[dict], str]:
    """Daily bars over an explicit window. Uses Yahoo ``period1``/``period2`` so
    arbitrary historical windows return true daily granularity (the ``range``
    shortcut silently downsamples long spans to monthly)."""
    payload, served_by = prices.price_window(ticker, start=start, end=end, interval="1d")
    bars = [b for b in payload["bars"] if b.get("close") is not None]
    bars.sort(key=lambda bar: str(bar["date"]))
    return bars, served_by


def _window(bars: list[dict], start: date, end: date) -> list[dict]:
    s, e = start.isoformat(), end.isoformat()
    return [b for b in bars if s <= str(b["date"]) <= e]


# --------------------------------------------------------------------------- #
# Rule parsing                                                                #
# --------------------------------------------------------------------------- #

_SIGNAL_TYPES = {"new_high", "new_low", "pct_drop", "pct_gain", "ma_cross_up", "ma_cross_down"}


def parse_rules(strategy: dict) -> dict | None:
    """Normalise ``parameters.rules`` into an engine-ready spec, or ``None``."""
    params = (strategy or {}).get("parameters", {}) or {}
    rules = params.get("rules")
    if not isinstance(rules, dict):
        return None
    signal = rules.get("signal") or {}
    stype = str(signal.get("type") or rules.get("signal_type") or "").lower().strip()
    if stype in ("", "buy_hold", "always", "none"):
        return None
    if stype not in _SIGNAL_TYPES:
        raise ValidationError(f"Unknown signal type '{stype}'")

    tickers = params.get("tickers") or []
    instrument = str(rules.get("instrument") or (tickers[0] if tickers else "")).upper()
    if not instrument:
        raise ValidationError("Rule-based strategy needs an instrument to trade")

    reference = str(signal.get("reference") or rules.get("reference") or "").upper()
    # Index-style signals default to the S&P 500; price signals default to self.
    if not reference:
        reference = SP500_REFERENCE if stype in ("new_high", "new_low") else instrument

    def _pct(value, fallback):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return fallback
        return v / 100 if v > 1 else v

    return {
        "instrument": instrument,
        "reference": reference,
        "direction": "short" if str(rules.get("direction", "long")).lower() == "short" else "long",
        "signal_type": stype,
        "lookback_days": int(signal.get("lookback_days") or 0) or None,
        "window_days": int(signal.get("window_days") or signal.get("days") or 21),
        "pct": _pct(signal.get("pct"), 0.05),
        "fast_days": int(signal.get("fast_days") or 20),
        "slow_days": int(signal.get("slow_days") or 50),
        "take_profit_pct": _pct(rules.get("take_profit_pct", rules.get("take_profit")), 0.10),
        "stop_loss_pct": _pct(rules.get("stop_loss_pct", rules.get("stop_loss")), 0.05),
        "max_hold_days": int(rules.get("max_hold_days") or 0) or None,
    }


def _signal_dates(ref_bars: list[dict], spec: dict, upto: date) -> set[str]:
    """Return the set of dates on which the entry signal fires."""
    bars = [b for b in ref_bars if str(b["date"]) <= upto.isoformat()]
    closes = [float(b["close"]) for b in bars]
    dates = [str(b["date"]) for b in bars]
    stype = spec["signal_type"]
    fired: set[str] = set()

    if stype in ("new_high", "new_low"):
        look = spec["lookback_days"]
        for i in range(1, len(closes)):
            window = closes[max(0, i - look):i] if look else closes[:i]
            if not window:
                continue
            if stype == "new_high" and closes[i] >= max(window) * (1 - 1e-9):
                fired.add(dates[i])
            elif stype == "new_low" and closes[i] <= min(window) * (1 + 1e-9):
                fired.add(dates[i])
    elif stype in ("pct_drop", "pct_gain"):
        w = max(1, spec["window_days"])
        for i in range(w, len(closes)):
            change = closes[i] / closes[i - w] - 1
            if stype == "pct_drop" and change <= -spec["pct"]:
                fired.add(dates[i])
            elif stype == "pct_gain" and change >= spec["pct"]:
                fired.add(dates[i])
    elif stype in ("ma_cross_up", "ma_cross_down"):
        fast, slow = max(1, spec["fast_days"]), max(2, spec["slow_days"])

        def sma(idx: int, n: int) -> float | None:
            if idx + 1 < n:
                return None
            return sum(closes[idx - n + 1:idx + 1]) / n

        for i in range(1, len(closes)):
            f0, s0, f1, s1 = sma(i - 1, fast), sma(i - 1, slow), sma(i, fast), sma(i, slow)
            if None in (f0, s0, f1, s1):
                continue
            if stype == "ma_cross_up" and f0 <= s0 and f1 > s1:
                fired.add(dates[i])
            elif stype == "ma_cross_down" and f0 >= s0 and f1 < s1:
                fired.add(dates[i])
    return fired


# --------------------------------------------------------------------------- #
# Benchmark                                                                   #
# --------------------------------------------------------------------------- #

def _benchmark_lookup(benchmark: str, start: date, end: date, warnings: list[str]):
    """Return a callable ``date -> normalised price`` for the benchmark, or None."""
    if not benchmark:
        return None
    try:
        bars, _ = _fetch_window(benchmark, start, end)
        if len(bars) < 2:
            raise ValueError("insufficient benchmark history")
    except Exception:
        warnings.append(f"Benchmark {benchmark.upper()} history was unavailable for this window.")
        return None
    by_date = {str(b["date"]): float(b["close"]) for b in bars}
    ordered = sorted(by_date.items())
    first_close = ordered[0][1]

    def lookup(day: date) -> float:
        key = day.isoformat()
        if key in by_date:
            return by_date[key] / first_close
        prior = [c for d, c in ordered if d <= key]
        return (prior[-1] if prior else first_close) / first_close

    return lookup


# --------------------------------------------------------------------------- #
# Execution paths                                                             #
# --------------------------------------------------------------------------- #

def _buy_hold(*, ticker, bars, starting_cash, cost_rate, benchmark_fn, end_date):
    first = bars[0]
    buy_price = float(first["close"]) * (1 + cost_rate)
    quantity = int((starting_cash * 0.95) / buy_price)
    cash = starting_cash - quantity * buy_price
    trades = [{
        "date": _parse_day(first["date"]), "ticker": ticker, "side": "buy",
        "quantity": quantity, "price": buy_price, "value": quantity * buy_price,
        "reason": "initial signal",
    }]
    equity_curve: list[dict] = []
    for bar in bars:
        day = _parse_day(bar["date"])
        close = float(bar["close"])
        equity_curve.append({
            "date": day, "cash": cash, "equity": cash + quantity * close,
            "benchmark_equity": starting_cash * (benchmark_fn(day) if benchmark_fn else close / float(first["close"])),
        })
    last = bars[-1]
    last_close = float(last["close"])
    # Settled position going into the next session — captured *before* the synthetic
    # end-of-window sale below, so the live overlay can mark these shares to a fresh quote.
    final_holdings = (
        [{"ticker": ticker, "quantity": quantity, "direction": "long",
          "entry_price": buy_price, "last_close": last_close}]
        if quantity > 0 else []
    )
    residual_cash = cash  # cash held alongside the position, pre-liquidation
    sell_price = last_close * (1 - cost_rate)
    proceeds = quantity * sell_price
    cash += proceeds
    trades.append({
        "date": _parse_day(last["date"]), "ticker": ticker, "side": "sell",
        "quantity": quantity, "price": sell_price, "value": proceeds,
        "reason": "end of backtest", "pnl": proceeds - trades[0]["value"],
    })
    equity_curve[-1]["cash"] = cash
    equity_curve[-1]["equity"] = cash
    holdings = [{"ticker": ticker, "weight": 1.0}]
    return trades, equity_curve, holdings, final_holdings, residual_cash


def _run_rules(*, spec, bars, ref_bars, starting_cash, cost_rate, benchmark_fn, start_date, end_date, warnings):
    instrument = spec["instrument"]
    direction = spec["direction"]
    tp, sl = spec["take_profit_pct"], spec["stop_loss_pct"]
    max_hold = spec["max_hold_days"]
    fire = _signal_dates(ref_bars, spec, end_date)

    cash = float(starting_cash)
    pos: dict | None = None
    trades: list[dict] = []
    equity_curve: list[dict] = []
    days_in_market = 0
    first_close = float(bars[0]["close"])

    def gain_pct(entry: float, close: float) -> float:
        return (close / entry - 1) if direction == "long" else (entry / close - 1)

    def close_position(day, close, reason):
        nonlocal cash, pos
        qty = pos["qty"]
        exit_price = close * (1 - cost_rate) if direction == "long" else close * (1 + cost_rate)
        if direction == "long":
            proceeds = qty * exit_price
            cash += proceeds
            pnl = proceeds - pos["cost_basis"]
            side = "sell"
        else:
            pnl = qty * (pos["entry_price"] - exit_price)
            cash += pnl
            proceeds = qty * exit_price
            side = "cover"
        trades.append({
            "date": day, "ticker": instrument, "side": side, "quantity": qty,
            "price": exit_price, "value": proceeds, "reason": reason, "pnl": pnl,
        })
        pos = None

    for bar in bars:
        day = _parse_day(bar["date"])
        close = float(bar["close"])
        closed_this_bar = False

        if pos is not None:
            g = gain_pct(pos["entry_price"], close)
            held_days = (day - pos["entry_date"]).days
            if g >= tp:
                close_position(day, close, f"take-profit +{tp * 100:.1f}%")
                closed_this_bar = True
            elif g <= -sl:
                close_position(day, close, f"stop-loss -{sl * 100:.1f}%")
                closed_this_bar = True
            elif max_hold and held_days >= max_hold:
                close_position(day, close, f"time stop ({max_hold}d)")
                closed_this_bar = True

        if pos is None and not closed_this_bar and bar["date"] in fire and cash > close:
            entry_price = close * (1 + cost_rate) if direction == "long" else close * (1 - cost_rate)
            budget = cash * 0.95
            qty = int(budget / (entry_price if direction == "long" else close))
            if qty > 0:
                if direction == "long":
                    cost_basis = qty * entry_price
                    cash -= cost_basis
                else:
                    cost_basis = qty * entry_price
                    cash -= qty * close * cost_rate  # short: pay only transaction cost up front
                pos = {"qty": qty, "entry_price": entry_price, "entry_date": day, "cost_basis": cost_basis}
                signal_label = {
                    "new_high": f"{spec['reference']} new high", "new_low": f"{spec['reference']} new low",
                    "pct_drop": f"{spec['reference']} −{spec['pct'] * 100:.0f}% dip",
                    "pct_gain": f"{spec['reference']} +{spec['pct'] * 100:.0f}% surge",
                    "ma_cross_up": f"{spec['reference']} MA cross up", "ma_cross_down": f"{spec['reference']} MA cross down",
                }.get(spec["signal_type"], "signal")
                trades.append({
                    "date": day, "ticker": instrument, "side": "buy" if direction == "long" else "short",
                    "quantity": qty, "price": entry_price, "value": qty * entry_price,
                    "reason": f"{signal_label} → {'buy' if direction == 'long' else 'short'} {instrument}",
                })

        if pos is not None:
            days_in_market += 1
            if direction == "long":
                equity = cash + pos["qty"] * close
            else:
                equity = cash + pos["qty"] * (pos["entry_price"] - close)
        else:
            equity = cash
        equity_curve.append({
            "date": day, "cash": cash, "equity": equity,
            "benchmark_equity": starting_cash * (benchmark_fn(day) if benchmark_fn else close / first_close),
        })

    # Settled position going into the next session — captured *before* the synthetic
    # end-of-window liquidation, so the live overlay can mark it to a fresh quote.
    if pos is not None:
        final_holdings = [{
            "ticker": instrument, "quantity": pos["qty"], "direction": direction,
            "entry_price": pos["entry_price"], "last_close": float(bars[-1]["close"]),
        }]
    else:
        final_holdings = []
    residual_cash = cash  # cash alongside the open position, pre-liquidation

    if pos is not None:
        last = bars[-1]
        close_position(_parse_day(last["date"]), float(last["close"]), "end of backtest")
        equity_curve[-1]["cash"] = cash
        equity_curve[-1]["equity"] = cash

    entries = [t for t in trades if t["side"] in ("buy", "short")]
    if not entries:
        warnings.append("No entry signals fired in this window — the strategy stayed in cash.")
    in_market = round(days_in_market / max(1, len(equity_curve)), 3)
    holdings = [{"ticker": instrument, "weight": in_market}, {"ticker": "Cash", "weight": round(1 - in_market, 3)}]
    return trades, equity_curve, holdings, final_holdings, residual_cash


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #

def run_backtest(
    *,
    strategy: dict,
    tickers: list[str],
    start_date: date,
    end_date: date,
    starting_cash: float,
    transaction_cost_bps: float = 5.0,
    slippage_bps: float = 5.0,
    benchmark: str = "SPY",
    use_fixture_data: bool = False,
) -> dict:
    if end_date <= start_date:
        raise ValidationError("Backtest end_date must be after start_date")

    spec = parse_rules(strategy)
    tickers = tickers or strategy.get("parameters", {}).get("tickers", [])
    instrument = (spec["instrument"] if spec else (tickers[0] if tickers else "")).upper()
    if not instrument:
        raise ValidationError("At least one ticker is required")

    # Real catalogue (non-rule) strategies are actively managed over the whole S&P 500: each
    # day, scan the index and buy names that newly meet the model's criteria (point-in-time),
    # exit on take-profit / stop-loss / max-hold / criteria-break. The model's own tickers are
    # folded in as extra candidates. Fixtures and rule-based models keep their existing paths.
    if spec is None and not use_fixture_data:
        universe = sorted(set(sp500_tickers()) | {t.strip().upper() for t in tickers if t and t.strip()})
        return run_active_backtest(
            strategy=strategy, universe=universe, start_date=start_date, end_date=end_date,
            starting_cash=starting_cash, transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps, benchmark=benchmark,
        )

    warnings: list[str] = []
    cost_rate = (transaction_cost_bps + slippage_bps) / 10000

    if use_fixture_data:
        all_bars = fixture_bars(instrument)
        served_by = "fixture"
        bars = all_bars
        ref_bars = fixture_bars(spec["reference"]) if spec else all_bars
        benchmark_fn = None
        warnings.append("Fixture data used for deterministic contract testing.")
    else:
        try:
            bars, served_by = _fetch_window(instrument, start_date, end_date)
        except Exception:
            bars, served_by = [], "yahoo"
        if not bars:
            raise ValidationError(
                f"{instrument} has no price history for {start_date.isoformat()} → {end_date.isoformat()}. "
                "Pick a later window — newer ETFs (e.g. SQQQ from 2010) don't cover early regimes.",
                ticker=instrument,
            )
        if bars and _parse_day(bars[0]["date"]) > start_date + timedelta(days=10):
            warnings.append(f"{instrument} price history begins {bars[0]['date']}; the earlier part of the window has no fills.")
        if spec:
            # Reference needs warm-up history *before* the window so trailing peaks
            # and moving averages are established on the first trading day.
            warmup_years = 6 if spec["signal_type"] in ("new_high", "new_low") else 2
            ref_start = date(max(1962, start_date.year - warmup_years), 1, 1)
            try:
                ref_bars, _ = _fetch_window(spec["reference"], ref_start, end_date)
            except Exception:
                raise ValidationError(f"Could not load signal reference {spec['reference']}")
            if len(ref_bars) < 2:
                raise ValidationError(f"No price history for signal reference {spec['reference']}")
        else:
            ref_bars = bars
        benchmark_fn = _benchmark_lookup(benchmark, start_date, end_date, warnings)

    if len(bars) < 2:
        raise ValidationError("Backtest needs at least two price bars in the window", ticker=instrument)

    if spec:
        trades, equity_curve, holdings, final_holdings, residual_cash = _run_rules(
            spec=spec, bars=bars, ref_bars=ref_bars, starting_cash=starting_cash,
            cost_rate=cost_rate, benchmark_fn=benchmark_fn, start_date=start_date,
            end_date=end_date, warnings=warnings,
        )
    else:
        trades, equity_curve, holdings, final_holdings, residual_cash = _buy_hold(
            ticker=instrument, bars=bars, starting_cash=starting_cash, cost_rate=cost_rate,
            benchmark_fn=benchmark_fn, end_date=end_date,
        )
        if benchmark and benchmark.upper() != instrument and benchmark_fn is None:
            warnings.append(f"Benchmark {benchmark.upper()} approximated from {instrument} path in this run.")

    return {
        "strategy": strategy,
        "served_by": served_by,
        "trades": trades,
        "equity_curve": equity_curve,
        "metrics": summarize(equity_curve, trades, starting_cash),
        "warnings": warnings,
        "holdings": holdings,
        # Settled position(s) going into the next session (pre-liquidation) — powers the
        # live intraday mark; does not affect equity_curve/metrics/holdings above.
        "final_holdings": final_holdings,
        "residual_cash": residual_cash,
        "date_range": {"start": start_date, "end": end_date},
    }


def next_business_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate
