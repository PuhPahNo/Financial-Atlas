"""Backtest performance metrics."""
from __future__ import annotations

import math
from datetime import date


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


def summarize(points: list[dict], trades: list[dict], starting_cash: float) -> dict:
    if not points:
        return {"total_return": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "trades": 0}
    start = points[0]["date"]
    end = points[-1]["date"]
    ending = float(points[-1]["equity"])
    sells = [trade for trade in trades if trade["side"] in {"sell", "cover"}]
    winning = [trade for trade in sells if trade.get("pnl", 0) > 0]
    return {
        "total_return": (ending - starting_cash) / starting_cash,
        "cagr": cagr(start, end, starting_cash, ending),
        "max_drawdown": max_drawdown(points),
        "win_rate": len(winning) / len(sells) if sells else None,
        "trades": len(trades),
        "ending_equity": ending,
    }
