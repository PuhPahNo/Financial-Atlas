"""Backtest performance metrics.

``summarize`` keeps its original keys (total_return, cagr, max_drawdown, win_rate,
trades, ending_equity) and adds the mainstream risk panel: annualized volatility,
Sharpe, Sortino, Calmar, plus benchmark-relative alpha/beta when the equity curve
carries ``benchmark_equity`` points. All ratios are computed from daily returns and
annualized with √252; the risk-free rate is treated as zero (consistent, and honest
for a free-data simulator).
"""
from __future__ import annotations

import math
from datetime import date

_TRADING_DAYS = 252


def max_drawdown(points: list[dict]) -> float:
    peak = None
    worst = 0.0
    for point in points:
        equity = float(point["equity"])
        peak = equity if peak is None else max(peak, equity)
        if peak:
            worst = min(worst, (equity - peak) / peak)
    return worst


def cagr(start: date, end: date, start_value: float, end_value: float) -> float:
    days = max((end - start).days, 1)
    years = days / 365.25
    if start_value <= 0 or end_value <= 0:
        return 0.0
    return math.pow(end_value / start_value, 1 / years) - 1


def _daily_returns(points: list[dict], key: str = "equity") -> list[float]:
    rets: list[float] = []
    prev: float | None = None
    for p in points:
        value = p.get(key)
        if value is None:
            prev = None
            continue
        value = float(value)
        if prev and prev > 0:
            rets.append(value / prev - 1)
        prev = value
    return rets


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var ** 0.5


def sharpe(rets: list[float]) -> float | None:
    sd = _stdev(rets)
    if not sd:
        return None
    return (_mean(rets) / sd) * math.sqrt(_TRADING_DAYS)


def sortino(rets: list[float]) -> float | None:
    """Mean daily return over downside deviation (vs 0), annualized."""
    if len(rets) < 2:
        return None
    downside = [min(r, 0.0) for r in rets]
    dd = math.sqrt(sum(r * r for r in downside) / len(rets))
    if dd == 0:
        return None
    return (_mean(rets) / dd) * math.sqrt(_TRADING_DAYS)


def beta_alpha(rets: list[float], bench_rets: list[float]) -> tuple[float | None, float | None]:
    """(beta, annualized alpha) of strategy daily returns vs benchmark daily returns."""
    n = min(len(rets), len(bench_rets))
    if n < 2:
        return None, None
    r, b = rets[-n:], bench_rets[-n:]
    mr, mb = _mean(r), _mean(b)
    var_b = sum((x - mb) ** 2 for x in b) / (n - 1)
    if var_b == 0:
        return None, None
    cov = sum((r[i] - mr) * (b[i] - mb) for i in range(n)) / (n - 1)
    beta = cov / var_b
    alpha_daily = mr - beta * mb
    return beta, alpha_daily * _TRADING_DAYS


def summarize(points: list[dict], trades: list[dict], starting_cash: float) -> dict:
    if not points:
        return {"total_return": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "trades": 0}
    start = points[0]["date"]
    end = points[-1]["date"]
    ending = float(points[-1]["equity"])
    sells = [trade for trade in trades if trade["side"] in {"sell", "cover"}]
    winning = [trade for trade in sells if trade.get("pnl", 0) > 0]

    rets = _daily_returns(points)
    bench_rets = _daily_returns(points, key="benchmark_equity")
    vol = _stdev(rets)
    growth = cagr(start, end, starting_cash, ending)
    dd = max_drawdown(points)

    bench_values = [p.get("benchmark_equity") for p in points if p.get("benchmark_equity") is not None]
    benchmark_return = (float(bench_values[-1]) / float(bench_values[0]) - 1) if len(bench_values) >= 2 and bench_values[0] else None
    total_return = (ending - starting_cash) / starting_cash
    beta, _ = beta_alpha(rets, bench_rets) if bench_rets else (None, None)

    gross_wins = sum(t.get("pnl", 0) for t in sells if t.get("pnl", 0) > 0)
    gross_losses = -sum(t.get("pnl", 0) for t in sells if t.get("pnl", 0) < 0)

    return {
        "total_return": total_return,
        "cagr": growth,
        "max_drawdown": dd,
        "win_rate": len(winning) / len(sells) if sells else None,
        "trades": len(trades),
        "ending_equity": ending,
        "volatility": vol * math.sqrt(_TRADING_DAYS) if vol is not None else None,
        "sharpe": sharpe(rets),
        "sortino": sortino(rets),
        "calmar": (growth / abs(dd)) if dd < 0 else None,
        "benchmark_return": benchmark_return,
        "alpha": (total_return - benchmark_return) if benchmark_return is not None else None,
        "beta": beta,
        "profit_factor": (gross_wins / gross_losses) if gross_losses > 0 else None,
    }
